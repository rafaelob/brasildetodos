"""Synthetic metadata with official field names; never production fixture data."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.domain import Source, digest
from bdt.evidence import Resource, initialize_extensions
from bdt.resource_profiles import collection_plan, normalize_resource, money
from bdt.resource_sync import (ResourceRevision, decode, import_resources, semantic,
                               changed_fields, _newer, main)
from bdt.storage import Finance, Ingestion
from bdt.sync import collect, atomic_json, page_url

PNCP = 'pncp_contracts'
PLAN = 'transferegov_special_plans'
WORK = 'obrasgov_projects'
DATE = '2026-09-04T12:00:00'
COLLECTED = '2026-09-06T04:00:00+00:00'


def contract(number=1, **updates):
    return {'numeroControlePNCP': f'12345678000199-2-{number:06}/2026',
        'anoContrato': 2026, 'sequencialContrato': number,
        'orgaoEntidade': {'cnpj': '12345678000199', 'razaoSocial': 'Synthetic public purchaser'},
        'unidadeOrgao': {'codigoIbge': '1234567', 'ufSigla': 'BA'},
        'objetoContrato': 'SYNTHETIC public resource', 'dataAtualizacao': DATE,
        'dataPublicacaoPncp': DATE, 'valorInicial': '100.01', 'valorGlobal': '150.02',
        'valorAcumulado': None, 'receita': False,
        'dataVigenciaInicio': '2026-09-04', 'dataVigenciaFim': '2027-09-04',
        'niFornecedor': 'CPF-MUST-NOT-BE-COPIED', 'nomeRazaoSocialFornecedor': 'PRIVATE SUPPLIER',
        **updates}


def action_plan(**updates):
    return {'id_plano_acao': 101, 'codigo_plano_acao': '09042026-0001', 'ano_plano_acao': 2026,
        'id_beneficiario': 22, 'id_programa': 10, 'nome_objeto': 'SYNTHETIC action plan',
        'situacao_plano_acao': 'Em análise', 'valor_custeio_plano_acao': Decimal('300.20'),
        'valor_investimento_plano_acao': Decimal('500.01'),
        'email': 'private@example.org', 'numero_conta': 'PRIVATE', **updates}


def project(**updates):
    return {'id_projeto_investimento': 'abc-1', 'desc_nome': 'SYNTHETIC investment project',
        'situacao': 'Em execução', 'uf_principal': 'BA', 'ano_cadastro': 2026,
        'investimentos_previstos': [{'vl_investimento_previsto': Decimal('50.01'),
                                    'desc_nome_fonte_recurso': 'SYNTHETIC'}],
        'pins': [{'latitude': '-10', 'longitude': '-40'}], **updates}


def source(profile=PNCP):
    return Source(dataset=profile, url='https://pncp.gov.br/api/consulta/v1/contratos',
        record_id='collection', reference_date=None, collected_at=COLLECTED, snapshot_sha256='a'*64)


def plan(profile=PNCP, **kwargs):
    return collection_plan(profile, **({'start':'20260904','end':'20260904'} if profile==PNCP else {}), **kwargs)


def save_collection(root, rows, *, profile=PNCP, timestamp=COLLECTED, options=None):
    p = plan(profile, **(options or {}))
    pages = [rows[n:n+p.page_size] for n in range(0, len(rows), p.page_size)] or [[]]
    def loader(url, path, max_bytes):
        index = int(path.stem.split('-')[-1])
        payload = {'data': pages[index], p.total_pages_field: len(pages),
                   p.total_records_field: len(rows), p.response_page_field: index+1}
        # Serialize Decimal as JSON numbers exactly, not floats. Test values are
        # serialized as decimal strings as also accepted by these profiles.
        raw = json.dumps(payload, default=str, ensure_ascii=False).encode()
        path.write_bytes(raw)
        return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'collected_at': timestamp}
    return collect(p, root, loader=loader, sleep=lambda _: None)


def current(database):
    with database.session() as session:
        return [deepcopy(row.payload) for row in session.scalars(select(Resource).order_by(Resource.id))]


def test_precise_json_numeric_values_not_binary_float():
    data = decode(b'{"valorInicial": 90071992547409.91, "tiny":0.01}')
    assert money(data['valorInicial']) == 9_007_199_254_740_991
    assert money(data['tiny']) == 1


@pytest.mark.parametrize('raw',[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}',b'{"a":-Infinity}'])
def test_json_refuses_ambiguity(raw):
    with pytest.raises(ValueError):decode(raw)


@pytest.mark.parametrize('value',[True,1.01,Decimal('0.001'),Decimal('NaN'),Decimal('Infinity'),'-0.01','90071992547409.92','bad'])
def test_money_refuses_ambiguous_or_unsafe_values(value):
    with pytest.raises(ValueError):money(value)


@pytest.mark.parametrize('profile,row,kind',[(PNCP,contract(),'contract'),(PLAN,action_plan(),'proposal'),(WORK,project(),'work')])
def test_profiles_do_not_infer_payment_or_facility(profile,row,kind):
    result = normalize_resource(profile,row,source(profile),{'1234567':('Synthetic','BA')})
    assert result.kind == kind
    payload=result.model_dump(mode='json')
    assert payload['attributes']['financial_interpretation']=='not_payment'
    assert payload['attributes']['facility_id'] is None
    assert 'PRIVATE' not in json.dumps(payload)
    assert 'pins' not in payload['attributes']
    assert result.municipality_id == ('1234567' if profile==PNCP else None)


def test_pncp_identity_and_exact_publisher_field_casing():
    body=normalize_resource(PNCP,contract(numeroControlePncpCompra='12345678000199-1-000001/2026'),source(),{'1234567':('Test','BA')})
    assert body.attributes['purchase_control_number']=='12345678000199-1-000001/2026'
    assert body.attributes['initial_cents']==10001
    assert body.attributes['global_cents']==15002
    assert body.attributes['budget_direction']=='expense'
    assert body.attributes['territorial_basis']=='buyer_registered_municipality_not_execution'
    revenue=normalize_resource(PNCP,contract(receita=True),source(),{'1234567':('Test','BA')})
    assert revenue.attributes['budget_direction']=='revenue'


@pytest.mark.parametrize('changes',[
    {'anoContrato':2025},{'sequencialContrato':2},{'orgaoEntidade':{'cnpj':'00000000000100'}},
    {'dataAtualizacao':None},{'valorInicial':None},{'dataAssinatura':'2026-02-31'},
    {'dataAtualizacao':'not a date'},{'receita':'false'},
    {'unidadeOrgao':{'codigoIbge':'9999999','ufSigla':'BA'}},
    {'unidadeOrgao':{'codigoIbge':'1234567','ufSigla':'SP'}},
])
def test_pncp_profile_rejects_conflicts(changes):
    with pytest.raises(ValueError):normalize_resource(PNCP,contract(**changes),source(),{'1234567':('Test','BA')})


@pytest.mark.parametrize('profile,kwargs',[(PNCP,{'start':'2026-09-04','end':'20260904'}),
    (PNCP,{'start':'20260905','end':'20260904'}),(PNCP,{'start':'20260101','end':'20260301'}),
    (PNCP,{'start':'20260904','end':'20260904','page_size':501}),(PLAN,{'page_size':201}),
    (WORK,{'year':True}),(PLAN,{'updates':True}),('not-real',{})])
def test_reviewed_collection_bounds(profile,kwargs):
    with pytest.raises(ValueError):collection_plan(profile,**kwargs)


def test_three_profiles_have_real_pagination_names():
    assert plan().total_pages_field=='totalPaginas'
    assert plan().size_parameter=='tamanhoPagina'
    for profile in (PLAN,WORK):
        p=plan(profile,year=2026,identity='123')
        assert p.total_pages_field=='total_pages'
        assert p.size_parameter=='tamanho_da_pagina'
    assert plan(updates=True).url.endswith('/contratos/atualizacao')


def test_atomic_import_and_repeated_collection_are_idempotent(database,tmp_path):
    folder=tmp_path/'collection';save_collection(folder,[contract()])
    first=import_resources(database,folder);second=import_resources(database,folder)
    assert first['created']==1 and second['unchanged']==1
    assert not first['national_catalog_certified']
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ResourceRevision))==1
        assert session.scalar(select(func.count()).select_from(Finance))==0
    assert first['automatic_place_links']==0


def test_versions_preserve_previous_value_and_exact_evidence(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    save_collection(a,[contract()]);import_resources(database,a)
    original=current(database)[0]
    save_collection(b,[contract(valorGlobal='200.00',dataAtualizacao='2026-09-05T12:00:00')])
    result=import_resources(database,b)
    assert result['updated']==1
    with database.session() as session:
        rows=session.scalars(select(ResourceRevision).order_by(ResourceRevision.revision)).all()
        assert len(rows)==2 and rows[0].payload==original
        assert rows[1].payload['attributes']['global_cents']==20000
        assert 'attributes.global_cents' in rows[1].changed_fields
        assert rows[0].payload['source']['snapshot_sha256']!=rows[1].payload['source']['snapshot_sha256']


@pytest.mark.parametrize('date',['2026-09-03T12:00:00',DATE])
def test_stale_or_same_version_conflict_rolls_back_whole_query(database,tmp_path,date):
    a,b=tmp_path/'a',tmp_path/'b';save_collection(a,[contract()]);import_resources(database,a)
    original=current(database)
    save_collection(b,[contract(2),contract(valorGlobal='300.00',dataAtualizacao=date)])
    with pytest.raises(ValueError,match='stale_or_conflicting'):import_resources(database,b)
    assert current(database)==original
    with database.session() as session:
        failed=session.scalar(select(Ingestion).where(Ingestion.status=='failed'))
        assert failed.counts['published']==0 and failed.counts['rolled_back']


def test_collection_change_does_not_create_artificial_history(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';save_collection(a,[contract()]);import_resources(database,a)
    original=current(database)
    save_collection(b,[contract()],timestamp='2026-09-07T04:00:00+00:00')
    assert import_resources(database,b)['unchanged']==1
    assert current(database)==original


def test_snapshot_based_updates_need_later_collection(database,tmp_path):
    a,b,c=tmp_path/'a',tmp_path/'b',tmp_path/'c'
    save_collection(a,[action_plan()],profile=PLAN);import_resources(database,a)
    save_collection(b,[action_plan(valor_custeio_plano_acao='9.00')],profile=PLAN)
    with pytest.raises(ValueError):import_resources(database,b)
    save_collection(c,[action_plan(valor_custeio_plano_acao='9.00')],profile=PLAN,timestamp='2026-09-07T04:00:00+00:00')
    assert import_resources(database,c)['updated']==1
    assert current(database)[0]['source']['reference_date']=='2026'


def test_missing_row_is_not_a_deletion(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';save_collection(a,[contract(),contract(2)]);import_resources(database,a)
    save_collection(b,[contract()]);assert import_resources(database,b)['removed']==0
    assert len(current(database))==2


def test_verified_empty_query_keeps_prior_records(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';save_collection(a,[contract()]);import_resources(database,a)
    save_collection(b,[]);assert import_resources(database,b)['read']==0
    assert len(current(database))==1


@pytest.mark.parametrize('mutate',[
    lambda r:r.update(status='partial_budget'),
    lambda r:r.update(plan_sha256='f'*64),
    lambda r:r.update(records=200),
    lambda r:r['pages'][0].update(sha256='f'*64),
    lambda r:r['pages'][0].update(file='../other.json'),
    lambda r:r['pages'][0].update(url='https://example.org/not-the-page'),
    lambda r:r.update(terminal='because_it_looked_complete'),
])
def test_collection_tampering_never_publishes_records(database,tmp_path,mutate):
    folder=tmp_path/'test';report=save_collection(folder,[contract()]);mutate(report)
    atomic_json(folder/'collection.json',report)
    with pytest.raises(ValueError):import_resources(database,folder)
    with database.session() as session:
        # Extensions may not have been created for early-invalid manifests.
        initialize_extensions(database)
        assert session.scalar(select(func.count()).select_from(Resource))==0


def test_query_window_enforced_per_row(database,tmp_path):
    folder=tmp_path/'bad';save_collection(folder,[contract(dataPublicacaoPncp='2026-08-01T00:00:00')])
    with pytest.raises(ValueError,match='requested_dates'):import_resources(database,folder)


def test_unresolved_project_territory_is_not_fabricated(database,tmp_path):
    folder=tmp_path/'works';save_collection(folder,[project()],profile=WORK,options={'year':2026})
    assert import_resources(database,folder)['unresolved_municipality']==1
    assert current(database)[0]['municipality_id'] is None


def test_manual_resource_cannot_be_overwritten_by_import(database,tmp_path):
    initialize_extensions(database)
    body=normalize_resource(PNCP,contract(),source(),{'1234567':('Test','BA')})
    with database.session() as session:
        session.add(Resource(id=body.id,kind=body.kind,title=body.title,municipality_id=body.municipality_id,
            payload=body.model_dump(mode='json'),source=body.source.model_dump()))
    folder=tmp_path/'conflict';save_collection(folder,[contract()])
    with pytest.raises(ValueError,match='not_owned'):import_resources(database,folder)


def test_metadata_clock_keeps_timezone_unknown():
    before=normalize_resource(PNCP,contract(),source(),{'1234567':('Test','BA')}).model_dump(mode='json')
    after=deepcopy(before);after['attributes']['upstream_updated_at']='2026-09-05T00:00:00+00:00'
    with pytest.raises(ValueError,match='incomparable'):_newer(before,after)
    assert changed_fields(None,before)==['initial_import']
    assert changed_fields(before,before)==[]


def test_full_multi_page_query_not_just_first_page(database,tmp_path):
    folder=tmp_path/'multi';save_collection(folder,[contract(n) for n in range(1,24)],options={'page_size':10})
    result=import_resources(database,folder)
    assert result['read']==23 and len(current(database))==23


def test_cli_imports_exact_cached_plan(database,tmp_path,monkeypatch,capsys):
    folder=tmp_path/'cli';save_collection(folder,[contract()])
    monkeypatch.setattr('sys.argv',['resource_sync',PNCP,'--folder',str(folder),'--database-url',str(database.engine.url),
        '--start','20260904','--end','20260904'])
    main()
    assert json.loads(capsys.readouterr().out)['created']==1
    assert (folder/'import-result.json').exists()


def test_public_resource_api_history_and_literal_search(database,tmp_path):
    from bdt.api import create_app
    a,b=tmp_path/'a',tmp_path/'b';save_collection(a,[contract(),contract(2,objetoContrato='SYNTHETIC with 10% provision')])
    import_resources(database,a)
    save_collection(b,[contract(valorGlobal='200.00',dataAtualizacao='2026-09-05T10:00:00')])
    import_resources(database,b)
    with TestClient(create_app(str(database.engine.url),testing=True)) as client:
        result=client.get('/api/resources?profile=pncp_contracts&state=BA&limit=1').json()
        assert result['total']==2 and len(result['items'])==1
        assert client.get('/api/resources?q=10%25').json()['total']==1
        assert client.get('/api/resources?state=SP').json()['total']==0
        assert client.get('/api/resources?profile=invalid').status_code==422
        assert client.get('/api/resources?state=ZZ').status_code==422
        assert client.get('/api/resources?limit=101').status_code==422
        path='/api/resource-history/pncp_contracts:12345678000199-2-000001/2026'
        result=client.get(path+'?limit=1').json()
        assert result['total']==2 and result['versions'][0]['revision']==2
        older=client.get(path+'?page=2&limit=1').json()
        assert older['versions'][0]['resource']['attributes']['global_cents']==15002
        assert not {'author_id','reviewer_id','extraction','password'}.intersection(result)
        assert client.get('/api/resource-history/missing:1').status_code==404
        assert client.get('/api/workbench/documents').status_code==401


def test_obrasgov_physical_execution_and_geometries():
    source_obj = source(WORK)
    proj_row = project(
        perc_execucao_fisica=78.5,
        dt_medicao='2026-08-15',
        pins=[{'latitude': -12.9714, 'longitude': -38.5014, 'tipo_geometria': 'point'}],
    )
    res = normalize_resource(WORK, proj_row, source_obj, {})
    assert res.attributes['physical_execution_percentage'] == 78.5
    assert res.attributes['last_measurement_on'] == '2026-08-15'
    assert res.attributes['project_geometries'] == [{'latitude': -12.9714, 'longitude': -38.5014, 'kind': 'point'}]
    assert res.attributes['territorial_basis'] == 'state_only_municipality_unresolved'


@pytest.mark.parametrize('value', [True, -0.01, 100.01, 'NaN', 'Infinity', 'not-a-number'])
def test_obrasgov_rejects_invalid_physical_execution_percentage(value):
    with pytest.raises(ValueError, match='invalid_physical_execution_percentage'):
        normalize_resource(WORK, project(perc_execucao_fisica=value), source(WORK), {})


def test_obrasgov_preserves_zero_physical_execution_percentage():
    result = normalize_resource(
        WORK,
        project(perc_execucao_fisica=0, percentual_execucao=75),
        source(WORK),
        {},
    )

    assert result.attributes['physical_execution_percentage'] == 0.0


@pytest.mark.parametrize(
    ('field', 'attribute', 'value'),
    [
        ('populacao_beneficiada', 'benefited_population', True),
        ('populacao_beneficiada', 'benefited_population', -1),
        ('populacao_beneficiada', 'benefited_population', 1.5),
        ('qtd_empregos_gerados', 'jobs_generated', True),
        ('qtd_empregos_gerados', 'jobs_generated', -1),
        ('qtd_empregos_gerados', 'jobs_generated', 1.5),
    ],
)
def test_obrasgov_omits_invalid_optional_nonnegative_counts(field, attribute, value):
    result = normalize_resource(WORK, project(**{field: value}), source(WORK), {})

    assert attribute not in result.attributes
