"""Exercise the actual app factory, not test-only route registration."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.api import create_app
from bdt.storage import Ingestion, User, LoginSession, Observation, Change

@pytest.fixture
def public_client(database):
    with TestClient(create_app(str(database.engine.url), testing=True)) as client:
        yield client


def test_routes_are_registered_once_and_documented(public_client):
    paths=public_client.get('/api/openapi.json').json()['paths']
    for path,method in [('/api/coverage','get'),('/api/imports','get'),('/api/saved-places/summary','post')]:
        assert method in paths[path]
        assert sum(route.path==path for route in public_client.app.routes)==1


def test_public_coverage_does_not_copy_legacy_ingestion_payload(public_client, database, stored):
    with database.session() as session:
        session.add(Ingestion(dataset='cnes-national-bulk', status='failed',
            source={'url':'https://example.org/private','token':'PRIVATE_TEST'},
            counts={'read':3,'created':2,'raw':'PRIVATE_TEST'},error='PRIVATE_TEST'))
    coverage=public_client.get('/api/coverage')
    history=public_client.get('/api/imports?source=cnes&status=failed')
    assert coverage.status_code==history.status_code==200
    assert 'PRIVATE_TEST' not in coverage.text+history.text
    assert 'https://example.org/private' not in coverage.text+history.text
    assert coverage.json()['summary']['places']==1
    assert history.json()['items'][0]['counts']['created']==0
    assert coverage.headers['Cache-Control']=='no-store'


def test_summary_requires_existing_request_header_and_does_not_create_user(public_client,database,stored):
    request={'place_ids':[stored.id]}
    assert public_client.post('/api/saved-places/summary',json=request).status_code==403
    response=public_client.post('/api/saved-places/summary',json=request,headers={'X-BDT-Client':'web'})
    assert response.status_code==200
    assert response.json()['favorites_persisted'] is False
    assert 'set-cookie' not in response.headers
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(User))==0
        assert session.scalar(select(func.count()).select_from(LoginSession))==0
        assert session.scalar(select(func.count()).select_from(Observation))==0
        assert session.scalar(select(func.count()).select_from(Change))==1

@pytest.mark.parametrize('query',['source=bogus','status=bogus','page=0','limit=51','page=10001'])
def test_public_import_filters_are_bounded(public_client,query):
    assert public_client.get('/api/imports?'+query).status_code==422


def test_tracking_request_is_not_echoed_by_validation(public_client):
    response=public_client.post('/api/saved-places/summary',headers={'X-BDT-Client':'web'},json={'place_ids':['PRIVATE_BAD_ID']})
    assert response.status_code==422
    assert 'PRIVATE_BAD_ID' not in response.text
