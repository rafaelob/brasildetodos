"""Private SQLite online backup and verified restore into a NEW database.

Unlike catalog_release, backups contain accounts and private contributions.
Never publish them as CI artifacts or public downloads. No network access or LLM.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path
from .domain import now
from .json_codec import decode

FORMAT = 'brasildetodos-private-sqlite-backup-v1'
MAX_BYTES = 32 * 1024**3


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def _reject_backup_sidecars(path: Path) -> None:
    # The manifest covers one self-contained file, not a SQLite journal/WAL set.
    # Broken symlinks must also fail closed instead of being treated as absent.
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists() or sidecar.is_symlink():
            raise ValueError('backup_sidecar_not_allowed')


def readonly(path: Path, *, snapshot: bool = False):
    if path.is_symlink() or not path.is_file():
        raise ValueError('database_file_required')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('database_size_budget')
    if snapshot:
        _reject_backup_sidecars(path)
    # Only a sealed backup is immutable. A live source MUST retain WAL visibility
    # so create_backup includes committed changes not yet checkpointed.
    query = '?mode=ro&immutable=1' if snapshot else '?mode=ro'
    connection = sqlite3.connect(path.resolve().as_uri() + query, uri=True, timeout=5)
    connection.execute('PRAGMA query_only=ON')
    connection.execute('PRAGMA trusted_schema=OFF')
    return connection


def check_database(connection):
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'schema_version', 'municipalities', 'places', 'users', 'sessions'}.issubset(tables):
        raise ValueError('not_a_brasildetodos_database')
    version = connection.execute('SELECT version FROM schema_version WHERE id=1').fetchone()
    if version != (1,):
        raise ValueError('unsupported_backup_schema')
    if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
        raise ValueError('backup_database_corrupt')
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('backup_foreign_key_failure')


def copy_online(source, target: Path, timeout_seconds: float):
    deadline = time.monotonic() + timeout_seconds
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError('backup_time_budget')
    with closing(sqlite3.connect(target)) as destination:
        source.backup(destination, pages=256, progress=progress, sleep=.05)
        destination.execute('PRAGMA journal_mode=DELETE')
        check_database(destination)
    target.chmod(0o600)
    with target.open('r+b') as stream:
        os.fsync(stream.fileno())


def create_backup(source: Path, destination: Path, timeout_seconds: float = 120) -> dict:
    source, destination = Path(source), Path(destination)
    if not 0 < timeout_seconds <= 3600:
        raise ValueError('invalid_backup_timeout')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('backup_destination_exists')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.bdt-private-backup-', dir=destination.parent))
    try:
        with closing(readonly(source)) as connection:
            check_database(connection)
            copy_online(connection, staging/'database.sqlite', timeout_seconds)
        database = staging/'database.sqlite'
        if database.stat().st_size > MAX_BYTES:
            raise ValueError('database_size_budget')
        manifest = {'format': FORMAT, 'created_at': now(), 'schema_version': 1,
            'bytes': database.stat().st_size, 'sha256': sha256(database),
            'contains_private_data': True, 'encrypted': False,
            'restore_requires_new_destination': True}
        path = staging/'manifest.json'
        path.write_text(json.dumps(manifest, indent=2), encoding='utf-8'); path.chmod(0o600)
        with path.open('r+b') as stream:
            os.fsync(stream.fileno())
        if destination.exists() or destination.is_symlink():
            raise FileExistsError('backup_destination_exists')
        staging.rename(destination)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_backup(folder: Path) -> dict:
    folder = Path(folder); manifest_path = folder/'manifest.json'; database = folder/'database.sqlite'
    if folder.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 16384:
        raise ValueError('invalid_backup_manifest')
    manifest = decode(manifest_path.read_bytes())
    if (not isinstance(manifest, dict) or manifest.get('format') != FORMAT
            or type(manifest.get('schema_version')) is not int or manifest.get('schema_version') != 1
            or manifest.get('contains_private_data') is not True or manifest.get('encrypted') is not False
            or manifest.get('restore_requires_new_destination') is not True):
        raise ValueError('unsupported_backup_format')
    size = manifest.get('bytes')
    if type(size) is not int or not 0 < size <= MAX_BYTES:
        raise ValueError('invalid_backup_size')
    if database.is_symlink() or not database.is_file() or database.stat().st_size != size:
        raise ValueError('backup_size_mismatch')
    if sha256(database) != manifest.get('sha256'):
        raise ValueError('backup_hash_mismatch')
    with closing(readonly(database, snapshot=True)) as connection:
        check_database(connection)
    _reject_backup_sidecars(database)
    return manifest


def restore_backup(folder: Path, destination: Path, timeout_seconds: float = 120) -> dict:
    """Keep data private; revoke sessions, recovery codes and group invites."""
    folder, destination = Path(folder), Path(destination)
    if not 0 < timeout_seconds <= 3600:
        raise ValueError('invalid_backup_timeout')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('restore_destination_exists')
    manifest = verify_backup(folder)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.bdt-private-restore-', dir=destination.parent))
    try:
        source = folder/'database.sqlite'; target = staging/'database.sqlite'
        if sha256(source) != manifest['sha256']:
            raise ValueError('backup_changed_during_restore')
        with closing(readonly(source, snapshot=True)) as connection:
            copy_online(connection, target, timeout_seconds)
        _reject_backup_sidecars(source)
        if sha256(source) != manifest['sha256']:
            raise ValueError('backup_changed_during_restore')
        with closing(sqlite3.connect(target)) as connection:
            connection.execute('PRAGMA foreign_keys=ON')
            with connection:
                connection.execute('DELETE FROM sessions')
                connection.execute('DELETE FROM rate_buckets')
                # A code consumed/revoked after this backup must not become usable
                # again. Older backups legitimately predate the recovery table.
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='recovery_codes'").fetchone():
                    connection.execute('DELETE FROM recovery_codes')
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_invites'").fetchone():
                    connection.execute("UPDATE group_invites SET token_hash=NULL,status='revoked'")
            check_database(connection)
        with target.open('r+b') as stream:
            os.fsync(stream.fileno())
        result = {'status': 'restored_new_database', 'contains_private_data': True,
            'sessions_revoked': True, 'recovery_codes_revoked': True,
            'source_backup_sha256': manifest['sha256'],
            'restored_sha256': sha256(target), 'restored_at': now(),
            'requires_post_backup_deletion_reconciliation': True}
        # Atomic exclusive publication. No overwrite even with competing restores.
        os.link(target, destination)
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command', required=True)
    backup=commands.add_parser('create'); backup.add_argument('database', type=Path)
    backup.add_argument('--output', type=Path, required=True)
    check=commands.add_parser('verify'); check.add_argument('folder', type=Path)
    restore=commands.add_parser('restore'); restore.add_argument('folder', type=Path)
    restore.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    if args.command=='create': result=create_backup(args.database,args.output)
    elif args.command=='verify': result=verify_backup(args.folder)
    else: result=restore_backup(args.folder,args.output)
    print(json.dumps(result, indent=2))


if __name__=='__main__':
    main()
