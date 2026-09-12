import hashlib
from copy import deepcopy
import pytest
from reportlab.pdfgen import canvas
from sqlalchemy import select
from bdt.evidence import (Audit, Decision, Document, DocumentInput, ExtensionVersion, Link, LinkInput, ResourceInput,
    initialize_extensions, link_payload, register_document, store_extraction, validate_excerpt)
from bdt.storage import User, Place


@pytest.fixture
def evidence_user(database):
    initialize_extensions(database)
    with database.session() as session:
        row = User(username='evidence_author', password_hash='not-a-usable-login', role='reviewer')
        session.add(row); session.flush(); identity = row.id
    return identity


def test_additive_migration_is_idempotent(database, stored):
    initialize_extensions(database); initialize_extensions(database)
    with database.session() as session:
        assert session.get(Place, stored.id).name == stored.name
        version = session.get(ExtensionVersion, 1)
        assert version.version == 1
        version.version = 99
    with pytest.raises(RuntimeError, match='Unsupported extension schema'):
        initialize_extensions(database)


def test_resource_and_decision_contracts(source):
    data = {'id': 'pncp:123/2025', 'kind': 'contract', 'title': 'Synthetic contract', 'source': source}
    assert ResourceInput(**data).municipality_id is None
    with pytest.raises(ValueError):
        ResourceInput(**data, attributes={'unbounded': 'x' * 17000})
    with pytest.raises(ValueError):
        ResourceInput(**(data | {'kind': 'paid'}))
    with pytest.raises(ValueError):
        Decision(decision='reviewed', note='A carefully reviewed test.', expected_revision=0)
    decision = Decision(decision='reviewed', note='A carefully reviewed test.', expected_revision=1)
    assert decision.public_excerpt_checked is False
    with pytest.raises(ValueError):
        LinkInput(place_id='test:school', resource_id='pncp:1', document_id='a'*64, page=0,
            excerpt='Sample excerpt', justification='This is a synthetic test only.')


def test_register_preserves_version_and_is_idempotent(database, source, evidence_user):
    data = DocumentInput(title='Synthetic agreement', source=source)
    with database.session() as session:
        first = register_document(session, data, evidence_user)
        second = register_document(session, data, evidence_user)
        assert first.id == second.id
        newer = register_document(session, data.model_copy(update={'source': source.model_copy(update={'snapshot_sha256': 'b'*64})}), evidence_user)
        assert newer.id != first.id
    with database.session() as session:
        assert len(list(session.scalars(select(Document)))) == 2
        assert len(list(session.scalars(select(Audit)))) == 2


def test_extract_native_preserves_original_and_remains_private(database, source, evidence_user, tmp_path):
    path = tmp_path / 'synthetic.pdf'
    pdf = canvas.Canvas(str(path)); pdf.drawString(50, 700, 'CONVENIO 977950/2025 - synthetic test only.'); pdf.save()
    original = path.read_bytes()
    with database.session() as session:
        row = register_document(session, DocumentInput(title='Synthetic document', source=source.model_copy(update={
            'snapshot_sha256': hashlib.sha256(original).hexdigest()})), evidence_user)
        identity = row.id
    result = store_extraction(database, identity, path)
    assert result['pages'] == 1 and result['public'] is False
    assert path.read_bytes() == original
    with database.session() as session:
        row = session.get(Document, identity)
        assert row.state == 'extracted' and 'filename' not in row.extraction
        validate_excerpt(row, 1, 'CONVENIO 977950/2025')
        with pytest.raises(ValueError, match='excerpt_not_found'):
            validate_excerpt(row, 1, 'CONVENIO 000000/2025')
        with pytest.raises(ValueError, match='page_not_found'):
            validate_excerpt(row, 2, 'CONVENIO 977950/2025')
    with pytest.raises(ValueError, match='document_not_found'):
        store_extraction(database, '0'*64, path)
    path.write_bytes(original + b'\nchanged')
    with pytest.raises(ValueError, match='document_hash_mismatch'):
        store_extraction(database, identity, path)


def test_repeated_extraction_reuses_exact_stored_package(database, source, evidence_user, tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.pdf'
    pdf = canvas.Canvas(str(path)); pdf.drawString(50, 700, 'CONVENIO 977950/2025 - synthetic test only.'); pdf.save()
    original = path.read_bytes()
    with database.session() as session:
        identity = register_document(session, DocumentInput(title='Synthetic document', source=source.model_copy(update={
            'snapshot_sha256': hashlib.sha256(original).hexdigest()})), evidence_user).id
    first = store_extraction(database, identity, path)
    with database.session() as session:
        stored = deepcopy(session.get(Document, identity).extraction)

    monkeypatch.setattr('bdt.documents.inspect_pdf', lambda *args, **kwargs: pytest.fail('stored extraction must be reused'))
    assert store_extraction(database, identity, path) == first
    with database.session() as session:
        assert session.get(Document, identity).extraction == stored


def test_repeated_extraction_rejects_corrupt_stored_page_structure(database, source, evidence_user, tmp_path):
    path = tmp_path / 'synthetic.pdf'
    pdf = canvas.Canvas(str(path)); pdf.drawString(50, 700, 'CONVENIO 977950/2025 - synthetic test only.'); pdf.save()
    original = path.read_bytes()
    with database.session() as session:
        identity = register_document(session, DocumentInput(title='Synthetic document', source=source.model_copy(update={
            'snapshot_sha256': hashlib.sha256(original).hexdigest()})), evidence_user).id
    expected = store_extraction(database, identity, path)
    with database.session() as session:
        valid = deepcopy(session.get(Document, identity).extraction)

    invalid_pages = [
        [{'page': True, 'text': 'Invalid boolean page number'}],
        [{'page': 1, 'text': []}],
        [{'page': 1, 'text': 'First'}, {'page': 1, 'text': 'Duplicate'}],
    ]
    for pages in invalid_pages:
        with database.session() as session:
            session.get(Document, identity).extraction = deepcopy(valid) | {'pages': pages}
        with pytest.raises(ValueError, match='stored_document_extraction_invalid'):
            store_extraction(database, identity, path)

    with database.session() as session:
        session.get(Document, identity).extraction = valid
    assert store_extraction(database, identity, path) == expected


def test_invalid_new_extraction_never_commits(database, source, evidence_user, tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.pdf'
    path.write_bytes(b'%PDF-synthetic-parser-contract')
    snapshot = hashlib.sha256(path.read_bytes()).hexdigest()
    with database.session() as session:
        identity = register_document(session, DocumentInput(
            title='Synthetic parser contract',
            source=source.model_copy(update={'snapshot_sha256': snapshot}),
        ), evidence_user).id

    monkeypatch.setattr('bdt.documents.inspect_pdf', lambda *args, **kwargs: {
        'sha256': snapshot,
        'pages': [{'page': True, 'text': 'Invalid boolean page number'}],
    })
    with pytest.raises(ValueError, match='stored_document_extraction_invalid'):
        store_extraction(database, identity, path)
    with database.session() as session:
        document = session.get(Document, identity)
        assert document.state == 'registered'
        assert document.extraction is None

    monkeypatch.setattr('bdt.documents.inspect_pdf', lambda *args, **kwargs: {
        'sha256': snapshot,
        'pages': [{'page': 1, 'text': 'Valid native extraction'}],
    })
    assert store_extraction(database, identity, path)['pages'] == 1


def test_reject_changed_bytes_during_extraction(database, source, evidence_user, tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.pdf'; path.write_bytes(b'%PDF-synthetic')
    src = source.model_copy(update={'snapshot_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    with database.session() as session:
        identity = register_document(session, DocumentInput(title='Synthetic document', source=src), evidence_user).id
    monkeypatch.setattr('bdt.documents.inspect_pdf', lambda *a, **kw: {'sha256': 'b'*64})
    with pytest.raises(ValueError, match='document_changed_during_extraction'):
        store_extraction(database, identity, path)


def test_excerpt_whitespace_and_pending_states():
    doc = Document(id='a'*64, state='registered')
    with pytest.raises(ValueError, match='document_not_extracted'):
        validate_excerpt(doc, 1, 'A test excerpt')
    doc.state = 'extracted'
    doc.extraction = {'pages': [{'page': 1, 'text': 'A test\n   excerpt', 'ocr_candidate_text': 'other observed words'}]}
    validate_excerpt(doc, 1, 'A test excerpt')
    validate_excerpt(doc, 1, 'other observed words')
    link = Link(id='x', place_id='test:school', resource_id='pncp:1', document_id=doc.id, page=1,
        excerpt='A test excerpt', justification='Private reviewer context', status='reviewed', revision=1)
    assert 'justification' not in link_payload(link, public=True)
    assert link_payload(link)['justification'] == 'Private reviewer context'
