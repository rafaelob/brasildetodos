"""Workbench OCR queue routes: reviewer-only, private, no automatic publication."""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from bdt.api import create_app, password_hash
from bdt.evidence import Document, DocumentInput, initialize_extensions, register_document
from bdt.storage import User

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'only-a-synthetic-test-password'


@pytest.fixture
def client(database, source):
    initialize_extensions(database)
    with database.session() as session:
        for name, role in [('ocr_editor', 'reviewer'), ('ocr_reader', 'contributor')]:
            session.add(User(username=name, role=role, password_hash=password_hash(PASSWORD)))
    sha = hashlib.sha256(b'synthetic-ocr-api-fixture-not-a-real-document').hexdigest()
    with database.session() as session:
        user = session.scalar(select(User).where(User.username == 'ocr_editor'))
        doc = register_document(session, DocumentInput(
            title='Synthetic OCR API fixture',
            source=source.model_copy(update={'snapshot_sha256': sha})), user.id)
        doc.state = 'extracted'
        doc.extraction = {'sha256': sha, 'extractor_version': 'synthetic-v1', 'pages': [
            {'page': 1, 'route': 'native', 'text': 'native', 'words': [], 'tables': []},
            {'page': 2, 'route': 'ocr_candidate', 'text': '', 'words': [], 'tables': []}]}
        identity = doc.id
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as test_client:
        test_client.document_id = identity
        yield test_client


def login(client, name='ocr_editor'):
    response = client.post('/api/auth/login', headers=HEAD,
                           json={'username': name, 'password': PASSWORD})
    assert response.status_code == 200


def test_reviewer_can_enqueue_list_cancel_and_retry(client):
    login(client)
    created = client.post('/api/workbench/ocr/jobs', headers=HEAD,
                          json={'document_id': client.document_id, 'pages': [2]})
    assert created.status_code == 201
    job = created.json()
    assert job['status'] == 'queued' and job['pages'] == [2]
    assert job['result'] is None and job['can_cancel'] is True
    assert 'original_sha256' not in job and 'text' not in job

    listed = client.get('/api/workbench/ocr/jobs', headers=HEAD)
    assert listed.status_code == 200 and [row['id'] for row in listed.json()] == [job['id']]

    cancelled = client.post(f"/api/workbench/ocr/jobs/{job['id']}/cancel", headers=HEAD)
    assert cancelled.status_code == 200 and cancelled.json()['status'] == 'cancelled'
    assert cancelled.json()['can_retry'] is True

    retried = client.post(f"/api/workbench/ocr/jobs/{job['id']}/retry", headers=HEAD)
    assert retried.status_code == 200 and retried.json()['status'] == 'queued'


def test_non_reviewer_and_anonymous_are_refused(client):
    login(client, 'ocr_reader')
    assert client.post('/api/workbench/ocr/jobs', headers=HEAD,
                       json={'document_id': client.document_id, 'pages': [2]}).status_code == 403
    assert client.get('/api/workbench/ocr/jobs', headers=HEAD).status_code == 403
    client.post('/api/auth/logout', headers=HEAD)
    assert client.get('/api/workbench/ocr/jobs', headers=HEAD).status_code == 401


def test_ineligible_page_and_unknown_document_are_rejected(client):
    login(client)
    assert client.post('/api/workbench/ocr/jobs', headers=HEAD,
                       json={'document_id': client.document_id, 'pages': [1]}).status_code == 409
    assert client.post('/api/workbench/ocr/jobs', headers=HEAD,
                       json={'document_id': 'missing', 'pages': [2]}).status_code == 409
    assert client.post('/api/workbench/ocr/jobs', headers=HEAD,
                       json={'document_id': client.document_id, 'pages': [2],
                             'language': 'pt-BR'}).status_code == 409


def test_enqueue_never_changes_document_or_publishes(client, database):
    login(client)
    created = client.post('/api/workbench/ocr/jobs', headers=HEAD,
                          json={'document_id': client.document_id, 'pages': [2]})
    assert created.status_code == 201
    with database.session() as session:
        document = session.get(Document, client.document_id)
        assert document.state == 'extracted'
        assert 'ocr_candidate_text' not in document.extraction['pages'][1]
