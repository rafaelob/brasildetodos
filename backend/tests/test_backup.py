"""Synthetic private backups: online/WAL contents, recovery and no overwrite."""
import json
import os
import sqlite3
from pathlib import Path
from contextlib import closing
import pytest
from sqlalchemy import select
from bdt.backup import create_backup, restore_backup, verify_backup, sha256
from bdt.storage import User, LoginSession, Place, upsert_place


@pytest.fixture
def dbfile(database, place):
    with database.session() as session:
        upsert_place(session,place)
        session.add(User(id='backup-test-user',username='synthetic_backup',password_hash='synthetic-non-login-password'))
        session.flush()
        session.add(LoginSession(token_hash='synthetic-session',user_id='backup-test-user',expires_at=9000000000))
    return Path(database.engine.url.database)


def test_online_backup_restores_private_state_but_revokes_sessions(dbfile,tmp_path):
    folder=tmp_path/'backup';manifest=create_backup(dbfile,folder)
    assert manifest['contains_private_data'] is True and manifest['encrypted'] is False
    assert verify_backup(folder)==manifest
    if os.name != 'nt':
        assert folder.stat().st_mode & 0o777 == 0o700
        assert (folder/'database.sqlite').stat().st_mode & 0o777 == 0o600
    source_hash=sha256(folder/'database.sqlite')
    target=tmp_path/'restored.db';result=restore_backup(folder,target)
    assert result['sessions_revoked'] is True
    assert sha256(folder/'database.sqlite')==source_hash
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute('SELECT count(*) FROM users').fetchone()==(1,)
        assert connection.execute('SELECT count(*) FROM places').fetchone()==(1,)
        assert connection.execute('SELECT count(*) FROM sessions').fetchone()==(0,)
    with closing(sqlite3.connect(dbfile)) as connection:
        assert connection.execute('SELECT count(*) FROM sessions').fetchone()==(1,)


def test_backup_includes_committed_wal_data(dbfile,tmp_path):
    # Keep the connection open and disable automatic checkpointing, so a raw file
    # copy would miss this committed change. The online backup API must see it.
    with closing(sqlite3.connect(dbfile)) as writer:
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("UPDATE places SET name='WAL-only-name' WHERE id='test:school'");writer.commit()
        assert Path(str(dbfile)+'-wal').is_file()
        folder=tmp_path/'backup';create_backup(dbfile,folder)
        with closing(sqlite3.connect(folder/'database.sqlite')) as restored:
            assert restored.execute("SELECT name FROM places WHERE id='test:school'").fetchone()==('WAL-only-name',)


def test_no_overwrite_existing_backup_or_database(dbfile,tmp_path):
    folder=tmp_path/'backup';create_backup(dbfile,folder)
    original=(folder/'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):create_backup(dbfile,folder)
    assert (folder/'manifest.json').read_bytes()==original
    before=sha256(dbfile)
    with pytest.raises(FileExistsError):restore_backup(folder,dbfile)
    assert sha256(dbfile)==before


def test_failed_integrity_never_installs(dbfile,tmp_path):
    folder=tmp_path/'backup';create_backup(dbfile,folder)
    target=folder/'database.sqlite'
    content=bytearray(target.read_bytes());content[-1]^=1;target.write_bytes(content)
    with pytest.raises(ValueError,match='hash_mismatch'):restore_backup(folder,tmp_path/'invalid.db')
    assert not (tmp_path/'invalid.db').exists()


def test_missing_source_does_not_create_database(tmp_path):
    path=tmp_path/'missing.db'
    with pytest.raises(ValueError):create_backup(path,tmp_path/'backup')
    assert not path.exists() and not list(tmp_path.glob('.bdt-private-*'))


@pytest.mark.parametrize('value',[0,-1,3601])
def test_bounded_runtime(dbfile,tmp_path,value):
    with pytest.raises(ValueError):create_backup(dbfile,tmp_path/'backup',value)
    with pytest.raises(ValueError):restore_backup(tmp_path/'backup',tmp_path/'restored.db',value)


@pytest.mark.parametrize('mutation',[
    lambda m:m.update(format='other'),lambda m:m.update(schema_version=999),
    lambda m:m.update(schema_version=True),lambda m:m.update(encrypted=True),
    lambda m:m.update(restore_requires_new_destination=False),
    lambda m:m.update(contains_private_data=False),lambda m:m.update(bytes=True),
    lambda m:m.update(bytes=-1),lambda m:m.update(sha256='wrong'),
])
def test_manifest_validation(dbfile,tmp_path,mutation):
    folder=tmp_path/'backup';create_backup(dbfile,folder)
    path=folder/'manifest.json';manifest=json.loads(path.read_text());mutation(manifest);path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):verify_backup(folder)


def test_refuse_symlink(dbfile,tmp_path):
    link=tmp_path/'linked.db';link.symlink_to(dbfile)
    with pytest.raises(ValueError):create_backup(link,tmp_path/'backup')
    folder=tmp_path/'backup';create_backup(dbfile,folder)
    alias=tmp_path/'alias';alias.symlink_to(folder,target_is_directory=True)
    with pytest.raises(ValueError):verify_backup(alias)


def test_reject_unrelated_sqlite_database(tmp_path):
    path=tmp_path/'unrelated.db'
    with closing(sqlite3.connect(path)) as connection:connection.execute('CREATE TABLE unrelated (id integer)')
    with pytest.raises(ValueError,match='not_a_brasildetodos'):create_backup(path,tmp_path/'backup')


def test_reject_foreign_key_inconsistency(dbfile,tmp_path):
    with closing(sqlite3.connect(dbfile)) as connection:
        connection.execute("INSERT INTO sessions VALUES ('invalid-fk','missing-user',9000000000)");connection.commit()
    with pytest.raises(ValueError,match='foreign_key_failure'):create_backup(dbfile,tmp_path/'backup')


def test_cleanup_on_backup_timeout(dbfile,tmp_path,monkeypatch):
    import bdt.backup as backup
    times=iter([0,200])
    monkeypatch.setattr(backup.time,'monotonic',lambda:next(times))
    with pytest.raises(TimeoutError):create_backup(dbfile,tmp_path/'backup')
    assert not (tmp_path/'backup').exists() and not list(tmp_path.glob('.bdt-private-*'))


def test_cli(dbfile,tmp_path,monkeypatch,capsys):
    import sys
    from bdt.backup import main
    folder=tmp_path/'backup'
    for args in (['create',str(dbfile),'--output',str(folder)],['verify',str(folder)],
                 ['restore',str(folder),'--output',str(tmp_path/'restored.db')]):
        monkeypatch.setattr(sys,'argv',['backup']+args);main()
        assert json.loads(capsys.readouterr().out)['contains_private_data'] is True
