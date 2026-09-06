"""Municipal journeys use synthetic, isolated records; no production seed."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from bdt.api import create_app
from bdt.domain import MoneyEvent, digest
from bdt.evidence import Resource
from bdt.regions import directory, _public_source
from bdt.storage import Finance, Municipality, Place, upsert_place


@pytest.fixture
def client(database, monkeypatch, tmp_path):
    monkeypatch.setenv('BDT_DATA_DIR', str(tmp_path / 'private'))
    monkeypatch.setenv('BDT_STATIC_DIR', str(tmp_path / 'no-web'))
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        yield client


def test_real_app_registers_routes_once(client):
    for path in ('/api/territories/search', '/api/territories/{municipality_id}/summary'):
        assert sum(route.path == path for route in client.app.routes) == 1
    assert client.get('/api/territories/search').json()['total'] == 1


def test_accent_search_includes_empty_municipalities(database, source, client):
    with database.session() as session:
        for identifier, name, state in [('2222222', 'São José', 'SC'), ('3333333', 'SÃO LUÍS', 'MA'),
                                         ('4444444', 'São José', 'SP'), ('5555555', 'Cidade 100%', 'BA')]:
            session.add(Municipality(id=identifier, name=name, state=state, source=source.model_dump()))
    result = client.get('/api/territories/search?q=sao&limit=2').json()
    assert result['total'] == 3 and result['has_more']
    assert [row['id'] for row in result['items']] == ['2222222', '4444444']
    assert client.get('/api/territories/search?q=SÃO&page=2&limit=2').json()['items'][0]['id'] == '3333333'
    assert client.get('/api/territories/search?q=sao&state=SP').json()['total'] == 1
    assert client.get('/api/territories/search?q=22222').json()['total'] == 1
    assert client.get('/api/territories/search?q=%25').json()['total'] == 1
    assert client.get('/api/territories/search?q=_').json()['total'] == 0
    assert client.get('/api/territories/search?q=sao&page=99999').json()['items'] == []
    assert result['national_coverage_certified'] is False


@pytest.mark.parametrize('query', ['limit=0', 'limit=101', 'page=0', 'page=100001', 'state=ZZ', 'q='+'x'*201])
def test_directory_filters_fail_explicitly(client, query):
    assert client.get('/api/territories/search?'+query).status_code == 422


@pytest.mark.parametrize('identifier,status', [('123',422), ('abcdefg',422), ('9999999',404)])
def test_context_identity_validation(client, identifier, status):
    assert client.get(f'/api/territories/{identifier}/summary').status_code == status


def test_context_has_real_zero_not_fake_completeness(client):
    result = client.get('/api/territories/1234567/summary').json()
    assert result['service_records'] == result['resource_records'] == 0
    assert result['sources'] == []
    assert len(result['services']) == 3
    assert result['municipality']['source']['dataset'] == 'synthetic'
    assert not result['national_coverage_certified']
    assert not result['financial_total_computed']


def test_context_separates_buyer_from_execution_and_never_sums_money(database, source, place, client):
    with database.session() as session:
        upsert_place(session, place)
        upsert_place(session, place.model_copy(update={'id':'test:health','kind':'health','latitude':-12.9,
            'longitude':-38.5,'geo_source':'synthetic'}))
        upsert_place(session, place.model_copy(update={'id':'test:excluded','catalogue_eligible':False}))
        for identifier, municipality, dataset, basis in [
            ('r:buyer','1234567','pncp_contracts','buyer_registered_municipality_not_execution'),
            ('r:territory','1234567','obrasgov_projects','reviewed_municipal_reference'),
            ('r:unresolved',None,'obrasgov_projects','municipality_unknown')]:
            session.add(Resource(id=identifier,kind='contract',title='TEST only project',municipality_id=municipality,
                source=source.model_copy(update={'dataset':dataset}).model_dump(),
                payload={'attributes':{'territorial_basis':basis,'private':'NEVER_EXPOSE'}, 'secret':'NEVER_EXPOSE'}))
        item=MoneyEvent(id='synthetic:payment',source=source,municipality_id='1234567',instrument_id='X',
            phase='paid',cents=123456789,period='2025',recipient='PRIVATE TEST RECIPIENT',perspective='municipal')
        session.add(Finance(key=digest([source.dataset,item.id]),municipality_id='1234567',
            cents=item.cents,payload=item.model_dump(mode='json')))
    result=client.get('/api/territories/1234567/summary')
    data=result.json()
    assert data['service_records']==2 and data['resource_records']==2
    assert data['services'][0]['without_geometry']==1
    assert data['services'][1]['with_geometry']==1
    assert data['financial_event_groups']==[{'phase':'paid','records':1}]
    assert {'source_id':'pncp','territorial_basis':'buyer_registered_municipality','records':1} in data['resource_groups']
    assert all(secret not in result.text for secret in ['NEVER_EXPOSE','PRIVATE TEST RECIPIENT','123456789'])
    assert data['facility_assignment_inferred'] is False


def test_source_projection_minimizes_legacy_fields(source):
    assert _public_source(source.model_dump()|{'private':'secret'}) == source.model_dump(mode='json')
    assert _public_source({'broken':True}) is None
    assert _public_source(None) is None


def test_reads_have_no_side_effects_and_bounded_query_count(database, client):
    before={table.name:None for table in Place.metadata.sorted_tables}
    with database.engine.connect() as connection:
        for table in Place.metadata.sorted_tables:
            before[table.name]=connection.scalar(select(func.count()).select_from(table))
    queries=[]
    def collect(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            queries.append(statement)
    event.listen(client.app.state.database.engine,'before_cursor_execute',collect)
    assert client.get('/api/territories/1234567/summary').status_code==200
    event.remove(client.app.state.database.engine,'before_cursor_execute',collect)
    assert len(queries)==5
    with database.engine.connect() as connection:
        for table in Place.metadata.sorted_tables:
            assert before[table.name]==connection.scalar(select(func.count()).select_from(table))


def test_budget_failure_is_not_a_partial_directory(database, client, monkeypatch):
    monkeypatch.setattr('bdt.regions.DIRECTORY_BUDGET',0)
    result=client.get('/api/territories/search')
    assert result.status_code==503 and result.json()['detail']=='municipality_directory_unavailable'


@pytest.mark.parametrize('kwargs',[{'state':'ZZ'},{'page':0},{'limit':101},{'q':'x'*201}])
def test_internal_validation(database, kwargs):
    with pytest.raises(ValueError):
        directory(database,**kwargs)
