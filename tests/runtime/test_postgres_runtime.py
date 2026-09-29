import json
import os
from pathlib import Path

import pytest
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import Column, ForeignKey, Integer, String, Table, Text, event, inspect, text
from sqlalchemy.exc import IntegrityError

from bdt.storage import Base, Database
from ops.postgres_smoke import main


@pytest.mark.parametrize("database_url,compose_enabled", [
    ("postgresql+psycopg://bdt_ci@db.example:5432/bdt_ci", True),
    ("postgresql+psycopg://bdt_ci@postgres-test:5432/bdt_ci", False),
    ("postgresql+psycopg://bdt_test_admin@postgres-test:5432/bdt_ci", True),
])
def test_postgres_proof_refuses_non_ephemeral_targets(
        monkeypatch, database_url, compose_enabled):
    monkeypatch.setenv("BDT_RUNTIME_TEST_DATABASE_URL", database_url)
    monkeypatch.setenv("BDT_EPHEMERAL_TEST", "1")
    if compose_enabled:
        monkeypatch.setenv("BDT_COMPOSE_TEST", "1")
    else:
        monkeypatch.delenv("BDT_COMPOSE_TEST", raising=False)

    with pytest.raises(ValueError, match="only_explicit_ephemeral_test_database_allowed"):
        main()


def exercise_schema_atomicity(database):
    """Called only AFTER main() validates the isolated, explicitly ephemeral target."""
    assert database.engine.dialect.name == 'postgresql'
    probe = Table('bdt_schema_probe', Base.metadata,
                  Column('id', Integer, primary_key=True),
                  Column('body', Text, nullable=False),
                  Column('revision', Integer, nullable=False, server_default='0'),
                  Column('reviewer_id', String(36), ForeignKey('users.id')),
                  Column('note', String, nullable=False, server_default="O'Reilly"))
    try:
        with database.engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE bdt_schema_probe (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            connection.exec_driver_sql("INSERT INTO bdt_schema_probe VALUES (1, 'synthetic persistence')")
        before = inspect(database.engine).get_columns('bdt_schema_probe')
        executed = []
        def interrupt(connection, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith('ALTER TABLE') and 'bdt_schema_probe' in statement:
                executed.append(statement)
                if len(executed) == 2:
                    raise RuntimeError('synthetic_ddl_interruption')
        event.listen(database.engine, 'before_cursor_execute', interrupt)
        try:
            with pytest.raises(RuntimeError, match='synthetic_ddl_interruption'):
                database.initialize()
        finally:
            event.remove(database.engine, 'before_cursor_execute', interrupt)
        assert len(executed) == 2
        assert [c['name'] for c in inspect(database.engine).get_columns('bdt_schema_probe')] == [c['name'] for c in before]
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: database.initialize(), range(4)))
        with database.engine.connect() as connection:
            row = connection.execute(text('SELECT body, revision, reviewer_id, note FROM bdt_schema_probe')).one()
            assert tuple(row) == ('synthetic persistence', 0, None, "O'Reilly")
        fks = inspect(database.engine).get_foreign_keys('bdt_schema_probe')
        assert any(fk['constrained_columns'] == ['reviewer_id'] and fk['referred_table'] == 'users' for fk in fks)
        with pytest.raises(IntegrityError):
            with database.engine.begin() as connection:
                connection.execute(text("UPDATE bdt_schema_probe SET reviewer_id = 'missing-synthetic-user' WHERE id = 1"))
        return ['schema_ddl_failure_rolled_back', 'concurrent_schema_initializers_serialized',
                'quoted_schema_defaults_and_foreign_keys']
    finally:
        with database.engine.begin() as connection:
            probe.drop(connection, checkfirst=True)
        Base.metadata.remove(probe)


def test_postgres_schema_and_moderation_contract(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    main()

    database = Database(os.environ["BDT_RUNTIME_TEST_DATABASE_URL"])
    with database.session() as session:
        assert session.scalar(text(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        )) is False
    try:
        schema_checks = exercise_schema_atomicity(database)
    finally:
        database.engine.dispose()

    output = Path(os.getenv("BDT_RUNTIME_TEST_OUTPUT", "test-results/runtime"))
    receipt = json.loads((output / "postgres.json").read_text())
    receipt["checks"].extend(schema_checks)
    (output / "postgres.json").write_text(json.dumps(receipt, indent=2))
    assert receipt["backend"] == "postgresql"
    assert receipt["synthetic_test_only"] is True
    assert receipt["production_deployed"] is False
    assert {
        "schema_initialized_twice",
        "schema_ddl_failure_rolled_back",
        "concurrent_schema_initializers_serialized",
        "quoted_schema_defaults_and_foreign_keys",
        "foreign_keys_unique_constraints_and_indexes",
        "non_superuser_database_role",
        "constraint_failure_rolled_back",
        "contribution_moderation_public_read",
    }.issubset(receipt["checks"])
