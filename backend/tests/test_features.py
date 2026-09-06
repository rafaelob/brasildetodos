import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from bdt.api import create_app, password_hash
from bdt.evidence import Audit, Document, Link, Resource
from bdt.storage import Finance, LoginSession, Observation, User, upsert_place

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'only-a-synthetic-test-password'


@pytest.fixture
def client(database, stored):
    app = create_app(str(database.engine.url), testing=True)
    with database.session() as session:
        for name, role in [('editor', 'reviewer'), ('reviewer', 'reviewer'), ('reader', 'contributor'), ('other', 'contributor')]:
            session.add(User(username=name, role=role, password_hash=password_hash(PASSWORD)))
    with TestClient(app) as client:
        yield client


def login(client, name='editor'):
    response = client.post('/api/auth/login', headers=HEAD, json={'username': name, 'password': PASSWORD})
    assert response.status_code == 200


def resource(source):
    return {'id': 'pncp:synthetic/2025', 'kind': 'contract', 'title': 'Synthetic school renovation contract',
            'municipality_id': '1234567', 'source': source.model_dump(), 'attributes': {'phase': 'contracted'}}


def document(source):
    return {'title': 'Synthetic evidence document', 'source': source.model_dump()}


def prepare_link(client, database, source):
    login(client)
    assert client.post('/api/workbench/resources', headers=HEAD, json=resource(source)).status_code == 201
    identity = client.post('/api/workbench/documents', headers=HEAD, json=document(source)).json()['id']
    with database.session() as session:
        row = session.get(Document, identity)
        row.state = 'extracted'
        row.extraction = {'pages': [{'page': 1, 'text': 'Explicit reference to test:school in this synthetic document.', 'words': [], 'candidates': []}]}
    body = {'place_id': 'test:school', 'resource_id': 'pncp:synthetic/2025', 'document_id': identity, 'page': 1,
            'excerpt': 'Explicit reference to test:school', 'justification': 'The identifier is explicitly included in the synthetic text.'}
    return body


def decision(action='reviewed', revision=1):
    return {'decision': action, 'expected_revision': revision, 'note': 'Independent review of this synthetic document and excerpt.',
            'public_excerpt_checked': True}


def observe(client):
    return client.post('/api/observations', headers=HEAD, json={'place_id': 'test:school', 'mode': 'field',
        'observed_on': '2025-01-01', 'body': 'A synthetic observation from the public entrance.', 'consent': True}).json()['id']


def test_feature_auth_and_validation(client, source):
    assert client.get('/api/workbench/documents').status_code == 401
    assert client.get('/api/workbench/links').status_code == 401
    assert client.post('/api/workbench/resources', headers=HEAD, json=resource(source)).status_code == 401
    login(client, 'reader')
    assert client.get('/api/workbench/documents').status_code == 403
    assert client.get('/api/workbench/links').status_code == 403
    assert client.post('/api/workbench/documents', headers=HEAD, json=document(source)).status_code == 403
    assert client.post('/api/workbench/resources', json=resource(source)).status_code == 403
    assert client.get('/api/map/viewport?bbox=bad').status_code == 422
    assert client.get('/api/map/viewport?bbox=-75,-35,-32,6&zoom=30').status_code == 422
    assert client.get('/api/map/viewport?bbox=-75,-35,-32,6').json()['matched_records'] == 0


def test_resources_preserve_scope_and_versions(client, source):
    login(client)
    assert client.post('/api/workbench/resources', headers=HEAD, json=resource(source)|{'municipality_id': '9999999'}).status_code == 422
    for _ in range(2):
        assert client.post('/api/workbench/resources', headers=HEAD, json=resource(source)).status_code == 201
    assert client.post('/api/workbench/resources', headers=HEAD, json=resource(source)|{'title': 'Conflicting replacement'}).status_code == 409
    assert client.get('/api/resources').json()['total'] == 1
    assert len(client.get('/api/resources?page=2&limit=1').json()['items']) == 0
    assert client.get('/api/resources?municipality_id=1234567&kind=contract').json()['total'] == 1
    assert client.get('/api/resources?kind=work').json()['total'] == 0
    assert client.get('/api/resources?municipality_id=9999999').json()['total'] == 0


def test_document_register_metadata_and_pages_private(client, source, database):
    login(client)
    response = client.post('/api/workbench/documents', headers=HEAD, json=document(source))
    assert response.status_code == 201
    identity = response.json()['id']
    assert client.post('/api/workbench/documents', headers=HEAD, json=document(source)).json()['id'] == identity
    items = client.get('/api/workbench/documents').json()
    assert len(items) == 1 and items[0]['pages'] == 0 and 'extraction' not in items[0]
    assert client.get('/api/workbench/documents/missing/pages/1').status_code == 404
    assert client.get(f'/api/workbench/documents/{identity}/pages/1').status_code == 404
    with database.session() as session:
        session.get(Document, identity).extraction = {'pages': [{'page': 1, 'text': 'restricted test text'}]}
    assert client.get(f'/api/workbench/documents/{identity}/pages/1').json()['public'] is False
    client.post('/api/auth/logout', headers=HEAD)
    assert client.get(f'/api/workbench/documents/{identity}/pages/1').status_code == 401


def test_exact_excerpt_is_required_and_never_guess_link(client, database, source):
    body = prepare_link(client, database, source)
    for changes, code in [({'place_id':'test:missing'},404), ({'resource_id':'pncp:missing'},404),
                          ({'document_id':'0'*64},404), ({'page':2},422), ({'excerpt':'Invented untraceable quotation'},422)]:
        assert client.post('/api/workbench/links', headers=HEAD, json=body|changes).status_code == code
    with database.session() as session:
        session.get(Document, body['document_id']).state = 'registered'
    assert client.post('/api/workbench/links', headers=HEAD, json=body).status_code == 422


def test_link_review_publication_and_retraction(client, database, source):
    body = prepare_link(client, database, source)
    submitted = client.post('/api/workbench/links', headers=HEAD, json=body)
    assert submitted.status_code == 201
    identity = submitted.json()['id']
    assert client.get('/api/place-links/test:school').json() == []
    assert client.get('/api/place-links/test:missing').status_code == 404
    assert client.get('/api/workbench/links').json()[0]['can_review'] is False
    path = f'/api/workbench/links/{identity}/review'
    assert client.post(path, headers=HEAD, json=decision()).status_code == 403
    login(client, 'reviewer')
    assert client.get('/api/workbench/links').json()[0]['can_review'] is True
    assert client.post('/api/workbench/links/missing/review', headers=HEAD, json=decision()).status_code == 404
    assert client.post(path, headers=HEAD, json=decision(revision=5)).status_code == 409
    assert client.post(path, headers=HEAD, json=decision()|{'public_excerpt_checked':False}).status_code == 422
    reviewed = client.post(path, headers=HEAD, json=decision())
    assert reviewed.status_code == 200 and reviewed.json()['revision'] == 2
    published = client.get('/api/place-links/test:school').json()[0]
    assert published['resource']['id'] == body['resource_id']
    assert published['excerpt'] == body['excerpt']
    assert not {'author_id', 'justification', 'extraction', 'review_note'} & published.keys()
    assert client.get('/api/places/test:school').json()['finance'] == []
    assert client.post(path, headers=HEAD, json=decision()).status_code == 409
    assert client.post(path, headers=HEAD, json=decision('retracted', 2)).status_code == 200
    assert client.get('/api/place-links/test:school').json() == []
    assert client.get('/api/workbench/links?status=retracted').json()[0]['revision'] == 3
    with database.session() as session:
        assert [x.action for x in session.scalars(select(Audit).where(Audit.entity_id == identity).order_by(Audit.at))] == ['proposed', 'reviewed', 'retracted']


def test_rejected_link_does_not_publish(client, database, source):
    body = prepare_link(client, database, source)
    identity = client.post('/api/workbench/links', headers=HEAD, json=body).json()['id']
    login(client, 'reviewer')
    assert client.post(f'/api/workbench/links/{identity}/review', headers=HEAD, json=decision('rejected')).status_code == 200
    assert client.get('/api/place-links/test:school').json() == []


def test_author_withdrawal_is_private_and_idempotent(client):
    login(client, 'reader'); identity = observe(client)
    login(client, 'other')
    assert client.post(f'/api/observations/{identity}/withdraw', headers=HEAD).status_code == 404
    login(client, 'reader')
    for _ in range(2):
        assert client.post(f'/api/observations/{identity}/withdraw', headers=HEAD).json()['status'] == 'withdrawn'
    assert client.get('/api/observations/mine').json()[0]['status'] == 'withdrawn'
    assert client.get('/api/places/test:school').json()['observations'] == []
    login(client, 'reviewer')
    assert client.post(f'/api/review/{identity}', headers=HEAD, json={'decision':'approved','note':'Cannot approve withdrawn content.'}).status_code == 409


def test_published_observation_can_be_retracted(client):
    login(client, 'reader'); identity = observe(client)
    login(client, 'reviewer')
    assert client.post(f'/api/review/{identity}', headers=HEAD, json={'decision':'approved','note':'Reviewed synthetic observation.'}).status_code == 200
    assert len(client.get('/api/places/test:school').json()['observations']) == 1
    body = {'note': 'Publication retracted after additional contextual review.'}
    path = f'/api/moderation/observations/{identity}/retract'
    assert client.post(path, headers=HEAD, json=body).status_code == 200
    assert client.post(path, headers=HEAD, json=body).status_code == 409
    assert client.get('/api/places/test:school').json()['observations'] == []


def test_export_and_account_deactivation(client, database):
    assert client.get('/api/account/export').status_code == 401
    login(client, 'reader'); identity = observe(client)
    login(client, 'other'); observe(client)
    login(client, 'reader')
    exported = client.get('/api/account/export').json()
    assert len(exported['observations']) == 1 and exported['credentials_included'] is False
    assert 'password' not in str(exported) and 'token' not in str(exported)
    body = {'password': PASSWORD, 'confirmed': True}
    assert client.post('/api/account/delete', headers=HEAD, json=body|{'password':'wrong-password-long'}).status_code == 403
    assert client.post('/api/account/delete', headers=HEAD, json=body|{'confirmed':False}).status_code == 422
    assert client.post('/api/account/delete', headers=HEAD, json=body).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert client.post('/api/auth/login', headers=HEAD, json={'username':'reader','password':PASSWORD}).status_code == 401
    with database.session() as session:
        row = session.get(Observation, identity)
        assert row.status == 'withdrawn' and row.payload['body'] == '' and row.payload['erased'] is True
        author = session.get(User, row.author_id)
        assert author.role == 'disabled' and author.username.startswith('deleted_')
        assert not list(session.scalars(select(LoginSession).where(LoginSession.user_id == author.id)))
    login(client, 'other')
    assert len(client.get('/api/account/export').json()['observations']) == 1
