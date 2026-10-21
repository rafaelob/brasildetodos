"""Retention tests for the private content-addressed store."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import select

from bdt.document_originals import DocumentOriginal
from bdt.domain import now
from bdt.evidence import DocumentInput, initialize_extensions, register_document
from bdt.private_store import content_path, store_file
from bdt.private_store_admin import main, prune_orphans, verify_store
from bdt.pncp_documents import PncpContractDocument, PncpDocumentRevision
from bdt.storage import User


def put(folder: Path, data: bytes, mtime: float) -> tuple[str, Path]:
    sha = hashlib.sha256(data).hexdigest()
    path = content_path(folder, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return sha, path


def referenced_document(database, source, folder: Path, data: bytes, mtime: float) -> Path:
    initialize_extensions(database)
    sha, path = put(folder, data, mtime)
    with database.session() as session:
        session.add(User(username="prune_editor", role="reviewer", password_hash="x"))
        session.flush()
        user = session.scalar(select(User).where(User.username == "prune_editor"))
        document = register_document(session, DocumentInput(
            title="Synthetic retention fixture",
            source=source.model_copy(update={"snapshot_sha256": sha, "record_id": "prune-1"})),
            user.id)
        session.add(DocumentOriginal(document_id=document.id, sha256=sha,
                                     byte_size=len(data), media_type="application/pdf",
                                     stored_at=now()))
    return path


def referenced_pncp(database, folder: Path, current: bytes, previous: bytes,
                    mtime: float) -> tuple[Path, Path]:
    current_sha, current_path = put(folder, current, mtime)
    previous_sha, previous_path = put(folder, previous, mtime)
    stamp = now()
    with database.session() as session:
        document = PncpContractDocument(
            id="pncp-doc:00394460005887:2024:7096:1", cnpj="00394460005887",
            ano_contract=2024, sequencial_contract=7096, sequencial_document=1,
            title="Synthetic contract document", source_url=(
                "https://pncp.gov.br/pncp-api/v1/orgaos/00394460005887/contratos/"
                "2024/7096/arquivos/1"),
            snapshot_sha256=current_sha, byte_size=len(current), status="present",
            revision=2, first_seen_at=stamp, last_seen_at=stamp, metadata_json={})
        session.add(document)
        session.flush()
        session.add(PncpDocumentRevision(
            document_id=document.id, revision=1, snapshot_sha256=previous_sha,
            byte_size=len(previous), status="present", collected_at=stamp,
            metadata_json={}))
    return current_path, previous_path


def test_dry_run_then_apply_keeps_current_and_revision_references(database, source, tmp_path):
    folder = tmp_path / "private-store"
    clock = 2_000_000_000.0
    old = clock - 40 * 86400
    recent = clock - 5 * 86400
    referenced = referenced_document(database, source, folder, b"%PDF-1.4 referenced", old)
    current, previous = referenced_pncp(database, folder, b"%PDF-1.4 current",
                                        b"%PDF-1.4 previous", old)
    _, orphan = put(folder, b"%PDF-1.4 orphan", old)
    _, young = put(folder, b"%PDF-1.4 young", recent)
    invalid = folder / "sha256" / "aa" / "not-a-hash"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_bytes(b"unknown")
    os.utime(invalid, (old, old))

    dry = prune_orphans(database, folder, older_than_days=30, now=clock)
    assert dry["status"] == "dry_run"
    assert dry["referenced"] == 3 and dry["young"] == 1 and dry["invalid"] == 1
    assert dry["deleted"] == 0 and dry["orphan_candidates"] == 1
    assert orphan.exists() and young.exists() and invalid.exists()

    applied = prune_orphans(database, folder, older_than_days=30, apply=True, now=clock)
    assert applied["status"] == "applied" and applied["deleted"] == 1
    assert not orphan.exists()
    assert referenced.exists() and current.exists() and previous.exists()
    assert young.exists() and invalid.exists()


def test_verify_checks_current_revision_and_original_bytes(database, source, tmp_path):
    folder = tmp_path / "private-store"
    old = 1_900_000_000.0
    referenced_document(database, source, folder, b"%PDF-1.4 referenced", old)
    current, previous = referenced_pncp(database, folder, b"%PDF-1.4 current",
                                        b"%PDF-1.4 previous", old)

    healthy = verify_store(database, folder)
    assert healthy["status"] == "ok" and healthy["referenced"] == 3
    assert healthy["checked"] == 3 and healthy["missing"] == 0 and healthy["corrupt"] == 0

    previous.unlink()
    missing = verify_store(database, folder)
    assert missing["status"] == "failed" and missing["missing"] == 1

    current.write_bytes(b"corrupt")
    corrupt = verify_store(database, folder)
    assert corrupt["status"] == "failed" and corrupt["corrupt"] == 1


def test_store_file_does_not_delete_its_own_target(tmp_path):
    data = b"%PDF-1.4 already stored"
    sha = hashlib.sha256(data).hexdigest()
    folder = tmp_path / "private-store"
    target = content_path(folder, sha)
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    assert store_file(target, folder, sha) == target
    assert target.read_bytes() == data


def test_apply_refuses_an_empty_reference_database(database, tmp_path):
    folder = tmp_path / "private-store"
    _, orphan = put(folder, b"%PDF-1.4 orphan", 0)
    with pytest.raises(ValueError, match="private_store_has_no_references_refusing_apply"):
        prune_orphans(database, folder, apply=True)
    assert orphan.exists()


def test_missing_store_and_bad_retention_are_rejected(database, tmp_path):
    with pytest.raises(ValueError, match="private_store_missing"):
        prune_orphans(database, tmp_path / "missing")
    for days in (0, 3651, True):
        with pytest.raises(ValueError, match="retention_days_out_of_range"):
            prune_orphans(database, tmp_path / "missing", older_than_days=days)


def test_cli_defaults_to_dry_run(database, tmp_path, capsys):
    folder = tmp_path / "private-store"
    _, orphan = put(folder, b"%PDF-1.4 orphan", 0)
    main(["prune", "--database", str(database.engine.url), "--folder", str(folder),
          "--older-than-days", "1"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "dry_run" and result["destructive"] is False
    assert orphan.exists()
