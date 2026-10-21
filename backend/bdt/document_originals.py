# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private, content-addressed storage for original evidence documents.

The operator stores a file that was already registered as an evidence document.
The SHA-256 must match the document source hash; this module never publishes,
extracts text or links the document to a place or resource.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from sqlalchemy import BigInteger, Column, ForeignKey, String, select

from .domain import now
from .evidence import Document, audit
from .private_store import store_copy, verified_path
from .storage import Base, Database, User
from .sync import file_hash


MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
PDF_HEADER_SCAN = 1024


class DocumentOriginal(Base):
    __tablename__ = "document_originals"
    document_id = Column(String(64), ForeignKey("evidence_documents.id"), primary_key=True)
    sha256 = Column(String(64), nullable=False, index=True)
    byte_size = Column(BigInteger, nullable=False)
    media_type = Column(String(80), nullable=False, default="application/pdf")
    stored_at = Column(String(40), nullable=False)


def default_folder() -> Path:
    return Path(os.getenv(
        "BDT_DOCUMENT_STORE",
        str(Path(os.getenv("BDT_DATA_DIR", "data")) / "document-originals")))


def _document_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("invalid_document_id")
    return value


def _pdf(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("document_original_not_regular")
    size = path.stat().st_size
    if size < 1 or size > MAX_DOCUMENT_BYTES:
        raise ValueError("document_original_size_invalid")
    with path.open("rb") as stream:
        if b"%PDF-" not in stream.read(PDF_HEADER_SCAN):
            raise ValueError("document_original_not_pdf")


def payload(row: DocumentOriginal) -> dict:
    return {"document_id": row.document_id, "sha256": row.sha256,
            "byte_size": row.byte_size, "media_type": row.media_type,
            "stored_at": row.stored_at, "public": False, "review_required": True}


def store_original(database: Database, document_id: str, path: Path, *,
                   folder: Path | None = None, operator: str) -> dict:
    """Store one operator-provided original; idempotent for identical bytes."""
    document_id = _document_id(document_id)
    path = Path(path)
    _pdf(path)
    sha256 = file_hash(path)
    folder = Path(folder) if folder is not None else default_folder()
    with database.session() as session:
        user = session.scalar(select(User).where(User.username == operator, User.role == "reviewer"))
        if not user:
            raise ValueError("existing_reviewer_operator_required")
        document = session.get(Document, document_id)
        if not document:
            raise ValueError("document_not_found")
        expected = document.source.get("snapshot_sha256") if isinstance(document.source, dict) else None
        if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("document_source_hash_missing")
        if expected != sha256:
            raise ValueError("document_original_hash_mismatch")
        existing = session.get(DocumentOriginal, document_id)
        if existing is not None:
            if existing.sha256 != sha256 or existing.byte_size != path.stat().st_size:
                raise ValueError("document_original_conflict")
            try:
                verified_path(folder, existing.sha256, existing.byte_size)
            except ValueError as error:
                if str(error) != "private_store_content_missing":
                    raise
                store_copy(path, folder, sha256)
            return payload(existing)
        store_copy(path, folder, sha256)
        row = DocumentOriginal(document_id=document_id, sha256=sha256,
                               byte_size=path.stat().st_size,
                               media_type="application/pdf", stored_at=now())
        session.add(row)
        session.flush()
        audit(session, user.id, "document_original", document_id, "stored",
              sha256=sha256, bytes=row.byte_size, media_type=row.media_type,
              public=False)
        return payload(row)


def get_original(database: Database, document_id: str, *,
                 folder: Path | None = None) -> tuple[Path, DocumentOriginal]:
    document_id = _document_id(document_id)
    folder = Path(folder) if folder is not None else default_folder()
    with database.session() as session:
        row = session.get(DocumentOriginal, document_id)
        if not row:
            raise ValueError("document_original_not_stored")
        try:
            path = verified_path(folder, row.sha256, row.byte_size)
        except ValueError as error:
            if str(error) == "private_store_content_missing":
                raise ValueError("document_original_missing") from None
            raise ValueError("document_original_corrupt") from None
        session.expunge(row)
        return path, row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    store = sub.add_parser("store")
    store.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    store.add_argument("--folder", type=Path, default=None)
    store.add_argument("--document-id", required=True)
    store.add_argument("--path", type=Path, required=True)
    store.add_argument("--operator", required=True)
    args = parser.parse_args(argv)
    database = Database(args.database)
    database.initialize()
    try:
        result = store_original(database, args.document_id, args.path,
                                folder=args.folder, operator=args.operator)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
