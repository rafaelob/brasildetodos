"""Schema rejection and interrupted DDL must not leave a half-upgraded database."""
import sqlite3

import pytest
from sqlalchemy import event

from bdt.storage import Database
from test_schema_upgrade import legacy_database


def schema(url):
    connection = sqlite3.connect(url.removeprefix('sqlite:///'))
    try:
        return connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
        ).fetchall()
    finally:
        connection.close()


@pytest.mark.parametrize('version_table', ['schema_version', 'extension_version',
                                                  'photo_schema_version', 'group_schema_version'])
def test_future_version_is_rejected_before_creating_tables(tmp_path, version_table):
    path = tmp_path / 'future.db'
    with sqlite3.connect(path) as connection:
        connection.executescript(f'CREATE TABLE {version_table} (id INTEGER PRIMARY KEY, version INTEGER NOT NULL);'
                                 f'INSERT INTO {version_table} VALUES (1, 99);')
    db = Database(f'sqlite:///{path}')
    before = schema(str(db.engine.url))
    try:
        with pytest.raises(RuntimeError, match='Unsupported schema version'):
            db.initialize()
        assert schema(str(db.engine.url)) == before
    finally:
        db.engine.dispose()


def test_incompatible_shape_is_rejected_without_partial_creation(tmp_path):
    path = tmp_path / 'stale.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE places (id VARCHAR(180) PRIMARY KEY)')
    db = Database(f'sqlite:///{path}')
    before = schema(str(db.engine.url))
    try:
        with pytest.raises(RuntimeError, match='reviewed migration'):
            db.initialize()
        assert schema(str(db.engine.url)) == before
    finally:
        db.engine.dispose()


def test_mid_upgrade_failure_rolls_back_ddl_and_allows_retry(tmp_path):
    url = legacy_database(tmp_path)
    db = Database(url)
    before = schema(url)
    executed = []
    def interrupt(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('ALTER TABLE'):
            executed.append(statement)
            if len(executed) == 2:
                raise RuntimeError('synthetic_ddl_interruption')
    event.listen(db.engine, 'before_cursor_execute', interrupt)
    try:
        with pytest.raises(RuntimeError, match='synthetic_ddl_interruption'):
            db.initialize()
        assert len(executed) == 2
        assert schema(url) == before
        with sqlite3.connect(tmp_path / 'legacy.db') as connection:
            assert connection.execute('SELECT id, payload FROM observations').fetchall() == [('o1', '{}')]
        event.remove(db.engine, 'before_cursor_execute', interrupt)
        db.initialize()
        db.initialize()
        with sqlite3.connect(tmp_path / 'legacy.db') as connection:
            assert connection.execute('SELECT contest_count, previous_reviewer_id FROM observations').fetchall() == [(0, None)]
    finally:
        db.engine.dispose()


def test_string_defaults_and_identifiers_are_quoted(tmp_path):
    from sqlalchemy import Column, Integer, String, Table
    from bdt.storage import Base
    table = Table('synthetic"defaults', Base.metadata,
                  Column('id', Integer, primary_key=True),
                  Column('review"note', String, nullable=False, server_default="O'Reilly"))
    path = tmp_path / 'quoted.db'
    db = Database(f'sqlite:///{path}')
    try:
        with sqlite3.connect(path) as connection:
            connection.executescript('CREATE TABLE "synthetic""defaults" (id INTEGER PRIMARY KEY);'
                                     'INSERT INTO "synthetic""defaults" (id) VALUES (1);')
        db.initialize()
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT "review""note" FROM "synthetic""defaults"').fetchall() == [("O'Reilly",)]
    finally:
        Base.metadata.remove(table)
        db.engine.dispose()


def test_concurrent_initializers_observe_one_complete_schema(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from bdt.evidence import ExtensionVersion  # Register the optional schema for this test.
    path = tmp_path / 'concurrent.db'
    db = Database(f'sqlite:///{path}')
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: db.initialize(), range(8)))
        with sqlite3.connect(path) as connection:
            assert connection.execute('SELECT id, version FROM schema_version').fetchall() == [(1, 1)]
            assert connection.execute(f'SELECT id, version FROM {ExtensionVersion.__tablename__}').fetchall() == [(1, 1)]
            fks = connection.execute("PRAGMA foreign_key_list('observations')").fetchall()
            assert any(row[2:5] == ('users', 'previous_reviewer_id', 'id') for row in fks)
    finally:
        db.engine.dispose()


@pytest.mark.parametrize('constraint', ['unique', 'index', 'foreign_key_option'])
def test_unsupported_additive_constraints_fail_before_mutation(tmp_path, constraint):
    from sqlalchemy import Column, ForeignKey, Integer, String, Table
    from bdt.storage import Base
    options = {constraint: True} if constraint != 'foreign_key_option' else {}
    references = [ForeignKey('users.id', ondelete='CASCADE')] if constraint == 'foreign_key_option' else []
    table = Table('synthetic_constraint', Base.metadata,
                  Column('id', Integer, primary_key=True), Column('detail', String, *references, **options))
    path = tmp_path / 'constraint.db'
    db = Database(f'sqlite:///{path}')
    try:
        with sqlite3.connect(path) as connection:
            connection.execute('CREATE TABLE synthetic_constraint (id INTEGER PRIMARY KEY)')
        before = schema(str(db.engine.url))
        with pytest.raises(RuntimeError, match='reviewed migration'):
            db.initialize()
        assert schema(str(db.engine.url)) == before
    finally:
        Base.metadata.remove(table)
        db.engine.dispose()
