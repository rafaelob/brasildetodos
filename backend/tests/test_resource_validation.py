"""Preflight identifies all rejected records without publishing any of them."""
import json
import pytest
from sqlalchemy import func,select
from bdt.evidence import Resource,ResourceInput
from bdt.resource_profiles import normalize_resource
from bdt.resource_validation import validate_collection
from bdt.resource_diagnostics import public_validation
from bdt.resource_sync import import_resources
from bdt.storage import Ingestion
from test_resource_sync import contract,source,save_collection,PNCP,current


def test_all_record_errors_are_reported_while_nothing_is_published(database,tmp_path):
    root=tmp_path/'records'
    save_collection(root,[contract(1),contract(2,objetoContrato=None),
        contract(3,objetoContrato='SECRET '*3000),contract(4,numeroContratoEmpenho=' '),contract(5)])
    report=validate_collection(database,root)
    assert report['read']==5 and report['accepted']==2 and report['invalid']==3
    assert report['published']==0 and report['validation_only']
    assert {i['rule'] for i in report['issues']}=={'required_missing','too_long','blank'}
    assert 'SECRET' not in json.dumps(report)
    assert report['diagnostics'][0]['field']=='objetoContrato'
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource))==0
        assert session.scalar(select(func.count()).select_from(Ingestion))==0


@pytest.mark.parametrize('limit',[0,1,2,100])
def test_diagnostic_budget_never_hides_total_invalid_count(database,tmp_path,limit):
    root=tmp_path/'records';save_collection(root,[contract(n,objetoContrato=None) for n in range(1,5)])
    result=validate_collection(database,root,max_diagnostics=limit)
    assert result['invalid']==4 and len(result['diagnostics'])==min(limit,4)
    assert result['diagnostics_truncated']==(limit<4)


def test_successful_preflight_does_not_replace_import(database,tmp_path):
    root=tmp_path/'records';save_collection(root,[contract(objetoContrato='A'*5120)])
    result=validate_collection(database,root)
    assert result['status']=='valid' and result['published']==0 and current(database)==[]
    assert import_resources(database,root)['created']==1


def test_profile_scope_mismatch_is_diagnosed_not_accepted(database,tmp_path):
    root=tmp_path/'records';save_collection(root,[contract(dataPublicacaoPncp='2026-09-05T12:00:00')])
    result=validate_collection(database,root)
    assert result['invalid']==1 and result['accepted']==0
    assert result['issues'][0]['rule']=='record_outside_requested_dates'


def test_corrupt_bytes_abort_preflight_instead_of_becoming_rejected_rows(database,tmp_path):
    root=tmp_path/'records';save_collection(root,[contract()]);(root/'page-000000.json').write_text('{}')
    with pytest.raises(ValueError,match='integrity'):validate_collection(database,root)


def test_unrecognized_error_does_not_reveal_arbitrary_message():
    result=public_validation(ValueError('SECRET MESSAGE'),PNCP,'not-public','a'*64)
    assert 'SECRET' not in json.dumps(result) and result['reference'] is None


@pytest.mark.parametrize('limit',[True,-1,101,'1'])
def test_invalid_budget_is_rejected(database,tmp_path,limit):
    with pytest.raises(ValueError,match='diagnostic_limit'):validate_collection(database,tmp_path,max_diagnostics=limit)


def test_model_diagnostic_retains_constraints_not_input_or_exception_context():
    from pydantic import ValidationError
    data=normalize_resource(PNCP,contract(),source(),{'1234567':('Test','BA')}).model_dump()
    data['title']=''
    with pytest.raises(ValidationError) as caught:ResourceInput.model_validate(data)
    result=public_validation(caught.value,PNCP,contract()['numeroControlePNCP'],'a'*64)
    assert result['issues']==[{'field':'title','rule':'string_too_short','length':0,'constraints':{'min_length':1}}]
    assert 'input' not in result and 'ctx' not in json.dumps(result)
