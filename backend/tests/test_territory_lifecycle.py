"""A read-only territorial connection must close independently of transactions."""
import sqlite3
from types import SimpleNamespace

import pytest

import bdt.territory as territory
from bdt.storage import Municipality
from test_operator_commands import territory_snapshot


@pytest.fixture
def observed_source(monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def tracked(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    # Only intercept this module's source connection, not SQLAlchemy/other tests.
    monkeypatch.setattr(territory, 'sqlite3', SimpleNamespace(connect=tracked))
    yield opened
    # Clean up even on the RED run; the assertion below must detect the leak.
    for connection in opened:
        connection.close()


def assert_closed(opened):
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        opened[0].execute('SELECT 1')


def test_source_closes_after_success_without_changing_original(database, tmp_path, source, observed_source):
    path, provenance = territory_snapshot(tmp_path, source)
    original = path.read_bytes()
    result = territory.import_territory_snapshot(database, path)
    assert_closed(observed_source)
    assert path.read_bytes() == original and result['records'] == 1
    assert result['original_collection_dates'] == [provenance['collected_at']]


def test_source_closes_on_invalid_schema(database, tmp_path, observed_source):
    path = tmp_path / 'missing-table.db'
    sqlite3.connect(path).close()
    original = path.read_bytes()
    with pytest.raises(sqlite3.OperationalError, match='no such table'):
        territory.import_territory_snapshot(database, path)
    assert_closed(observed_source)
    assert path.read_bytes() == original


def test_source_closes_when_record_validation_fails(database, tmp_path, source, observed_source):
    path, _ = territory_snapshot(tmp_path, source, {'state': 'XX'})
    with pytest.raises(ValueError, match='invalid_territory_state'):
        territory.import_territory_snapshot(database, path)
    assert_closed(observed_source)
    with database.session() as session:
        assert session.get(Municipality, '7654321') is None


def test_snapshot_connection_is_read_only(database, tmp_path, source, monkeypatch):
    path, _ = territory_snapshot(tmp_path, source)
    real_connect = sqlite3.connect
    intercepted = []

    def inspect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        assert kwargs['uri'] is True and 'mode=ro' in args[0]
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            connection.execute('CREATE TABLE should_not_exist(x)')
        intercepted.append(connection)
        return connection

    monkeypatch.setattr(territory, 'sqlite3', SimpleNamespace(connect=inspect))
    try:
        territory.import_territory_snapshot(database, path)
        assert_closed(intercepted)
    finally:
        for connection in intercepted:
            connection.close()
