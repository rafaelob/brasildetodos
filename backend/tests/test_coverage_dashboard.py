"""Synthetic coverage scenarios; never loaded by application startup."""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from fastapi import FastAPI
from bdt.coverage_dashboard import install
from bdt.coverage_dashboard import public_run, _reference, _timestamp
from bdt.evidence import Resource, initialize_extensions
from bdt.storage import Ingestion, Municipality, Place, upsert_place


@pytest.fixture
def client(database):
    initialize_extensions(database)
    app = FastAPI()
    install(app, database)
    with TestClient(app) as test:
        yield test


def run_record(**changes):
    return {'id': str(uuid4()), 'dataset': 'cnes-national-bulk', 'status': 'completed_file',
            'started_at': '2026-09-05T09:00:00+00:00', 'finished_at': '2026-09-05T10:00:00+00:00',
            'counts': {'read': 8, 'inserted': 3, 'updated': 2, 'unchanged': 1, 'excluded': 2},
            'reference_date': '2025', **changes}


def save_run(database, **changes):
    row = run_record(**changes)
    reference = row.pop('reference_date')
    with database.session() as session:
        item = Ingestion(**row, source={'reference_date': reference, 'url': 'https://example.org/private?secret=test',
            'query': {'private': 'DO_NOT_DISCLOSE'}, 'record_id': '/operator/private/filename'},
            error='PRIVATE_TRACE_AND_CREDENTIAL_PLACEHOLDER')
        session.add(item)
    return row['id']


def test_empty_installation_is_not_national_coverage(database, client):
    coverage = client.get('/api/coverage').json()
    assert coverage['national_catalog_certified'] is False
    assert coverage['municipalities'] == 1
    assert coverage['summary'] == {'places': 0, 'geocoded': 0, 'without_geometry': 0,
        'states_with_places': 0, 'municipalities_with_places': 0, 'resources': 0}
    assert coverage['runs'] == [] and coverage['imports_total'] == 0
    # Territory is loaded even when a public catalog has no recorded import log.
    ibge = next(row for row in coverage['sources'] if row['id'] == 'ibge')
    assert ibge['data_state'] == 'loaded' and ibge['last_attempt'] is None
    assert coverage['scope'] == 'loaded_records_in_this_installation'


def test_loaded_totals_are_independent_of_last_failure(database, place, client):
    school = place.model_copy(update={'source': place.source.model_copy(update={'dataset': 'inep-schools-2025'})})
    health = place.model_copy(update={'id': 'test:health', 'kind': 'health', 'latitude': -12.9,
        'longitude': -38.5, 'geo_source': 'Synthetic fixture',
        'source': place.source.model_copy(update={'dataset': 'cnes-national-bulk'})})
    with database.session() as session:
        upsert_place(session, school)
        upsert_place(session, health)
        upsert_place(session, place.model_copy(update={'id': 'test:hidden', 'catalogue_eligible': False}))
    failed = save_run(database, status='failed', counts={'read': 200, 'inserted': 100, 'updated': 99})
    payload = client.get('/api/coverage').json()
    assert payload['summary']['places'] == 2
    assert payload['summary']['geocoded'] == 1
    assert payload['summary']['without_geometry'] == 1
    assert payload['summary']['municipalities_with_places'] == 1
    assert sum(row['records'] for row in payload['partitions']) == 2
    cnes = next(row for row in payload['sources'] if row['id'] == 'cnes')
    assert cnes['places'] == 1 and cnes['data_state'] == 'loaded'
    assert cnes['last_attempt']['id'] == failed
    assert cnes['last_attempt']['counts']['created'] == 0
    assert cnes['last_attempt']['counts']['updated'] == 0
    assert cnes['last_attempt']['publication'] == 'not_published'
    with database.session() as session:
        assert len(list(session.scalars(select(Place).where(Place.catalogue_eligible.is_(True))))) == 2


def test_incomplete_coordinate_pair_is_not_counted_as_geocoded(database, place, client):
    with database.session() as session:
        upsert_place(session, place)
        # Damaged legacy row must not be presented as map-ready.
        row = session.get(Place, place.id)
        row.latitude = -12.9
    result = client.get('/api/coverage').json()
    assert result['summary']['places'] == 1
    assert result['summary']['without_geometry'] == 1
    assert result['summary']['geocoded'] == 0


def test_no_raw_labels_errors_queries_or_source_objects_are_published(database, place, client):
    save_run(database, dataset='/private/data/hidden-dataset', status='PRIVATE_STATUS',
        started_at='/private/hidden-time', finished_at='PRIVATE_FINISH',
        reference_date='PRIVATE_REFERENCE', counts={'read': 1, 'detail': 'DO_NOT_DISCLOSE', 'scope': {'secret': 'HIDDEN'}})
    with database.session() as session:
        upsert_place(session, place)
        row = session.get(Place, place.id)
        row.dataset = '/private/dataset'
        row.state = 'PRIVATE_STATE'
    for url in ('/api/coverage', '/api/imports'):
        response = client.get(url)
        assert response.status_code == 200
        for text in ('PRIVATE', 'DO_NOT_DISCLOSE', '/private', '/operator', 'filename', 'HIDDEN', 'secret', 'query'):
            assert text not in response.text
        # Production security middleware remains unchanged; these query-module
        # tests use a separate app and do not claim entrypoint integration.
    result = client.get('/api/imports').json()['items'][0]
    assert result['dataset'] == 'other' and result['status'] == 'unknown'
    assert result['started_at'] is None and result['reference_date'] is None
    partition = client.get('/api/coverage').json()['partitions'][0]
    assert partition['source_id'] == 'other' and partition['state'] == 'unknown'


def test_public_resource_counts_do_not_allocate_money_or_return_payloads(database, source, client):
    initialize_extensions(database)
    with database.session() as session:
        for i, dataset in enumerate(('pncp_contracts', 'transferegov_special_plans', 'obrasgov_projects', '/private/unknown')):
            session.add(Resource(id=f'synthetic:{i}', kind='work', title='Synthetic hidden detail',
                municipality_id=None, payload={'secret': 'DO_NOT_DISCLOSE'},
                source=source.model_dump() | {'dataset': dataset}))
    result = client.get('/api/coverage').json()
    assert result['summary']['resources'] == 4
    assert result['summary']['places'] == 0
    assert 'DO_NOT_DISCLOSE' not in str(result)
    for key in ('pncp', 'transferegov', 'obrasgov', 'other'):
        assert next(row for row in result['sources'] if row['id'] == key)['resources'] == 1
    assert not any(key in str(result) for key in ('amount_cents', 'valorGlobal', 'investment_total'))


def test_history_filters_pagination_and_last_attempt_are_consistent(database, client):
    for index in range(14):
        save_run(database, dataset='pncp_contracts', started_at=f'2026-09-{index+1:02}T10:00:00Z',
                 status='failed' if index % 2 else 'success')
    health_id = save_run(database, started_at='2026-08-01T10:00:00Z')
    first = client.get('/api/imports', params={'source': 'pncp', 'status': 'failed', 'limit': 3}).json()
    second = client.get('/api/imports', params={'source': 'pncp', 'status': 'failed', 'limit': 3, 'page': 2}).json()
    assert first['total'] == 7 and len(first['items']) == 3 and first['has_more']
    assert second['total'] == 7 and len(second['items']) == 3
    assert not {row['id'] for row in first['items']} & {row['id'] for row in second['items']}
    assert all(row['source_id'] == 'pncp' and row['status'] == 'failed' for row in first['items'])
    assert first['items'][0]['started_at'] > first['items'][1]['started_at']
    last = client.get('/api/imports', params={'source': 'pncp', 'status': 'failed', 'limit': 3, 'page': 3}).json()
    assert len(last['items']) == 1 and not last['has_more']
    empty = client.get('/api/imports', params={'source': 'pncp', 'page': 100}).json()
    assert empty['items'] == [] and not empty['has_more']
    coverage = client.get('/api/coverage').json()
    assert coverage['imports_total'] == 15 and len(coverage['runs']) == 5
    assert next(row for row in coverage['sources'] if row['id'] == 'cnes')['last_attempt']['id'] == health_id
    assert client.get('/api/imports', params={'source': 'cnes'}).json()['total'] == 1


@pytest.mark.parametrize('params', [{'limit': 0}, {'limit': 51}, {'page': 0}, {'page': 10001},
    {'source': 'unreviewed'}, {'status': 'completed_file'}, {'limit': 'abc'}])
def test_request_bounds_and_fixed_vocabulary(client, params):
    assert client.get('/api/imports', params=params).status_code == 422


@pytest.mark.parametrize('status,expected,publication', [
    ('success', 'completed', 'recorded'), ('completed_file', 'completed', 'recorded'),
    ('partial_quality', 'partial', 'partial'), ('failed', 'failed', 'not_published'),
    ('running', 'running', 'pending'), ('unexpected', 'unknown', 'unknown')])
def test_status_projection(status, expected, publication):
    result = public_run(run_record(status=status))
    assert result['status'] == expected and result['publication'] == publication
    if expected in ('running', 'unknown'):
        assert result['counts']['created'] is None


def test_partial_quality_is_visible_and_not_national_completion(database, client):
    save_run(database, status='partial_quality', counts={'source_read': 100, 'read': 20,
        'inserted': 18, 'unchanged': 2, 'quarantined': 1, 'without_geometry': 3})
    result = client.get('/api/imports').json()
    assert result['national_catalog_certified'] is False
    row = result['items'][0]
    assert row['status'] == 'partial' and row['publication'] == 'partial'
    assert row['counts']['source_read'] == 100 and row['counts']['created'] == 18
    assert row['counts']['quarantined'] == 1 and row['counts']['without_geometry'] == 3


@pytest.mark.parametrize('invalid', [-1, True, 1.2, '23', {'value': 4}, [5], 2**53])
def test_counter_types_do_not_leak_or_fabricate_numbers(invalid):
    projected = public_run(run_record(counts={'read': invalid, 'created': invalid, 'excluded': invalid}))
    assert projected['counts']['read'] is None and projected['counts']['created'] is None
    assert projected['counts']['excluded'] is None


def test_resource_rollback_does_not_promote_attempted_creation():
    row = public_run(run_record(status='failed', counts={'records_attempted': 120, 'published': 0,
        'inserted': 44, 'updated': 30, 'unchanged': 7, 'rolled_back': True}))
    assert row['counts']['read'] == 120
    assert row['counts']['created'] == row['counts']['updated'] == 0
    assert row['counts']['unchanged'] is None


def test_conflicting_counter_aliases_are_unknown_not_added():
    result = public_run(run_record(counts={'inserted': 1, 'created': 4, 'read': 5}))
    assert result['counts']['created'] is None


def test_successful_empty_query_does_not_create_records():
    result = public_run(run_record(status='success', counts={'read': 0, 'created': 0, 'updated': 0, 'unchanged': 0}))
    assert result['publication'] == 'recorded' and result['counts']['created'] == 0


@pytest.mark.parametrize('value,expected', [
    ('2025','2025'), ('2025-12','2025-12'), ('2025-02-28','2025-02-28'),
    ('2025-02-30',None), ('2025-13',None), ('private-reference',None), (2025,None),
    ('2026-09-06T12:00:00-03:00','2026-09-06T15:00:00+00:00'), ('2026-09-06T12:00:00',None)])
def test_reference_does_not_become_collection_date(value, expected):
    assert _reference(value) == expected


def test_timestamp_and_identifier_are_bounded_safe_values():
    assert _timestamp('2026-99-06T12:00:00Z') is None
    result = public_run(run_record(id='/private/local/path', started_at='https://example.org/private'))
    assert result['id'].startswith('run-') and '/private' not in str(result)
    assert result['started_at'] is None


def test_deterministic_tied_timestamp_pagination(database, client):
    ids = [save_run(database) for _ in range(3)]
    actual = [client.get('/api/imports', params={'limit': 1, 'page': i}).json()['items'][0]['id'] for i in (1,2,3)]
    assert actual == sorted(ids, reverse=True)


def test_reads_leave_import_ledger_unchanged(database, client):
    save_run(database, status='failed')
    with database.session() as session:
        before = [(row.id, row.counts, row.error, row.source) for row in session.scalars(select(Ingestion))]
    client.get('/api/coverage'); client.get('/api/imports')
    with database.session() as session:
        after = [(row.id, row.counts, row.error, row.source) for row in session.scalars(select(Ingestion))]
    assert after == before


def test_transferegov_and_obrasgov_aliases_map_correctly(database, client):
    """Verify that transferegov and obrasgov dataset aliases map to their families, not 'other'."""
    save_run(database, dataset='transferegov', status='success',
             counts={'read': 50, 'inserted': 45, 'updated': 5, 'unchanged': 0})
    save_run(database, dataset='transferegov-national-financial', status='completed_file',
             counts={'read': 30, 'inserted': 30, 'updated': 0, 'unchanged': 0})
    save_run(database, dataset='obrasgov', status='completed_file',
             counts={'read': 20, 'inserted': 18, 'updated': 2, 'unchanged': 0})
    save_run(database, dataset='obrasgov_projects', status='completed_file',
             counts={'read': 10, 'inserted': 10, 'updated': 0, 'unchanged': 0})

    # Verify /api/imports filtering for transferegov
    tgov_res = client.get('/api/imports', params={'source': 'transferegov'}).json()
    assert tgov_res['total'] == 2
    for item in tgov_res['items']:
        assert item['source_id'] == 'transferegov'
        assert item['dataset'] == 'transferegov'

    # Verify /api/imports filtering for obrasgov
    ogov_res = client.get('/api/imports', params={'source': 'obrasgov'}).json()
    assert ogov_res['total'] == 2
    for item in ogov_res['items']:
        assert item['source_id'] == 'obrasgov'
        assert item['dataset'] == 'obrasgov'

    # Verify /api/coverage attribution and last_attempt
    cov = client.get('/api/coverage').json()
    tgov_source = next(s for s in cov['sources'] if s['id'] == 'transferegov')
    ogov_source = next(s for s in cov['sources'] if s['id'] == 'obrasgov')
    other_source = next(s for s in cov['sources'] if s['id'] == 'other')

    assert tgov_source['last_attempt'] is not None
    assert tgov_source['last_attempt']['source_id'] == 'transferegov'
    assert ogov_source['last_attempt'] is not None
    assert ogov_source['last_attempt']['source_id'] == 'obrasgov'
    assert other_source['last_attempt'] is None

