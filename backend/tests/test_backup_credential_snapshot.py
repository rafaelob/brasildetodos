"""Issue #5: synthetic credentials and real SQLite WAL; no private production data."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from sqlalchemy import delete
from bdt import backup
from bdt.storage import User, LoginSession, RecoveryCode


@pytest.fixture
def private_source(database):
    with database.session() as session:
        session.add(User(id='synthetic-owner', username='synthetic_owner',
                         password_hash='synthetic-not-a-login-hash'))
        session.flush()
        session.add(LoginSession(token_hash='synthetic-session',
                                 user_id='synthetic-owner', expires_at=9000000000))
        session.add(RecoveryCode(user_id='synthetic-owner',
            digest=hashlib.sha256(b'SYNTHETIC-recovery-code').hexdigest(),
            created_at=1, expires_at=9000000000, version=1))
    return Path(database.engine.url.database)


def test_restore_cannot_resurrect_a_consumed_recovery_code(private_source, database, tmp_path):
    folder = tmp_path / 'backup'
    manifest = backup.create_backup(private_source, folder)
    with database.session() as session:
        session.execute(delete(RecoveryCode))
    target = tmp_path / 'restored.db'
    receipt = backup.restore_backup(folder, target)
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute('SELECT count(*) FROM recovery_codes').fetchone() == (0,)
        assert connection.execute('SELECT count(*) FROM sessions').fetchone() == (0,)
        assert connection.execute('SELECT count(*) FROM users').fetchone() == (1,)
    assert receipt['recovery_codes_revoked'] is True
    assert backup.sha256(folder / 'database.sqlite') == manifest['sha256']
    with closing(sqlite3.connect(folder / 'database.sqlite')) as connection:
        assert connection.execute('SELECT count(*) FROM recovery_codes').fetchone() == (1,)


def test_restore_older_schema_without_recovery_table(private_source, tmp_path):
    with closing(sqlite3.connect(private_source)) as connection:
        connection.execute('DROP TABLE recovery_codes')
        connection.commit()
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    target = tmp_path / 'restored.db'
    backup.restore_backup(folder, target)
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute('SELECT count(*) FROM sessions').fetchone() == (0,)
        assert connection.execute('SELECT count(*) FROM users').fetchone() == (1,)


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
@pytest.mark.parametrize('dangling_symlink', [False, True])
def test_manifest_does_not_cover_sqlite_sidecars(private_source, tmp_path, suffix, dangling_symlink):
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    sidecar = folder / ('database.sqlite' + suffix)
    if dangling_symlink:
        sidecar.symlink_to(tmp_path / 'absent-sidecar')
    else:
        sidecar.write_bytes(b'SYNTHETIC-unmanifested-sidecar')
    target = tmp_path / 'restored.db'
    with pytest.raises(ValueError, match='backup_sidecar_not_allowed'):
        backup.verify_backup(folder)
    with pytest.raises(ValueError, match='backup_sidecar_not_allowed'):
        backup.restore_backup(folder, target)
    assert not target.exists()


def test_committed_wal_cannot_overlay_a_valid_main_file_hash(private_source, tmp_path):
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    snapshot = folder / 'database.sqlite'
    # Freeze a legitimate checkpoint and hash. Later committed WAL pages do not
    # change these main-file bytes, but a plain mode=ro connection reads them.
    with closing(sqlite3.connect(snapshot)) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        manifest_path = folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest.update(sha256=backup.sha256(snapshot), bytes=snapshot.stat().st_size)
        manifest_path.write_text(json.dumps(manifest))
        writer.execute("UPDATE users SET role='reviewer' WHERE id='synthetic-owner'")
        writer.commit()
        assert backup.sha256(snapshot) == manifest['sha256']
        target = tmp_path / 'restored.db'
        with pytest.raises(ValueError, match='backup_sidecar_not_allowed'):
            backup.restore_backup(folder, target)
        assert not target.exists()


def test_late_sidecar_after_verification_never_publishes(private_source, tmp_path, monkeypatch):
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    real_verify = backup.verify_backup
    def verify_then_add_sidecar(path):
        manifest = real_verify(path)
        (path / 'database.sqlite-wal').write_bytes(b'SYNTHETIC-late-sidecar')
        return manifest
    monkeypatch.setattr(backup, 'verify_backup', verify_then_add_sidecar)
    target = tmp_path / 'restored.db'
    with pytest.raises(ValueError, match='backup_sidecar_not_allowed'):
        backup.restore_backup(folder, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.bdt-private-restore-*'))


def test_snapshot_connection_ignores_wal_inserted_after_sidecar_check(private_source, tmp_path, monkeypatch):
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    snapshot = folder / 'database.sqlite'
    # A closed, checkpointed WAL-mode database has no sidecars. Opening the
    # sealed main file must not discover a writer's journal added after the gate.
    with closing(sqlite3.connect(snapshot)) as connection:
        connection.execute('PRAGMA journal_mode=WAL')
    assert not Path(str(snapshot) + '-wal').exists()
    real_connect = sqlite3.connect
    writers = []
    def connect_then_inject(*args, **kwargs):
        reader = real_connect(*args, **kwargs)
        if str(args[0]).startswith('file:'):
            writer = real_connect(snapshot)
            writers.append(writer)
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute("UPDATE users SET role='reviewer' WHERE id='synthetic-owner'")
            writer.commit()
        return reader
    monkeypatch.setattr(backup.sqlite3, 'connect', connect_then_inject)
    try:
        with closing(backup.readonly(snapshot, snapshot=True)) as reader:
            assert Path(str(snapshot) + '-wal').is_file()
            assert reader.execute('SELECT role FROM users').fetchone() == ('contributor',)
    finally:
        for writer in writers:
            writer.close()


def test_late_sidecar_during_copy_never_publishes(private_source, tmp_path, monkeypatch):
    folder = tmp_path / 'backup'
    backup.create_backup(private_source, folder)
    real_copy = backup.copy_online
    def copy_then_add_sidecar(*args, **kwargs):
        real_copy(*args, **kwargs)
        (folder / 'database.sqlite-shm').write_bytes(b'SYNTHETIC-late-sidecar')
    monkeypatch.setattr(backup, 'copy_online', copy_then_add_sidecar)
    target = tmp_path / 'restored.db'
    with pytest.raises(ValueError, match='backup_sidecar_not_allowed'):
        backup.restore_backup(folder, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.bdt-private-restore-*'))


def test_failed_code_revocation_never_installs_partial_restore(private_source, tmp_path):
    with closing(sqlite3.connect(private_source)) as connection:
        connection.executescript('''
            CREATE TRIGGER synthetic_refuse_revoke BEFORE DELETE ON recovery_codes
            BEGIN SELECT RAISE(ABORT, 'synthetic_revocation_failure'); END;
        ''')
    folder = tmp_path / 'backup'
    manifest = backup.create_backup(private_source, folder)
    target = tmp_path / 'restored.db'
    with pytest.raises(sqlite3.IntegrityError, match='synthetic_revocation_failure'):
        backup.restore_backup(folder, target)
    assert not target.exists()
    assert not list(tmp_path.glob('.bdt-private-restore-*'))
    assert backup.sha256(folder / 'database.sqlite') == manifest['sha256']
