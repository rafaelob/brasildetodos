"""Quatro catálogos adicionais publicados pela API pública do ObrasGov.

Pode afirmar: as linhas publicadas de ``/obras/projeto-investimento``,
``/obras/geometria``, ``/obras/empenho`` e ``/obras/contrato``, exatamente como
retornadas, com a URL da página, o SHA-256 do arquivo, a data de coleta e a
frescura declarada em ``/obras/data-atualizacao``. O envelope
(``data``/``total_pages``/``total_items``/``page_number``/``page_size``) é
validado em toda página; ``complete`` exige condição terminal observada (a
paginação declarada alcançada ou uma página vazia coerente com os totais
declarados). Página vazia com itens declarados ainda não servidos é erro de
contrato, nunca terminal completo; caso contrário o status é ``bounded`` e
permanece visível como parcial.

Chave natural determinística (documentada porque a origem não publica um id de
linha único em todos os datasets):

- ``projeto-investimento``: ``["projeto-investimento", id_projeto_investimento]``;
- ``geometria``: ``["geometria", id_projeto_investimento, id_geometria]`` — o
  ``id_geometria`` sozinho se repete entre projetos (medido na origem em
  2026-09-27: 580 valores únicos para 600 linhas);
- ``empenho``: ``["empenho", id_projeto_investimento, ug_emitente, nr_empenho]``
  — o endpoint não publica id de linha e o empenho é identificado pelo emitente
  e pelo número dentro do projeto;
- ``contrato``: ``["contrato", id_contrato]``.

O ``key`` é o SHA-256 do JSON canônico dessa lista; ids inteiros permanecem
inteiros, então a chave é reproduzível a partir da linha publicada. A tabela
guarda ``project_id`` (nullable) e ``ibge_code`` como texto (só ``geometria``
publica ``cod_ibge``); nenhum vínculo municipal, de lugar ou de unidade física é
criado.

Nunca pode afirmar: soma de fases financeiras (``aliquidar``, ``liquidado``,
``pago``, RP), valor agregado, localização da obra, vínculo do projeto com
município, completude nacional ou ``national_catalog_certified``. CNPJ mascarado
do fornecedor e ``pins`` sem CRS ficam como publicados. A importação usa apenas
arquivos e manifestos locais, confere tamanho e SHA-256 de cada página (e da
frescura) antes de gravar, grava tudo em uma única transação e nunca inventa
valores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import JSON, Column, String, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

COLLECTOR = "obrasgov_catalog"
BASE_URL = "https://api-publica.obrasgov.gestao.gov.br/obras"
FRESHNESS_URL = f"{BASE_URL}/data-atualizacao"
MAX_PAGE_SIZE = 200
MIN_DELAY_SECONDS = 1.0
MAX_PROJECT_ID = 60
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre apenas as páginas solicitadas de um endpoint público do ObrasGov; "
    "status complete/bounded nunca prova cobertura nacional, e total_pages/total_items "
    "refletem o declarado pela origem, não uma verificação independente."
)
DATASETS = {
    "projeto-investimento": {"endpoint": "/projeto-investimento"},
    "geometria": {"endpoint": "/geometria"},
    "empenho": {"endpoint": "/empenho"},
    "contrato": {"endpoint": "/contrato"},
}
COMPLETE_TERMINALS = ("declared_total_pages", "empty_page")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


class ObrasgovCatalog(Base):
    """Uma linha publicada de um dos quatro catálogos; nenhum vínculo territorial é criado."""
    __tablename__ = "obrasgov_catalog"
    key = Column(String(64), primary_key=True)
    dataset = Column(String(40), nullable=False, index=True)
    project_id = Column(String(60), index=True)
    ibge_code = Column(String(7))
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_obrasgov_catalog(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    ObrasgovCatalog.__table__.create(database.engine, checkfirst=True)


def api_url(dataset: str) -> str:
    return f"{BASE_URL}{DATASETS[dataset]['endpoint']}"


def page_url(dataset: str, page: int, page_size: int) -> str:
    query = urlencode({"pagina": page, "tamanho_da_pagina": page_size})
    return f"{api_url(dataset)}?{query}"


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _download(url: str, path: Path) -> dict:
    """Baixa pela allowlist e traduz erro HTTP em erro de contrato, nunca em página vazia."""
    try:
        return safe_download(url, path)
    except httpx.HTTPStatusError as error:
        raise ValueError(f"obrasgov_catalog_http_error_{error.response.status_code}") from error


def _validated_plan(*, dataset, page_size, max_pages, delay_seconds) -> dict:
    """Valida dataset e plano antes de qualquer rede; nunca normaliza um dataset inventado."""
    if dataset not in DATASETS:
        raise ValueError(f"dataset must be one of {', '.join(sorted(DATASETS))}")
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("page_size must be an integer between 1 and 200")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError("delay_seconds must be at least 1.0 second")
    return {"page_size": page_size, "max_pages": max_pages, "delay_seconds": float(delay_seconds)}


def _reviewed_envelope(payload, page: int, page_size: int) -> tuple[list, int, int]:
    """Valida o envelope publicado; qualquer troca de forma vira erro, nunca leitura parcial."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("obrasgov_catalog_page_schema_changed")
    rows = payload["data"]
    page_number = payload.get("page_number")
    declared_pages = payload.get("total_pages")
    declared_items = payload.get("total_items")
    declared_size = payload.get("page_size")
    if (type(page_number) is not int or page_number != page
            or type(declared_pages) is not int or declared_pages < 0
            or type(declared_items) is not int or declared_items < 0
            or type(declared_size) is not int or declared_size != page_size
            or len(rows) > page_size):
        raise ValueError("obrasgov_catalog_page_totals_invalid")
    return rows, declared_pages, declared_items


def _freshness_receipt(folder: Path) -> dict:
    """Registra a frescura declarada pela origem; o recibo entra conferido na importação."""
    path = folder / "freshness.json"
    metadata = _download(FRESHNESS_URL, path)
    payload = decode(path.read_bytes())
    value = payload.get("data_ultima_atualizacao") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("obrasgov_catalog_freshness_schema_changed")
    return {"url": FRESHNESS_URL, "sha256": metadata["sha256"], "bytes": metadata["bytes"],
            "data_ultima_atualizacao": value.strip()}


def collect_obrasgov_catalog(folder: Path, *, dataset: str, page_size: int = 200,
                             max_pages: int = 20, delay_seconds: float = 1.0) -> dict:
    """Baixa páginas com o baixador allowlisted e grava ``<dataset>/page-<i>.json``.

    Sem autenticação e sem limite de taxa documentado: o intervalo entre páginas
    é obrigatório e nunca inferior a 1 segundo. Reutilizar a pasta para outro
    plano ou dataset é recusado antes de qualquer rede. ``complete`` exige
    condição terminal observada (paginação declarada alcançada ou página vazia
    coerente com os totais declarados); página vazia que contradiz os totais
    declarados é erro de contrato e não grava manifesto.
    """
    plan = _validated_plan(dataset=dataset, page_size=page_size, max_pages=max_pages,
                           delay_seconds=delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("obrasgov_catalog_manifest_unreadable") from error
        if (not isinstance(existing, dict) or existing.get("dataset") != dataset
                or existing.get("plan") != plan):
            raise ValueError("collection.json belongs to another plan; use a different folder")
    pages_dir = folder / dataset
    pages_dir.mkdir(parents=True, exist_ok=True)
    started_at = now()
    freshness = _freshness_receipt(folder)
    entries: list[dict] = []
    total_pages = total_items = None
    read_items = 0
    terminal = None
    page = 1
    while page <= plan["max_pages"]:
        if page > 1:
            time.sleep(plan["delay_seconds"])
        url = page_url(dataset, page, plan["page_size"])
        path = pages_dir / f"page-{page}.json"
        metadata = _download(url, path)
        payload = decode(path.read_bytes())
        rows, declared_pages, declared_items = _reviewed_envelope(payload, page, plan["page_size"])
        if total_pages is not None and (declared_pages != total_pages or declared_items != total_items):
            raise ValueError("obrasgov_catalog_page_totals_changed")
        total_pages, total_items = declared_pages, declared_items
        entries.append({"index": page, "url": metadata["url"], "sha256": metadata["sha256"],
                        "bytes": metadata["bytes"]})
        if not rows:
            if declared_items != 0 and read_items != declared_items:
                raise ValueError("obrasgov_catalog_empty_page_contradicts_totals")
            terminal = "empty_page"
            break
        read_items += len(rows)
        if page >= declared_pages:
            terminal = "declared_total_pages"
            break
        page += 1
    else:
        terminal = "max_pages_bound"
    status = "complete" if terminal in COMPLETE_TERMINALS else "bounded"
    collection = {
        "collector": COLLECTOR,
        "dataset": dataset,
        "url": api_url(dataset),
        "plan": plan,
        "started_at": started_at,
        "finished_at": now(),
        "status": status,
        "terminal": terminal,
        "pages": entries,
        "total_pages": total_pages,
        "total_items": total_items,
        "freshness": freshness,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    _write_json(checkpoint, collection)
    return collection


def _reviewed_manifest(manifest) -> tuple[str, dict, str, str, list, str]:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo de completo."""
    if not isinstance(manifest, dict) or manifest.get("collector") != COLLECTOR:
        raise ValueError("obrasgov_catalog_manifest_collector_mismatch")
    dataset = manifest.get("dataset")
    if dataset not in DATASETS:
        raise ValueError("obrasgov_catalog_manifest_dataset_invalid")
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("obrasgov_catalog_manifest_plan_invalid")
    try:
        reviewed = _validated_plan(dataset=dataset, page_size=plan.get("page_size"),
                                   max_pages=plan.get("max_pages"),
                                   delay_seconds=plan.get("delay_seconds"))
    except ValueError as error:
        raise ValueError("obrasgov_catalog_manifest_plan_invalid") from error
    if reviewed != plan:
        raise ValueError("obrasgov_catalog_manifest_plan_invalid")
    if manifest.get("url") != api_url(dataset):
        raise ValueError("obrasgov_catalog_manifest_url_invalid")
    status = manifest.get("status")
    terminal = manifest.get("terminal")
    if status not in {"complete", "bounded"} or not isinstance(terminal, str) or not terminal:
        raise ValueError("obrasgov_catalog_manifest_status_invalid")
    if status == "complete" and terminal not in COMPLETE_TERMINALS:
        raise ValueError("obrasgov_catalog_complete_without_terminal_evidence")
    entries = manifest.get("pages")
    if not isinstance(entries, list) or not entries or len(entries) > plan["max_pages"]:
        raise ValueError("obrasgov_catalog_manifest_pages_invalid")
    finished_at = manifest.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        raise ValueError("obrasgov_catalog_manifest_finished_at_invalid")
    for field in ("total_pages", "total_items"):
        if type(manifest.get(field)) is not int or manifest[field] < 0:
            raise ValueError("obrasgov_catalog_manifest_totals_invalid")
    if not isinstance(manifest.get("freshness"), dict):
        raise ValueError("obrasgov_catalog_manifest_freshness_invalid")
    return dataset, plan, status, terminal, entries, finished_at


def _verified_freshness(folder: Path, entry: dict) -> dict:
    """Confere o recibo de frescura antes de qualquer gravação."""
    url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
    value = entry.get("data_ultima_atualizacao")
    if (url != FRESHNESS_URL or not isinstance(sha, str) or not _SHA256.fullmatch(sha)
            or type(size) is not int or size < 1
            or not isinstance(value, str) or not value.strip()):
        raise ValueError("obrasgov_catalog_freshness_manifest_invalid")
    path = folder / "freshness.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("obrasgov_catalog_freshness_missing_or_not_regular")
    raw = path.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("obrasgov_catalog_freshness_integrity_failure")
    payload = decode(raw)
    if not isinstance(payload, dict) or payload.get("data_ultima_atualizacao") != value:
        raise ValueError("obrasgov_catalog_freshness_schema_changed")
    return entry


def _verified_pages(folder: Path, dataset: str, entries: list, status: str, plan: dict,
                    totals: tuple[int, int]) -> list[tuple[dict, dict]]:
    """Confere bytes, SHA-256, envelope e totais de cada página antes de publicar qualquer linha."""
    pages_dir = folder / dataset
    declared_pages = declared_items = None
    read_items = 0
    verified: list[tuple[dict, dict]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("obrasgov_catalog_page_manifest_invalid")
        index = entry.get("index")
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        if type(index) is not int or index != position + 1:
            raise ValueError("obrasgov_catalog_page_manifest_invalid")
        if not isinstance(url, str) or url != page_url(dataset, index, plan["page_size"]):
            raise ValueError("obrasgov_catalog_page_url_invalid")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("obrasgov_catalog_page_sha256_invalid")
        if type(size) is not int or size < 1:
            raise ValueError("obrasgov_catalog_page_bytes_invalid")
        path = pages_dir / f"page-{index}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("obrasgov_catalog_page_missing_or_not_regular")
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("obrasgov_catalog_page_integrity_failure")
        payload = decode(raw)
        rows, page_pages, page_items = _reviewed_envelope(payload, index, plan["page_size"])
        if declared_pages is None:
            declared_pages, declared_items = page_pages, page_items
        elif declared_pages != page_pages or declared_items != page_items:
            raise ValueError("obrasgov_catalog_page_totals_changed")
        if not rows and page_items != 0 and read_items != page_items:
            raise ValueError("obrasgov_catalog_empty_page_contradicts_totals")
        if (status == "complete" and position == len(entries) - 1
                and not (index >= page_pages or not rows)):
            raise ValueError("obrasgov_catalog_complete_without_terminal_evidence")
        read_items += len(rows)
        verified.append((entry, payload))
    if (declared_pages, declared_items) != totals:
        raise ValueError("obrasgov_catalog_manifest_totals_mismatch")
    return verified


def _required_text(value, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"obrasgov_catalog_row_missing_{field}")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"obrasgov_catalog_row_malformed_{field}")
    return text


def _optional_project_id(raw: dict) -> str | None:
    value = raw.get("id_projeto_investimento")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise ValueError("obrasgov_catalog_row_malformed_project_id")
    text = value.strip()
    if len(text) > MAX_PROJECT_ID:
        raise ValueError("obrasgov_catalog_row_malformed_project_id")
    return text


def _required_int(value, field: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 1:
        raise ValueError(f"obrasgov_catalog_row_missing_{field}")
    return value


def _ibge_code(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("obrasgov_catalog_row_malformed_ibge_code")
    if type(value) is int:
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError("obrasgov_catalog_row_malformed_ibge_code")
    if not re.fullmatch(r"[0-9]{7}", text):
        raise ValueError("obrasgov_catalog_row_malformed_ibge_code")
    return text


def _published_date(value) -> str | None:
    """Só vira reference_date a data YYYY-MM-DD exata; o texto original segue no payload."""
    if not isinstance(value, str) or not _DATE.fullmatch(value.strip()):
        return None
    text = value.strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _item_row(dataset: str, raw, source: dict) -> dict:
    """Valida a identidade publicada; qualquer dúvida vira rejeição contada, nunca valor inventado."""
    if not isinstance(raw, dict):
        raise ValueError("obrasgov_catalog_row_not_object")
    ibge_code = None
    if dataset == "projeto-investimento":
        project_id = _required_text(raw.get("id_projeto_investimento"), "project_id", MAX_PROJECT_ID)
        natural_id = [project_id]
        reference = _published_date(raw.get("dt_cadastro"))
    elif dataset == "geometria":
        project_id = _required_text(raw.get("id_projeto_investimento"), "project_id", MAX_PROJECT_ID)
        natural_id = [project_id, _required_int(raw.get("id_geometria"), "id_geometria")]
        ibge_code = _ibge_code(raw.get("cod_ibge"))
        reference = None
    elif dataset == "empenho":
        project_id = _required_text(raw.get("id_projeto_investimento"), "project_id", MAX_PROJECT_ID)
        natural_id = [project_id, _required_int(raw.get("ug_emitente"), "ug_emitente"),
                      _required_text(raw.get("nr_empenho"), "nr_empenho", 60)]
        reference = _published_date(raw.get("data_emissao"))
    elif dataset == "contrato":
        natural_id = [_required_int(raw.get("id_contrato"), "id_contrato")]
        project_id = _optional_project_id(raw)
        reference = _published_date(raw.get("data_publicacao_contrato"))
    else:
        raise ValueError("obrasgov_catalog_dataset_unknown")
    return {
        "key": digest([dataset, *natural_id]),
        "dataset": dataset,
        "project_id": project_id,
        "ibge_code": ibge_code,
        "payload": raw,
        "source": dict(source) | ({"reference_date": reference} if reference else {}),
    }


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Uma transação por lote: o lote inteiro grava ou volta atrás junto."""
    keys = [item["key"] for item in batch]
    existing = {}
    for key, payload in session.execute(
            select(ObrasgovCatalog.key, ObrasgovCatalog.payload).where(ObrasgovCatalog.key.in_(keys))):
        existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        key = item["key"]
        recorded = pending[key] if key in pending else existing.get(key)
        if recorded is not None and recorded == item["payload"]:
            counts["unchanged"] += 1
            continue
        if recorded is not None:
            raise ValueError("obrasgov_catalog_row_conflict_requires_reconciliation")
        session.add(ObrasgovCatalog(key=key, dataset=item["dataset"], project_id=item["project_id"],
                                    ibge_code=item["ibge_code"], payload=item["payload"],
                                    source=item["source"]))
        pending[key] = item["payload"]
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_obrasgov_catalog(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa páginas e manifesto locais; nunca baixa, nunca soma e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    decoded = decode(raw_manifest)
    dataset, plan, status, terminal, entries, finished_at = _reviewed_manifest(decoded)
    freshness = _verified_freshness(folder, decoded["freshness"])
    totals = (decoded["total_pages"], decoded["total_items"])
    initialize_obrasgov_catalog(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "collector": COLLECTOR,
        "dataset": dataset,
        "url": api_url(dataset),
        "freshness": freshness,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "plan": plan,
        "collection_status": status,
        "terminal": terminal,
        "pages": len(entries),
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=f"{COLLECTOR}_{dataset}", source=source_json)
        session.add(load)
        session.flush()
        load_id = load.id
    batch: list[dict] = []
    try:
        # Uma única transação para as linhas: qualquer conflito ou troca de manifesto
        # volta com tudo, sem deixar registros parciais commitados.
        with database.session() as session:
            for entry, payload in _verified_pages(folder, dataset, entries, status, plan, totals):
                page_source = {"dataset": dataset, "url": entry["url"], "sha256": entry["sha256"],
                               "collected_at": finished_at}
                for raw in payload["data"]:
                    counts["read"] += 1
                    try:
                        item = _item_row(dataset, raw, page_source)
                    except ValueError:
                        counts["rejected"] += 1
                        continue
                    batch.append(item)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts)
            if batch:
                _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("obrasgov_catalog_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("obrasgov_catalog_manifest_changed_during_import")
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
    return {
        "status": "imported",
        "collector": COLLECTOR,
        "dataset": dataset,
        "ingestion_id": load_id,
        "counts": dict(counts),
        "collection_status": status,
        "collection_terminal": terminal,
        "pages": len(entries),
        "manifest_sha256": source_json["manifest_sha256"],
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa páginas públicas e grava <dataset>/page-<i>.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    collector.add_argument("--page-size", type=int, default=200)
    collector.add_argument("--max-pages", type=int, default=20)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa páginas locais com hashes verificados")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_obrasgov_catalog(args.folder, dataset=args.dataset, page_size=args.page_size,
                                          max_pages=args.max_pages, delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_obrasgov_catalog(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
