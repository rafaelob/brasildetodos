"""Author contest of a rejected observation: one re-review, independent reviewer only."""
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from bdt.api import create_app, password_hash
from bdt.evidence import Audit
from bdt.storage import Observation, User

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'synthetic-password-only'
BODY = 'Synthetic description of the sign at the public entrance.'
NOTE = 'The original rejection did not match the documented synthetic entrance sign.'
REVIEW_NOTE = 'Not suitable for this synthetic test.'
SECOND_NOTE = 'Independent re-review of the contested synthetic observation.'


@pytest.fixture
def client(database, stored, monkeypatch):
    monkeypatch.setenv('BDT_ALLOW_REGISTRATION', '1')
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        yield client


def register(client, name='reader'):
    assert client.post('/api/auth/register', headers=HEAD, json={'username': name, 'password': PASSWORD}).status_code == 201


def login(client, name='reader'):
    response = client.post('/api/auth/login', headers=HEAD, json={'username': name, 'password': PASSWORD})
    assert response.status_code == 200
    return response


def add_reviewer(database, name='reviewer'):
    with database.session() as session:
        session.add(User(username=name, password_hash=password_hash(PASSWORD), role='reviewer'))


def observation():
    return {'place_id': 'test:school', 'mode': 'field', 'observed_on': '2025-01-01', 'body': BODY, 'consent': True}


def contest(client, observation_id, note=NOTE):
    return client.post(f'/api/observations/{observation_id}/contest', headers=HEAD, json={'note': note})


def submit(client):
    response = client.post('/api/observations', headers=HEAD, json=observation())
    assert response.status_code == 201
    return response.json()['id']


def reject(client, observation_id, note=REVIEW_NOTE):
    response = client.post(f'/api/review/{observation_id}', headers=HEAD, json={'decision': 'rejected', 'note': note})
    assert response.status_code == 200
    return response


def public_ids(payload):
    return set(payload) & {'author_id', 'previous_reviewer_id', 'reviewer_id', 'contest_count'}


def rejected_owned(client, database):
    register(client)
    login(client)
    identity = submit(client)
    client.post('/api/auth/logout', headers=HEAD)
    add_reviewer(database)
    add_reviewer(database, 'other_reviewer')
    login(client, 'reviewer')
    reject(client, identity)
    client.post('/api/auth/logout', headers=HEAD)
    login(client)
    return identity


def test_author_contests_rejected_appears_in_second_reviewer_queue(client, database):
    identity = rejected_owned(client, database)
    response = contest(client, identity)
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'pending' and payload['contested'] is True
    assert payload['reviewed_at'] is None
    assert public_ids(payload) == set()
    assert client.get('/api/places/test:school').json()['observations'] == []
    mine = client.get('/api/observations/mine').json()[0]
    assert mine['status'] == 'pending' and mine['contested'] is True and mine['review_note'] == REVIEW_NOTE
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'other_reviewer')
    queue = client.get('/api/review').json()
    assert len(queue) == 1 and queue[0]['id'] == identity and queue[0]['contested'] is True
    assert public_ids(queue[0]) == set()
    with database.session() as session:
        row = session.get(Observation, identity)
        original = session.scalar(select(User).where(User.username == 'reviewer'))
        assert row.status == 'pending' and row.contest_count == 1
        assert row.previous_reviewer_id == original.id and row.reviewer_id is None
        assert row.review_note == REVIEW_NOTE and row.payload['body'] == BODY


def test_original_reviewer_cannot_decide_contest(client, database):
    identity = rejected_owned(client, database)
    assert contest(client, identity).status_code == 200
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    blocked = client.post(f'/api/review/{identity}', headers=HEAD,
                          json={'decision': 'approved', 'note': SECOND_NOTE})
    assert blocked.status_code == 403 and blocked.json() == {'detail': 'independent_review_required'}
    assert client.get('/api/places/test:school').json()['observations'] == []


def test_second_reviewer_can_reject_or_approve(client, database):
    first = rejected_owned(client, database)
    assert contest(client, first).status_code == 200
    client.post('/api/auth/logout', headers=HEAD)
    login(client)
    second = submit(client)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    reject(client, second)
    client.post('/api/auth/logout', headers=HEAD)
    login(client)
    assert contest(client, second).status_code == 200
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'other_reviewer')
    rejected = client.post(f'/api/review/{first}', headers=HEAD,
                           json={'decision': 'rejected', 'note': SECOND_NOTE})
    assert rejected.status_code == 200 and rejected.json()['status'] == 'rejected'
    assert rejected.json()['contested'] is True
    assert public_ids(rejected.json()) == set()
    approved = client.post(f'/api/review/{second}', headers=HEAD,
                           json={'decision': 'approved', 'note': SECOND_NOTE})
    assert approved.status_code == 200 and approved.json()['status'] == 'approved'
    public = client.get('/api/places/test:school').json()['observations']
    assert len(public) == 1 and public[0]['id'] == second and public[0]['contested'] is True
    assert public_ids(public[0]) == set()


def test_self_review_remains_forbidden_after_contest(client, database):
    add_reviewer(database, 'author_reviewer')
    add_reviewer(database, 'first_reviewer')
    login(client, 'author_reviewer')
    identity = submit(client)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'first_reviewer')
    reject(client, identity)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'author_reviewer')
    assert contest(client, identity).status_code == 200
    blocked = client.post(f'/api/review/{identity}', headers=HEAD,
                          json={'decision': 'approved', 'note': SECOND_NOTE})
    assert blocked.status_code == 403 and blocked.json() == {'detail': 'self_review_forbidden'}


def test_second_contest_conflict(client, database):
    identity = rejected_owned(client, database)
    assert contest(client, identity).status_code == 200
    again = contest(client, identity)
    assert again.status_code == 409 and again.json() == {'detail': 'already_contested'}
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'other_reviewer')
    assert client.post(f'/api/review/{identity}', headers=HEAD,
                       json={'decision': 'rejected', 'note': SECOND_NOTE}).status_code == 200
    client.post('/api/auth/logout', headers=HEAD)
    login(client)
    after_second_reject = contest(client, identity)
    assert after_second_reject.status_code == 409
    assert after_second_reject.json() == {'detail': 'already_contested'}


def test_contest_requires_csrf_and_authentication(client):
    path = '/api/observations/00000000-0000-0000-0000-000000000001/contest'
    body = {'note': NOTE}
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, headers=HEAD, json=body).status_code == 401
    register(client)
    assert client.post(path, json=body).status_code == 403
    assert client.post(path, headers=HEAD, json=body).status_code == 401


def test_contest_is_uniform_not_found_for_missing_and_foreign(client, database):
    register(client, 'owner')
    login(client, 'owner')
    identity = submit(client)
    client.post('/api/auth/logout', headers=HEAD)
    add_reviewer(database)
    login(client, 'reviewer')
    reject(client, identity)
    client.post('/api/auth/logout', headers=HEAD)
    register(client, 'other')
    login(client, 'other')
    missing = contest(client, '00000000-0000-0000-0000-000000000001')
    foreign = contest(client, identity)
    assert missing.status_code == 404 and missing.json() == {'detail': 'observation_not_found'}
    assert foreign.status_code == 404 and foreign.json() == missing.json()


def test_pending_approved_withdrawn_retracted_are_not_contestable(client, database):
    register(client)
    login(client)
    pending = submit(client)
    pending_contest = contest(client, pending)
    assert pending_contest.status_code == 409 and pending_contest.json() == {'detail': 'not_rejected'}
    client.post('/api/auth/logout', headers=HEAD)
    add_reviewer(database)
    add_reviewer(database, 'other_reviewer')
    login(client)
    approved = submit(client)
    withdrawn = submit(client)
    retracted = submit(client)
    rejected = submit(client)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    assert client.post(f'/api/review/{approved}', headers=HEAD,
                       json={'decision': 'approved', 'note': SECOND_NOTE}).status_code == 200
    assert client.post(f'/api/review/{retracted}', headers=HEAD,
                       json={'decision': 'approved', 'note': SECOND_NOTE}).status_code == 200
    assert client.post(f'/api/moderation/observations/{retracted}/retract', headers=HEAD,
                       json={'note': NOTE}).status_code == 200
    reject(client, rejected)
    client.post('/api/auth/logout', headers=HEAD)
    login(client)
    assert client.post(f'/api/observations/{withdrawn}/withdraw', headers=HEAD).status_code == 200
    for identity in (approved, withdrawn, retracted):
        response = contest(client, identity)
        assert response.status_code == 409 and response.json() == {'detail': 'not_rejected'}
    assert contest(client, rejected).status_code == 200


def test_contest_rate_limited(client):
    register(client)
    login(client)
    identity = submit(client)
    codes = [contest(client, identity).status_code for _ in range(6)]
    assert codes[:5] == [409, 409, 409, 409, 409]
    assert codes[5] == 429
    limited = contest(client, identity)
    assert limited.status_code == 429 and limited.headers.get('retry-after')
    assert limited.json() == {'detail': 'rate_limited'}


def test_contest_audit_omits_observation_body(client, database, caplog):
    caplog.set_level(logging.DEBUG)
    identity = rejected_owned(client, database)
    assert contest(client, identity).status_code == 200
    with database.session() as session:
        rows = list(session.scalars(select(Audit).where(Audit.entity_id == identity)))
        actions = [row.action for row in rows]
        assert 'contest_requested' in actions and 'rejected' in actions
        contested = next(row for row in rows if row.action == 'contest_requested')
        detail = contested.detail if contested.detail is not None else {}
        assert BODY not in str(detail) and BODY not in str(contested.__dict__)
        assert 'observation' not in detail and 'payload' not in detail and 'body' not in detail
    assert BODY not in caplog.text


def test_disabled_author_cannot_contest(client, database):
    identity = rejected_owned(client, database)
    with database.session() as session:
        session.scalar(select(User).where(User.username == 'reader')).role = 'disabled'
    assert contest(client, identity).status_code == 401
    with database.session() as session:
        row = session.get(Observation, identity)
        assert row.status == 'rejected' and row.contest_count == 0


def test_short_contest_note_is_rejected(client, database):
    identity = rejected_owned(client, database)
    response = contest(client, identity, note='too short')
    assert response.status_code == 422
    with database.session() as session:
        row = session.get(Observation, identity)
        assert row.status == 'rejected' and row.contest_count == 0


def test_concurrent_contest_has_one_winner(client, database):
    identity = rejected_owned(client, database)
    token = client.cookies['bdt_session']
    app = client.app
    barrier = Barrier(2)

    def attempt(_):
        extra = TestClient(app)
        extra.cookies.set('bdt_session', token)
        barrier.wait()
        return extra.post(f'/api/observations/{identity}/contest', headers=HEAD, json={'note': NOTE}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    assert sorted(results) == [200, 409]
    with database.session() as session:
        row = session.get(Observation, identity)
        assert row.status == 'pending' and row.contest_count == 1
        assert row.previous_reviewer_id is not None and row.reviewer_id is None
