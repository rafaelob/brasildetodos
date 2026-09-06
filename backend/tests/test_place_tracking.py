"""Synthetic lifecycle/privilege fixtures only; these do not certify any service."""
import copy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from bdt.api import create_app
from bdt.domain import now
from bdt.place_tracking import WatchRequest, watch_summary, install
from bdt.storage import Change, Ingestion, LoginSession, Observation, Place, User, upsert_place


@pytest.fixture
def client(database):
    app = create_app(str(database.engine.url), testing=True)
    # Explicit test-only router; production API registration remains pending.
    install(app, app.state.database)
    with TestClient(app) as client:
        yield client


def summary(client, ids, **extra):
    return client.post('/api/saved-places/summary', json={'place_ids': ids, **extra}, headers={'X-BDT-Client': 'web'})


def test_initial_is_started_not_a_claim_of_change(stored, client):
    response = summary(client, [stored.id])
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    result = response.json()
    assert result['favorites_persisted'] is False and result['scope'] == 'loaded_records_only'
    row = result['items'][0]
    assert row['status'] == 'available' and row['place']['latitude'] is None
    assert row['history']['total_versions'] == 1
    assert row['history']['versions'][0]['type'] == 'started'
    assert row['history']['versions'][0]['fields'] == []


def test_public_field_differences_have_their_own_source(stored, database, client):
    later = stored.model_copy(update={'address': 'Novo endereço sintético', 'source': stored.source.model_copy(update={'reference_date': '2026'})})
    with database.session() as session: upsert_place(session, later)
    result = summary(client, [stored.id]).json()['items'][0]['history']
    assert result['total_versions'] == result['included'] == 2
    version = result['versions'][0]
    assert version['type'] == 'updated' and version['source']['reference_date'] == '2026'
    assert {field['key'] for field in version['fields']} == {'address', 'source.reference_date'}
    assert version['fields'][0]['before'] == ''


def test_identical_reload_does_not_invent_history(stored, database, client):
    fresh = stored.model_copy(update={'source': stored.source.model_copy(update={'collected_at': now(), 'snapshot_sha256': 'b'*64})})
    with database.session() as session: assert upsert_place(session, fresh) == 'unchanged'
    row = summary(client, [stored.id]).json()['items'][0]
    assert row['history']['total_versions'] == 1
    assert row['place']['source']['snapshot_sha256'] == 'b'*64
    assert row['history']['versions'][0]['source']['snapshot_sha256'] == 'a'*64


def test_missing_outside_profile_and_duplicate_ids(stored, database, client):
    with database.session() as session: upsert_place(session, stored.model_copy(update={'catalogue_eligible': False}))
    rows = summary(client, ['missing:one', stored.id, stored.id]).json()['items']
    assert [row['id'] for row in rows] == ['missing:one', stored.id]
    assert rows[0]['status'] == 'not_found' and rows[0]['history'] is None
    assert rows[1]['status'] == 'outside_current_profile'
    assert rows[1]['place']['catalogue_eligible'] is False


def test_window_is_bounded_but_counts_are_not(stored, database, client):
    for index in range(7):
        with database.session() as session: upsert_place(session, stored.model_copy(update={'address': f'Mudança {index}'}))
    row = summary(client, [stored.id], versions_per_place=2).json()['items'][0]
    assert row['history']['total_versions'] == 8 and row['history']['included'] == 2
    assert row['history']['truncated'] is True
    assert row['history']['versions'][0]['fields'][0]['after'] == 'Mudança 6'


def test_no_accounts_favorites_or_private_observations_are_written(stored, database, client):
    with database.session() as session:
        session.add(User(id='test-author', username='fixture', password_hash='NOT_REAL'))
        session.flush()
        session.add(Observation(id='private', place_id=stored.id, author_id='test-author', status='pending', payload={'body': 'DO_NOT_EXPORT'}))
    before = None
    with database.session() as session:
        before = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in (User, LoginSession, Observation, Change)}
    response = summary(client, [stored.id])
    assert 'DO_NOT_EXPORT' not in response.text and 'test-author' not in response.text
    with database.session() as session:
        assert before == {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in (User, LoginSession, Observation, Change)}


def test_legacy_extra_keys_are_not_copied(stored, database, client):
    with database.session() as session:
        row = session.get(Place, stored.id); raw = copy.deepcopy(row.payload)
        raw['private_raw'] = 'DO_NOT_EXPORT'; raw['source']['internal_path'] = 'DO_NOT_EXPORT'; row.payload = raw
        version = session.scalar(select(Change)); other = copy.deepcopy(version.after)
        other['private_raw'] = 'DO_NOT_EXPORT'; version.after = other
    response = summary(client, [stored.id])
    assert response.status_code == 200 and 'DO_NOT_EXPORT' not in response.text
    assert response.json()['items'][0]['status'] == 'available'


def test_corrupt_one_item_does_not_hide_valid_others(stored, database, client):
    other = stored.model_copy(update={'id': 'test:other'})
    with database.session() as session:
        upsert_place(session, other)
        row = session.get(Place, stored.id); row.payload = row.payload | {'id': 'wrong:id'}
    rows = summary(client, [stored.id, other.id]).json()['items']
    assert rows[0]['status'] == 'unavailable' and rows[0]['place'] is None
    assert rows[1]['status'] == 'available'


def test_source_revision_is_not_called_service_change(stored, database, client):
    value = stored.model_copy(update={'source': stored.source.model_copy(update={'url': 'https://example.org/new-source'})})
    with database.session() as session: upsert_place(session, value)
    version = summary(client, [stored.id]).json()['items'][0]['history']['versions'][0]
    assert version['type'] == 'source_revision' and version['fields'] == []


@pytest.mark.parametrize('payload', [
    {'place_ids': []}, {'place_ids': ['test:x']*31}, {'place_ids': [123]},
    {'place_ids': ['not-an-id']}, {'place_ids': ['test:'+('x'*181)]},
    {'place_ids': ['test:x'], 'versions_per_place': 0},
    {'place_ids': ['test:x'], 'versions_per_place': 6},
    {'place_ids': ['test:x'], 'versions_per_place': True},
    {'place_ids': ['test:x'], 'versions_per_place': '3'},
    {'place_ids': ['test:x'], 'private_token': 'DO_NOT_ECHO'},
])
def test_request_limits_and_no_echo(client, payload):
    response = client.post('/api/saved-places/summary', json=payload, headers={'X-BDT-Client': 'web'})
    assert response.status_code == 422 and 'DO_NOT_ECHO' not in response.text


def test_origin_and_header_guards_are_retained(client):
    payload = {'place_ids': ['test:x']}
    assert client.post('/api/saved-places/summary', json=payload).status_code == 403
    assert client.post('/api/saved-places/summary', json=payload, headers={'X-BDT-Client': 'web', 'Origin': 'https://example.net'}).status_code == 403


def test_two_selects_instead_of_per_place_queries(stored, database):
    with database.session() as session:
        for i in range(29): upsert_place(session, stored.model_copy(update={'id': f'test:p{i}'}))
    statements = []
    def record(_conn, _cursor, statement, *_):
        if statement.lstrip().upper().startswith('SELECT'): statements.append(statement)
    event.listen(database.engine, 'before_cursor_execute', record)
    try: result = watch_summary(database, WatchRequest(place_ids=[stored.id]+[f'test:p{i}' for i in range(29)]))
    finally: event.remove(database.engine, 'before_cursor_execute', record)
    assert len(result['items']) == 30 and len(statements) == 2


def test_no_history_is_explicit_not_a_manufactured_initial_event(stored, database, client):
    from sqlalchemy import delete
    with database.session() as session: session.execute(delete(Change).where(Change.place_id == stored.id))
    history = summary(client, [stored.id]).json()['items'][0]['history']
    assert history == {'total_versions': 0, 'included': 0, 'truncated': False, 'first_recorded_at': None, 'versions': []}


def test_missing_historical_source_does_not_get_published(stored, database, client):
    with database.session() as session:
        row = session.scalar(select(Change)); row.after = row.after | {'source': None}
    result = summary(client, [stored.id]).json()['items'][0]
    assert result['status'] == 'unavailable' and result['history'] is None


def test_malformed_history_date_is_unknown_not_leaked(stored, database, client):
    with database.session() as session:
        row = session.scalar(select(Change)); row.at = '/private/timestamp'
    response = summary(client, [stored.id])
    assert '/private/' not in response.text
    assert response.json()['items'][0]['history']['versions'][0]['recorded_at'] is None


def test_batch_read_is_not_available_with_identifiers_in_query_url(stored, client):
    assert client.get('/api/saved-places/summary', params={'place_ids': stored.id}).status_code == 405


def test_reference_period_only_is_a_source_revision(stored, database, client):
    replacement = stored.model_copy(update={'source': stored.source.model_copy(update={'reference_date': '2026'})})
    with database.session() as session:
        upsert_place(session, replacement)
    version = summary(client, [stored.id]).json()['items'][0]['history']['versions'][0]
    assert version['type'] == 'source_revision'
    assert version['fields'] == [{'key': 'source.reference_date', 'before': '2025', 'after': '2026'}]
    assert version['previous_source']['reference_date'] == '2025'
    assert version['source']['reference_date'] == '2026'


@pytest.mark.parametrize('column,value', [('name', 'Different stored name'), ('state', 'SP'),
    ('kind', 'health'), ('dataset', 'another-source'), ('latitude', -15.0),
    ('fingerprint', 'f'*64)])
def test_mismatched_stored_columns_are_not_published(stored, database, client, column, value):
    with database.session() as session:
        setattr(session.get(Place, stored.id), column, value)
    row = summary(client, [stored.id]).json()['items'][0]
    assert row['status'] == 'unavailable' and row['place'] is None and row['history'] is None


def test_history_must_describe_the_current_semantic_record(stored, database, client):
    with database.session() as session:
        change = session.scalar(select(Change))
        change.after = change.after | {'address': 'Inconsistent historical address'}
    row = summary(client, [stored.id]).json()['items'][0]
    assert row['status'] == 'unavailable'


def test_previous_source_is_projected_and_initial_has_none(stored, database, client):
    assert summary(client, [stored.id]).json()['items'][0]['history']['versions'][0]['previous_source'] is None
    with database.session() as session:
        upsert_place(session, stored.model_copy(update={'address': 'Another public address'}))
    with database.session() as session:
        row = session.scalar(select(Change).order_by(Change.at.desc(), Change.id.desc()).limit(1))
        before = copy.deepcopy(row.before)
        before['source']['private_path'] = 'DO_NOT_PUBLISH'
        before['extra_internal'] = 'DO_NOT_PUBLISH'
        row.before = before
    response = summary(client, [stored.id])
    assert 'DO_NOT_PUBLISH' not in response.text
    assert response.json()['items'][0]['history']['versions'][0]['previous_source'] == stored.source.model_dump(mode='json')


def test_concurrent_import_cannot_mix_place_and_history_snapshots(stored, database):
    fired = False
    def concurrent_change(_connection, _cursor, statement, *_):
        nonlocal fired
        # First SELECT already read the old place. Commit an update with a
        # separate connection before the second SELECT of the reader.
        if not fired and statement.lstrip().upper().startswith('SELECT') and 'row_number()' in statement:
            fired = True
            with database.session() as session:
                upsert_place(session, stored.model_copy(update={'address': 'Later committed version'}))
    event.listen(database.engine, 'before_cursor_execute', concurrent_change)
    try:
        result = watch_summary(database, WatchRequest(place_ids=[stored.id]))
    finally:
        event.remove(database.engine, 'before_cursor_execute', concurrent_change)
    item = result['items'][0]
    assert fired and item['status'] == 'available'
    assert item['place']['address'] == stored.address
    assert item['history']['total_versions'] == 1
    fresh = watch_summary(database, WatchRequest(place_ids=[stored.id]))['items'][0]
    assert fresh['place']['address'] == 'Later committed version'
    assert fresh['history']['total_versions'] == 2
