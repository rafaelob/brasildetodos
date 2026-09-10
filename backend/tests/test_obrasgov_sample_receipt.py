# SPDX-License-Identifier: AGPL-3.0-or-later
"""Honesty receipt for a bounded Obrasgov sample — not a live census."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import ingest_obrasgov_batch as command

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_RECEIPT = REPO_ROOT / 'docs' / 'reports' / '20260909-obrasgov-sample.json'
SYNTHETIC_STATS = {
    'pages_fetched': 0,
    'status': 'not_run_live_http',
    'reason': 'quality CI / this wave does not recense via live Obrasgov',
}
CENSUS_COUNTER_KEYS = ('read', 'created', 'updated', 'unchanged', 'records', 'works', 'total')


def test_writer_uses_defaults_and_refuses_census_flags(tmp_path, monkeypatch):
    def forbidden_ingest(*args, **kwargs):
        raise AssertionError('write_sample_receipt must not ingest')

    monkeypatch.setattr(command, 'batch_ingest_obrasgov', forbidden_ingest)
    stats = {}
    path = tmp_path / 'receipt.json'
    receipt = command.write_sample_receipt(stats, path)
    assert receipt['schema'] == 'bdt.obrasgov-sample.v1'
    assert receipt['national_catalog_certified'] is False
    assert receipt['brazil_census'] is False
    assert receipt['public_deployment'] is False
    assert receipt['facility_id_invented'] is False
    assert receipt['sample_states'] == list(command.DEFAULT_SAMPLE_STATES)
    assert receipt['pages_fetched'] == 0
    assert json.loads(path.read_text(encoding='utf-8')) == receipt
    assert stats == {}
    for key in CENSUS_COUNTER_KEYS:
        assert key not in receipt


def test_writer_reads_sample_states_and_pages_from_stats(tmp_path):
    path = tmp_path / 'nested' / 'out.json'
    receipt = command.write_sample_receipt(
        {'states': ['RR', 'AP'], 'pages_fetched': 2, 'status': 'completed_file', 'errors': 0},
        path,
    )
    assert receipt['sample_states'] == ['RR', 'AP']
    assert receipt['pages_fetched'] == 2
    assert receipt['status'] == 'completed_file'
    assert receipt['errors'] == 0
    assert receipt['brazil_census'] is False
    assert receipt['national_catalog_certified'] is False
    assert path.is_file()


def test_writer_does_not_trust_certified_or_census_claims(tmp_path):
    receipt = command.write_sample_receipt(
        {
            'sample_states': ['RR'],
            'pages_fetched': 1,
            'national_catalog_certified': True,
            'brazil_census': True,
            'public_deployment': True,
            'facility_id_invented': False,
        },
        tmp_path / 'claimed.json',
    )
    assert receipt['national_catalog_certified'] is False
    assert receipt['brazil_census'] is False
    assert receipt['public_deployment'] is False
    assert receipt['facility_id_invented'] is False


def test_writer_rejects_invented_facility_id(tmp_path):
    with pytest.raises(ValueError, match='obrasgov_facility_id_invented'):
        command.write_sample_receipt(
            {'facility_id_invented': True, 'pages_fetched': 0},
            tmp_path / 'bad.json',
        )
    assert not (tmp_path / 'bad.json').exists()


@pytest.mark.parametrize('pages', [True, False, -1, '0', 1.5, None])
def test_writer_rejects_invalid_pages_fetched(tmp_path, pages):
    with pytest.raises(ValueError, match='invalid_pages_fetched'):
        command.write_sample_receipt({'pages_fetched': pages}, tmp_path / 'pages.json')


@pytest.mark.parametrize('states', [None, [], '', 'RR', ['RR', ''], [1]])
def test_writer_rejects_invalid_sample_states(tmp_path, states):
    with pytest.raises(ValueError, match='invalid_sample_states'):
        command.write_sample_receipt({'sample_states': states}, tmp_path / 'states.json')


def test_writer_rejects_summed_financial_totals(tmp_path):
    target = tmp_path / 'money.json'
    with pytest.raises(ValueError, match='obrasgov_sample_must_not_sum_financial_totals'):
        command.write_sample_receipt({'pages_fetched': 0, 'total_cents': 0}, target)
    with pytest.raises(ValueError, match='obrasgov_sample_must_not_sum_financial_totals'):
        command.write_sample_receipt(
            {'pages_fetched': 0, 'counts': {'convenio': {'total_cents': 10}}},
            target,
        )
    assert not target.exists()


def test_writer_refuses_directory_output(tmp_path):
    folder = tmp_path / 'dir'
    folder.mkdir()
    with pytest.raises(ValueError, match='obrasgov_sample_receipt_output_is_directory'):
        command.write_sample_receipt(SYNTHETIC_STATS, folder)


def test_writer_rejects_non_dict_stats(tmp_path):
    with pytest.raises(ValueError, match='invalid_obrasgov_sample_stats'):
        command.write_sample_receipt(['RR'], tmp_path / 'x.json')
    assert not (tmp_path / 'x.json').exists()


def test_writer_replaces_existing_receipt(tmp_path):
    path = tmp_path / 'receipt.json'
    path.write_text('{"stale": true, "total_cents": 1}', encoding='utf-8')
    receipt = command.write_sample_receipt(dict(SYNTHETIC_STATS), path)
    on_disk = json.loads(path.read_text(encoding='utf-8'))
    assert on_disk == receipt
    assert 'stale' not in on_disk
    assert 'total_cents' not in on_disk
    assert on_disk['pages_fetched'] == 0


def test_zero_pages_is_not_a_fake_empty_brazil(tmp_path):
    receipt = command.write_sample_receipt(dict(SYNTHETIC_STATS), tmp_path / 'honest.json')
    assert receipt['pages_fetched'] == 0
    assert receipt['status'] == 'not_run_live_http'
    assert receipt['reason'] == 'quality CI / this wave does not recense via live Obrasgov'
    for key in CENSUS_COUNTER_KEYS:
        assert key not in receipt
    dumped = json.dumps(receipt)
    assert 'total_cents' not in dumped
    assert 'financial_total' not in dumped


def test_committed_receipt_matches_writer_and_is_not_live_http(tmp_path):
    generated = command.write_sample_receipt(dict(SYNTHETIC_STATS), tmp_path / 'generated.json')
    on_disk = json.loads(COMMITTED_RECEIPT.read_text(encoding='utf-8'))
    assert on_disk == generated
    assert on_disk['schema'] == 'bdt.obrasgov-sample.v1'
    assert on_disk['national_catalog_certified'] is False
    assert on_disk['brazil_census'] is False
    assert on_disk['public_deployment'] is False
    assert on_disk['facility_id_invented'] is False
    assert on_disk['pages_fetched'] == 0
    assert on_disk['status'] == 'not_run_live_http'
    assert on_disk['sample_states'] == ['RR', 'AP', 'AC', 'SE', 'RO']
    for key in CENSUS_COUNTER_KEYS:
        assert key not in on_disk
    assert 'total_cents' not in on_disk
    assert 'combined_cents' not in on_disk
