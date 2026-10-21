"""Private original document storage and reviewer-only download."""
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bdt import features as features_module
from bdt.api import create_app, password_hash
from bdt.document_originals import (DocumentOriginal, get_original, main, store_original)
from bdt.evidence import Audit, Document, DocumentInput, initialize_extensions, register_document
from bdt.private_store import content_path
from bdt.storage import User


PASSWORD = "only-a-synthetic-test-password"
HEAD = {"X-BDT-Client": "web"}
DATA = b"%PDF-1.4 synthetic original"


def fixture_document(database, source):
    initialize_extensions(database)
    sha = hashlib.sha256(DATA).hexdigest()
    with database.session() as session:
        session.add(User(username="originals_editor", role="reviewer",
                         password_hash=password_hash(PASSWORD)))
        session.flush()
        user = session.scalar(select(User).where(User.username == "originals_editor"))
        document = register_document(session, DocumentInput(
            title="Synthetic original fixture",
            source=source.model_copy(update={"snapshot_sha256": sha, "record_id": "original-1"})),
            user.id)
        identity = document.id
    return identity, sha


def test_store_original_is_private_content_addressed_and_idempotent(database, source, tmp_path):
    document_id, sha = fixture_document(database, source)
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(DATA)
    folder = tmp_path / "private-store"

    first = store_original(database, document_id, source_file, folder=folder,
                           operator="originals_editor")
    second = store_original(database, document_id, source_file, folder=folder,
                            operator="originals_editor")

    assert first == second
    assert first["sha256"] == sha and first["byte_size"] == len(DATA)
    assert first["public"] is False and first["review_required"] is True
    assert content_path(folder, sha).read_bytes() == DATA
    assert source_file.exists()
    with database.session() as session:
        assert session.get(DocumentOriginal, document_id).sha256 == sha
        audits = list(session.scalars(select(Audit).where(
            Audit.entity == "document_original", Audit.entity_id == document_id)))
        assert len(audits) == 1


def test_hash_mismatch_non_pdf_and_unknown_operator_are_rejected(database, source, tmp_path):
    document_id, _ = fixture_document(database, source)
    folder = tmp_path / "private-store"
    wrong = tmp_path / "wrong.pdf"
    wrong.write_bytes(b"%PDF-1.4 different bytes")
    with pytest.raises(ValueError, match="document_original_hash_mismatch"):
        store_original(database, document_id, wrong, folder=folder, operator="originals_editor")

    not_pdf = tmp_path / "not-pdf.pdf"
    not_pdf.write_bytes(b"plain text")
    with pytest.raises(ValueError, match="document_original_not_pdf"):
        store_original(database, document_id, not_pdf, folder=folder, operator="originals_editor")

    valid = tmp_path / "valid.pdf"
    valid.write_bytes(DATA)
    with pytest.raises(ValueError, match="existing_reviewer_operator_required"):
        store_original(database, document_id, valid, folder=folder, operator="missing")
    with database.session() as session:
        assert session.get(DocumentOriginal, document_id) is None


def test_get_original_detects_missing_and_corrupt_bytes(database, source, tmp_path):
    document_id, sha = fixture_document(database, source)
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(DATA)
    folder = tmp_path / "private-store"
    store_original(database, document_id, source_file, folder=folder,
                   operator="originals_editor")

    path, row = get_original(database, document_id, folder=folder)
    assert path.read_bytes() == DATA and row.sha256 == sha

    path.unlink()
    with pytest.raises(ValueError, match="document_original_missing"):
        get_original(database, document_id, folder=folder)

    path.write_bytes(b"%PDF-1.4 corrupted")
    with pytest.raises(ValueError, match="document_original_corrupt"):
        get_original(database, document_id, folder=folder)


@pytest.fixture
def original_client(database, source, tmp_path, monkeypatch):
    document_id, _ = fixture_document(database, source)
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(DATA)
    folder = tmp_path / "private-store"
    store_original(database, document_id, source_file, folder=folder,
                   operator="originals_editor")
    monkeypatch.setenv("BDT_DOCUMENT_STORE", str(folder))
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        client.document_id = document_id
        yield client


def login(client, name="originals_editor"):
    response = client.post("/api/auth/login", headers=HEAD,
                           json={"username": name, "password": PASSWORD})
    assert response.status_code == 200


def test_reviewer_can_download_original_but_non_reviewer_cannot(original_client):
    anonymous = original_client.get(f"/api/workbench/documents/{original_client.document_id}/original")
    assert anonymous.status_code == 401

    login(original_client)
    response = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/original")
    assert response.status_code == 200
    assert response.content == DATA
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment" in response.headers["content-disposition"]
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_document_list_and_page_expose_original_availability(original_client, database):
    login(original_client)
    listed = original_client.get("/api/workbench/documents")
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == original_client.document_id)
    assert row["has_original"] is True

    with database.session() as session:
        document = session.get(Document, original_client.document_id)
        document.extraction = {"sha256": document.source["snapshot_sha256"],
                               "extractor_version": "synthetic-v1",
                               "pages": [{"page": 1, "route": "native", "text": "native",
                                          "words": [], "tables": []}]}
    page = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/pages/1")
    assert page.status_code == 200
    assert page.json()["original_available"] is True


def test_reviewer_can_render_one_original_page(original_client, monkeypatch):
    png = b"\x89PNG\r\n\x1a\nsynthetic"
    monkeypatch.setattr(features_module, "render_page", lambda path, page: png)
    anonymous = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/pages/1/image")
    assert anonymous.status_code == 401

    login(original_client)
    response = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/pages/1/image")
    assert response.status_code == 200 and response.content == png
    assert response.headers["content-type"] == "image/png"
    assert "no-store" in response.headers["cache-control"]


def test_renderer_unavailable_is_visible(original_client, monkeypatch):
    def unavailable(path, page):
        raise ValueError("page_renderer_unavailable")

    monkeypatch.setattr(features_module, "render_page", unavailable)
    login(original_client)
    response = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/pages/1/image")
    assert response.status_code == 503
    assert response.json()["detail"] == "page_renderer_unavailable"


def test_contributor_is_refused_original_download(original_client, database):
    with database.session() as session:
        session.add(User(username="originals_reader", role="contributor",
                         password_hash=password_hash(PASSWORD)))
    login(original_client, "originals_reader")
    response = original_client.get(
        f"/api/workbench/documents/{original_client.document_id}/original")
    assert response.status_code == 403


def test_cli_store_reports_the_private_metadata(database, source, tmp_path, capsys):
    document_id, sha = fixture_document(database, source)
    source_file = tmp_path / "source.pdf"
    source_file.write_bytes(DATA)
    folder = tmp_path / "private-store"
    main(["store", "--database", str(database.engine.url), "--folder", str(folder),
          "--document-id", document_id, "--path", str(source_file),
          "--operator", "originals_editor"])
    result = json.loads(capsys.readouterr().out)
    assert result["document_id"] == document_id
    assert result["sha256"] == sha and result["public"] is False
