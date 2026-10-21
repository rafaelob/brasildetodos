# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operator-only integrity checks and cleanup for private content-addressed files.

``verify`` checks every referenced hash and size. ``prune`` is a dry run by
default; ``--apply`` removes only files older than the retention window that are
not referenced by a current document row or any document revision. Unknown
names and symlinks are never deleted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

from sqlalchemy import select

from .document_originals import DocumentOriginal
from .pncp_documents import PncpContractDocument, PncpDocumentRevision
from .private_store import verified_path
from .storage import Database


HEX = re.compile(r"[a-f0-9]{64}")


def reference_rows(database: Database) -> list[tuple[str, int]]:
    with database.session() as session:
        rows = list(session.execute(select(
            PncpContractDocument.snapshot_sha256, PncpContractDocument.byte_size)))
        rows += list(session.execute(select(
            PncpDocumentRevision.snapshot_sha256, PncpDocumentRevision.byte_size)))
        rows += list(session.execute(select(
            DocumentOriginal.sha256, DocumentOriginal.byte_size)))
        return [(str(sha), int(size)) for sha, size in rows]


def referenced_hashes(database: Database) -> set[str]:
    return {sha for sha, _ in reference_rows(database)}


def verify_store(database: Database, folder: Path) -> dict:
    folder = Path(folder)
    references = reference_rows(database)
    unique: dict[str, set[int]] = {}
    for sha, size in references:
        unique.setdefault(sha, set()).add(size)
    errors: list[dict] = []
    checked = missing = corrupt = 0
    for sha, sizes in sorted(unique.items()):
        for size in sorted(sizes):
            checked += 1
            try:
                verified_path(folder, sha, size)
            except ValueError as error:
                code = str(error)
                if code == "private_store_content_missing":
                    missing += 1
                else:
                    corrupt += 1
                errors.append({"sha256": sha, "byte_size": size, "error": code})
    return {
        "schema": "bdt.private-store-verify.v1",
        "status": "failed" if errors else "ok",
        "referenced": len(references),
        "unique": len(unique),
        "checked": checked,
        "ok": checked - len(errors),
        "missing": missing,
        "corrupt": corrupt,
        "errors": errors[:100],
        "publication_allowed": False,
    }


def prune_orphans(database: Database, folder: Path, *, older_than_days: int = 30,
                  apply: bool = False, now: float | None = None) -> dict:
    if type(older_than_days) is not int or not 1 <= older_than_days <= 3650:
        raise ValueError("retention_days_out_of_range")
    folder = Path(folder)
    root = folder / "sha256"
    if folder.is_symlink() or root.is_symlink():
        raise ValueError("private_store_cannot_be_a_symlink")
    if not root.is_dir():
        raise ValueError("private_store_missing")
    references = referenced_hashes(database)
    if apply and not references:
        # An empty reference set usually means the wrong database was passed.
        # Never let --apply erase the whole private store in that case.
        raise ValueError("private_store_has_no_references_refusing_apply")
    cutoff = (time.time() if now is None else now) - older_than_days * 86400
    scanned = referenced = young = invalid = deleted = 0
    orphan_candidates = 0
    errors: list[dict] = []
    for prefix in sorted(root.iterdir()):
        if not prefix.is_dir() or prefix.is_symlink() or not re.fullmatch(r"[a-f0-9]{2}", prefix.name):
            continue
        for item in sorted(prefix.iterdir()):
            if not item.is_file() or item.is_symlink():
                continue
            scanned += 1
            if not HEX.fullmatch(item.name):
                invalid += 1
                continue
            if item.name in references:
                referenced += 1
                continue
            try:
                mtime = item.stat().st_mtime
            except OSError as error:
                errors.append({"name": item.name, "error": str(error)[:120]})
                continue
            if mtime > cutoff:
                young += 1
                continue
            orphan_candidates += 1
            if not apply:
                continue
            try:
                item.unlink()
                deleted += 1
            except OSError as error:
                errors.append({"name": item.name, "error": str(error)[:120]})
        if apply:
            try:
                prefix.rmdir()
            except OSError:
                pass
    return {
        "schema": "bdt.private-store-prune.v1",
        "status": "applied" if apply else "dry_run",
        "older_than_days": older_than_days,
        "scanned": scanned,
        "referenced": referenced,
        "young": young,
        "invalid": invalid,
        "deleted": deleted,
        "orphan_candidates": orphan_candidates,
        "errors": errors[:100],
        "destructive": bool(apply),
        "publication_allowed": False,
    }


def default_folder() -> Path:
    return Path(os.getenv(
        "BDT_DOCUMENT_STORE",
        str(Path(os.getenv("BDT_DATA_DIR", "data")) / "document-originals")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prune = sub.add_parser("prune")
    prune.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    prune.add_argument("--folder", type=Path, default=None)
    prune.add_argument("--older-than-days", type=int, default=30)
    prune.add_argument("--apply", action="store_true",
                       help="Delete orphan candidates; omitted means dry run.")
    verify = sub.add_parser("verify")
    verify.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    verify.add_argument("--folder", type=Path, default=None)
    args = parser.parse_args(argv)
    folder = args.folder if args.folder is not None else default_folder()
    database = Database(args.database)
    database.initialize()
    try:
        if args.command == "prune":
            result = prune_orphans(database, folder, older_than_days=args.older_than_days,
                                   apply=args.apply)
        else:
            result = verify_store(database, folder)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
