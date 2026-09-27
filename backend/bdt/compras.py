"""Contratos administrativos declarados no portal de dados abertos do Compras.gov.br.

Pode afirmar: os contratos retornados pelo endpoint público
``/modulo-contratos/1_consultarContratos`` para o órgão (``codigoOrgao``) e a
janela de vigência inicial declarados, exatamente como publicados, com a URL da
página, o SHA-256 do arquivo e a data de coleta. O envelope
(``resultado``/``totalRegistros``/``totalPaginas``/``paginasRestantes``) é
validado em toda página; o fim só é reconhecido quando ``paginasRestantes`` é
zero ou a página retorna vazio, e um HTTP 404 com JSON de erro é tratado como
erro de contrato, nunca como "página ausente". Valores monetários permanecem no
payload JSON e só viram float quando finitos; nunca são somados.

Nunca pode afirmar: execução, pagamento ou liquidação; vínculo do contrato com
município, unidade federativa, localidade ou unidade física (o DTO não publica
IBGE/UF, então nenhum vínculo territorial é criado); valor somado; completude
nacional ou ``national_catalog_certified``. A coleta é recortada pelo órgão e
pela janela solicitados: ``complete`` significa apenas que a paginação
declarada terminou. Contratos com ``contratoExcluido=True`` são preservados com
a coluna ``excluded`` marcada e o payload original — a exclusão é um ato
declarado pelo publicador e continua sendo evidência; a linha nunca é descartada
em silêncio. A importação usa apenas arquivos e manifestos locais, confere
tamanho e SHA-256 de todas as páginas antes de gravar e nunca inventa valores.

Licença declarada no rodapé do site: CC BY-ND 3.0, registrada no manifesto sem
certificação de redistribuição.
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
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy import JSON, Boolean, Column, Float, String, Text, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "compras"
API_URL = "https://dadosabertos.compras.gov.br/modulo-contratos/1_consultarContratos"
PAGES_DIR = "contratos"
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 500
MAX_WINDOW_DAYS = 365
MIN_DELAY_SECONDS = 1.0
COMPLETE_TERMINALS = ("no_pages_remaining", "empty_page")
LICENSE = "CC BY-ND 3.0"
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre apenas as páginas solicitadas do endpoint público de contratos do "
    "Compras.gov.br para o órgão e a janela de vigência declarados; status complete/bounded "
    "nunca prova cobertura nacional, de todos os órgãos ou de todos os contratos publicados."
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_SUPPLIER = re.compile(r"[0-9]{14}\Z")


class ComprasContract(Base):
    """Uma linha publicada de contrato; nenhum vínculo territorial é criado."""
    __tablename__ = "compras_contracts"
    key = Column(String(64), primary_key=True)
    orgao_code = Column(String(20), nullable=False, index=True)
    unit_code = Column(String(20), nullable=False, index=True)
    contract_number = Column(String(60), nullable=False, index=True)
    supplier_id = Column(String(20), nullable=False, index=True)
    supplier_name = Column(String(300))
    organ_name = Column(String(300))
    unit_name = Column(String(300))
    object_text = Column(Text)
    starts_on = Column(String(40), nullable=False)
    ends_on = Column(String(40))
    published_at = Column(String(40))
    pncp_contract_id = Column(String(80))
    global_value = Column(Float)
    excluded = Column(Boolean, nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_compras(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    ComprasContract.__table__.create(database.engine, checkfirst=True)


def page_url(page: int, orgao: str, window_from: str, window_to: str, page_size: int) -> str:
    query = urlencode({"codigoOrgao": orgao, "dataVigenciaInicialMin": window_from,
                       "dataVigenciaInicialMax": window_to, "pagina": page,
                       "tamanhoPagina": page_size})
    return f"{API_URL}?{query}"


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _window_day(value, field: str) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value.strip()):
        raise ValueError(f"{field} must be a YYYY-MM-DD date")
    text = value.strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field} must be a YYYY-MM-DD date") from None
    return text


def _validated_plan(*, orgao, window_from, window_to, page_size, max_pages, delay_seconds) -> dict:
    """Valida o plano antes de qualquer rede; nunca normaliza código de órgão inventado."""
    if type(page_size) is not int or not MIN_PAGE_SIZE <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("page_size must be an integer between 10 and 500")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError("delay_seconds must be at least 1.0 second")
    if isinstance(orgao, bool) or not isinstance(orgao, (str, int)):
        raise ValueError("orgao must be a non-empty code")
    code = str(orgao).strip()
    if not code or len(code) > 20:
        raise ValueError("orgao must be a non-empty code")
    window_from = _window_day(window_from, "--from")
    window_to = _window_day(window_to, "--to")
    if window_from > window_to:
        raise ValueError("window_from must not be after window_to")
    if (date.fromisoformat(window_to) - date.fromisoformat(window_from)).days > MAX_WINDOW_DAYS:
        raise ValueError("window must be at most 365 days")
    return {"orgao": code, "window_from": window_from, "window_to": window_to,
            "page_size": page_size, "max_pages": max_pages, "delay_seconds": float(delay_seconds)}


def _download(url: str, path: Path) -> dict:
    """Baixa pela allowlist e traduz 400/404 em erro de contrato, nunca em fim de paginação."""
    try:
        return safe_download(url, path)
    except httpx.HTTPStatusError as error:
        status = error.response.status_code
        if status in {400, 404}:
            raise ValueError(f"compras_contract_error_http_{status}") from error
        raise ValueError(f"compras_http_error_{status}") from error


def _reviewed_envelope(payload, page_size: int) -> tuple[list, int, int, int]:
    if (not isinstance(payload, dict) or not isinstance(payload.get("resultado"), list)
            or type(payload.get("totalRegistros")) is not int or payload["totalRegistros"] < 0
            or type(payload.get("totalPaginas")) is not int or payload["totalPaginas"] < 0
            or type(payload.get("paginasRestantes")) is not int or payload["paginasRestantes"] < 0):
        raise ValueError("compras_page_schema_changed")
    rows = payload["resultado"]
    if len(rows) > page_size:
        raise ValueError("compras_page_totals_invalid")
    return rows, payload["totalRegistros"], payload["totalPaginas"], payload["paginasRestantes"]


def collect_compras(folder: Path, *, orgao, window_from, window_to, page_size: int = 500,
                    max_pages: int = 20, delay_seconds: float = 1.0) -> dict:
    """Baixa páginas com o baixador allowlisted e grava ``contratos/page-<i>.json``.

    Sem autenticação: o intervalo entre páginas é obrigatório e nunca inferior a
    1 segundo. Reutilizar a pasta para outro plano é recusado antes de qualquer
    rede. ``complete`` exige condição terminal observada (``paginasRestantes``
    zero ou página vazia); caso contrário o status é ``bounded``.
    """
    plan = _validated_plan(orgao=orgao, window_from=window_from, window_to=window_to,
                           page_size=page_size, max_pages=max_pages, delay_seconds=delay_seconds)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("compras_collection_manifest_unreadable") from error
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET or existing.get("plan") != plan:
            raise ValueError("compras_collection_manifest_plan_mismatch; use a different folder")
    pages_dir = folder / PAGES_DIR
    pages_dir.mkdir(parents=True, exist_ok=True)
    started_at = now()
    entries: list[dict] = []
    total_registros = total_paginas = None
    terminal = None
    page = 1
    while page <= plan["max_pages"]:
        if page > 1:
            time.sleep(plan["delay_seconds"])
        url = page_url(page, plan["orgao"], plan["window_from"], plan["window_to"], plan["page_size"])
        path = pages_dir / f"page-{page}.json"
        metadata = _download(url, path)
        payload = decode(path.read_bytes())
        rows, declared_registros, declared_paginas, remaining = _reviewed_envelope(payload, plan["page_size"])
        if total_registros is not None and (declared_registros != total_registros
                                            or declared_paginas != total_paginas):
            raise ValueError("compras_page_totals_changed")
        total_registros, total_paginas = declared_registros, declared_paginas
        entries.append({"index": page, "url": metadata["url"], "sha256": metadata["sha256"],
                        "bytes": metadata["bytes"]})
        if not rows:
            terminal = "no_pages_remaining" if remaining == 0 else "empty_page"
            break
        if remaining == 0:
            terminal = "no_pages_remaining"
            break
        page += 1
    else:
        terminal = "max_pages_bound"
    status = "complete" if terminal in COMPLETE_TERMINALS else "bounded"
    collection = {
        "dataset": DATASET,
        "url": API_URL,
        "license": LICENSE,
        "plan": plan,
        "started_at": started_at,
        "finished_at": now(),
        "status": status,
        "terminal": terminal,
        "pages": entries,
        "total_registros": total_registros,
        "total_paginas": total_paginas,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    _write_json(checkpoint, collection)
    return collection


def _reviewed_manifest(manifest) -> tuple[dict, str, str, list, str]:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo de completo."""
    if not isinstance(manifest, dict) or manifest.get("dataset") != DATASET:
        raise ValueError("compras_collection_manifest_dataset_mismatch")
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("compras_collection_manifest_plan_invalid")
    try:
        reviewed = _validated_plan(orgao=plan.get("orgao"), window_from=plan.get("window_from"),
                                   window_to=plan.get("window_to"), page_size=plan.get("page_size"),
                                   max_pages=plan.get("max_pages"),
                                   delay_seconds=plan.get("delay_seconds"))
    except ValueError as error:
        raise ValueError("compras_collection_manifest_plan_invalid") from error
    if reviewed != plan:
        raise ValueError("compras_collection_manifest_plan_invalid")
    status = manifest.get("status")
    terminal = manifest.get("terminal")
    if status not in {"complete", "bounded"} or not isinstance(terminal, str) or not terminal:
        raise ValueError("compras_collection_manifest_status_invalid")
    if status == "complete" and terminal not in COMPLETE_TERMINALS:
        raise ValueError("compras_collection_complete_without_terminal_evidence")
    entries = manifest.get("pages")
    if not isinstance(entries, list) or not entries or len(entries) > plan["max_pages"]:
        raise ValueError("compras_collection_manifest_pages_invalid")
    finished_at = manifest.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        raise ValueError("compras_collection_manifest_finished_at_invalid")
    return plan, status, terminal, entries, finished_at


def _verified_pages(folder: Path, entries: list, status: str, plan: dict) -> list[tuple[dict, dict]]:
    """Confere bytes e SHA-256 de cada página antes de publicar qualquer linha."""
    pages_dir = folder / PAGES_DIR
    declared_registros = declared_paginas = None
    verified: list[tuple[dict, dict]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("compras_page_manifest_invalid")
        index = entry.get("index")
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        if type(index) is not int or index != position + 1:
            raise ValueError("compras_page_manifest_invalid")
        expected = page_url(index, plan["orgao"], plan["window_from"], plan["window_to"], plan["page_size"])
        if not isinstance(url, str) or url != expected:
            raise ValueError("compras_page_url_invalid")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("compras_page_sha256_invalid")
        if type(size) is not int or size < 1:
            raise ValueError("compras_page_bytes_invalid")
        path = pages_dir / f"page-{index}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("compras_page_missing_or_not_regular")
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("compras_page_integrity_failure")
        payload = decode(raw)
        rows, registros, paginas, remaining = _reviewed_envelope(payload, plan["page_size"])
        if declared_registros is None:
            declared_registros, declared_paginas = registros, paginas
        elif declared_registros != registros or declared_paginas != paginas:
            raise ValueError("compras_page_totals_changed")
        if (status == "complete" and position == len(entries) - 1
                and not (remaining == 0 or not rows)):
            raise ValueError("compras_collection_complete_without_terminal_evidence")
        verified.append((entry, payload))
    return verified


def _required_text(value, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"compras_row_missing_{field}")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"compras_row_malformed_{field}")
    return text


def _optional_text(value, field: str, limit: int | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"compras_row_malformed_{field}")
    text = value.strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        raise ValueError(f"compras_row_malformed_{field}")
    return text


def _iso_timestamp(value, field: str, *, required: bool) -> str | None:
    """Aceita data ou carimbo sem fuso como publicados; guarda o texto exato, sem converter."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"compras_row_missing_{field}")
        return None
    if not isinstance(value, str):
        raise ValueError(f"compras_row_malformed_{field}")
    text = value.strip()
    if _DATE.fullmatch(text):
        try:
            date.fromisoformat(text)
        except ValueError:
            raise ValueError(f"compras_row_malformed_{field}") from None
        return text
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"compras_row_malformed_{field}") from None
    if len(text) > 40:
        raise ValueError(f"compras_row_malformed_{field}")
    return text


def _finite_number(value, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"compras_row_malformed_{field}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"compras_row_malformed_{field}")
    return number


def _contract_row(raw, source: dict) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca vínculo inventado."""
    if not isinstance(raw, dict):
        raise ValueError("compras_row_not_object")
    contract_number = _required_text(raw.get("numeroContrato"), "contract_number", 60)
    orgao_code = _required_text(raw.get("codigoOrgao"), "orgao_code", 20)
    unit_code = _required_text(raw.get("codigoUnidadeGestora"), "unit_code", 20)
    supplier_id = _required_text(raw.get("niFornecedor"), "supplier_id", 20)
    if not _SUPPLIER.fullmatch(supplier_id):
        raise ValueError("compras_row_malformed_supplier_id")
    excluded = raw.get("contratoExcluido")
    if type(excluded) is not bool:
        raise ValueError("compras_row_malformed_excluded")
    starts_on = _iso_timestamp(raw.get("dataVigenciaInicial"), "start_date", required=True)
    ends_on = _iso_timestamp(raw.get("dataVigenciaFinal"), "end_date", required=False)
    published_at = _iso_timestamp(raw.get("dataHoraInclusao"), "published_at", required=False)
    return {
        "key": digest([DATASET, orgao_code, unit_code, contract_number, supplier_id]),
        "orgao_code": orgao_code,
        "unit_code": unit_code,
        "contract_number": contract_number,
        "supplier_id": supplier_id,
        "supplier_name": _optional_text(raw.get("nomeRazaoSocialFornecedor"), "supplier_name", 300),
        "organ_name": _optional_text(raw.get("nomeOrgao"), "organ_name", 300),
        "unit_name": _optional_text(raw.get("nomeUnidadeGestora"), "unit_name", 300),
        "object_text": _optional_text(raw.get("objeto"), "object"),
        "starts_on": starts_on,
        "ends_on": ends_on,
        "published_at": published_at,
        "pncp_contract_id": _optional_text(raw.get("numeroControlePncpContrato"), "pncp_contract_id", 80),
        "global_value": _finite_number(raw.get("valorGlobal"), "global_value"),
        "excluded": excluded,
        "payload": raw,
        "source": dict(source),
    }


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Uma transação por lote: o lote inteiro grava ou volta atrás junto."""
    keys = [item["key"] for item in batch]
    existing = {}
    for key, payload in session.execute(
            select(ComprasContract.key, ComprasContract.payload).where(ComprasContract.key.in_(keys))):
        existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        key = item["key"]
        recorded = pending[key] if key in pending else existing.get(key)
        if recorded is not None and recorded == item["payload"]:
            counts["unchanged"] += 1
            continue
        if recorded is not None:
            raise ValueError("compras_row_conflict_requires_reconciliation")
        session.add(ComprasContract(
            key=key, orgao_code=item["orgao_code"], unit_code=item["unit_code"],
            contract_number=item["contract_number"], supplier_id=item["supplier_id"],
            supplier_name=item["supplier_name"], organ_name=item["organ_name"],
            unit_name=item["unit_name"], object_text=item["object_text"],
            starts_on=item["starts_on"], ends_on=item["ends_on"], published_at=item["published_at"],
            pncp_contract_id=item["pncp_contract_id"], global_value=item["global_value"],
            excluded=item["excluded"], payload=item["payload"], source=item["source"]))
        pending[key] = item["payload"]
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_compras(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa páginas e manifesto locais; nunca baixa, nunca soma e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    plan, status, terminal, entries, finished_at = _reviewed_manifest(decode(raw_manifest))
    initialize_compras(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "url": API_URL,
        "collected_at": finished_at,
        "orgao": plan["orgao"],
        "window": {"from": plan["window_from"], "to": plan["window_to"]},
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "plan": plan,
        "collection_status": status,
        "terminal": terminal,
        "pages": len(entries),
        "license": LICENSE,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json)
        session.add(load)
        session.flush()
        load_id = load.id
    batch: list[dict] = []
    try:
        # Uma única transação para as linhas: qualquer erro volta com o lote inteiro,
        # sem deixar registros parciais commitados.
        with database.session() as session:
            for entry, payload in _verified_pages(folder, entries, status, plan):
                page_source = {"url": entry["url"], "sha256": entry["sha256"], "collected_at": finished_at}
                for raw in payload["resultado"]:
                    counts["read"] += 1
                    try:
                        item = _contract_row(raw, page_source)
                    except ValueError:
                        counts["rejected"] += 1
                        continue
                    batch.append(item)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts)
            if batch:
                _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("compras_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("compras_manifest_changed_during_import")
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
        "dataset": DATASET,
        "ingestion_id": load_id,
        "counts": dict(counts),
        "collection_status": status,
        "collection_terminal": terminal,
        "pages": len(entries),
        "orgao": plan["orgao"],
        "window": {"from": plan["window_from"], "to": plan["window_to"]},
        "manifest_sha256": source_json["manifest_sha256"],
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa páginas públicas e grava contratos/page-<i>.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--orgao", required=True)
    collector.add_argument("--from", dest="window_from", required=True, metavar="YYYY-MM-DD")
    collector.add_argument("--to", dest="window_to", required=True, metavar="YYYY-MM-DD")
    collector.add_argument("--page-size", type=int, default=500)
    collector.add_argument("--max-pages", type=int, default=20)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa páginas locais com hashes verificados")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_compras(args.folder, orgao=args.orgao, window_from=args.window_from,
                                 window_to=args.window_to, page_size=args.page_size,
                                 max_pages=args.max_pages, delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_compras(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
