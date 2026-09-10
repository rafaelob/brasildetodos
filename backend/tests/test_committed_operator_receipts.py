# SPDX-License-Identifier: AGPL-3.0-or-later
"""Committed operator JSON receipts are honesty contracts, not a national census."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / 'docs' / 'reports'
FREEZE = REPORTS / '20260909-transferegov-freeze.json'
INGEST = REPORTS / '20260909-transferegov-ingest.json'
INGEST_UNBOUNDED = REPORTS / '20260910-transferegov-ingest.json'
OBRASGOV = REPORTS / '20260909-obrasgov-sample.json'
FORBIDDEN_TOTAL_KEYS = frozenset({'total_cents', 'combined_cents', 'financial_total'})
PHASE_COUNT_KEYS = ('agreed', 'amendments', 'transferred')
LIMIT_KEYS = ('agreements', 'amendments', 'disbursements')


def _load(path: Path) -> dict:
    assert path.is_file(), f'missing committed receipt {path}'
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert isinstance(payload, dict), f'{path.name} must be a JSON object'
    return payload


def _assert_no_forbidden_totals(value, path='$'):
    if isinstance(value, dict):
        forbidden = FORBIDDEN_TOTAL_KEYS.intersection(value)
        assert not forbidden, f'{path} contains {sorted(forbidden)}'
        for key, child in value.items():
            _assert_no_forbidden_totals(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_totals(child, f'{path}[{index}]')


def _archive_sha256(archives) -> dict[str, str]:
    assert isinstance(archives, list) and archives, 'receipt must list archives'
    hashes = {}
    for archive in archives:
        assert isinstance(archive, dict) and archive.get('name'), 'archive needs a name'
        sha = archive['sha256']
        assert isinstance(sha, str) and len(sha) == 64, f'{archive["name"]} sha256 must be 64 hex'
        int(sha, 16)
        hashes[archive['name']] = sha
    return hashes


def test_committed_receipts_are_not_certified_national_totals():
    for path in (FREEZE, INGEST, INGEST_UNBOUNDED, OBRASGOV):
        receipt = _load(path)
        assert receipt['national_catalog_certified'] is False, path.name
        _assert_no_forbidden_totals(receipt, path.name)


def test_freeze_receipt_imports_nothing_and_records_archive_sha256():
    freeze = _load(FREEZE)
    assert freeze['records_imported'] == 0
    assert freeze['financial_total_computed'] is False
    _archive_sha256(freeze['archives'])


def test_ingest_receipt_refuses_live_app_db_matches_freeze_hashes_and_declares_limits():
    ingest = _load(INGEST)
    freeze = _load(FREEZE)
    assert ingest['live_app_database_refused'] == 'data/bdt.db'
    counts = ingest['counts']
    assert ingest['records_imported'] == sum(counts[key] for key in PHASE_COUNT_KEYS)
    assert _archive_sha256(ingest['archives']) == _archive_sha256(freeze['archives'])
    limits = ingest['limits']
    assert isinstance(limits, dict) and limits, 'limits must be present so this is not a silent Brazil census'
    for key in LIMIT_KEYS:
        assert isinstance(limits[key], int), f'limits.{key} must be set'


def test_unbounded_ingest_receipt_has_null_limits_and_matching_hashes():
    ingest = _load(INGEST_UNBOUNDED)
    freeze = _load(FREEZE)
    assert ingest['national_catalog_certified'] is False
    assert ingest['financial_total_computed'] is False
    assert ingest['phases_summed'] is False
    assert ingest['live_app_database_refused'] == 'data/bdt.db'
    assert ingest['database'] != 'data/bdt.db'
    counts = ingest['counts']
    assert ingest['records_imported'] == sum(counts[key] for key in PHASE_COUNT_KEYS)
    assert ingest['records_imported'] == counts['total']
    assert _archive_sha256(ingest['archives']) == _archive_sha256(freeze['archives'])
    limits = ingest['limits']
    assert isinstance(limits, dict)
    for key in LIMIT_KEYS:
        assert limits[key] is None, f'unbounded ingest must record null limits.{key}'


def test_obrasgov_receipt_is_not_a_live_brazil_census():
    receipt = _load(OBRASGOV)
    assert receipt['brazil_census'] is False
    assert receipt['pages_fetched'] == 0
    assert receipt['status'] == 'not_run_live_http'
    assert receipt['facility_id_invented'] is False
    assert 'facility_id' not in receipt
