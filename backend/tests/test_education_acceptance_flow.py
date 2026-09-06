"""Operator-flow fixtures only; source download and school parser have separate tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from bdt.domain import now


@pytest.fixture
def operator(monkeypatch):
    path=Path(__file__).resolve().parents[2]/'ops/education_bulk.py'
    spec=importlib.util.spec_from_file_location('education_operator_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'import_territory_snapshot',lambda *a:{'records':0,'mode':'synthetic_flow_fixture'})
    monkeypatch.setattr(module,'official_anchor',lambda:('fixture',{'synthetic_test_only':True}))
    monkeypatch.setattr(module,'discover_distribution',lambda *a:'https://download.inep.gov.br/synthetic-test-only.zip')
    def download(url,path,*a):
        data=b'synthetic operator-flow archive; never real microdata';path.write_bytes(data)
        return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'collected_at':now()}
    monkeypatch.setattr(module,'download_retry',download)
    monkeypatch.setattr(module,'import_school_archive',lambda *a,**k:{'status':'imported','counts':{},'missing_eligible_states':[],'tables':[]})
    return module


def args(tmp_path):
    return ['--output',str(tmp_path/'output'),'--territory-snapshot',str(tmp_path/'synthetic-placeholder.db')]


def test_success_requires_api_acceptance_after_export(operator,tmp_path):
    assert operator.main(args(tmp_path))==0
    report=json.loads((tmp_path/'output/report.json').read_text())
    assert report['status']=='imported'
    assert report['api_acceptance']['status']=='passed'
    assert report['api_acceptance']['saved_places']['integration']=='query_module_only_not_public_endpoint'
    assert [x['stage'] for x in report['stages']][-2:]==['public_catalog','api_acceptance']
    assert report['national_catalog_certified'] is False and report['application_deployed'] is False
    assert not (tmp_path/'output/inep-distribution.zip').exists()


def test_api_failure_cannot_be_reported_as_success(operator,tmp_path,monkeypatch):
    def fail(*a):raise ValueError('catalog_watch_projection_failure')
    monkeypatch.setattr(operator,'exercise_catalog',fail)
    assert operator.main(args(tmp_path))==1
    report=json.loads((tmp_path/'output/report.json').read_text())
    assert report['status']=='failed'
    assert report['stages'][-1]['stage']=='failure'
    assert 'api_acceptance' not in report


def test_original_error_is_not_copied_to_public_report(operator,tmp_path,monkeypatch):
    def fail(*a):raise RuntimeError('DO_NOT_PUBLISH arbitrary internal failure details')
    monkeypatch.setattr(operator,'exercise_catalog',fail)
    assert operator.main(args(tmp_path))==1
    raw=(tmp_path/'output/report.json').read_text()
    assert 'DO_NOT_PUBLISH' not in raw
    assert json.loads(raw)['error_type']=='RuntimeError'


def test_existing_output_is_not_overwritten(operator,tmp_path):
    root=tmp_path/'output';root.mkdir();target=root/'existing.json';target.write_text('preserve')
    with pytest.raises(SystemExit):operator.main(args(tmp_path))
    assert target.read_text()=='preserve'
