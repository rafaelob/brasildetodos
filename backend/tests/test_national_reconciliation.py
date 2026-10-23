"""Synthetic reconciliation tests - no live sources are contacted."""
import json
import sys

import pytest

import ops.national_reconciliation as schema
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Municipality, upsert_place


def receipt(health_eligible=5, school_eligible=2):
    return {
        'release_installation': {'counts': {'health': 4, 'school': 2}},
        'fresh_sources': {
            'cnes': {
                'url': 'https://example.org/cnes.zip',
                'sha256': 'b' * 64,
                'collected_at': '2026-10-21T23:42:14Z',
                'eligible': health_eligible,
                'scope': 'outpatient',
                'status': 'partial_quality',
            },
            'inep': {
                'url': 'https://example.org/inep.zip',
                'sha256': 'c' * 64,
                'collected_at': '2026-10-21T23:44:51Z',
                'eligible': school_eligible,
                'scope': 'public schools',
                'status': 'imported',
            },
        },
    }


def _place(identifier: str, kind: str, state: str, with_geometry: bool = True):
    source = Source(dataset='synthetic', url='https://example.org/test-only',
                    record_id=identifier, reference_date='2025', collected_at=now(),
                    snapshot_sha256='a' * 64)
    municipality = {'BA': '1234567', 'MG': '3156702', 'SP': '3106200'}.get(state, '1234567')
    return PlaceInput(id=identifier, kind=kind, name=f'Reconciled {identifier}',
                      municipality_id=municipality, state=state, source=source,
                      latitude=1.5 if with_geometry else None,
                      longitude=2.5 if with_geometry else None,
                      geo_source='synthetic-geocoder' if with_geometry else None)


@pytest.fixture
def seeded(database, source):
    with database.session() as session:
        session.add(Municipality(id='3106200', name='Reconciled municipality south',
                                 state='SP', source=source.model_dump()))
        session.add(Municipality(id='3156702', name='Reconciled municipality center',
                                 state='MG', source=source.model_dump()))
        upsert_place(session, _place('test:health-ba', 'health', 'BA'))
        upsert_place(session, _place('test:health-ba-2', 'health', 'BA'))
        upsert_place(session, _place('test:health-mg', 'health', 'MG'))
        upsert_place(session, _place('test:school-ba', 'school', 'BA'))
        upsert_place(session, _place('test:school-sp', 'school', 'SP', with_geometry=False))
    yield database


def test_reconciliation_compares_installed_with_declared_only(seeded):
    report = schema.compute(seeded, receipt(), database_path='synthetic.db',
                            receipt_path='receipt.json')
    assert report['national_catalog_certified'] is False
    assert report['installed']['total_places'] == 5
    assert report['installed']['by_kind'] == {'health': 3, 'school': 2}
    assert report['installed']['without_geometry'] == 1
    states = {row['state']: row for row in report['installed']['by_state']}
    assert states['BA'] == {'state': 'BA', 'health': 2, 'school': 1}
    assert states['MG']['school'] == 0
    health = report['sources']['health']
    assert health['status'] == 'reconciled'
    assert health['declared_total'] == 5 and health['installed'] == 3 and health['gap'] == -2
    school = report['sources']['school']
    assert school['declared_total'] == 2 and school['installed'] == 2 and school['gap'] == 0
    assert report['notes'][3].startswith('Certification requires')


def test_missing_denominator_is_never_invented(seeded):
    broken = receipt()
    del broken['fresh_sources']['inep']['eligible']
    report = schema.compute(seeded, broken, database_path='synthetic.db',
                            receipt_path='receipt.json')
    assert report['sources']['school'] == {'status': 'missing_denominator'}
    assert report['sources']['health']['gap'] == -2


def test_changed_receipt_schema_is_refused(seeded):
    with pytest.raises(ValueError, match='receipt_schema_changed'):
        schema.compute(seeded, {'unexpected': True}, database_path='synthetic.db',
                       receipt_path='receipt.json')


def test_cli_writes_the_report_explicitly(tmp_path, monkeypatch):
    target = tmp_path / 'reconciliation.json'
    if not (schema.DEFAULT_RECEIPT.exists() and schema.DEFAULT_DATABASE.exists()):
        pytest.skip('local reconciliation inputs not present on this runner')
    monkeypatch.setattr(sys, 'argv', ['national_reconciliation.py',
                                      '--report', str(target)])
    schema.main()
    report = json.loads(target.read_text(encoding='utf-8'))
    assert report['schema'] == 'bdt.national-reconciliation.v1'
    assert report['national_catalog_certified'] is False
    assert target.with_name(target.name + '.tmp').exists() is False
