"""Whitespace must never establish a reviewed institutional relationship."""
import pytest
from sqlalchemy import select

from bdt.evidence import Audit, Decision, Document, Link, LinkInput, validate_excerpt
from test_features import HEAD, client, decision, login, prepare_link


@pytest.mark.parametrize('blank', [' ' * 30, '\t\n' * 15, '\u00a0' * 30])
@pytest.mark.parametrize('field', ['excerpt', 'justification'])
def test_proposal_requires_meaningful_text(client, database, source, field, blank):
    body = prepare_link(client, database, source)
    response = client.post('/api/workbench/links', headers=HEAD, json=body | {field: blank})
    assert response.status_code == 422
    with database.session() as session:
        assert list(session.scalars(select(Link))) == []
    assert client.get('/api/place-links/test:school').json() == []


@pytest.mark.parametrize('blank', [' ' * 30, '\t\n' * 15, '\u00a0' * 30])
def test_review_requires_meaningful_reason(blank):
    with pytest.raises(ValueError):
        Decision.model_validate(decision() | {'note': blank})


def test_review_rejects_legacy_whitespace_excerpt(client, database, source):
    body = prepare_link(client, database, source)
    identity = client.post('/api/workbench/links', headers=HEAD, json=body).json()['id']
    with database.session() as session:
        session.get(Link, identity).excerpt = ' ' * 20
    login(client, 'reviewer')
    response = client.post(f'/api/workbench/links/{identity}/review', headers=HEAD, json=decision())
    assert response.status_code == 422
    assert client.get('/api/place-links/test:school').json() == []
    with database.session() as session:
        link = session.get(Link, identity)
        assert (link.status, link.revision, link.reviewer_id) == ('candidate', 1, None)
        assert [a.action for a in session.scalars(select(Audit).where(Audit.entity_id == identity))] == ['proposed']


@pytest.mark.parametrize('text', ['', 'A real native text without OCR.'])
def test_low_level_validation_refuses_empty_quotation(source, text):
    document = Document(state='extracted', source=source.model_dump(), extraction={
        'sha256': source.snapshot_sha256, 'pages': [{'page': 1, 'text': text}]})
    with pytest.raises(ValueError, match='excerpt_not_found'):
        validate_excerpt(document, 1, '\n \t' * 10)


def test_layout_whitespace_is_preserved_for_valid_evidence(client, database, source):
    body = prepare_link(client, database, source)
    body['excerpt'] = 'Explicit\n reference to\t test:school'
    validated = LinkInput.model_validate(body)
    assert validated.excerpt == body['excerpt']
    response = client.post('/api/workbench/links', headers=HEAD, json=body)
    assert response.status_code == 201
    login(client, 'reviewer')
    identity = response.json()['id']
    assert client.post(f'/api/workbench/links/{identity}/review', headers=HEAD, json=decision()).status_code == 200
    assert client.get('/api/place-links/test:school').json()[0]['excerpt'] == body['excerpt']


@pytest.mark.parametrize('field', ['excerpt', 'justification'])
def test_internal_padding_cannot_satisfy_minimum_evidence_length(client, database, source, field):
    body = prepare_link(client, database, source)
    with pytest.raises(ValueError):
        LinkInput.model_validate(body | {field: 'a' + ' ' * 30 + 'b'})


def test_internal_padding_is_not_a_review_reason():
    with pytest.raises(ValueError):
        Decision.model_validate(decision() | {'note': 'a' + ' ' * 30 + 'b'})


@pytest.mark.parametrize('missing_hash', [None, ''])
def test_matching_invalid_hashes_cannot_validate_document(source, missing_hash):
    source_data = source.model_dump() | {'snapshot_sha256': missing_hash}
    document = Document(state='extracted', source=source_data, extraction={
        'sha256': missing_hash, 'pages': [{'page': 1, 'text': 'Synthetic explicit institutional evidence.'}]})
    with pytest.raises(ValueError, match='stored_document_extraction_invalid'):
        validate_excerpt(document, 1, 'Synthetic explicit institutional evidence.')
