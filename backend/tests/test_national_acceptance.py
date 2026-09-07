# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic fixtures isolate failures; the workflow separately uses released data."""
import json
from pathlib import Path
import sys

import pytest
from bdt.domain import PlaceInput
from bdt.storage import upsert_place
from test_public_data_bundle import bundler, bundle_input
from test_education_release import package, pack
from test_national_installation import inputs, stored

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import national_catalog_acceptance as acceptance
from browser_national_catalog import select_mixed_samples, CATEGORIES
from browser_public_catalog import LABELS


def test_acceptance_installs_both_inputs_and_checks_each_partition(inputs, tmp_path):
    health, health_selection, schools = inputs
    archive, school_selection = pack(schools)
    out = tmp_path / 'result'
    result = acceptance.exercise(health, archive, health_selection=health_selection,
        education_selection=school_selection, output=out)
    assert result['status'] == 'passed' and result['browser_checked'] is False
    assert result['api']['partitions_checked'] == 2
    assert result['installation']['by_kind'] == {'health': 1, 'school': 2}
    assert result['installation']['counts']['finance'] == 0
    text = (out / 'acceptance.json').read_text()
    assert str(tmp_path) not in text and 'private_not_in_bundle' not in text
    assert json.loads(text) == result
    assert list(out.iterdir()) == [out / 'acceptance.json']


def test_bad_input_writes_sanitized_failure_receipt_without_publishing_database(inputs, tmp_path):
    health, health_selection, schools = inputs
    archive, selected = pack(schools)
    health.write_bytes(b'invalid source')
    out = tmp_path / 'failure'
    with pytest.raises(ValueError):
        acceptance.exercise(health, archive, health_selection=health_selection,
            education_selection=selected, output=out)
    result = json.loads((out / 'acceptance.json').read_text())
    assert result['status'] == 'failed' and result['failed_stage'] == 'installation'
    assert result['browser_checked'] is False and 'installation' not in result
    assert list(out.iterdir()) == [out / 'acceptance.json']


def test_existing_report_directory_is_never_overwritten(inputs, tmp_path):
    out = tmp_path / 'existing'; out.mkdir()
    original = out / 'acceptance.json'; original.write_text('prior independent evidence')
    with pytest.raises(FileExistsError):
        acceptance.exercise(inputs[0], tmp_path / 'missing', health_selection=inputs[1],
                            education_selection=tmp_path / 'missing-selection', output=out)
    assert original.read_text() == 'prior independent evidence'


def test_failed_api_does_not_become_success_or_expose_error_text(inputs, tmp_path, monkeypatch):
    health, health_selection, schools = inputs
    archive, selected = pack(schools)
    private_database = []
    def fail(path, result):
        private_database.append(path)
        raise ValueError('secret raw error with private path')
    monkeypatch.setattr(acceptance, 'accept_api', fail)
    out = tmp_path / 'result'
    with pytest.raises(ValueError):
        acceptance.exercise(health, archive, health_selection=health_selection,
                            education_selection=selected, output=out)
    text = (out / 'acceptance.json').read_text(); receipt = json.loads(text)
    assert receipt['status'] == 'failed' and receipt['failed_stage'] == 'api'
    assert 'secret' not in text and 'private path' not in text
    assert private_database and not private_database[0].exists()


def test_browser_build_failure_is_not_reported_as_ui_success(inputs, tmp_path):
    health, health_selection, schools = inputs
    archive, selected = pack(schools)
    out = tmp_path / 'result'
    with pytest.raises(ValueError, match='build_missing'):
        acceptance.exercise(health, archive, health_selection=health_selection,
            education_selection=selected, output=out, static=tmp_path / 'not-built')
    report = json.loads((out / 'acceptance.json').read_text())
    assert report['failed_stage'] == 'browser' and report['browser_checked'] is False
    assert report['status'] == 'failed'


def test_mixed_samples_are_deterministic_bounded_and_keep_geometry_absence(database, source):
    with database.session() as session:
        for kind in ('school', 'health'):
            for number in range(6):
                located = number % 2 == 0
                upsert_place(session, PlaceInput(id=f'test:{kind}-{number}', kind=kind,
                    name=f'Synthetic {kind} {number}', municipality_id='1234567', state='BA',
                    latitude=-12.5 if located else None, longitude=-38.5 if located else None,
                    geo_source='synthetic-test' if located else None, source=source))
    result = select_mixed_samples(database)
    assert result['counts'] == {'health': 6, 'school': 6}
    assert [item['id'] for item in result['samples']] == [
        'test:health-1', 'test:health-0', 'test:school-1', 'test:school-0']
    assert sum(item['latitude'] is None for item in result['samples']) == 2
    assert result == select_mixed_samples(database)


@pytest.mark.parametrize('missing', ['health', 'school'])
def test_missing_eligible_kind_cannot_pass_mixed_acceptance(database, source, missing):
    with database.session() as session:
        for kind in ('school', 'health'):
            upsert_place(session, PlaceInput(id=f'test:{kind}', kind=kind, name='Synthetic test',
                municipality_id='1234567', state='BA', catalogue_eligible=(kind != missing), source=source))
    with pytest.raises(ValueError, match='missing_kind'):
        select_mixed_samples(database)


def test_three_locales_define_both_kind_actions():
    assert set(CATEGORIES) == set(LABELS) == {'pt-BR', 'en', 'es'}
    assert all(set(labels) == {'health', 'school'} and all(labels.values()) for labels in CATEGORIES.values())
