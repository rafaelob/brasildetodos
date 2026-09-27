"""An installation upgraded in place must keep serving a database written by an earlier revision."""
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from bdt.api import create_app
from bdt.storage import Database, Municipality, upsert_place

OLD_OBSERVATIONS = """
CREATE TABLE observations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    place_id VARCHAR(180) NOT NULL,
    author_id VARCHAR(36) NOT NULL,
    status VARCHAR(20) NOT NULL,
    payload JSON NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    reviewer_id VARCHAR(36),
    reviewed_at VARCHAR(40),
    review_note TEXT
)
"""


def legacy_database(tmp_path, name="legacy.db"):
    url = f"sqlite:///{tmp_path/name}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(OLD_OBSERVATIONS)
        connection.exec_driver_sql(
            "INSERT INTO observations VALUES "
            "('o1','place:1','u1','approved','{}','2026-01-01T00:00:00+00:00',NULL,NULL,NULL)"
        )
    engine.dispose()
    return url


def test_initialize_adds_columns_missing_from_an_earlier_revision(tmp_path):
    url = legacy_database(tmp_path)
    database = Database(url)
    database.initialize()
    with database.session() as session:
        row = session.execute(
            text("SELECT contest_count, previous_reviewer_id FROM observations WHERE id='o1'")
        ).one()
        assert tuple(row) == (0, None)
    database.initialize()
    connection = sqlite3.connect(tmp_path / "legacy.db")
    try:
        assert connection.execute(
            "SELECT count(*) FROM pragma_table_info('observations') "
            "WHERE name IN ('contest_count','previous_reviewer_id')"
        ).fetchone() == (2,)
    finally:
        connection.close()
    database.engine.dispose()


def test_place_detail_reads_an_upgraded_database(tmp_path, source, place):
    url = legacy_database(tmp_path, "upgraded.db")
    database = Database(url)
    database.initialize()
    with database.session() as session:
        session.add(Municipality(id="1234567", name="Município Sintético", state="BA", source=source.model_dump()))
        upsert_place(session, place)
    with TestClient(create_app(url, testing=True)) as client:
        response = client.get(f"/api/places/{place.id}")
    assert response.status_code == 200
    assert response.json()["observations"] == []
    database.engine.dispose()


def test_initialize_refuses_a_missing_column_without_a_server_default(tmp_path):
    url = f"sqlite:///{tmp_path/'stale.db'}"
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE places (id VARCHAR(180) NOT NULL PRIMARY KEY)")
    engine.dispose()
    database = Database(url)
    with pytest.raises(RuntimeError, match="reviewed migration"):
        database.initialize()
    database.engine.dispose()
