import json
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from bdt.storage import Database
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


def test_postgres_schema_and_moderation_contract(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    main()

    database = Database(os.environ["BDT_RUNTIME_TEST_DATABASE_URL"])
    with database.session() as session:
        assert session.scalar(text(
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user"
        )) is False
    database.engine.dispose()

    output = Path(os.getenv("BDT_RUNTIME_TEST_OUTPUT", "test-results/runtime"))
    receipt = json.loads((output / "postgres.json").read_text())
    assert receipt["backend"] == "postgresql"
    assert receipt["synthetic_test_only"] is True
    assert receipt["production_deployed"] is False
    assert {
        "schema_initialized_twice",
        "foreign_keys_unique_constraints_and_indexes",
        "non_superuser_database_role",
        "constraint_failure_rolled_back",
        "contribution_moderation_public_read",
    }.issubset(receipt["checks"])
