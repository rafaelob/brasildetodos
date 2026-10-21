"""Behavioral tests for the private PNCP contract-document collector."""
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import select

from bdt.catalog_release import EXCLUDED
from bdt.pncp_documents import (PncpContractDocument, PncpDocumentRevision,
                                collect_contract_documents, content_path,
                                document_id)


CNPJ = "00394460005887"
ANO = 2024
SEQUENCIAL = 7096


def dto(documento=1, **overrides):
    url = f"https://pncp.gov.br/pncp-api/v1/orgaos/{CNPJ}/contratos/{ANO}/{SEQUENCIAL}/arquivos/{documento}"
    row = {
        "uri": url,
        "url": url,
        "cnpj": CNPJ,
        "anoCompra": ANO,
        "sequencialCompra": SEQUENCIAL,
        "dataPublicacaoPncp": "2025-01-01T00:30:03",
        "sequencialDocumento": documento,
        "titulo": f"Contrato_Pncp_2024_900100_{documento}.pdf",
        "tipoDocumentoNome": "Contrato",
    }
    row.update(overrides)
    return row


class FakePncp:
    def __init__(self, pages, files=None):
        self.pages = pages
        self.files = files if files is not None else {
            document["sequencialDocumento"]: f"%PDF-1.4 synthetic {document['sequencialDocumento']}".encode()
            for page in pages.values() for document in page
        }
        self.fail_list_page = None
        self.fail_document = None

    def list_loader(self, url, target, max_bytes):
        page = int(parse_qs(urlsplit(url).query)["pagina"][0])
        if self.fail_list_page == page:
            raise RuntimeError("synthetic list failure")
        payload = self.pages.get(page, [])
        target.write_bytes(json.dumps(payload).encode("utf-8"))
        return {"bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    def document_loader(self, url, target, max_bytes):
        documento = int(url.rsplit("/", 1)[-1])
        if self.fail_document == documento:
            raise RuntimeError("synthetic download failure")
        data = self.files[documento]
        target.write_bytes(data)
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def collect(database, folder, fake, **overrides):
    options = {"cnpj": CNPJ, "ano": ANO, "sequencial": SEQUENCIAL, "page_size": 2,
               "list_loader": fake.list_loader, "document_loader": fake.document_loader}
    options.update(overrides)
    return collect_contract_documents(database, folder, **options)


def stored_rows(database):
    with database.session() as session:
        return list(session.scalars(select(PncpContractDocument).order_by(
            PncpContractDocument.sequencial_document)))


def revisions(database, documento):
    with database.session() as session:
        row = session.scalar(select(PncpContractDocument).where(
            PncpContractDocument.sequencial_document == documento))
        return list(session.scalars(select(PncpDocumentRevision).where(
            PncpDocumentRevision.document_id == row.id).order_by(PncpDocumentRevision.revision)))


def test_complete_collection_stores_official_metadata_and_private_bytes(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)], 2: [dto(3)]})
    folder = tmp_path / "private-pncp"
    report = collect(database, folder, fake)

    assert report["status"] == "complete"
    assert report["documents"] == 3 and report["new"] == 3
    assert report["publication_allowed"] is False
    assert report["review_required"] is True
    rows = stored_rows(database)
    assert [row.sequencial_document for row in rows] == [1, 2, 3]
    for row in rows:
        data = fake.files[row.sequencial_document]
        assert row.snapshot_sha256 == hashlib.sha256(data).hexdigest()
        assert row.byte_size == len(data)
        assert row.status == "present" and row.revision == 1
        assert row.metadata_json["cnpj"] == CNPJ
        assert content_path(folder, row.snapshot_sha256).read_bytes() == data
        assert len(revisions(database, row.sequencial_document)) == 1
    assert json.loads((folder / "collection.json").read_text(encoding="utf-8"))["status"] == "complete"


def test_unchanged_revisit_does_not_create_a_revision(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)
    first = stored_rows(database)[0]

    report = collect(database, folder, fake)

    assert report["unchanged"] == 2 and report["updated"] == 0 and report["new"] == 0
    row = stored_rows(database)[0]
    assert row.revision == 1 and row.snapshot_sha256 == first.snapshot_sha256
    assert len(revisions(database, 1)) == 1


def test_changed_bytes_create_a_revision_and_keep_the_old_file(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)
    old = stored_rows(database)[0]
    old_path = content_path(folder, old.snapshot_sha256)

    fake.files[1] = b"%PDF-1.4 synthetic changed"
    report = collect(database, folder, fake)

    assert report["updated"] == 1
    row = stored_rows(database)[0]
    assert row.revision == 2
    assert row.snapshot_sha256 == hashlib.sha256(fake.files[1]).hexdigest()
    assert old_path.exists() and old_path.read_bytes() == b"%PDF-1.4 synthetic 1"
    assert [item.revision for item in revisions(database, 1)] == [1, 2]


def test_complete_revisit_marks_missing_document_not_listed_without_deleting(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)], 2: [dto(3)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)
    missing = stored_rows(database)[1]
    missing_path = content_path(folder, missing.snapshot_sha256)

    fake.pages = {1: [dto(1), dto(3)]}
    report = collect(database, folder, fake)

    assert report["status"] == "complete" and report["not_listed"] == 1
    row = next(row for row in stored_rows(database) if row.sequencial_document == 2)
    assert row.status == "not_listed" and row.revision == 1
    assert missing_path.exists()


def test_bounded_revisit_does_not_change_visibility(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)], 2: [dto(3)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)

    fake.pages = {1: [dto(1), dto(2)]}
    report = collect(database, folder, fake, max_pages=1)

    assert report["status"] == "bounded" and report["not_listed"] == 0
    row = next(row for row in stored_rows(database) if row.sequencial_document == 3)
    assert row.status == "present"


def test_failed_download_leaves_previous_rows_and_success_report_untouched(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)
    before = stored_rows(database)
    success_report = (folder / "collection.json").read_bytes()

    fake.files[1] = b"%PDF-1.4 synthetic changed"
    fake.fail_document = 1
    with pytest.raises(RuntimeError, match="synthetic download failure"):
        collect(database, folder, fake)

    after = stored_rows(database)
    assert [(row.sequencial_document, row.snapshot_sha256, row.revision) for row in after] == [
        (row.sequencial_document, row.snapshot_sha256, row.revision) for row in before]
    assert (folder / "collection.json").read_bytes() == success_report
    failed = json.loads((folder / "collection-failed.json").read_text(encoding="utf-8"))
    assert failed["status"] == "failed" and failed["publication_allowed"] is False


def test_empty_complete_listing_marks_prior_documents_not_listed(database, tmp_path):
    fake = FakePncp({1: [dto(1)]})
    folder = tmp_path / "private-pncp"
    collect(database, folder, fake)

    fake.pages = {}
    report = collect(database, folder, fake)

    assert report["status"] == "complete" and report["terminal"] == "empty_page"
    assert stored_rows(database)[0].status == "not_listed"


@pytest.mark.parametrize("mutation,message", [
    (lambda row: row.update(cnpj="11111111111111"), "pncp_document_cnpj_mismatch"),
    (lambda row: row.update(anoCompra=2023), "pncp_document_year_mismatch"),
    (lambda row: row.update(sequencialDocumento=0), "invalid_pncp_document_sequence"),
    (lambda row: row.update(titulo=" "), "invalid_pncp_document_title"),
    (lambda row: row.update(dataPublicacaoPncp="not-a-date"), "invalid_pncp_document_timestamp"),
    (lambda row: row.update(url="https://evil.example/pncp/arquivos/1"), "untrusted_pncp_download_url"),
    (lambda row: row.update(url=f"https://pncp.gov.br/pncp-api/v1/orgaos/{CNPJ}/contratos/{ANO}/{SEQUENCIAL}/arquivos/2"),
     "pncp_download_url_does_not_match_contract"),
])
def test_invalid_official_metadata_is_rejected_before_writing(database, tmp_path, mutation, message):
    row = dto(1)
    mutation(row)
    fake = FakePncp({1: [row]})
    with pytest.raises(ValueError, match=message):
        collect(database, tmp_path / "private-pncp", fake)
    assert stored_rows(database) == []


def test_duplicate_document_sequence_is_rejected(database, tmp_path):
    fake = FakePncp({1: [dto(1), dto(2)], 2: [dto(2)]})
    with pytest.raises(ValueError, match="duplicate_pncp_document_sequence"):
        collect(database, tmp_path / "private-pncp", fake)
    assert stored_rows(database) == []


def test_declared_more_pages_but_short_page_is_not_treated_as_complete(database, tmp_path):
    def list_loader(url, target, max_bytes):
        page = int(parse_qs(urlsplit(url).query)["pagina"][0])
        target.write_bytes(json.dumps({
            "numeroPagina": page, "totalPaginas": 2, "data": [dto(1)],
        }).encode("utf-8"))
        return {"bytes": target.stat().st_size, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    fake = FakePncp({})
    with pytest.raises(ValueError, match="pncp_document_list_ended_before_declared_end"):
        collect(database, tmp_path / "private-pncp", fake, list_loader=list_loader)
    assert stored_rows(database) == []


def test_private_tables_are_never_in_the_public_catalog_export():
    assert "pncp_contract_documents" in EXCLUDED
    assert "pncp_document_revisions" in EXCLUDED


def test_content_path_rejects_invalid_hash(tmp_path):
    with pytest.raises(ValueError, match="invalid_content_hash"):
        content_path(tmp_path, "../not-a-hash")


def test_document_id_is_stable_and_contract_scoped():
    assert document_id(CNPJ, ANO, SEQUENCIAL, 1) == f"pncp-doc:{CNPJ}:{ANO}:{SEQUENCIAL}:1"
