"""Coletor operacional do SICONFI (Tesouro Nacional) para relatórios declarados.

Pode afirmar: execução orçamentária/fiscal declarada por ente (``cod_ibge``),
exercício, período e anexo, exatamente como publicada pela API pública do
Tesouro Nacional (ODbL), preservando rótulo, conta, coluna e o texto publicado
do valor (``valor``), com URL, SHA-256 de cada página e data de coleta.

Nunca pode afirmar: pagamentos a uma escola ou UBS específica; completude
nacional (uma coleta ``complete`` ou ``bounded`` registra apenas as páginas
retornadas pelas consultas declaradas); redistribuição própria sob a licença
ODbL do publicador. A paginação ORDS usa ``limit``/``offset`` e para quando
``hasMore`` é falso ou ``max_pages`` é atingido (status ``bounded``); links de
paginação nunca são seguidos. O acesso é anônimo e o coletor impõe intervalo
mínimo de 1 segundo entre requisições.

A chave primária é o SHA-256 de dataset + id do ente + exercício + período +
anexo + código da conta + coluna + rótulo; valores nunca são somados,
arredondados ou convertidos para float, e ``national_catalog_certified`` nunca
é True.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from sqlalchemy import JSON, Column, ForeignKey, String, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion, Municipality

DATASET = "siconfi"
BASE_URL = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/"
PAGE_DATASETS = ("entes", "rreo", "dca")
RREO_PARAMETERS = ("an_exercicio", "nr_periodo", "co_tipo_demonstrativo", "id_ente", "no_anexo")
DCA_PARAMETERS = ("an_exercicio", "id_ente", "no_anexo")
LICENSE = "ODbL"
MIN_DELAY_SECONDS = 1.0
PAGE_MAX_BYTES = 256 * 1024 * 1024
NOT_NATIONAL_COVERAGE = (
    "Cada página corresponde apenas à consulta declarada no plano; status "
    "complete/bounded não prova cobertura nacional, de todos os entes, "
    "exercícios, períodos ou anexos."
)
_READ_BLOCK = 1024 * 1024
_PAGE_FILE = "page-{index}.json"
_QUERY_CHUNK = 500
_IDENTIFIER_PATTERN = re.compile(r"[a-f0-9]{64}")


class SiconfiReport(Base):
    """Uma linha de relatório fiscal declarado (RREO/DCA) como publicada."""
    __tablename__ = "siconfi_reports"
    key = Column(String(64), primary_key=True)
    dataset = Column(String(20), nullable=False, index=True)
    entity_code = Column(String(20), nullable=False, index=True)
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), index=True)
    exercise = Column(String(4), nullable=False, index=True)
    period = Column(String(10))
    annex = Column(String(120))
    account_code = Column(String(60))
    account = Column(String(300))
    column_label = Column(String(200))
    value_text = Column(String(200), nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_siconfi(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    SiconfiReport.__table__.create(database.engine, checkfirst=True)


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_query(kind: str, spec) -> dict:
    if not isinstance(spec, dict):
        raise ValueError("siconfi_query_must_be_a_mapping")
    allowed = RREO_PARAMETERS if kind == "rreo" else DCA_PARAMETERS
    if set(spec) - set(allowed):
        raise ValueError("siconfi_query_unknown_parameter")
    params: dict[str, str] = {}
    for name in allowed:
        if name not in spec:
            continue
        value = spec[name]
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("siconfi_query_invalid_value")
        text = str(value).strip()
        if not text:
            raise ValueError("siconfi_query_invalid_value")
        if name == "an_exercicio" and not re.fullmatch(r"[0-9]{4}", text):
            raise ValueError("siconfi_query_invalid_value")
        if name == "nr_periodo" and not re.fullmatch(r"[0-9]{1,2}", text):
            raise ValueError("siconfi_query_invalid_value")
        if name == "id_ente" and not re.fullmatch(r"[0-9]{1,7}", text):
            raise ValueError("siconfi_query_invalid_value")
        params[name] = text
    if "an_exercicio" not in params:
        raise ValueError("siconfi_query_requires_an_exercicio")
    return params


def _collection_plan(entes: bool, rreo, dca, page_size: int, max_pages: int) -> dict:
    queries = []
    if entes:
        queries.append({"dataset": "entes", "params": {}})
    for kind, specs in (("rreo", rreo), ("dca", dca)):
        normalized = [{"dataset": kind, "params": _normalize_query(kind, spec)} for spec in specs]
        normalized.sort(key=lambda query: tuple(sorted(query["params"].items())))
        queries.extend(normalized)
    return {"dataset": DATASET, "base_url": BASE_URL, "page_size": page_size,
            "max_pages": max_pages, "queries": queries}


def collect_siconfi(folder: Path, *, entes: bool = False, rreo=(), dca=(), page_size: int = 5000,
                    max_pages: int = 20, delay_seconds: float = 1.0) -> dict:
    """Baixa páginas RREO/DCA/entes com o baixador allowlisted e grava collection.json.

    Reutilizar a pasta com outro plano é recusado antes de qualquer rede.
    ``status`` é ``complete`` apenas quando toda consulta alcançou
    ``hasMore=false``; caso contrário ``bounded``. O plano e os recibos de
    página (índice, URL, SHA-256, bytes) ficam no manifesto.
    """
    if type(entes) is not bool:
        raise ValueError("entes must be a boolean")
    if type(page_size) is not int or page_size < 1:
        raise ValueError("page_size must be a positive integer")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)):
        raise ValueError("delay_seconds must be a number")
    delay = max(MIN_DELAY_SECONDS, float(delay_seconds))
    plan = _collection_plan(entes, list(rreo), list(dca), page_size, max_pages)
    if not plan["queries"]:
        raise ValueError("siconfi_plan_has_no_queries")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except json.JSONDecodeError as error:
            raise ValueError("siconfi_collection_manifest_unreadable") from error
        if not isinstance(existing, dict) or existing.get("plan") != plan:
            raise ValueError("siconfi_collection_plan_mismatch; use a different folder")
    started = now()
    pages: list[dict] = []
    counters: Counter = Counter()
    incomplete: list[dict] = []
    requests = 0
    for query in plan["queries"]:
        dataset, params = query["dataset"], query["params"]
        offset = 0
        for _ in range(max_pages):
            if requests:
                time.sleep(delay)
            url = BASE_URL + dataset + "?" + urlencode(dict(params) | {"limit": page_size, "offset": offset})
            page_index = counters[dataset]
            target = folder / dataset / _PAGE_FILE.format(index=page_index)
            metadata = safe_download(url, target, PAGE_MAX_BYTES)
            requests += 1
            payload = decode(target.read_bytes())
            if (not isinstance(payload, dict) or not isinstance(payload.get("items"), list)
                    or type(payload.get("hasMore")) is not bool):
                raise ValueError("siconfi_response_schema_changed")
            pages.append({"index": page_index, "dataset": dataset, "url": metadata["url"],
                          "sha256": metadata["sha256"], "bytes": metadata["bytes"],
                          "collected_at": metadata["collected_at"]})
            counters[dataset] += 1
            if not payload["hasMore"]:
                break
            count = payload.get("count")
            step = count if type(count) is int and 0 < count <= page_size else len(payload["items"])
            if step < 1:
                incomplete.append({"dataset": dataset, "params": dict(params)})
                break
            offset += step
        else:
            incomplete.append({"dataset": dataset, "params": dict(params)})
    manifest = {
        "dataset": DATASET,
        "plan": plan,
        "plan_sha256": digest(plan),
        "started": started,
        "finished": now(),
        "status": "complete" if not incomplete else "bounded",
        "pages": pages,
        "queries_incomplete": incomplete,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "license": LICENSE,
    }
    _write_json(checkpoint, manifest)
    return manifest


def _manifest_metadata(manifest) -> tuple[dict, str, list, str]:
    if not isinstance(manifest, dict) or manifest.get("dataset") != DATASET:
        raise ValueError("siconfi_manifest_dataset_mismatch")
    plan = manifest.get("plan")
    if not isinstance(plan, dict) or plan.get("dataset") != DATASET:
        raise ValueError("siconfi_manifest_plan_invalid")
    recorded = manifest.get("plan_sha256")
    if recorded is not None and recorded != digest(plan):
        raise ValueError("siconfi_manifest_plan_mismatch")
    status = manifest.get("status")
    if status not in {"complete", "bounded"}:
        raise ValueError("siconfi_manifest_status_invalid")
    entries = manifest.get("pages")
    if not isinstance(entries, list) or not entries:
        raise ValueError("siconfi_manifest_has_no_pages")
    coverage = manifest.get("not_national_coverage")
    if not isinstance(coverage, str) or not coverage:
        raise ValueError("siconfi_manifest_coverage_note_absent")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("siconfi_manifest_page_invalid")
        key = (entry.get("dataset"), entry.get("index"))
        if key in seen:
            raise ValueError("siconfi_manifest_duplicate_page")
        seen.add(key)
    return plan, status, entries, coverage


def _verified_page(folder: Path, entry: dict, manifest: dict):
    url = entry.get("url")
    if not isinstance(url, str) or not url.startswith(BASE_URL):
        raise ValueError("siconfi_manifest_page_url_invalid")
    dataset = entry.get("dataset")
    if dataset is None:
        dataset = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    if dataset not in PAGE_DATASETS:
        raise ValueError("siconfi_manifest_page_dataset_invalid")
    index = entry.get("index")
    if type(index) is not int or index < 0:
        raise ValueError("siconfi_manifest_page_index_invalid")
    sha256 = entry.get("sha256")
    if not isinstance(sha256, str) or not _IDENTIFIER_PATTERN.fullmatch(sha256):
        raise ValueError("siconfi_manifest_page_sha256_invalid")
    size = entry.get("bytes")
    if type(size) is not int or size < 1:
        raise ValueError("siconfi_manifest_page_bytes_invalid")
    collected_at = entry.get("collected_at") or manifest.get("finished")
    if not isinstance(collected_at, str) or not collected_at:
        raise ValueError("siconfi_manifest_page_collected_at_invalid")
    path = folder / dataset / _PAGE_FILE.format(index=index)
    if path.is_symlink() or not path.is_file():
        raise ValueError("siconfi_page_missing_or_not_regular")
    if path.stat().st_size != size:
        raise ValueError("siconfi_page_size_mismatch")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_READ_BLOCK), b""):
            sha.update(block)
    if sha.hexdigest() != sha256:
        raise ValueError("siconfi_page_hash_mismatch")
    return path, dataset, url, sha256, collected_at


def _identifier(value, field: str, pattern: str, *, required: bool = True):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"siconfi_row_missing_{field}")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"siconfi_row_malformed_{field}")
    text = str(value).strip()
    if not re.fullmatch(pattern, text):
        raise ValueError(f"siconfi_row_malformed_{field}")
    return text


def _text(value, field: str, limit: int, *, required: bool):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"siconfi_row_missing_{field}")
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"siconfi_row_malformed_{field}")
    text = str(value).strip()
    if len(text) > limit:
        raise ValueError(f"siconfi_row_malformed_{field}")
    return text


def _report_row(dataset: str, item, url: str, sha256: str, collected_at: str) -> dict:
    """Valida uma linha publicada; o valor permanece texto exato, nunca float."""
    if not isinstance(item, dict):
        raise ValueError("siconfi_row_not_object")
    required = dataset == "rreo"
    exercise = _identifier(item.get("exercicio"), "exercise", r"[0-9]{4}")
    entity = _identifier(item.get("cod_ibge"), "entity", r"[0-9]{1,7}")
    if len(entity) not in {1, 2, 7}:
        raise ValueError("siconfi_row_malformed_entity")
    period = _identifier(item.get("periodo"), "period", r"[0-9]{1,2}", required=required)
    annex = _text(item.get("anexo"), "annex", 120, required=True)
    account_code = _text(item.get("cod_conta"), "account_code", 60, required=required)
    account = _text(item.get("conta"), "account", 300, required=required)
    column_label = _text(item.get("coluna"), "column_label", 200, required=required)
    label = _text(item.get("rotulo"), "label", 300, required=required)
    raw_value = item.get("valor")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int)):
        raise ValueError("siconfi_row_malformed_value")
    value_text = str(raw_value).strip()
    if not value_text or len(value_text) > 200:
        raise ValueError("siconfi_row_malformed_value")
    return {
        "key": digest([dataset, entity, exercise, period or "", annex or "", account_code or "",
                       column_label or "", label or ""]),
        "dataset": dataset,
        "entity_code": entity,
        "exercise": exercise,
        "period": period,
        "annex": annex,
        "account_code": account_code,
        "account": account,
        "column_label": column_label,
        "value_text": value_text,
        "payload": item,
        "source": {"url": url, "sha256": sha256, "collected_at": collected_at, "reference_date": exercise},
    }


def _chunks(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _flush_batch(session, batch: list[dict], counts: Counter, known_municipalities: set) -> None:
    if not batch:
        return
    existing = {}
    for chunk in _chunks([item["key"] for item in batch], _QUERY_CHUNK):
        for key, payload in session.execute(
                select(SiconfiReport.key, SiconfiReport.payload).where(SiconfiReport.key.in_(chunk))):
            existing[key] = payload
    pending = {}
    for item in batch:
        recorded = pending[item["key"]] if item["key"] in pending else existing.get(item["key"])
        if recorded is not None:
            if recorded == item["payload"]:
                counts["unchanged"] += 1
                continue
            raise ValueError("siconfi_row_conflict_requires_reconciliation")
        entity = item["entity_code"]
        session.add(SiconfiReport(
            key=item["key"], dataset=item["dataset"], entity_code=entity,
            municipality_id=entity if len(entity) == 7 and entity in known_municipalities else None,
            exercise=item["exercise"], period=item["period"], annex=item["annex"],
            account_code=item["account_code"], account=item["account"],
            column_label=item["column_label"], value_text=item["value_text"],
            payload=item["payload"], source=item["source"]))
        pending[item["key"]] = item["payload"]
        counts["created"] += 1
    session.flush()
    batch.clear()


def import_siconfi(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa as páginas locais; nunca baixa, nunca soma e nunca inventa valores.

    Cada página tem tamanho e SHA-256 conferidos contra o manifesto. Linhas
    malformadas são rejeitadas e contabilizadas; a reimportação idêntica não
    duplica. O status da coleta (``complete``/``bounded``) é preservado na
    ingestão e nunca vira certificação nacional.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    manifest = decode(raw_manifest)
    plan, collection_status, entries, coverage_note = _manifest_metadata(manifest)
    initialize_siconfi(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "plan": plan,
        "plan_sha256": manifest.get("plan_sha256"),
        "collection_status": collection_status,
        "not_national_coverage": coverage_note,
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json, counts=dict(counts))
        session.add(load)
        session.flush()
        load_id = load.id
    try:
        with database.session() as session:
            known_municipalities = set(session.scalars(select(Municipality.id)))
            batch: list[dict] = []
            for entry in entries:
                path, dataset, url, sha256, collected_at = _verified_page(folder, entry, manifest)
                payload = decode(path.read_bytes(), parse_float=str)
                if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                    raise ValueError("siconfi_page_schema_changed")
                for item in payload["items"]:
                    if dataset == "entes":
                        continue
                    counts["read"] += 1
                    try:
                        row = _report_row(dataset, item, url, sha256, collected_at)
                    except ValueError:
                        counts["rejected"] += 1
                        continue
                    batch.append(row)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts, known_municipalities)
            _flush_batch(session, batch, counts, known_municipalities)
            if counts["read"] == 0:
                raise ValueError("siconfi_manifest_has_no_report_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("siconfi_manifest_changed_during_import")
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at, load.counts = "success", now(), dict(counts)
    except Exception as error:
        with database.session() as session:
            load = session.get(Ingestion, load_id)
            if load is not None:
                load.status, load.finished_at = "failed", now()
                load.counts = dict(counts) | {"rolled_back": True}
                load.error = str(error)[:160] if isinstance(error, ValueError) else type(error).__name__
        raise
    return {"status": "imported", "dataset": DATASET, "ingestion_id": load_id,
            "collection_status": collection_status, "pages": len(entries), "counts": dict(counts),
            "manifest_sha256": source_json["manifest_sha256"], "national_catalog_certified": False}


def _json_query(value: str) -> dict:
    try:
        parsed = decode(value.encode("utf-8"))
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("consulta deve ser um objeto JSON") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("consulta deve ser um objeto JSON")
    return parsed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa páginas públicas do SICONFI e grava <dataset>/page-N.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--entes", action="store_true")
    collector.add_argument("--rreo", action="append", default=[], type=_json_query, metavar="JSON")
    collector.add_argument("--dca", action="append", default=[], type=_json_query, metavar="JSON")
    collector.add_argument("--page-size", type=int, default=5000)
    collector.add_argument("--max-pages", type=int, default=20)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa as páginas locais para o banco operacional")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_siconfi(args.folder, entes=args.entes, rreo=args.rreo, dca=args.dca,
                                 page_size=args.page_size, max_pages=args.max_pages,
                                 delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_siconfi(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
