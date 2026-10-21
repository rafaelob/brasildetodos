# SPDX-License-Identifier: AGPL-3.0-or-later
"""Operator-only cleanup for unreferenced content-addressed private files.

A dry run is the default. ``--apply`` removes only files that are older than
the retention window and are not referenced by any current document row or
document revision. Unknown names and symlinks are never deleted.
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
from .storage import Database


HEX = re.compile(r"[a-f0-9]{64}")


def referenced_hashes(database: Database) -> set[str]:
    with database.session() as session:
        hashes = set(session.scalars(select(PncpContractDocument.snapshot_sha256)))
        hashes |= set(session.scalars(select(PncpDocumentRevision.snapshot_sha256)))
        hashes |= set(session.scalars(select(DocumentOriginal.sha256)))
        return hashes


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prune = sub.add_parser("prune")
    prune.add_argument("--database", default=os.getenv("BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
    prune.add_argument("--folder", type=Path, default=None)
    prune.add_argument("--older-than-days", type=int, default=30)
    prune.add_argument("--apply", action="store_true",
                       help="Delete orphan candidates; omitted means dry run.")
    args = parser.parse_args(argv)
    folder = args.folder
    if folder is None:
        folder = Path(os.getenv(
            "BDT_DOCUMENT_STORE",
            str(Path(os.getenv("BDT_DATA_DIR", "data")) / "document-originals")))
    database = Database(args.database)
    database.initialize()
    try:
        result = prune_orphans(database, folder, older_than_days=args.older_than_days,
                               apply=args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == "__main__":
    main()
