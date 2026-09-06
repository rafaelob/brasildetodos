"""Synthetic strings matching the observed 5120-character PNCP failure; no raw source copy."""
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from bdt.api import create_app
from bdt.evidence import MAX_PNCP_OBJECT_CHARS, ResourceInput
from bdt.resource_profiles import normalize_resource
from bdt.resource_sync import import_resources
from bdt.resource_diagnostics import ResourceTextError
from test_resource_sync import contract, source, PNCP, save_collection, current


@pytest.mark.parametrize('length',[4000,4001,5120,MAX_PNCP_OBJECT_CHARS])
def test_pncp_long_object_preserved_exactly(length):
    text='Objeto sintético — '+('A'*(length-len('Objeto sintético — ')))
    obj=normalize_resource(PNCP,contract(objetoContrato=text),source(),{'1234567':('Test','BA')})
    assert obj.title==text and len(obj.title)==length
    assert ResourceInput.model_validate(obj.model_dump()).title==text


@pytest.mark.parametrize('length',[MAX_PNCP_OBJECT_CHARS+1,100000])
def test_bounded_budget_has_structural_error_and_no_silent_truncation(length):
    with pytest.raises(ResourceTextError) as caught:
        normalize_resource(PNCP,contract(objetoContrato='X'*length),source(),{'1234567':('Test','BA')})
    assert caught.value.public_diagnostic()['accepted_limit']==MAX_PNCP_OBJECT_CHARS
    assert caught.value.length==length


@pytest.mark.parametrize('change',[{'kind':'proposal'}, {'attributes':{}},
    {'attributes':{'profile':'obrasgov_projects'}}, {'source':source('other_source').model_dump()}])
def test_other_profiles_keep_previous_limit(change):
    obj=normalize_resource(PNCP,contract(objetoContrato='X'*5120),source(),{'1234567':('Test','BA')})
    with pytest.raises(ValidationError,match='resource_title_profile_limit'):
        ResourceInput.model_validate(obj.model_dump()|change)


def test_other_pncp_fields_do_not_inherit_object_budget():
    with pytest.raises(ResourceTextError) as caught:
        normalize_resource(PNCP,contract(numeroContratoEmpenho='X'*4001),source(),{'1234567':('Test','BA')})
    assert caught.value.field=='numeroContratoEmpenho' and caught.value.limit==4000


def test_long_object_import_idempotent_api_and_export(database,tmp_path):
    from bdt.resource_export import snapshot,render
    root=tmp_path/'records';text='SYNTHETIC '+('Á'*5110)
    save_collection(root,[contract(objetoContrato=text)])
    assert import_resources(database,root)['created']==1
    assert import_resources(database,root)['unchanged']==1
    item=current(database)[0]
    assert item['title']==text
    report=snapshot(database,item['id'])
    assert report['resource']['title']==text
    for fmt in ('json','text','csv'):
        assert text in render(report,fmt)[0]
    app=create_app(str(database.engine.url),testing=True)
    with TestClient(app) as client:
        assert client.get('/api/resources').json()['items'][0]['title']==text
        assert client.get('/api/resource-history/'+item['id']).json()['total']==1


def test_long_object_is_versioned_not_overwritten(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    save_collection(a,[contract(objetoContrato='A'*5120)])
    import_resources(database,a)
    save_collection(b,[contract(objetoContrato='B'*5120,dataAtualizacao='2026-09-05T12:00:00')])
    assert import_resources(database,b)['updated']==1
    from bdt.resource_export import snapshot
    key=contract()['numeroControlePNCP']
    assert snapshot(database,PNCP+':'+key,1)['resource']['title']=='A'*5120


def test_oversized_record_preserves_previous_committed_state(database,tmp_path):
    a,b=tmp_path/'a',tmp_path/'b'
    save_collection(a,[contract(objetoContrato='A'*5120)]);import_resources(database,a)
    previous=deepcopy(current(database))
    save_collection(b,[contract(2),contract(3,objetoContrato='X'*(MAX_PNCP_OBJECT_CHARS+1))])
    with pytest.raises(ResourceTextError):import_resources(database,b)
    assert current(database)==previous
