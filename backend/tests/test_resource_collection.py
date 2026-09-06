"""Deterministic public collection contracts, distinct from official-source replay."""
import csv
import hashlib
import io
import json
from copy import deepcopy
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from bdt.evidence import Resource
from bdt.resource_routes import install, browse
from bdt.resource_collection import collection, render
from bdt.resource_sync import import_resources, ResourceRevision
from test_resource_sync import contract, save_collection

@pytest.fixture
def client(database):
    app=FastAPI();install(app,database)
    with TestClient(app) as client:yield client

def seed(database,tmp_path,rows=None):
    save_collection(tmp_path/'records', rows or [contract(valorInicial='100.0001')])
    import_resources(database,tmp_path/'records')

@pytest.mark.parametrize('locale',['pt-BR','en','es'])
@pytest.mark.parametrize('format',['json','text','csv'])
def test_public_collection_formats_exact_and_traceable(client,database,tmp_path,locale,format):
    seed(database,tmp_path)
    response=client.get('/api/resource-collection-export',params={'format':format,'locale':locale})
    assert response.status_code==200 and '100.0001' in response.text and 'PRIVATE' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-content-sha256']==hashlib.sha256(response.content).hexdigest()
    if format=='json':
        data=response.json();assert data['total']==data['included']==1 and not data['truncated']
        assert data['records'][0]['resource']['amounts'][0]['decimal']=='100.0001'
        assert data['records'][0]['revision']==1
    if format=='csv':
        rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
        assert len(rows)==1 and json.loads(rows[0]['amounts_json'])[0]['decimal']=='100.0001'


def test_same_literal_filters_and_explicit_bound(client,database,tmp_path):
    seed(database,tmp_path,[contract(i,objetoContrato=f'SYNTHETIC {i}%') for i in range(1,104)])
    query={'q':'%','state':'BA','profile':'pncp_contracts','municipality_id':'1234567','kind':'contract'}
    data=client.get('/api/resource-collection-export',params=query).json()
    assert data['total']==browse(database,**query)['total']==103
    assert data['included']==100 and data['truncated']
    assert len({r['resource']['id'] for r in data['records']})==100
    assert client.get('/api/resource-collection-export?state=SP').json()['total']==0


def test_empty_csv_preserves_context(client):
    response=client.get('/api/resource-collection-export?format=csv&q=absent')
    rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
    assert rows[0]['total']=='0' and rows[0]['notice'] and json.loads(rows[0]['filters_json'])=={'q':'absent'}

@pytest.mark.parametrize('params',[{'limit':0},{'limit':101},{'locale':'fr'},{'format':'xml'},{'q':'a'*201},
    {'profile':'internal'},{'state':'ZZ'},{'municipality_id':'12'},{'kind':'user'}])
def test_invalid_queries_do_not_export(client,params):
    assert client.get('/api/resource-collection-export',params=params).status_code==422


def test_current_and_immutable_version_must_agree(client,database,tmp_path):
    seed(database,tmp_path)
    with database.session() as session:
        row=session.scalar(select(Resource));row.payload=deepcopy(row.payload)|{'title':'UNVERIFIED CHANGE'}
    assert client.get('/api/resource-collection-export').status_code==409


def test_corrupt_revision_is_not_silently_exported(client,database,tmp_path):
    seed(database,tmp_path)
    with database.session() as session:
        row=session.scalar(select(ResourceRevision));row.fingerprint='b'*64
    assert client.get('/api/resource-collection-export').status_code==409


def test_unknown_fields_do_not_enter_export(client,database,tmp_path):
    seed(database,tmp_path)
    with database.session() as session:
        row=session.scalar(select(Resource));version=session.scalar(select(ResourceRevision))
        # Simulate extra private bookkeeping outside the immutable public semantic state.
        # Projection itself is tested directly; ledger integrity must still be enforced.
        from bdt.resource_export import public_resource
        value=deepcopy(row.payload);value['attributes']['private_note']='PRIVATE';value['raw']='PRIVATE'
        assert 'PRIVATE' not in json.dumps(public_resource(value))
    assert client.get('/api/resource-collection-export').status_code==200


def test_no_false_zero_or_rounded_value(client,database,tmp_path):
    seed(database,tmp_path)
    with database.session() as session:
        row=session.scalar(select(Resource));version=session.scalar(select(ResourceRevision))
        data=deepcopy(row.payload);data['attributes']['initial_cents']=True
        from bdt.domain import digest
        from bdt.resource_sync import semantic
        row.payload=data;version.payload=data;version.fingerprint=digest(semantic(data))
    assert client.get('/api/resource-collection-export').status_code==409


def test_no_versions_has_explicit_unversioned_record(client,database,tmp_path):
    seed(database,tmp_path)
    with database.session() as session:
        session.delete(session.scalar(select(ResourceRevision)))
    result=client.get('/api/resource-collection-export').json()
    assert result['records'][0]['revision'] is None


def test_direct_options(database):
    with pytest.raises(ValueError):collection(database,locale='fr')
    with pytest.raises(ValueError):collection(database,limit=True)
    with pytest.raises(ValueError):render(collection(database),'xml')
