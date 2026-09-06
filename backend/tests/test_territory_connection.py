"""A SQLite transaction context is not a connection-closing context."""
import sqlite3
import pytest
from bdt.territory import import_territory_snapshot
from test_operator_commands import territory_snapshot


@pytest.mark.parametrize('invalid', [False, True])
def test_read_only_snapshot_connection_is_closed(database, source, tmp_path, monkeypatch, invalid):
    path, _ = territory_snapshot(tmp_path, source)
    if invalid:
        with sqlite3.connect(path) as connection:
            connection.execute('DROP TABLE municipalities')
        connection.close()
    original = sqlite3.connect
    readers = []
    class ObservedConnection(sqlite3.Connection):
        was_closed = False
        def close(self):
            self.was_closed = True
            super().close()
    def connect(*args, **kwargs):
        if kwargs.get('uri'):
            value = original(*args, factory=ObservedConnection, **kwargs)
            readers.append(value)
            return value
        return original(*args, **kwargs)
    monkeypatch.setattr('bdt.territory.sqlite3.connect', connect)
    if invalid:
        with pytest.raises(sqlite3.OperationalError): import_territory_snapshot(database, path)
    else:
        assert import_territory_snapshot(database, path)['records'] == 1
    assert len(readers) == 1 and readers[0].was_closed
    with pytest.raises(sqlite3.ProgrammingError): readers[0].execute('SELECT 1')
