"""Account recovery: digest-only codes, no auto-login, uniform failures."""
import logging
import threading
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.api import create_app, password_hash
from bdt.catalog_release import EXCLUDED, TABLES, export_catalog
from bdt.evidence import Audit, initialize_extensions
from bdt.recovery import code_digest, issue_code, take_code
from bdt.storage import LoginSession, RecoveryCode, User

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'synthetic-password-only'
NEW = 'synthetic-password-next'


@pytest.fixture
def client(database, stored, monkeypatch):
    monkeypatch.setenv('BDT_ALLOW_REGISTRATION', '1')
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        yield client


def register(client, name='alice'):
    assert client.post('/api/auth/register', headers=HEAD, json={'username': name, 'password': PASSWORD}).status_code == 201


def login(client, name='alice', password=PASSWORD):
    return client.post('/api/auth/login', headers=HEAD, json={'username': name, 'password': password})


def prepare(client, password=PASSWORD):
    return client.post('/api/auth/recovery/prepare', headers=HEAD, json={'password': password})


def revoke(client, password=PASSWORD):
    return client.post('/api/auth/recovery/revoke', headers=HEAD, json={'password': password})


def consume(client, username, code, new_password=NEW):
    return client.post('/api/auth/recovery/consume', headers=HEAD,
                       json={'username': username, 'code': code, 'new_password': new_password})


def invalid(response):
    assert response.status_code == 401
    assert response.json() == {'detail': 'invalid_credentials'}


def test_prepare_requires_auth_csrf_and_password(client):
    assert client.post('/api/auth/recovery/prepare', json={'password': PASSWORD}).status_code == 403
    assert client.post('/api/auth/recovery/prepare', headers=HEAD, json={'password': PASSWORD}).status_code == 401
    register(client); login(client)
    assert prepare(client, 'wrong-password-long').status_code == 403
    assert prepare(client, 'wrong-password-long').json() == {'detail': 'reauthentication_failed'}


def test_prepare_returns_code_once_and_stores_digest_only(client, database, caplog):
    caplog.set_level(logging.DEBUG)
    register(client); login(client)
    response = prepare(client)
    assert response.status_code == 200
    payload = response.json()
    code = payload['code']
    assert len(code) >= 43 and payload['version'] == 1 and payload['ttl_seconds'] > 0
    assert payload['expires_at'] > int(time.time())
    with database.session() as session:
        row = session.scalar(select(RecoveryCode))
        assert row.digest == code_digest(code) and code not in row.digest
        assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 1
        audits = list(session.scalars(select(Audit)))
        assert code not in str([item.detail for item in audits])
    assert code not in caplog.text
    exported = client.get('/api/account/export').json()
    assert code not in str(exported) and 'credentials_included' in exported


def test_rotate_and_revoke_invalidate_previous_codes(client):
    register(client); login(client)
    first = prepare(client).json()['code']
    second = prepare(client).json()['code']
    assert first != second
    invalid(consume(client, 'alice', first))
    assert revoke(client).json() == {'status': 'revoked'}
    invalid(consume(client, 'alice', second))


def test_consume_resets_password_without_auto_login(client, database):
    register(client); login(client)
    other = TestClient(client.app)
    assert login(other, 'alice').status_code == 200
    code = prepare(client).json()['code']
    assert client.get('/api/auth/me').status_code == 200
    response = consume(client, 'alice', code)
    assert response.status_code == 200
    assert response.json() == {'status': 'password_reset'}
    assert 'set-cookie' not in response.headers
    assert client.get('/api/auth/me').status_code == 401
    assert other.get('/api/auth/me').status_code == 401
    invalid(login(client, 'alice', PASSWORD))
    assert login(client, 'alice', NEW).status_code == 200
    assert client.get('/api/auth/me').json() == {'username': 'alice', 'role': 'contributor'}
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0
        assert session.scalar(select(func.count()).select_from(LoginSession)) == 1


def test_replay_unknown_expired_and_wrong_code_are_generic(client, database):
    register(client); login(client)
    code = prepare(client).json()['code']
    assert consume(client, 'alice', code).status_code == 200
    invalid(consume(client, 'alice', code))
    invalid(consume(client, 'missinguser', 'x' * 43))
    invalid(consume(client, 'alice', 'not-the-stored-code-value'))
    with database.session() as session:
        user = session.scalar(select(User).where(User.username == 'alice'))
        session.add(RecoveryCode(user_id=user.id, digest=code_digest('expired-recovery-cd'),
                                 expires_at=int(time.time()) - 10, version=1, created_at=1))
    invalid(consume(client, 'ALICE', 'expired-recovery-cd'))
    assert consume(client, 'alice', 'short').status_code == 422


def test_disabled_account_cannot_revive_and_codes_are_purged(client, database):
    register(client); login(client)
    code = prepare(client).json()['code']
    with database.session() as session:
        session.scalar(select(User).where(User.username == 'alice')).role = 'disabled'
    invalid(consume(client, 'alice', code))
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0
        assert session.scalar(select(User).where(User.username == 'alice')).role == 'disabled'


def test_two_users_are_isolated_and_role_change_does_not_block(client, database):
    register(client, 'alice'); register(client, 'bob')
    login(client, 'alice'); alice_code = prepare(client).json()['code']
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'bob'); bob_code = prepare(client).json()['code']
    invalid(consume(client, 'bob', alice_code))
    with database.session() as session:
        session.scalar(select(User).where(User.username == 'alice')).role = 'reviewer'
    assert consume(client, 'alice', alice_code).status_code == 200
    assert login(client, 'alice', NEW).json()['role'] == 'reviewer'
    invalid(consume(client, 'alice', bob_code))


def test_consume_requires_csrf_and_does_not_echo_secrets(client):
    register(client)
    body = {'username': 'alice', 'code': 'synthetic-recovery-code', 'new_password': NEW}
    assert client.post('/api/auth/recovery/consume', json=body).status_code == 403
    assert client.get('/api/auth/recovery/consume').status_code == 405
    response = client.post('/api/auth/recovery/consume', headers=HEAD, json=body | {'private_token': 'DO_NOT_ECHO'})
    assert response.status_code == 422 and 'DO_NOT_ECHO' not in response.text and NEW not in response.text


def test_consume_rate_limit_matches_login_window(client):
    body = {'username': 'nobody', 'code': 'x' * 43, 'new_password': NEW}
    for _ in range(20):
        invalid(client.post('/api/auth/recovery/consume', headers=HEAD, json=body))
    limited = client.post('/api/auth/recovery/consume', headers=HEAD, json=body)
    assert limited.status_code == 429 and limited.headers.get('retry-after')


def test_saved_places_summary_rate_limit(client, stored):
    payload = {'place_ids': [stored.id]}
    assert client.post('/api/saved-places/summary', json=payload).status_code == 403
    for _ in range(60):
        assert client.post('/api/saved-places/summary', headers=HEAD, json=payload).status_code == 200
    limited = client.post('/api/saved-places/summary', headers=HEAD, json=payload)
    assert limited.status_code == 429 and limited.headers.get('retry-after')


def test_catalog_release_omits_recovery_codes(database, stored, tmp_path):
    initialize_extensions(database)
    digest = code_digest('synthetic-recovery-code-value')
    with database.session() as session:
        session.add(User(id='private-user', username='hidden-owner', password_hash='NOT_EXPORTED'))
        session.flush()
        session.add(RecoveryCode(user_id='private-user', digest=digest, expires_at=9_000_000_000,
                                 version=1, created_at=1))
    assert 'recovery_codes' in EXCLUDED
    assert all(table.name != 'recovery_codes' for table in TABLES)
    folder = tmp_path / 'release'
    manifest = export_catalog(database, folder, 'a' * 40)
    combined = ''.join(path.read_text(encoding='utf-8') for path in folder.iterdir())
    assert digest not in combined and 'hidden-owner' not in combined
    assert 'synthetic-recovery-code-value' not in combined
    assert manifest['excluded'] == EXCLUDED


def test_concurrent_take_code_only_one_succeeds(database):
    with database.session() as session:
        session.add(User(id='concurrent-user', username='alice', password_hash=password_hash(PASSWORD)))
        session.flush()
        plaintext, row = issue_code(session, 'concurrent-user')
        digest, user_id = row.digest, row.user_id
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        with database.session() as session:
            results.append(take_code(session, user_id, digest, int(time.time()) + 10))

    workers = [threading.Thread(target=worker) for _ in range(2)]
    for thread in workers:
        thread.start()
    for thread in workers:
        thread.join()
    assert sorted(results) == [False, True]
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0
    assert code_digest(plaintext) == digest
