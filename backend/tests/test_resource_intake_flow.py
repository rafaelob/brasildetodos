"""Complete operator flow with synthetic HTTP pages; no external data requests."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import pytest
from bdt.domain import Source, now
from bdt.storage import Municipality
from test_resource_sync import contract, action_plan, project, save_collection


@pytest.fixture
def operator(monkeypatch):
    path=Path(__file__).resolve().parents[2]/'ops/resource_intake.py'
    spec=importlib.util.spec_from_file_location('resource_operator_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def territory(database,_path):
        source=Source(dataset='synthetic-flow-test',record_id='territory',
            url='https://example.org/synthetic',reference_date='2026',
            collected_at=now(),snapshot_sha256='a'*64)
        with database.session() as session:
            session.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()))
        return {'records':1,'synthetic_test_only':True,'fresh_upstream_request':False}
    monkeypatch.setattr(module,'import_territory_snapshot',territory)
    rows={'pncp_contracts':[contract(valorGlobal='1.0001')],
          'transferegov_special_plans':[action_plan()], 'obrasgov_projects':[project()]}
    def collect(plan,folder):
        return save_collection(folder,deepcopy(rows[plan.dataset]),profile=plan.dataset)
    monkeypatch.setattr(module,'collect',collect)
    return module


def arguments(tmp_path):
    return ['--territory-snapshot',str(tmp_path/'placeholder.db'),'--output',str(tmp_path/'out')]


def test_success_requires_byte_hash_count_and_public_projection(operator,tmp_path,capsys):
    operator.main(arguments(tmp_path))
    root=tmp_path/'out/public'
    report=json.loads((root/'report.json').read_text())
    check=json.loads((root/'artifact-check.json').read_text())
    assert report['status']=='passed' and report['resources']==3
    assert check['status']=='passed' and check['records']==3
    assert check['subcent_records']==1 and check['subcent_fields']==1
    assert check['production_database_changed'] is False
    assert report['api_acceptance']=='passed'
    assert all(c.get('idempotent',True) for c in report['collections'])
    assert not report['public_deployment'] and not report['national_resources_certified']
    assert 'PRIVATE SUPPLIER' not in (root/'resources.jsonl').read_text()
    import hashlib
    assert check['report_sha256']==hashlib.sha256((root/'report.json').read_bytes()).hexdigest()


def test_export_verification_failure_cannot_stay_green(operator,tmp_path,monkeypatch,capsys):
    def fail(*_):raise ValueError('DO_NOT_PUBLISH arbitrary internal message')
    monkeypatch.setattr(operator,'verify_resource_artifact',fail)
    with pytest.raises(SystemExit) as error:operator.main(arguments(tmp_path))
    assert error.value.code==1
    text=(tmp_path/'out/public/report.json').read_text()
    assert json.loads(text)['status']=='failed' and 'DO_NOT_PUBLISH' not in text
    assert json.loads(text)['reason']=='public_resource_artifact_reconciliation_failed'
    assert not (tmp_path/'out/public/artifact-check.json').exists()


def test_partial_collection_never_receives_a_complete_artifact_check(operator,tmp_path,monkeypatch,capsys):
    original=operator.collect
    def missing(plan,folder):
        if plan.dataset=='pncp_contracts':raise RuntimeError('synthetic transport failure')
        return original(plan,folder)
    monkeypatch.setattr(operator,'collect',missing)
    with pytest.raises(SystemExit):operator.main(arguments(tmp_path))
    report=json.loads((tmp_path/'out/public/report.json').read_text())
    assert report['status']=='partial_with_explicit_failures' and report['resources']==2
    assert not (tmp_path/'out/public/artifact-check.json').exists()


def test_existing_evidence_is_not_replaced(operator,tmp_path):
    root=tmp_path/'out';root.mkdir();(root/'preserve').write_text('existing')
    with pytest.raises(FileExistsError):operator.main(arguments(tmp_path))
    assert (root/'preserve').read_text()=='existing'
