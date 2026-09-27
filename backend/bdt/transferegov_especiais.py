"""Empenhos especiais publicados pela API pública de dados abertos do Transferegov.

Pode afirmar: o empenho especial (``id_empenho``) exatamente como publicado no
endpoint público ``/especiais/empenhos-especiais`` — número (que pode ser nulo
enquanto minuta), situação, tipo de documento, unidades gestoras, fonte de
recurso, plano interno, natureza da despesa, data de emissão, prioridade de
desbloqueio, ``id_plano_acao`` e valor —, sempre com a URL da página, o SHA-256
do arquivo e a data de coleta. Uma coleta só termina em ``complete`` quando a
API sinaliza o fim com ``data`` vazio; caso contrário é ``bounded`` e permanece
visível como parcial. ``total_items`` é o declarado pela origem, nunca uma
verificação independente.

Nunca pode afirmar: pagamento, liquidação, transferência, contrato, beneficiário,
vínculo com município, UF, ente ou unidade física (o endpoint não traz código
IBGE de município e ``id_ente`` é interno, não um código IBGE), completude
nacional, ``national_catalog_certified`` ou soma de valores. A ausência de uma
linha não prova ausência de empenho. A importação usa apenas arquivos e
manifestos locais, confere tamanho e SHA-256 de cada página antes de gravar,
rejeita linha malformada com contagem e nunca inventa valores.
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

import httpx
from sqlalchemy import JSON, Column, Float, Integer, String, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "transferegov_especiais"
API_URL = "https://api-publica.transferegov.gestao.gov.br/especiais/empenhos-especiais"
MAX_PAGE_SIZE = 200
MIN_DELAY_SECONDS = 1.0
PAGES_DIRECTORY = "empenhos"
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre apenas as páginas solicitadas do endpoint público de empenhos "
    "especiais do Transferegov; coleta limitada é status bounded, nunca cobertura "
    "nacional, e total_items reflete o declarado pela origem, não uma verificação "
    "independente. O endpoint não traz código IBGE de município: nenhum vínculo "
    "territorial é afirmado."
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class TransferegovEspeciaisEmpenho(Base):
    """Uma linha publicada de empenho especial, como publicada pela origem."""
    __tablename__ = "transferegov_especiais_empenhos"
    key = Column(String(64), primary_key=True)
    empenho_id = Column(Integer, nullable=False, index=True)
    minuta_id = Column(String(120), nullable=False)
    numero_empenho = Column(String(60))
    situacao = Column(Integer, nullable=False)
    descricao_situacao = Column(String(200), nullable=False)
    tipo_documento = Column(Integer, nullable=False)
    descricao_tipo_documento = Column(String(200), nullable=False)
    status_processamento = Column(String(100), nullable=False)
    ug_responsavel = Column(Integer, nullable=False)
    ug_emitente = Column(Integer, nullable=False)
    descricao_ug_emitente = Column(String(300), nullable=False)
    fonte_recurso = Column(String(120), nullable=False)
    plano_interno = Column(String(120), nullable=False)
    ptres = Column(Integer, nullable=False)
    grupo_natureza_despesa = Column(Integer, nullable=False)
    natureza_despesa = Column(Integer, nullable=False)
    subitem = Column(Integer, nullable=False)
    categoria_despesa = Column(String(200), nullable=False)
    modalidade_despesa = Column(Integer, nullable=False)
    numero_ro = Column(String(60))
    data_emissao = Column(String(40), nullable=False)
    prioridade_desbloqueio = Column(Integer, nullable=False)
    valor_empenho = Column(Float, nullable=False)
    id_plano_acao = Column(Integer, nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_transferegov_especiais(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    TransferegovEspeciaisEmpenho.__table__.create(database.engine, checkfirst=True)


def page_url(page: int, page_size: int) -> str:
    return f"{API_URL}?pagina={page}&tamanho_da_pagina={page_size}"


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _decode_page(raw: bytes):
    """Recusa HTML/404 antes de tratar o corpo como envelope; exige JSON estrito."""
    probe = raw.lstrip()
    if probe.startswith(b"\xef\xbb\xbf"):
        probe = probe[3:]
    if not probe.startswith(b"{"):
        raise ValueError("transferegov_especiais_page_not_json")
    try:
        return decode(raw)
    except ValueError as error:
        raise ValueError("transferegov_especiais_page_not_json") from error


def _required_int(value, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or type(value) is not int or value < minimum:
        raise ValueError(f"transferegov_especiais_row_malformed_{field}")
    return value


def _required_text(value, field: str, limit: int) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"transferegov_especiais_row_missing_{field}")
    if not isinstance(value, str):
        raise ValueError(f"transferegov_especiais_row_malformed_{field}")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"transferegov_especiais_row_malformed_{field}")
    return text


def _optional_text(value, field: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"transferegov_especiais_row_malformed_{field}")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"transferegov_especiais_row_malformed_{field}")
    return text


def _emission_date(value) -> str:
    if not isinstance(value, str) or not _DATE.fullmatch(value.strip()):
        raise ValueError("transferegov_especiais_row_malformed_data_emissao")
    text = value.strip()
    try:
        date.fromisoformat(text)
    except ValueError:
        raise ValueError("transferegov_especiais_row_malformed_data_emissao") from None
    return text


def _amount(value) -> float:
    """Valor só vira float quando é número finito; nunca é somado nem inventado."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("transferegov_especiais_row_malformed_valor")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("transferegov_especiais_row_malformed_valor")
    return number


def _item_row(raw, source: dict) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca valor inventado."""
    if not isinstance(raw, dict):
        raise ValueError("transferegov_especiais_row_not_object")
    empenho_id = raw.get("id_empenho")
    if isinstance(empenho_id, bool) or type(empenho_id) is not int or empenho_id < 1:
        raise ValueError("transferegov_especiais_row_missing_empenho_id")
    amount = _amount(raw.get("valor_empenho"))
    data_emissao = _emission_date(raw.get("data_emissao_empenho"))
    return {
        "key": digest([DATASET, empenho_id]),
        "empenho_id": empenho_id,
        "minuta_id": _required_text(raw.get("id_minuta_empenho"), "minuta_id", 120),
        "numero_empenho": _optional_text(raw.get("numero_empenho"), "numero_empenho", 60),
        "situacao": _required_int(raw.get("situacao_empenho"), "situacao"),
        "descricao_situacao": _required_text(
            raw.get("descricao_situacao_empenho"), "descricao_situacao", 200),
        "tipo_documento": _required_int(raw.get("tipo_documento_empenho"), "tipo_documento"),
        "descricao_tipo_documento": _required_text(
            raw.get("descricao_tipo_documento_empenho"), "descricao_tipo_documento", 200),
        "status_processamento": _required_text(
            raw.get("status_processamento_empenho"), "status_processamento", 100),
        "ug_responsavel": _required_int(raw.get("ug_responsavel_empenho"), "ug_responsavel"),
        "ug_emitente": _required_int(raw.get("ug_emitente_empenho"), "ug_emitente"),
        "descricao_ug_emitente": _required_text(
            raw.get("descricao_ug_emitente_empenho"), "descricao_ug_emitente", 300),
        "fonte_recurso": _required_text(raw.get("fonte_recurso_empenho"), "fonte_recurso", 120),
        "plano_interno": _required_text(raw.get("plano_interno_empenho"), "plano_interno", 120),
        "ptres": _required_int(raw.get("ptres_empenho"), "ptres"),
        "grupo_natureza_despesa": _required_int(
            raw.get("grupo_natureza_despesa_empenho"), "grupo_natureza_despesa"),
        "natureza_despesa": _required_int(raw.get("natureza_despesa_empenho"), "natureza_despesa"),
        "subitem": _required_int(raw.get("subitem_empenho"), "subitem"),
        "categoria_despesa": _required_text(
            raw.get("categoria_despesa_empenho"), "categoria_despesa", 200),
        "modalidade_despesa": _required_int(
            raw.get("modalidade_despesa_empenho"), "modalidade_despesa"),
        "numero_ro": _optional_text(raw.get("numero_ro_empenho"), "numero_ro", 60),
        "data_emissao": data_emissao,
        "prioridade_desbloqueio": _required_int(
            raw.get("prioridade_desbloqueio_empenho"), "prioridade_desbloqueio"),
        "valor_empenho": amount,
        "id_plano_acao": _required_int(raw.get("id_plano_acao"), "id_plano_acao"),
        "payload": raw,
        "source": dict(source) | {"reference_date": data_emissao},
    }


def collect_transferegov_especiais(folder: Path, *, page_size: int = 200, max_pages: int = 20,
                                   delay_seconds: float = 1.0) -> dict:
    """Baixa páginas com o baixador allowlisted e grava ``empenhos/page-<i>.json``.

    Sem autenticação e sem limite de taxa documentado: o intervalo entre páginas
    é obrigatório e nunca inferior a 1 segundo. Reutilizar a pasta para outro
    plano é recusado antes de qualquer rede. ``complete`` exige a condição
    terminal observada da API: uma página com ``data`` vazio. Enquanto isso,
    ``bounded`` permanece visível como coleta parcial.
    """
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("page_size must be an integer between 1 and 200")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < MIN_DELAY_SECONDS):
        raise ValueError("delay_seconds must be at least 1.0 second")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / "collection.json"
    plan = {"page_size": page_size, "max_pages": max_pages, "delay_seconds": float(delay_seconds)}
    if checkpoint.exists():
        try:
            existing = decode(checkpoint.read_bytes())
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("transferegov_especiais_collection_manifest_unreadable") from error
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET or existing.get("plan") != plan:
            raise ValueError("collection.json belongs to another plan; use a different folder")
    pages_dir = folder / PAGES_DIRECTORY
    pages_dir.mkdir(parents=True, exist_ok=True)
    started_at = now()
    entries: list[dict] = []
    total_pages = total_items = None
    terminal = None
    page = 1
    while page <= max_pages:
        if page > 1:
            time.sleep(float(delay_seconds))
        url = page_url(page, page_size)
        path = pages_dir / f"page-{page}.json"
        try:
            metadata = safe_download(url, path)
        except httpx.HTTPStatusError as error:
            raise ValueError(f"transferegov_especiais_http_error_{error.response.status_code}") from error
        payload = _decode_page(path.read_bytes())
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("transferegov_especiais_page_schema_changed")
        page_number = payload.get("page_number")
        declared_pages = payload.get("total_pages")
        declared_items = payload.get("total_items")
        declared_size = payload.get("page_size")
        rows = payload["data"]
        if (type(page_number) is not int or page_number != page
                or type(declared_pages) is not int or declared_pages < 0
                or type(declared_items) is not int or declared_items < 0
                or type(declared_size) is not int or declared_size < 0
                or len(rows) > page_size
                or (rows and declared_size != page_size)):
            raise ValueError("transferegov_especiais_page_totals_invalid")
        if total_pages is None:
            total_pages, total_items = declared_pages, declared_items
        elif rows and (declared_pages != total_pages or declared_items != total_items):
            raise ValueError("transferegov_especiais_page_totals_changed")
        entries.append({"index": page, "url": metadata["url"], "sha256": metadata["sha256"],
                        "bytes": metadata["bytes"]})
        if not rows:
            terminal = "empty_page"
            break
        page += 1
    else:
        terminal = "max_pages_bound"
    status = "complete" if terminal == "empty_page" else "bounded"
    collection = {
        "dataset": DATASET,
        "url": API_URL,
        "plan": plan,
        "started_at": started_at,
        "finished_at": now(),
        "status": status,
        "terminal": terminal,
        "pages": entries,
        "total_pages": total_pages,
        "total_items": total_items,
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
    }
    _write_json(checkpoint, collection)
    return collection


def _reviewed_manifest(manifest) -> tuple[dict, str, str, list, str]:
    """Valida o manifesto local antes de qualquer gravação; nunca confia no rótulo de completo."""
    if not isinstance(manifest, dict) or manifest.get("dataset") != DATASET:
        raise ValueError("collection_manifest_dataset_mismatch")
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise ValueError("collection_manifest_plan_invalid")
    page_size, max_pages, delay = plan.get("page_size"), plan.get("max_pages"), plan.get("delay_seconds")
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("collection_manifest_plan_invalid")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("collection_manifest_plan_invalid")
    if (isinstance(delay, bool) or not isinstance(delay, (int, float))
            or not math.isfinite(float(delay)) or float(delay) < MIN_DELAY_SECONDS):
        raise ValueError("collection_manifest_plan_invalid")
    status = manifest.get("status")
    terminal = manifest.get("terminal")
    if status not in {"complete", "bounded"} or not isinstance(terminal, str) or not terminal:
        raise ValueError("collection_manifest_status_invalid")
    if status == "complete" and terminal != "empty_page":
        raise ValueError("collection_manifest_complete_without_terminal_evidence")
    entries = manifest.get("pages")
    if not isinstance(entries, list) or not entries or len(entries) > max_pages:
        raise ValueError("collection_manifest_pages_invalid")
    finished_at = manifest.get("finished_at")
    if not isinstance(finished_at, str) or not finished_at:
        raise ValueError("collection_manifest_finished_at_invalid")
    return plan, status, terminal, entries, finished_at


def _verified_pages(folder: Path, entries: list, status: str,
                    expected_page_size: int) -> list[tuple[dict, dict]]:
    """Confere bytes e SHA-256 de cada página antes de publicar qualquer linha."""
    pages_dir = folder / PAGES_DIRECTORY
    declared_pages = declared_items = None
    verified: list[tuple[dict, dict]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("transferegov_especiais_page_manifest_invalid")
        index = entry.get("index")
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        if type(index) is not int or index != position + 1:
            raise ValueError("transferegov_especiais_page_manifest_invalid")
        if not isinstance(url, str) or url != page_url(index, expected_page_size):
            raise ValueError("transferegov_especiais_page_url_invalid")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("transferegov_especiais_page_sha256_invalid")
        if type(size) is not int or size < 1:
            raise ValueError("transferegov_especiais_page_bytes_invalid")
        path = pages_dir / f"page-{index}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("transferegov_especiais_page_missing_or_not_regular")
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("transferegov_especiais_page_integrity_failure")
        payload = _decode_page(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("transferegov_especiais_page_schema_changed")
        page_number = payload.get("page_number")
        total_pages = payload.get("total_pages")
        total_items = payload.get("total_items")
        page_size = payload.get("page_size")
        rows = payload["data"]
        if (type(page_number) is not int or page_number != index
                or type(total_pages) is not int or total_pages < 0
                or type(total_items) is not int or total_items < 0
                or type(page_size) is not int or page_size < 0
                or len(rows) > expected_page_size
                or (rows and page_size != expected_page_size)):
            raise ValueError("transferegov_especiais_page_totals_invalid")
        if declared_pages is None:
            declared_pages, declared_items = total_pages, total_items
        elif rows and (declared_pages != total_pages or declared_items != total_items):
            raise ValueError("transferegov_especiais_page_totals_changed")
        if not rows and position != len(entries) - 1:
            raise ValueError("transferegov_especiais_page_totals_invalid")
        if (status == "complete" and position == len(entries) - 1 and rows):
            raise ValueError("transferegov_especiais_complete_without_terminal_evidence")
        verified.append((entry, payload))
    return verified


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Uma transação por lote: o lote inteiro grava ou volta atrás junto."""
    keys = [item["key"] for item in batch]
    existing = {}
    for key, payload in session.execute(
            select(TransferegovEspeciaisEmpenho.key, TransferegovEspeciaisEmpenho.payload)
            .where(TransferegovEspeciaisEmpenho.key.in_(keys))):
        existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        key = item["key"]
        recorded = pending[key] if key in pending else existing.get(key)
        if recorded is not None and recorded == item["payload"]:
            counts["unchanged"] += 1
            continue
        if recorded is not None:
            raise ValueError("transferegov_especiais_row_conflict_requires_reconciliation")
        session.add(TransferegovEspeciaisEmpenho(
            key=key, empenho_id=item["empenho_id"], minuta_id=item["minuta_id"],
            numero_empenho=item["numero_empenho"], situacao=item["situacao"],
            descricao_situacao=item["descricao_situacao"], tipo_documento=item["tipo_documento"],
            descricao_tipo_documento=item["descricao_tipo_documento"],
            status_processamento=item["status_processamento"],
            ug_responsavel=item["ug_responsavel"], ug_emitente=item["ug_emitente"],
            descricao_ug_emitente=item["descricao_ug_emitente"],
            fonte_recurso=item["fonte_recurso"], plano_interno=item["plano_interno"],
            ptres=item["ptres"], grupo_natureza_despesa=item["grupo_natureza_despesa"],
            natureza_despesa=item["natureza_despesa"], subitem=item["subitem"],
            categoria_despesa=item["categoria_despesa"],
            modalidade_despesa=item["modalidade_despesa"], numero_ro=item["numero_ro"],
            data_emissao=item["data_emissao"],
            prioridade_desbloqueio=item["prioridade_desbloqueio"],
            valor_empenho=item["valor_empenho"], id_plano_acao=item["id_plano_acao"],
            payload=item["payload"], source=item["source"]))
        pending[key] = item["payload"]
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_transferegov_especiais(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa páginas e manifesto locais; nunca baixa, nunca inventa e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    plan, status, terminal, entries, finished_at = _reviewed_manifest(decode(raw_manifest))
    initialize_transferegov_especiais(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "url": API_URL,
        "collected_at": finished_at,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "plan": plan,
        "collection_status": status,
        "terminal": terminal,
        "pages": len(entries),
        "national_catalog_certified": False,
    }
    with database.session() as session:
        load = Ingestion(dataset=DATASET, source=source_json)
        session.add(load)
        session.flush()
        load_id = load.id
    batch: list[dict] = []
    try:
        # Uma única transação para as linhas: um conflito em qualquer página volta
        # com o lote inteiro, sem deixar registros parciais commitados.
        with database.session() as session:
            for entry, payload in _verified_pages(folder, entries, status, plan["page_size"]):
                page_source = {"url": entry["url"], "sha256": entry["sha256"], "collected_at": finished_at}
                for raw in payload["data"]:
                    counts["read"] += 1
                    try:
                        item = _item_row(raw, page_source)
                    except ValueError:
                        counts["rejected"] += 1
                        continue
                    batch.append(item)
                    if len(batch) >= batch_size:
                        _flush_batch(session, batch, counts)
            if batch:
                _flush_batch(session, batch, counts)
            if counts["read"] == 0:
                raise ValueError("transferegov_especiais_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("transferegov_especiais_manifest_changed_during_import")
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
        "manifest_sha256": source_json["manifest_sha256"],
        "not_national_coverage": NOT_NATIONAL_COVERAGE,
        "national_catalog_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    collector = commands.add_parser(
        "collect", help="Baixa páginas públicas e grava empenhos/page-<i>.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--page-size", type=int, default=200)
    collector.add_argument("--max-pages", type=int, default=20)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa páginas locais com hashes verificados")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_transferegov_especiais(args.folder, page_size=args.page_size,
                                                max_pages=args.max_pages,
                                                delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_transferegov_especiais(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
