"""Synthetic records stay in tests; no fixture is loaded by application startup."""
import pytest
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Database, Municipality, upsert_place

@pytest.fixture
def source():
    return Source(dataset="synthetic", url="https://example.org/test-only", record_id="fixture", reference_date="2025", collected_at=now(), snapshot_sha256="a"*64)

@pytest.fixture
def database(tmp_path, source):
    db=Database(f"sqlite:///{tmp_path/'test.db'}");db.initialize()
    with db.session() as s:
        s.add(Municipality(id="1234567", name="Município Sintético", state="BA", source=source.model_dump()))
    yield db
    db.engine.dispose()

@pytest.fixture
def place(source):
    return PlaceInput(id="test:school",kind="school",name="Escola Sintética Árvore",municipality_id="1234567",state="BA",source=source)

@pytest.fixture
def stored(database,place):
    with database.session() as s:upsert_place(s,place)
    return place
