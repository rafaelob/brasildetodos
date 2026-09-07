"""Actual ZIP, SQLite and API installation; synthetic inputs never enter production."""
from pathlib import Path
from contextlib import closing
import hashlib
import importlib
import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient
from bdt.api import create_app
from test_public_data_bundle import bundler, bundle_input


@pytest.fixture
def selected_bundle(bundler, bundle_input, tmp_path):
    catalog, resources, pins = bundle_input
    path = tmp_path / 'selected.zip'
    result = bundler.build(catalog, resources, path, **pins, revision='a' * 40)
    return path, result


def test_one_command_installs_all_public_records_and_actual_routes(bundler, selected_bundle, tmp_path):
    archive, expected = selected_bundle
    target = tmp_path / 'new' / 'application.db'
    result = bundler.install(archive, expected['archive_sha256'], target)
    assert result['status'] == 'installed_new_database'
    assert result['counts'] == expected['counts']
    assert result['database_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    assert result['public_deployment'] is False and result['fresh_collection'] is False
    if os.name != 'nt':
        assert target.stat().st_mode & 0o777 == 0o600
    with TestClient(create_app('sqlite:///' + str(target), testing=True)) as client:
        assert client.get('/api/places').json()['total'] == 1
        assert client.get('/api/resources').json()['total'] == 2
        assert client.get('/api/groups').status_code == 401
        assert client.get('/api/workbench/documents').status_code == 401
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
        assert connection.execute('SELECT count(*) FROM users').fetchone() == (0,)
        assert connection.execute('SELECT count(*) FROM observations').fetchone() == (0,)
        payloads = connection.execute('SELECT payload FROM resources').fetchall()
        assert any('100.0001' in row[0] for row in payloads)


@pytest.mark.parametrize('kind', ['database', 'directory', 'symlink', 'wal', 'shm', 'journal'])
def test_existing_destinations_and_sidecars_are_never_overwritten(bundler, selected_bundle, tmp_path, kind):
    archive, expected = selected_bundle
    target = tmp_path / 'application.db'
    preserve = target
    if kind == 'directory':
        target.mkdir(); preserve = target / 'keep'
    elif kind == 'symlink':
        preserve = tmp_path / 'private.db'; target.symlink_to(preserve)
    elif kind in ('wal', 'shm', 'journal'):
        preserve = Path(str(target) + '-' + kind)
    preserve.write_bytes(b'existing bytes')
    with pytest.raises(FileExistsError):
        bundler.install(archive, expected['archive_sha256'], target)
    assert preserve.read_bytes() == b'existing bytes'
    if kind in ('wal', 'shm', 'journal'):
        assert not target.exists()


def test_wrong_hash_never_creates_database(bundler, selected_bundle, tmp_path):
    archive, _ = selected_bundle
    target = tmp_path / 'out.db'
    with pytest.raises(ValueError, match='hash'):
        bundler.install(archive, 'b' * 64, target)
    assert not target.exists()


def test_resource_failure_leaves_no_partially_installed_catalog(bundler, selected_bundle, tmp_path, monkeypatch):
    archive, expected = selected_bundle
    import bdt.resource_release
    def failed(*args, **kwargs):
        raise ValueError('injected_resource_transaction_failure')
    monkeypatch.setattr(bdt.resource_release, 'install_resource_release', failed)
    target = tmp_path / 'failed.db'
    with pytest.raises(ValueError, match='transaction_failure'):
        bundler.install(archive, expected['archive_sha256'], target)
    assert not target.exists()
    assert not list(tmp_path.glob('.bdt-install-*'))


def test_concurrent_destination_wins_without_clobber(bundler, selected_bundle, tmp_path, monkeypatch):
    archive, expected = selected_bundle
    target = tmp_path / 'racing.db'
    link = bundler.os.link
    def racing(source, destination, **kwargs):
        if Path(destination) == target:
            target.write_bytes(b'other operator database')
        return link(source, destination, **kwargs)
    monkeypatch.setattr(bundler.os, 'link', racing)
    with pytest.raises(FileExistsError):
        bundler.install(archive, expected['archive_sha256'], target)
    assert target.read_bytes() == b'other operator database'


def test_replaced_input_after_freeze_does_not_change_installed_bytes(bundler, selected_bundle, tmp_path, monkeypatch):
    archive, expected = selected_bundle
    import bdt.catalog_release
    original = bdt.catalog_release.install_catalog
    def replace_source(folder, destination):
        archive.write_bytes(b'replaced outside the private snapshot')
        return original(folder, destination)
    monkeypatch.setattr(bdt.catalog_release, 'install_catalog', replace_source)
    result = bundler.install(archive, expected['archive_sha256'], tmp_path / 'out.db')
    assert result['counts'] == expected['counts']


def test_install_cli_reports_only_counts_hashes_and_status(bundler, selected_bundle, tmp_path, capsys):
    archive, expected = selected_bundle
    target = tmp_path / 'cli.db'
    bundler.main(['install', str(archive), '--sha256', expected['archive_sha256'], '--output', str(target)])
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'installed_new_database'
    assert str(target) not in json.dumps(result)
    assert 'private_not_in_bundle' not in json.dumps(result)
