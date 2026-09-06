"""Only structural diagnostics are public; failing input still rolls back."""
import json
import pytest
from sqlalchemy import func, select
from bdt.evidence import Resource
from bdt.resource_profiles import text
from bdt.resource_diagnostics import ResourceTextError
from bdt.resource_sync import import_resources
from test_resource_sync import contract, save_collection, source, normalize_resource, PNCP


@pytest.mark.parametrize('value,rule,value_type,length',[
    (None,'required_missing','null',None), (True,'wrong_type','boolean',None),
    (123,'wrong_type','number',None), ({'private':'SECRET'},'wrong_type','other',None),
    ('  \n','blank','string',3), ('SECRET TEXT '*500,'too_long','string',6000),
])
def test_no_failed_content_can_escape_in_error_or_diagnostic(value,rule,value_type,length):
    with pytest.raises(ResourceTextError) as caught:
        text(value, required=True, field='objetoContrato')
    error=caught.value;report=error.public_diagnostic()
    assert str(error)=='invalid_resource_text'
    assert report['rule']==rule and report['value_type']==value_type and report['length']==length
    assert report['raw_value_included'] is False and 'SECRET' not in json.dumps(report)


def test_unknown_field_is_not_echoed():
    assert ResourceTextError('SECRET', 'PRIVATE',2).public_diagnostic()['field']=='unspecified'


@pytest.mark.parametrize('value',[None,'Valid five words', 'X'*4000])
def test_instrumentation_does_not_relax_existing_policy(value):
    assert text(value,field='objetoContrato')==value


def test_public_identity_and_page_hash_are_bounded():
    e=ResourceTextError('objetoContrato','X'*4001,4000)
    assert e.with_reference(PNCP,'PRIVATE USERNAME','a'*64).public_diagnostic()['reference'] is None
    assert e.with_reference('unknown','12345678000199-2-000001/2026','a'*64).reference is None
    e.with_reference(PNCP,'12345678000199-2-000001/2026','not a hash')
    assert 'snapshot_sha256' not in e.reference


def test_exact_profile_field_is_identified():
    row=contract(numeroContratoEmpenho='   ')
    with pytest.raises(ResourceTextError) as caught:
        normalize_resource(PNCP,row,source(),{'1234567':('Test','BA')})
    assert caught.value.public_diagnostic()['field']=='numeroContratoEmpenho'


def test_reference_is_attached_after_verified_page_and_nothing_is_published(database,stored,tmp_path):
    # stored fixture supplies the synthetic municipality required by these tests.
    root=tmp_path/'input';save_collection(root,[contract(),contract(2,objetoContrato='SECRET '*1000)])
    with pytest.raises(ResourceTextError) as caught:
        import_resources(database,root)
    diagnostic=caught.value.public_diagnostic()
    assert diagnostic['reference']['record_id'].endswith('000002/2026')
    assert len(diagnostic['reference']['snapshot_sha256'])==64
    assert 'SECRET' not in json.dumps(diagnostic)
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Resource))==0
