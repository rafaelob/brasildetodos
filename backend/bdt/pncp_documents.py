# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private storage for official PNCP contract-document metadata and bytes.

The collector reads the documented PNCP endpoints, downloads each file to a
content-addressed private folder and records the SHA-256. It never publishes a
document, never links it to a place or resource and never treats a document
title as proof of an institutional relationship.

Revisits keep old bytes and revisions. A document that disappears from a
*complete* listing is marked ``not_listed``; it is not deleted and it is not
claimed to be cancelled. A bounded listing changes no visibility state.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import (BigInteger, Column, ForeignKey, Integer, JSON, String,
                        Text, UniqueConstraint, select)

from .domain import now
from .ingest import safe_download
from .json_codec import decode
from .private_store import content_path, store_file
from .storage import Base, Database
from .sync import atomic_json, download_retry, file_hash


API_ROOT = "https://pncp.gov.br/api/pncp/v1/orgaos"
MAX_PAGE_SIZE = 500
MAX_PAGES = 100
MAX_DOCUMENTS = 5_000
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_LIST_BYTES = 8 * 1024 * 1024
MAX_TITLE_CHARS = 1_000
MAX_TYPE_CHARS = 200


class PncpContractDocument(Base):
    __tablename__ = "pncp_contract_documents"
    __table_args__ = (
        UniqueConstraint("cnpj", "ano_contract", "sequencial_contract",
                         "sequencial_document", name="uq_pncp_document_natural"),
    )
    id = Column(String(200), primary_key=True)
    cnpj = Column(String(14), nullable=False, index=True)
    ano_contract = Column(Integer, nullable=False)
    sequencial_contract = Column(Integer, nullable=False)
    sequencial_document = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    document_type = Column(String(MAX_TYPE_CHARS))
    published_at = Column(String(40))
    source_url = Column(Text, nullable=False)
    snapshot_sha256 = Column(String(64), nullable=False, index=True)
    byte_size = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False, default="present", index=True)
    revision = Column(Integer, nullable=False, default=1)
    first_seen_at = Column(String(40), nullable=False)
    last_seen_at = Column(String(40), nullable=False)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)


class PncpDocumentRevision(Base):
    __tablename__ = "pncp_document_revisions"
    __table_args__ = (
        UniqueConstraint("document_id", "revision", name="uq_pncp_document_revision"),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String(200), ForeignKey("pncp_contract_documents.id"),
                         nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    snapshot_sha256 = Column(String(64), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False, default="present")
    collected_at = Column(String(40), nullable=False)
    metadata_json = Column("metadata", JSON, nullable=False, default=dict)


def document_id(cnpj: str, ano: int, sequencial: int, documento: int) -> str:
    return f"pncp-doc:{cnpj}:{ano}:{sequencial}:{documento}"


def list_url(cnpj: str, ano: int, sequencial: int, page: int, page_size: int) -> str:
    query = urlencode({"pagina": page, "tamanhoPagina": page_size})
    return f"{API_ROOT}/{cnpj}/contratos/{ano}/{sequencial}/arquivos?{query}"


def _validate_contract(cnpj: str, ano: int, sequencial: int, page_size: int, max_pages: int):
    if not isinstance(cnpj, str) or not re.fullmatch(r"[0-9]{14}", cnpj):
        raise ValueError("pncp_cnpj_requires_14_digits")
    if type(ano) is not int or not 2000 <= ano <= 2100:
        raise ValueError("pncp_contract_year_out_of_range")
    if type(sequencial) is not int or not 1 <= sequencial <= 999_999_999:
        raise ValueError("pncp_contract_sequence_out_of_range")
    if type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError("pncp_page_size_out_of_range")
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES:
        raise ValueError("pncp_max_pages_out_of_range")


def _safe_official_url(value: str, cnpj: str, ano: int, sequencial: int,
                       documento: int, field: str) -> str:
    if not isinstance(value, str) or len(value) > 2_000:
        raise ValueError(f"invalid_pncp_{field}_url")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname != "pncp.gov.br"
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ValueError(f"untrusted_pncp_{field}_url")
    suffix = f"/orgaos/{cnpj}/contratos/{ano}/{sequencial}/arquivos/{documento}"
    if not parsed.path.endswith(suffix):
        raise ValueError(f"pncp_{field}_url_does_not_match_contract")
    return value


def _timestamp(value: str) -> str:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid_pncp_document_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid_pncp_document_timestamp") from None
    return parsed.isoformat()


def _document(row, cnpj: str, ano: int, sequencial: int) -> dict:
    if not isinstance(row, dict):
        raise ValueError("invalid_pncp_document_row")
    if row.get("cnpj") != cnpj:
        raise ValueError("pncp_document_cnpj_mismatch")
    if type(row.get("anoCompra")) is not int or row["anoCompra"] != ano:
        raise ValueError("pncp_document_year_mismatch")
    if type(row.get("sequencialCompra")) is not int or row["sequencialCompra"] != sequencial:
        raise ValueError("pncp_document_contract_sequence_mismatch")
    documento = row.get("sequencialDocumento")
    if type(documento) is not int or not 1 <= documento <= 999_999_999:
        raise ValueError("invalid_pncp_document_sequence")
    title = row.get("titulo")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= MAX_TITLE_CHARS:
        raise ValueError("invalid_pncp_document_title")
    document_type = row.get("tipoDocumentoNome")
    if document_type is not None and (not isinstance(document_type, str)
                                       or len(document_type) > MAX_TYPE_CHARS):
        raise ValueError("invalid_pncp_document_type")
    source_url = _safe_official_url(row.get("url"), cnpj, ano, sequencial, documento, "download")
    uri = row.get("uri")
    if uri is not None:
        uri = _safe_official_url(uri, cnpj, ano, sequencial, documento, "metadata")
    published_at = _timestamp(row.get("dataPublicacaoPncp"))
    metadata = {
        "uri": uri, "url": source_url, "cnpj": cnpj, "anoCompra": ano,
        "sequencialCompra": sequencial, "dataPublicacaoPncp": published_at,
        "sequencialDocumento": documento, "titulo": title.strip(),
        "tipoDocumentoNome": document_type,
    }
    return {"sequencial_document": documento, "title": title.strip(),
            "document_type": document_type, "published_at": published_at,
            "source_url": source_url, "metadata": metadata}


def _page_rows(payload, *, cnpj: str, ano: int, sequencial: int,
               page: int, page_size: int) -> tuple[list[dict], bool | None]:
    """Return validated rows and an optional terminal signal from declared totals."""
    declared_end = None
    declared_total_zero = False
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        if payload.get("numeroPagina") is not None:
            if type(payload["numeroPagina"]) is not int or payload["numeroPagina"] != page:
                raise ValueError("pncp_document_page_mismatch")
        if payload.get("totalPaginas") is not None:
            total = payload["totalPaginas"]
            if type(total) is not int or not 0 <= total <= MAX_PAGES:
                raise ValueError("invalid_pncp_document_total_pages")
            declared_total_zero = total == 0
            declared_end = True if declared_total_zero else page >= total
        if payload.get("paginasRestantes") is not None:
            remaining = payload["paginasRestantes"]
            if type(remaining) is not int or remaining < 0:
                raise ValueError("invalid_pncp_document_remaining_pages")
            if remaining == 0:
                declared_end = True
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ValueError("invalid_pncp_document_list_payload")
        if declared_total_zero and rows:
            raise ValueError("pncp_document_total_pages_zero_with_rows")
    else:
        raise ValueError("invalid_pncp_document_list_payload")
    if len(rows) > page_size:
        raise ValueError("pncp_document_page_exceeds_requested_size")
    return [_document(row, cnpj, ano, sequencial) for row in rows], declared_end


def _list_download(url: str, target: Path, max_bytes: int) -> dict:
    for attempt in range(3):
        try:
            return safe_download(url, target, max_bytes, allow_no_content=True)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
            retryable = (not isinstance(error, httpx.HTTPStatusError)
                         or error.response.status_code in {429, 500, 502, 503, 504})
            if not retryable or attempt == 2:
                raise
            time.sleep(min(2 ** attempt, 8))
    raise ValueError("retry_budget_must_be_positive")


def _failed_report(path: Path, *, cnpj: str, ano: int, sequencial: int, error: Exception):
    try:
        atomic_json(path, {"schema": "bdt.pncp-contract-documents.v1",
                           "contract": {"cnpj": cnpj, "ano": ano, "sequencial": sequencial},
                           "status": "failed", "error": str(error)[:200],
                           "publication_allowed": False, "review_required": True,
                           "collected_at": now()})
    except OSError:
        pass


def collect_contract_documents(database: Database, folder: Path, *, cnpj: str, ano: int,
                               sequencial: int, page_size: int = 100, max_pages: int = 20,
                               max_bytes: int = MAX_DOCUMENT_BYTES,
                               list_loader=_list_download,
                               document_loader=download_retry) -> dict:
    """Collect one contract's official document metadata and private bytes.

    The database is changed only after every listing page and every document
    download succeeds. A failed run leaves prior rows and bytes untouched.
    """
    _validate_contract(cnpj, ano, sequencial, page_size, max_pages)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_DOCUMENT_BYTES:
        raise ValueError("pncp_document_byte_budget_out_of_range")
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("pncp_private_folder_cannot_be_a_symlink")
    folder.mkdir(parents=True, exist_ok=True)
    staging = folder / "tmp"
    if staging.is_symlink():
        raise ValueError("pncp_staging_folder_cannot_be_a_symlink")
    staging.mkdir(exist_ok=True)
    report_path = folder / "collection.json"
    failed_path = folder / "collection-failed.json"
    try:
        rows: list[dict] = []
        seen: set[int] = set()
        terminal = None
        complete = False
        page = 1
        while page <= max_pages:
            list_path = staging / f"list-{uuid4()}.json"
            list_loader(list_url(cnpj, ano, sequencial, page, page_size), list_path, MAX_LIST_BYTES)
            if not list_path.exists() or list_path.is_symlink():
                raise ValueError("pncp_document_list_missing")
            if list_path.stat().st_size == 0:
                terminal = "http_204_no_content"
                complete = True
                break
            payload = decode(list_path.read_bytes())
            page_rows, declared_end = _page_rows(payload, cnpj=cnpj, ano=ano, sequencial=sequencial,
                                                 page=page, page_size=page_size)
            for row in page_rows:
                identity = row["sequencial_document"]
                if identity in seen:
                    raise ValueError("duplicate_pncp_document_sequence")
                seen.add(identity)
                rows.append(row)
                if len(rows) > MAX_DOCUMENTS:
                    raise ValueError("pncp_document_count_exceeds_budget")
            if not page_rows:
                if declared_end is False:
                    raise ValueError("pncp_document_list_ended_before_declared_end")
                terminal = "empty_page"
                complete = True
                break
            if declared_end is True:
                terminal = "declared_end"
                complete = True
                break
            if len(page_rows) < page_size:
                if declared_end is False:
                    raise ValueError("pncp_document_list_ended_before_declared_end")
                terminal = "short_page"
                complete = True
                break
            if page == max_pages:
                terminal = "max_pages"
                break
            page += 1

        for row in rows:
            target = staging / f"document-{row['sequencial_document']}-{uuid4()}.bin"
            metadata = document_loader(row["source_url"], target, max_bytes)
            if not isinstance(metadata, dict):
                raise ValueError("pncp_document_download_metadata_missing")
            if not target.exists() or target.is_symlink() or not target.is_file():
                raise ValueError("pncp_document_download_missing")
            size = target.stat().st_size
            if size < 1 or size > max_bytes:
                raise ValueError("pncp_document_download_size_invalid")
            sha256 = file_hash(target)
            if metadata.get("sha256") not in (None, sha256):
                raise ValueError("pncp_document_download_hash_mismatch")
            store_file(target, folder, sha256)
            row["sha256"] = sha256
            row["bytes"] = size

        stamp = now()
        new = updated = unchanged = 0
        with database.session() as session:
            existing = {row.sequencial_document: row for row in session.scalars(
                select(PncpContractDocument).where(
                    PncpContractDocument.cnpj == cnpj,
                    PncpContractDocument.ano_contract == ano,
                    PncpContractDocument.sequencial_contract == sequencial))}
            for row in rows:
                current = existing.get(row["sequencial_document"])
                if current is None:
                    current = PncpContractDocument(
                        id=document_id(cnpj, ano, sequencial, row["sequencial_document"]),
                        cnpj=cnpj, ano_contract=ano, sequencial_contract=sequencial,
                        sequencial_document=row["sequencial_document"], title=row["title"],
                        document_type=row["document_type"], published_at=row["published_at"],
                        source_url=row["source_url"], snapshot_sha256=row["sha256"],
                        byte_size=row["bytes"], status="present", revision=1,
                        first_seen_at=stamp, last_seen_at=stamp, metadata_json=row["metadata"])
                    session.add(current)
                    session.flush()
                    session.add(PncpDocumentRevision(
                        document_id=current.id, revision=1, snapshot_sha256=row["sha256"],
                        byte_size=row["bytes"], status="present", collected_at=stamp,
                        metadata_json=row["metadata"]))
                    new += 1
                    continue
                changed = (current.snapshot_sha256 != row["sha256"]
                           or current.metadata_json != row["metadata"])
                if changed:
                    current.revision += 1
                    current.snapshot_sha256 = row["sha256"]
                    current.byte_size = row["bytes"]
                    current.title = row["title"]
                    current.document_type = row["document_type"]
                    current.published_at = row["published_at"]
                    current.source_url = row["source_url"]
                    current.metadata_json = row["metadata"]
                    current.status = "present"
                    current.last_seen_at = stamp
                    session.add(PncpDocumentRevision(
                        document_id=current.id, revision=current.revision,
                        snapshot_sha256=row["sha256"], byte_size=row["bytes"],
                        status="present", collected_at=stamp, metadata_json=row["metadata"]))
                    updated += 1
                else:
                    current.status = "present"
                    current.last_seen_at = stamp
                    unchanged += 1
            not_listed = 0
            if complete:
                for current in existing.values():
                    if current.sequencial_document not in seen and current.status != "not_listed":
                        current.status = "not_listed"
                        not_listed += 1
            session.flush()
            report = {
                "schema": "bdt.pncp-contract-documents.v1",
                "contract": {"cnpj": cnpj, "ano": ano, "sequencial": sequencial},
                "status": "complete" if complete else "bounded",
                "terminal": terminal, "pages": page,
                "documents": len(rows), "new": new, "updated": updated,
                "unchanged": unchanged, "not_listed": not_listed,
                "publication_allowed": False, "review_required": True,
                "official_metadata_only": True, "collected_at": stamp,
                "items": [{"id": document_id(cnpj, ano, sequencial, row["sequencial_document"]),
                           "sequencial_document": row["sequencial_document"],
                           "sha256": row["sha256"], "bytes": row["bytes"],
                           "status": "present"} for row in rows],
            }
        try:
            atomic_json(report_path, report)
        except OSError as error:
            # The database commit already succeeded; report the local write
            # failure instead of pretending the collection itself failed.
            report["report_write_error"] = str(error)[:200]
        return report
    except Exception as error:
        _failed_report(failed_path, cnpj=cnpj, ano=ano, sequencial=sequencial, error=error)
        raise
    finally:
        # Temporary list pages and partial downloads never become evidence.
        for child in staging.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    collect.add_argument("--folder", type=Path, required=True,
                         help="Private operator folder; never a public/static directory.")
    collect.add_argument("--cnpj", required=True)
    collect.add_argument("--ano", type=int, required=True)
    collect.add_argument("--sequencial", type=int, required=True)
    collect.add_argument("--page-size", type=int, default=100)
    collect.add_argument("--max-pages", type=int, default=20)
    collect.add_argument("--max-bytes", type=int, default=MAX_DOCUMENT_BYTES)
    args = parser.parse_args(argv)
    database = Database(args.database)
    database.initialize()
    try:
        report = collect_contract_documents(
            database, args.folder, cnpj=args.cnpj, ano=args.ano,
            sequencial=args.sequencial, page_size=args.page_size,
            max_pages=args.max_pages, max_bytes=args.max_bytes)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
