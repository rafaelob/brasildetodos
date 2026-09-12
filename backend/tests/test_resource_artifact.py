"""Synthetic artifact fixtures; real intake is evaluated by the operator command."""
import hashlib
import json
import pytest
from bdt.resource_artifact import verify_resource_artifact, main


def write(tmp_path, source, mutate=None):
    raw = {'id':'pncp_contracts:test', 'kind':'contract', 'title':'Synthetic resource',
        'municipality_id':None, 'source':source.model_copy(update={'dataset':'pncp_contracts'}).model_dump(mode='json'),
        'attributes':{'profile':'pncp_contracts','initial_cents':100,'global_cents':None,'precise_amounts':{'global':'1.0001'}}}
    if mutate: mutate(raw)
    data = (json.dumps(raw)+'\n').encode()
    (tmp_path/'resources.jsonl').write_bytes(data)
    report={'status':'passed','resources':1,'by_profile':{'pncp_contracts':1},'resources_sha256':hashlib.sha256(data).hexdigest()}
    (tmp_path/'report.json').write_text(json.dumps(report))
    return report


def test_exact_projection_and_no_data_or_false_completeness_claim(tmp_path, source):
    write(tmp_path,source)
    result=verify_resource_artifact(tmp_path)
    assert result['records']==1 and result['subcent_records']==result['subcent_fields']==1
    for key in ['financial_total_computed','fresh_collection','production_database_changed',
                'historical_ledger_verified','national_coverage_certified','public_deployment']:
        assert result[key] is False
    assert 'Synthetic resource' not in json.dumps(result) and 'https://' not in json.dumps(result)


def test_wrong_bytes_are_not_accepted(tmp_path,source):
    write(tmp_path,source)
    with (tmp_path/'resources.jsonl').open('ab') as f:f.write(b' ')
    with pytest.raises(ValueError):verify_resource_artifact(tmp_path)


@pytest.mark.parametrize('key,value',[('resources',2),('resources',True),('resources',-1),
 ('by_profile',{'obrasgov_projects':1}),('status','partial_with_explicit_failures'),('resources_sha256','b'*64)])
def test_declared_report_is_reconciled_not_trusted(tmp_path,source,key,value):
    report=write(tmp_path,source);report[key]=value
    (tmp_path/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError):verify_resource_artifact(tmp_path)


@pytest.mark.parametrize('surface',['report','record'])
def test_resource_artifact_rejects_duplicate_json_keys(tmp_path,source,surface):
    report=write(tmp_path,source)
    assert verify_resource_artifact(tmp_path)['status']=='passed'
    if surface=='report':
        path=tmp_path/'report.json';raw=path.read_bytes()
        path.write_bytes(raw.replace(b'"status":',b'"status":"failed","status":',1))
    else:
        path=tmp_path/'resources.jsonl';data=path.read_bytes()
        data=data.replace(b'"id":',b'"id":"other","id":',1);path.write_bytes(data)
        report['resources_sha256']=hashlib.sha256(data).hexdigest()
        (tmp_path/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='duplicate_json_key'):verify_resource_artifact(tmp_path)


def test_duplicate_id_even_with_consistent_count_and_hash_is_rejected(tmp_path,source):
    report=write(tmp_path,source);data=(tmp_path/'resources.jsonl').read_bytes()*2
    (tmp_path/'resources.jsonl').write_bytes(data)
    report.update(resources=2,by_profile={'pncp_contracts':2},resources_sha256=hashlib.sha256(data).hexdigest())
    (tmp_path/'report.json').write_text(json.dumps(report))
    with pytest.raises(ValueError,match='duplicate_identity'):verify_resource_artifact(tmp_path)


def test_profile_must_match_identity_and_source(tmp_path,source):
    write(tmp_path,source,lambda row:row['attributes'].update(profile='obrasgov_projects'))
    with pytest.raises(ValueError,match='profile_mismatch'):verify_resource_artifact(tmp_path)


def test_conflicting_monetary_representation_is_not_rounded(tmp_path,source):
    write(tmp_path,source,lambda row:row['attributes'].update(global_cents=100))
    with pytest.raises(ValueError,match='conflicting_public_resource_amount'):verify_resource_artifact(tmp_path)


def test_evidence_creation_is_exclusive(tmp_path,source,capsys):
    write(tmp_path,source);out=tmp_path/'checked.json'
    main([str(tmp_path),'--output',str(out)]);saved=out.read_bytes()
    with pytest.raises(SystemExit):main([str(tmp_path),'--output',str(out)])
    assert out.read_bytes()==saved


def test_file_and_record_budgets_fail_closed(tmp_path,source,monkeypatch):
    write(tmp_path,source)
    monkeypatch.setattr('bdt.resource_artifact.MAX_BYTES',10)
    with pytest.raises(ValueError,match='byte_budget'):verify_resource_artifact(tmp_path)
    monkeypatch.setattr('bdt.resource_artifact.MAX_BYTES',100000)
    monkeypatch.setattr('bdt.resource_artifact.MAX_LINE_BYTES',10)
    with pytest.raises(ValueError,match='row_budget'):verify_resource_artifact(tmp_path)


def test_symlinks_are_not_used_as_inputs(tmp_path,source):
    write(tmp_path,source)
    path=tmp_path/'report.json';other=tmp_path/'original.json';path.rename(other);path.symlink_to(other)
    with pytest.raises(ValueError,match='symlink'):verify_resource_artifact(tmp_path)
