import os
import sys
import pytest
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Database, Municipality, upsert_place

@pytest.fixture(autouse=True)
def handle_windows_symlink_privilege(monkeypatch):
    if sys.platform == 'win32':
        import pathlib
        orig_symlink_to = pathlib.Path.symlink_to
        def safe_symlink_to(self, target, target_is_directory=False):
            if 'pytest' in str(self) and self.name.endswith('current'):
                return orig_symlink_to(self, target, target_is_directory=target_is_directory)
            try:
                return orig_symlink_to(self, target, target_is_directory=target_is_directory)
            except OSError as e:
                if getattr(e, 'winerror', None) == 1314:
                    pytest.skip("Creating symlinks on Windows requires Developer Mode or Administrator privileges")
                raise
        monkeypatch.setattr(pathlib.Path, 'symlink_to', safe_symlink_to)

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
