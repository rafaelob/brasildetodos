"""Synthetic artifacts in temporary folders; real database transaction/API tests."""
import hashlib
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.api import create_app
from bdt.domain import Source, now
from bdt.evidence import Resource
from bdt.resource_profiles import normalize_resource
from bdt.resource_release import install_resource_release,main
from bdt.resource_sync import ResourceRevision
from bdt.storage import Ingestion,User,Finance,Observation


def records():
    source=Source(dataset='test',url='https://pncp.gov.br/api/consulta/v1/contratos?pagina=1',record_id='fixture',reference_date=None,collected_at='2026-09-06T12:00:00Z',snapshot_sha256='a'*64)
    raw={'numeroControlePNCP':'12345678000199-2-000001/2026','orgaoEntidade':{'cnpj':'12345678000199','razaoSocial':'Synthetic buyer'},
        'unidadeOrgao':{'codigoIbge':'1234567','ufSigla':'BA'},'objetoContrato':'Synthetic contract not a real procurement',
        'anoContrato':2026,'sequencialContrato':1,'dataAtualizacao':'2026-09-04T12:00:00','valorInicial':'100.0001','valorGlobal':'200.0123',
        'dataPublicacaoPncp':'2026-09-04T12:00:00','receita':False}
    p=normalize_resource('pncp_contracts',raw,source.model_copy(update={'dataset':'pncp_contracts'}),{'1234567':('Synthetic','BA')})
    source=source.model_copy(update={'dataset':'transferegov_special_plans','url':'https://api-publica.transferegov.gestao.gov.br/especiais/planos-acao-especiais'})
    t=normalize_resource('transferegov_special_plans',{'id_plano_acao':1,'codigo_plano_acao':'SYNTHETIC-1','ano_plano_acao':2026,'id_beneficiario':1,'id_programa':1,'valor_custeio_plano_acao':'25.00','valor_investimento_plano_acao':'50.00'},source,{})
    return [p.model_dump(mode='json'),t.model_dump(mode='json')]


def package(path,rows):
    path.mkdir()
    data=b''.join((json.dumps(r,ensure_ascii=False)+'\n').encode() for r in rows)
    digest=hashlib.sha256(data).hexdigest()
    profiles={p:sum(r['source']['dataset']==p for r in rows) for p in {r['source']['dataset'] for r in rows}}
    report=json.dumps({'status':'passed','resources':len(rows),'by_profile':profiles,'resources_sha256':digest}).encode()
    (path/'resources.jsonl').write_bytes(data);(path/'report.json').write_bytes(report)
    return {'report_sha256':hashlib.sha256(report).hexdigest(),'resources_sha256':digest}


def totals(db):
    with db.session() as s:
        return tuple(s.scalar(select(func.count()).select_from(t)) for t in (Resource,ResourceRevision,Finance,User,Observation))


def test_install_replay_history_api_and_private_data_unchanged(database,tmp_path):
    path=tmp_path/'release';pins=package(path,records())
    with database.session() as s:s.add(User(username='private-synthetic',role='contributor',password_hash='not-a-login'))
    result=install_resource_release(database,path,**pins)
    assert result['records']==2 and result['subcent_records']==1 and result['subcent_fields']==2
    assert result['financial_events_created']==0 and result['automatic_place_links']==0
    assert result['historical_ledger_imported'] is False and result['public_deployment'] is False
    assert totals(database)==(2,2,0,1,0)
    replay=install_resource_release(database,path,**pins)
    assert all(c['unchanged']==c['read'] for c in replay['by_profile'].values())
    assert totals(database)==(2,2,0,1,0)
    app=create_app(str(database.engine.url),testing=True)
    with TestClient(app) as client:
        assert client.get('/api/resources').json()['total']==2
        item=client.get('/api/resource-export/'+records()[0]['id']).json()
        assert item['revision']==1 and item['resource']['amounts'][0]['decimal']=='100.0001'
        assert client.get('/api/workbench/documents').status_code==401
        assert 'private-synthetic' not in client.get('/api/resources').text
        assert client.get('/api/resource-coverage').status_code==200


def test_changed_version_requires_newer_clock_and_preserves_original(database,tmp_path):
    original=records();pins=package(tmp_path/'first',original)
    install_resource_release(database,tmp_path/'first',**pins)
    updated=records();updated[0]['title']='Updated synthetic contract'
    updated[0]['attributes']['upstream_updated_at']='2026-09-05T12:00:00'
    updated[0]['source']['reference_date']='2026-09-05T12:00:00'
    pins2=package(tmp_path/'second',updated)
    result=install_resource_release(database,tmp_path/'second',**pins2)
    assert result['by_profile']['pncp_contracts']['updated']==1
    assert totals(database)[:2]==(2,3)
    with database.session() as s:
        versions=list(s.scalars(select(ResourceRevision).where(ResourceRevision.resource_id==original[0]['id']).order_by(ResourceRevision.revision)))
        assert versions[0].payload['title']==original[0]['title']
        assert versions[1].payload['title']==updated[0]['title']
    with pytest.raises(ValueError,match='stale_or_conflicting'):install_resource_release(database,tmp_path/'first',**pins)
    assert totals(database)[:2]==(2,3)


def test_invalid_late_row_rolls_back_entire_release(database,tmp_path):
    rows=records();rows[1]['attributes']['facility_id']='test:school'
    pins=package(tmp_path/'bad',rows)
    with pytest.raises(ValueError,match='financial_or_facility'):install_resource_release(database,tmp_path/'bad',**pins)
    assert totals(database)[:2]==(0,0)
    with database.session() as s:
        attempts=list(s.scalars(select(Ingestion)))
        assert len(attempts)==2 and all(a.status=='failed' and a.counts['published']==0 for a in attempts)


@pytest.mark.parametrize('which',['report_sha256','resources_sha256'])
def test_external_pin_is_mandatory_and_checked_before_install(database,tmp_path,which):
    pins=package(tmp_path/'data',records());pins[which]='b'*64
    with pytest.raises(ValueError,match='external_hash'):install_resource_release(database,tmp_path/'data',**pins)
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Ingestion))==0


@pytest.mark.parametrize('hashvalue',['','main','a'*63,'g'*64])
def test_pin_format(database,tmp_path,hashvalue):
    pins=package(tmp_path/'data',records());pins['report_sha256']=hashvalue
    with pytest.raises(ValueError,match='sha256_required'):install_resource_release(database,tmp_path/'data',**pins)


@pytest.mark.parametrize('change',[
 lambda x:x.update(kind='work'),
 lambda x:x['source'].update(record_id='different'),
 lambda x:x['attributes'].update(unreviewed_secret='not-public'),
 lambda x:x['attributes'].update(buyer_name={'unexpected':'object'}),
 lambda x:x['attributes'].update(state='AC'),
 lambda x:x['attributes'].update(version_basis='collection_snapshot'),
 lambda x:x['attributes'].update(source_control_number='different'),
 lambda x:x['attributes'].update(upstream_updated_at=None),
 lambda x:x['attributes'].update(territorial_basis='facility'),
 lambda x:x['attributes'].update(financial_interpretation='paid'),
 lambda x:x['attributes'].update(precise_amounts={'unexpected':'1.0001'}),
])
def test_reviewed_shape_and_scope_not_relaxed(database,tmp_path,change):
    rows=records();change(rows[0]);pins=package(tmp_path/'data',rows)
    with pytest.raises((ValueError,TypeError)):install_resource_release(database,tmp_path/'data',**pins)
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Resource))==0


def test_no_assignment_of_unresolved_plan_territory(database,tmp_path):
    rows=records();rows[1]['municipality_id']='1234567';pins=package(tmp_path/'data',rows)
    with pytest.raises(ValueError,match='unresolved_territory'):install_resource_release(database,tmp_path/'data',**pins)
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Resource))==0


def test_existing_ledger_conflict_is_not_overwritten(database,tmp_path):
    pins=package(tmp_path/'data',records());install_resource_release(database,tmp_path/'data',**pins)
    with database.session() as s:s.get(Resource,records()[0]['id']).title='Corrupted synthetic column'
    with pytest.raises(ValueError,match='ledger_conflict'):install_resource_release(database,tmp_path/'data',**pins)
    assert totals(database)[:2]==(2,2)


def test_empty_release_does_not_remove_existing_records(database,tmp_path):
    pins=package(tmp_path/'data',records());install_resource_release(database,tmp_path/'data',**pins)
    pins=package(tmp_path/'empty',[]);r=install_resource_release(database,tmp_path/'empty',**pins)
    assert r['records']==0 and r['removed']==0 and totals(database)[:2]==(2,2)


def test_cli_evidence_exclusive_and_failure_sanitized(database,tmp_path,monkeypatch,capsys):
    path=tmp_path/'data';pins=package(path,records());monkeypatch.setenv('BDT_DATABASE_URL',str(database.engine.url))
    out=tmp_path/'receipt.json'
    args=[str(path),'--report-sha256',pins['report_sha256'],'--resources-sha256',pins['resources_sha256'],'--output',str(out)]
    assert main(args)==0
    assert json.loads(out.read_text())['records']==2
    with pytest.raises(FileExistsError):main(args)
    args[-1]=str(tmp_path/'failed.json');args[2]='b'*64
    assert main(args)==1
    assert json.loads((tmp_path/'failed.json').read_text())=={'status':'failed','error_type':'ValueError','reason':'resource_release_requires_review','public_deployment':False}
    assert str(database.engine.url) not in capsys.readouterr().out
