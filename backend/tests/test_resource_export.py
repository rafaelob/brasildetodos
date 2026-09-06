import csv
import io
import json
import pytest
from fastapi.testclient import TestClient
from bdt.api import create_app
from bdt.domain import digest
from bdt.evidence import Resource
from bdt.resource_export import public_resource, render, snapshot, csv_cell
from bdt.resource_sync import import_resources
from test_resource_sync import contract, save_collection


@pytest.fixture
def resource(database, tmp_path):
    save_collection(tmp_path/'a', [contract(valorInicial='100.0001')])
    import_resources(database,tmp_path/'a')
    return 'pncp_contracts:12345678000199-2-000001/2026'


@pytest.mark.parametrize('locale',['pt-BR','en','es'])
@pytest.mark.parametrize('format',['json','text','csv'])
def test_public_export_api_preserves_precision_and_provenance(database,resource,locale,format):
    with TestClient(create_app(str(database.engine.url),testing=True)) as client:
        response=client.get('/api/resource-export/'+resource,params={'locale':locale,'format':format})
        assert response.status_code==200
        assert '100.0001' in response.text and '0.0001' not in response.headers.get('content-disposition','')
        assert 'snapshot_sha256' in response.text and 'municipality' in response.text
        assert response.headers['cache-control']=='no-store'
        assert response.headers['content-disposition'].startswith('attachment; filename="brasildetodos-resource-')
        assert 'PRIVATE' not in response.text
        if format=='json':
            data=response.json()
            assert data['resource']['amounts'][0]['cents'] is None
            assert data['content_sha256']==digest(data['resource'])
            assert 'sum' not in data['resource'] and data['revision']==1


def test_old_revision_export_stays_immutable(database,tmp_path,resource):
    before=snapshot(database,resource,1)
    save_collection(tmp_path/'b',[contract(valorInicial='200.0002',dataAtualizacao='2026-09-05T12:00:00')])
    import_resources(database,tmp_path/'b')
    assert snapshot(database,resource,1)==before
    latest=snapshot(database,resource)
    assert latest['revision']==2 and latest['resource']['amounts'][0]['decimal']=='200.0002'


def test_projection_does_not_export_unknown_fields(database,resource):
    report=snapshot(database,resource)
    payload={'id':resource,'title':'public','kind':'contract','source':report['resource']['source'],
        'attributes':{'notes':'PRIVATE NOTE','file_path':'PRIVATE PATH','initial_cents':123},
        'raw_document':'PRIVATE TEXT','author':'PRIVATE AUTHOR'}
    result=public_resource(payload)
    assert 'PRIVATE' not in json.dumps(result)
    assert result['amounts'][0]['decimal']=='1.23'


@pytest.mark.parametrize('value',['=1+1',' +1','-1','@a','\t123','\n123','\r123'])
def test_csv_does_not_execute_formula_cells(value):
    assert csv_cell(value).startswith("'")


def test_csv_quotes_and_json_original_remain_distinct(database,resource):
    report=snapshot(database,resource)
    report['resource']['title']='=SUM(1,2)\n"quoted"'
    csv_text,_=render(report,'csv')
    assert ['title',"'=SUM(1,2)\n\"quoted\""] in list(csv.reader(io.StringIO(csv_text.lstrip('\ufeff'))))
    assert json.loads(render(report,'json')[0])['resource']['title']==report['resource']['title']


@pytest.mark.parametrize('params,status',[({'revision':999},404),({'revision':0},422),
    ({'format':'html'},422),({'locale':'other'},422)])
def test_unknown_or_invalid_export_arguments(database,resource,params,status):
    with TestClient(create_app(str(database.engine.url),testing=True)) as client:
        assert client.get('/api/resource-export/'+resource,params=params).status_code==status
        assert client.get('/api/resource-export/unknown').status_code==404


def test_current_ledger_mismatch_refuses_export(database,resource):
    with database.session() as session:
        row=session.get(Resource,resource);row.payload=row.payload|{'title':'UNREVIEWED CHANGE'}
    with TestClient(create_app(str(database.engine.url),testing=True)) as client:
        assert client.get('/api/resource-export/'+resource).status_code==409


@pytest.mark.parametrize('attrs',[{'initial_cents':True},{'initial_cents':-1},
    {'planned_investments':[{'planned_cents':1.2}]},
    {'profile':'pncp_contracts','initial_cents':1,'precise_amounts':{'initial':'0.0001'}}])
def test_invalid_or_conflicting_metadata_is_not_rounded(attrs):
    with pytest.raises(ValueError):public_resource({'attributes':attrs})
