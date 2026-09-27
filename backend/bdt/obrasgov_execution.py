"""Execução física declarada dos projetos de investimento publicada pelo ObrasGov.

Pode afirmar: o percentual de execução física declarado por projeto de
investimento (``id_projeto_investimento``) e as datas de execução/instrumento
publicadas no endpoint público ``/obras/execucao-fisica``, sempre com a URL da
página, o SHA-256 do arquivo e a data de coleta. Uma coleta só termina em
``complete`` quando a paginação declarada ou uma página vazia é observada; caso
contrário é ``bounded`` e permanece visível como parcial. ``not_national_coverage``
acompanha o manifesto: ``total_items`` é o declarado pela origem, nunca uma
verificação independente.

Nunca pode afirmar: pagamento, valor financeiro executado, liquidação,
vínculo do projeto com município, obra, equipamento ou unidade física,
recenseamento de obras, completude nacional ou ``national_catalog_certified``.
A ausência de uma linha não prova ausência de execução. A importação usa
apenas arquivos e manifestos locais, confere todos os hashes antes de gravar e
nunca inventa valores.
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

from sqlalchemy import JSON, Column, Float, Integer, String, select

from .domain import digest, now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = "obrasgov_execution"
API_URL = "https://api-publica.obrasgov.gestao.gov.br/obras/execucao-fisica"
MAX_PAGE_SIZE = 200
MIN_DELAY_SECONDS = 1.0
NOT_NATIONAL_COVERAGE = (
    "Cada coleta cobre apenas as páginas solicitadas do endpoint público do ObrasGov; "
    "coleta limitada é status bounded, nunca cobertura nacional, e total_items reflete "
    "o declarado pela origem, não uma verificação independente."
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class ObrasgovExecution(Base):
    """Uma linha publicada de execução física por projeto de investimento."""
    __tablename__ = "obrasgov_execution"
    key = Column(String(64), primary_key=True)
    execution_id = Column(Integer, nullable=False, index=True)
    project_id = Column(String(60), nullable=False, index=True)
    percentage = Column(Float, nullable=False)
    starts_on = Column(String(40))
    ends_on = Column(String(40))
    instrument_type = Column(String(200))
    execution_form = Column(String(200))
    created_at_upstream = Column(String(40))
    registered_at = Column(String(40))
    updated_at_upstream = Column(String(40))
    indicatives = Column(JSON)
    reasons = Column(JSON)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def initialize_obrasgov_execution(database: Database) -> None:
    """Cria apenas a tabela aditiva; nunca substitui linhas já importadas."""
    ObrasgovExecution.__table__.create(database.engine, checkfirst=True)


def page_url(page: int, page_size: int) -> str:
    return f"{API_URL}?pagina={page}&tamanho_da_pagina={page_size}"


def _write_json(path: Path, content: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _iso_date(value, field: str) -> str | None:
    """Aceita a data e o carimbo como publicados; guarda o texto exato, sem converter."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"obrasgov_execution_row_malformed_{field}")
    text = value.strip()
    if _DATE.fullmatch(text):
        try:
            date.fromisoformat(text)
        except ValueError:
            raise ValueError(f"obrasgov_execution_row_malformed_{field}") from None
        return text
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"obrasgov_execution_row_malformed_{field}") from None
    if len(text) > 40:
        raise ValueError(f"obrasgov_execution_row_malformed_{field}")
    return text


def _percentage(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("obrasgov_execution_row_malformed_percentage")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 100.0:
        raise ValueError("obrasgov_execution_row_percentage_out_of_range")
    return number


def _optional_text(value, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"obrasgov_execution_row_malformed_{field}")
    return value.strip()


def _item_row(raw, source: dict) -> dict:
    """Valida uma linha publicada; qualquer dúvida vira rejeição contada, nunca valor inventado."""
    if not isinstance(raw, dict):
        raise ValueError("obrasgov_execution_row_not_object")
    execution_id = raw.get("id_execucao_fisica")
    if isinstance(execution_id, bool) or type(execution_id) is not int or execution_id < 1:
        raise ValueError("obrasgov_execution_row_missing_execution_id")
    project_id = raw.get("id_projeto_investimento")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("obrasgov_execution_row_missing_project_id")
    percentage = _percentage(raw.get("percentual_execucao_fisica"))
    starts_on = _iso_date(raw.get("dt_inicial_execucao"), "start_date")
    ends_on = _iso_date(raw.get("dt_final_execucao"), "end_date")
    created_at = _iso_date(raw.get("dt_criacao_instrumento"), "instrument_date")
    registered_at = _iso_date(raw.get("dt_cadastro_execucao"), "registration_date")
    updated_at = _iso_date(raw.get("dt_atualizacao_execucao"), "update_date")
    instrument_type = _optional_text(raw.get("tipo_instrumento"), "instrument_type")
    execution_form = _optional_text(raw.get("tipo_forma_execucao"), "execution_form")
    return {
        "key": digest([DATASET, execution_id]),
        "execution_id": execution_id,
        "project_id": project_id.strip(),
        "percentage": percentage,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "instrument_type": instrument_type,
        "execution_form": execution_form,
        "created_at_upstream": created_at,
        "registered_at": registered_at,
        "updated_at_upstream": updated_at,
        "indicatives": raw.get("indicativos"),
        "reasons": raw.get("motivos"),
        "payload": raw,
        "source": dict(source) | {"reference_date": registered_at},
    }


def collect_obrasgov_execution(folder: Path, *, page_size: int = 200, max_pages: int = 10,
                               delay_seconds: float = 1.0) -> dict:
    """Baixa páginas com o baixador allowlisted e grava ``execucao/page-<i>.json``.

    Sem autenticação e sem limite de taxa documentado: o intervalo entre páginas
    é obrigatório e nunca inferior a 1 segundo. Reutilizar a pasta para outro
    plano é recusado antes de qualquer rede. ``complete`` exige condição
    terminal observada (paginação declarada alcançada ou página vazia).
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
        existing = decode(checkpoint.read_bytes())
        if not isinstance(existing, dict) or existing.get("dataset") != DATASET or existing.get("plan") != plan:
            raise ValueError("collection.json belongs to another plan; use a different folder")
    pages_dir = folder / "execucao"
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
        metadata = safe_download(url, path)
        payload = decode(path.read_bytes())
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("obrasgov_execution_page_schema_changed")
        page_number = payload.get("page_number")
        declared_pages = payload.get("total_pages")
        declared_items = payload.get("total_items")
        declared_size = payload.get("page_size")
        rows = payload["data"]
        if (type(page_number) is not int or page_number != page
                or type(declared_pages) is not int or declared_pages < 0
                or type(declared_items) is not int or declared_items < 0
                or type(declared_size) is not int or declared_size != page_size
                or len(rows) > page_size):
            raise ValueError("obrasgov_execution_page_totals_invalid")
        if total_pages is not None and (declared_pages != total_pages or declared_items != total_items):
            raise ValueError("obrasgov_execution_page_totals_changed")
        total_pages, total_items = declared_pages, declared_items
        entries.append({"index": page, "url": metadata["url"], "sha256": metadata["sha256"],
                        "bytes": metadata["bytes"]})
        if page_number >= declared_pages:
            terminal = "declared_total_pages"
            break
        if not rows:
            terminal = "empty_page"
            break
        page += 1
    else:
        terminal = "max_pages_bound"
    status = "complete" if terminal in {"declared_total_pages", "empty_page"} else "bounded"
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
    if status == "complete" and terminal not in {"declared_total_pages", "empty_page"}:
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
    pages_dir = folder / "execucao"
    declared_pages = declared_items = None
    verified: list[tuple[dict, dict]] = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError("obrasgov_execution_page_manifest_invalid")
        index = entry.get("index")
        url, sha, size = entry.get("url"), entry.get("sha256"), entry.get("bytes")
        if type(index) is not int or index != position + 1:
            raise ValueError("obrasgov_execution_page_manifest_invalid")
        if not isinstance(url, str) or not url.startswith(API_URL + "?"):
            raise ValueError("obrasgov_execution_page_url_invalid")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise ValueError("obrasgov_execution_page_sha256_invalid")
        if type(size) is not int or size < 1:
            raise ValueError("obrasgov_execution_page_bytes_invalid")
        path = pages_dir / f"page-{index}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("obrasgov_execution_page_missing_or_not_regular")
        raw = path.read_bytes()
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("obrasgov_execution_page_integrity_failure")
        payload = decode(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("obrasgov_execution_page_schema_changed")
        page_number = payload.get("page_number")
        total_pages = payload.get("total_pages")
        total_items = payload.get("total_items")
        page_size = payload.get("page_size")
        if (type(page_number) is not int or page_number != index
                or type(total_pages) is not int or total_pages < 0
                or type(total_items) is not int or total_items < 0
                or type(page_size) is not int or page_size != expected_page_size
                or len(payload["data"]) > page_size):
            raise ValueError("obrasgov_execution_page_totals_invalid")
        if declared_pages is None:
            declared_pages, declared_items = total_pages, total_items
        elif declared_pages != total_pages or declared_items != total_items:
            raise ValueError("obrasgov_execution_page_totals_changed")
        if (status == "complete" and position == len(entries) - 1
                and not (page_number >= total_pages or not payload["data"])):
            raise ValueError("obrasgov_execution_complete_without_terminal_evidence")
        verified.append((entry, payload))
    return verified


def _flush_batch(session, batch: list[dict], counts: Counter) -> None:
    """Uma transação por lote: o lote inteiro grava ou volta atrás junto."""
    keys = [item["key"] for item in batch]
    existing = {}
    for key, payload in session.execute(
            select(ObrasgovExecution.key, ObrasgovExecution.payload).where(ObrasgovExecution.key.in_(keys))):
        existing[key] = payload
    pending: dict[str, dict] = {}
    for item in batch:
        key = item["key"]
        recorded = pending[key] if key in pending else existing.get(key)
        if recorded is not None and recorded == item["payload"]:
            counts["unchanged"] += 1
            continue
        if recorded is not None:
            raise ValueError("obrasgov_execution_row_conflict_requires_reconciliation")
        session.add(ObrasgovExecution(
            key=key, execution_id=item["execution_id"], project_id=item["project_id"],
            percentage=item["percentage"], starts_on=item["starts_on"], ends_on=item["ends_on"],
            instrument_type=item["instrument_type"], execution_form=item["execution_form"],
            created_at_upstream=item["created_at_upstream"], registered_at=item["registered_at"],
            updated_at_upstream=item["updated_at_upstream"], indicatives=item["indicatives"],
            reasons=item["reasons"], payload=item["payload"], source=item["source"]))
        pending[key] = item["payload"]
        counts["created"] += 1
    batch.clear()
    session.flush()


def import_obrasgov_execution(database: Database, folder: Path, *, batch_size: int = 500) -> dict:
    """Importa páginas e manifesto locais; nunca baixa, nunca inventa e nunca sobrescreve em silêncio."""
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    folder = Path(folder)
    checkpoint = folder / "collection.json"
    raw_manifest = checkpoint.read_bytes()
    plan, status, terminal, entries, finished_at = _reviewed_manifest(
        decode(raw_manifest))
    initialize_obrasgov_execution(database)
    counts: Counter = Counter({"read": 0, "created": 0, "unchanged": 0, "rejected": 0})
    source_json = {
        "dataset": DATASET,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "plan": plan,
        "collection_status": status,
        "terminal": terminal,
        "pages": len(entries),
        "url": API_URL,
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
                raise ValueError("obrasgov_execution_has_no_data_rows")
            if checkpoint.read_bytes() != raw_manifest:
                raise ValueError("obrasgov_execution_manifest_changed_during_import")
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
    collector = commands.add_parser("collect",
                                    help="Baixa páginas públicas e grava execucao/page-<i>.json + collection.json")
    collector.add_argument("--folder", required=True, type=Path)
    collector.add_argument("--page-size", type=int, default=200)
    collector.add_argument("--max-pages", type=int, default=10)
    collector.add_argument("--delay-seconds", type=float, default=1.0)
    importer = commands.add_parser("import", help="Importa páginas locais com hashes verificados")
    importer.add_argument("--database", required=True)
    importer.add_argument("--folder", required=True, type=Path)
    importer.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_obrasgov_execution(args.folder, page_size=args.page_size,
                                            max_pages=args.max_pages, delay_seconds=args.delay_seconds)
    else:
        database = Database(args.database)
        database.initialize()
        try:
            result = import_obrasgov_execution(database, args.folder, batch_size=args.batch_size)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
