"""Short published objects are not invented, discarded or treated as detailed descriptions."""
import pytest
from pydantic import ValidationError
from bdt.evidence import ResourceInput
from bdt.resource_profiles import normalize_resource
from bdt.resource_sync import import_resources
from bdt.resource_validation import validate_collection
from bdt.resource_export import snapshot
from test_resource_sync import contract, source, PNCP, save_collection, current


@pytest.mark.parametrize('title',['A','AB','ABC','ABCD'])
def test_nonblank_short_pncp_object_is_preserved_exactly(title):
    item=normalize_resource(PNCP,contract(objetoContrato=title),source(),{'1234567':('Test','BA')})
    assert item.title==title and item.attributes['facility_id'] is None
    assert item.attributes['financial_interpretation']=='not_payment'


@pytest.mark.parametrize('title',[None,'',' ','\n\t'])
def test_short_profile_does_not_accept_missing_or_blank_objects(title):
    with pytest.raises(ValueError):
        normalize_resource(PNCP,contract(objetoContrato=title),source(),{'1234567':('Test','BA')})


@pytest.mark.parametrize('override',[{'kind':'work'},{'attributes':{}},
    {'attributes':{'profile':'obrasgov_projects'}},{'source':source('other').model_dump()}])
def test_other_profiles_keep_five_character_minimum(override):
    body={'id':'pncp_contracts:12345678000199-2-000001/2026','kind':'contract','title':'ABCD',
        'municipality_id':'1234567','source':source().model_dump(),'attributes':{'profile':PNCP}}
    with pytest.raises(ValidationError,match='resource_title_profile_limit'):
        ResourceInput.model_validate(body|override)


def test_short_object_passes_preflight_import_and_exact_export(database,tmp_path):
    folder=tmp_path/'query';save_collection(folder,[contract(objetoContrato='TEST')])
    report=validate_collection(database,folder)
    assert report['invalid']==0 and report['accepted']==1 and report['published']==0
    assert current(database)==[]
    assert import_resources(database,folder)['created']==1
    assert import_resources(database,folder)['unchanged']==1
    row=current(database)[0]
    assert snapshot(database,row['id'])['resource']['title']=='TEST'
    assert row['attributes']['facility_id'] is None
