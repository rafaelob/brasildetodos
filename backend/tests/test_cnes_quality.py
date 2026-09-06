"""Malformed official-shaped records are quarantined, never invented or hidden."""
import json
import pytest
from sqlalchemy import func, select
from bdt.cnes_quality import QualityBudgetExceeded, prepare, publish
from bdt.storage import Place, Ingestion


def row(code='1234567', **changes):
    return {'CO_CNES':code,'NO_FANTASIA':'Unidade sintética','CO_IBGE':'123456',
            'CO_AMBULATORIAL_SUS':'SIM','CO_MOTIVO_DESAB':'', **changes}


def test_valid_and_excluded_counts(database,source,tmp_path):
    folder=tmp_path/'quality'
    report=prepare(database,[row(),row('1234568',CO_AMBULATORIAL_SUS='NAO')],source,folder)
    assert report['counts']['source_read']==2
    assert report['counts']['eligible']==1 and report['counts']['excluded_profile']==1
    assert report['status']=='ready'
    result=publish(database,folder)
    assert result['national_catalog_certified'] is False
    with database.session() as s:
        assert s.scalar(select(func.count()).select_from(Place))==1


def test_default_rejects_any_invalid_record_without_publishing(database,source,tmp_path):
    folder=tmp_path/'quality'
    with pytest.raises(QualityBudgetExceeded):
        prepare(database,[row(),row('1234568',NO_FANTASIA='')],source,folder)
    report=json.loads((folder/'quality.json').read_text())
    assert report['status']=='blocked' and report['counts']['quarantined']==1
    assert 'name:string_too_short' in report['reasons']
    with pytest.raises(ValueError,match='not_ready'):publish(database,folder)
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Place))==0


def test_explicit_budget_publishes_subset_with_visible_quarantine(database,source,tmp_path):
    folder=tmp_path/'quality'
    records=[row(str(1234567+i)) for i in range(100)]
    records[-1]['NO_FANTASIA']=''
    report=prepare(database,records,source,folder,max_rejected=1,max_rejected_fraction=.01)
    assert report['status']=='ready_with_quarantine'
    result=publish(database,folder)
    with database.session() as s:
        assert s.scalar(select(func.count()).select_from(Place))==99
        run=s.get(Ingestion,result['run_id'])
        assert run.status=='partial_quality'
        assert run.counts['source_read']==100 and run.counts['quarantined']==1
    rejected=json.loads((folder/'quarantine.jsonl').read_text())
    assert rejected['source_id']=='1234666' and 'row_sha256' in rejected
    assert 'NO_FANTASIA' not in rejected
    assert not (folder/'quarantine.jsonl').read_text().find('Unidade sintética')>=0


@pytest.mark.parametrize('records,code',[
    ([row(),row()], 'duplicate_cnes'),
    ([row(),row(CO_AMBULATORIAL_SUS='7')], 'dictionary_review'),
    ([row(),{'CO_CNES':'1234'}], 'schema_changed'),
])
def test_structural_errors_block_even_with_budget(database,source,tmp_path,records,code):
    with pytest.raises(ValueError,match=code):
        prepare(database,records,source,tmp_path/'quality',max_rejected=100,max_rejected_fraction=.01)
    with database.session() as s:assert s.scalar(select(func.count()).select_from(Place))==0


@pytest.mark.parametrize('changes,reason',[
    ({'CO_CNES':'bad'},'invalid_cnes_identifier'),
    ({'CO_IBGE':'999999'},'municipality_not_in_loaded_crosswalk'),
    ({'NO_FANTASIA':''},'name:string_too_short'),
    ({'NO_FANTASIA':'x'*301},'name:string_too_long'),
])
def test_explicit_outlier_reasons(database,source,tmp_path,changes,reason):
    folder=tmp_path/'quality'
    with pytest.raises(QualityBudgetExceeded):prepare(database,[row(**changes)],source,folder)
    report=json.loads((folder/'quality.json').read_text())
    assert reason in report['reasons']


def test_count_budget_and_fraction_both_apply(database,source,tmp_path):
    records=[row(str(1000000+i)) for i in range(100)]
    records[-1]['NO_FANTASIA']=''
    for index,policy in enumerate([{'max_rejected':0,'max_rejected_fraction':.01},
                                   {'max_rejected':1,'max_rejected_fraction':.001}]):
        with pytest.raises(QualityBudgetExceeded):prepare(database,records,source,tmp_path/str(index),**policy)


@pytest.mark.parametrize('policy',[
    {'max_rejected':-1},{'max_rejected':True},{'max_rejected':10001},
    {'max_rejected_fraction':-.1},{'max_rejected_fraction':.5},{'max_rejected_fraction':True},
])
def test_policy_validation(database,source,tmp_path,policy):
    with pytest.raises(ValueError):prepare(database,[row()],source,tmp_path/'quality',**policy)


def test_no_fabricated_coordinates(database,source,tmp_path):
    folder=tmp_path/'quality'
    prepare(database,[row(NU_LATITUDE='999',NU_LONGITUDE='invalid')],source,folder)
    publish(database,folder)
    with database.session() as s:
        place=s.get(Place,'cnes:1234567')
        assert place.latitude is None and place.longitude is None


def test_prepared_bytes_cannot_change(database,source,tmp_path):
    folder=tmp_path/'quality';prepare(database,[row()],source,folder)
    path=folder/'prepared.jsonl';path.write_text(path.read_text().replace('Unidade','Alterou'))
    with pytest.raises(ValueError,match='integrity'):publish(database,folder)


def test_failed_reprocessing_does_not_erase_prior_records(database,source,tmp_path):
    folder=tmp_path/'first';prepare(database,[row()],source,folder);publish(database,folder)
    with pytest.raises(QualityBudgetExceeded):prepare(database,[row(NO_FANTASIA='')],source,tmp_path/'bad')
    with database.session() as s:assert s.get(Place,'cnes:1234567').name=='Unidade sintética'


def test_empty_never_becomes_valid_load(database,source,tmp_path):
    with pytest.raises(QualityBudgetExceeded,match='no_eligible'):prepare(database,[],source,tmp_path/'quality')


def test_disabled_records_are_profile_exclusions_not_quality_defects(database,source,tmp_path):
    folder=tmp_path/'quality';report=prepare(database,[row(),row('7654321',CO_MOTIVO_DESAB='04',NO_FANTASIA='')],source,folder)
    assert report['counts']['excluded_profile']==1
    assert report['counts'].get('quarantined',0)==0
