# SPDX-License-Identifier: AGPL-3.0-or-later
"""Additional integrity regressions for the mixed catalog installer."""
import hashlib
import json
from pathlib import Path
import pytest
from test_public_data_bundle import bundler, bundle_input
from test_education_release import package, encode
from test_national_installation import inputs, stored, run, national


def test_every_kind_and_state_partition_is_checked_through_api(inputs, tmp_path):
    target = tmp_path / 'out.db'; result = run(inputs, target)
    assert result['partitions'] == [
        {'dataset': 'inep-schools-2025', 'kind': 'school', 'state': 'BA', 'records': 2, 'without_geometry': 2},
        {'dataset': 'synthetic', 'kind': 'health', 'state': 'BA', 'records': 1, 'without_geometry': 0}]
    assert national.accept_api(target, result)['partitions_checked'] == 2
    result['partitions'][0]['records'] += 1
    with pytest.raises(ValueError, match='api_partition'):
        national.accept_api(target, result)


def test_duplicate_municipality_cannot_mask_an_absent_identity(database, tmp_path, source):
    from bdt.catalog_release import export_catalog, load_manifest
    from bdt.storage import Municipality
    with database.session() as session:
        session.add(Municipality(id='1234568', name='Second synthetic city', state='BA', source=source.model_dump()))
    folder = tmp_path / 'dup-catalog'; export_catalog(database, folder, revision='a' * 40)
    path = folder / 'municipalities.jsonl'
    first = path.read_bytes().splitlines(keepends=True)[0]
    path.write_bytes(first + first)
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['files']['municipalities.jsonl'].update(bytes=len(first) * 2,
        sha256=hashlib.sha256(first + first).hexdigest())
    (folder / 'manifest.json').write_text(encode(manifest))
    with pytest.raises(ValueError, match='duplicate_territory'):
        national.append_school_catalog(database, folder, load_manifest(folder))


def test_missing_municipality_never_drops_existing_territory(database, tmp_path):
    from bdt.catalog_release import export_catalog, load_manifest
    folder = tmp_path / 'missing-catalog'; export_catalog(database, folder, revision='a' * 40)
    (folder / 'municipalities.jsonl').write_bytes(b'')
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest['files']['municipalities.jsonl'] = {'bytes': 0, 'records': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
    (folder / 'manifest.json').write_text(encode(manifest))
    with pytest.raises(ValueError, match='territory_coverage'):
        national.append_school_catalog(database, folder, load_manifest(folder))


def test_failed_health_creation_prevents_any_final_file(inputs, tmp_path, monkeypatch):
    def failed(*args): raise OSError('injected disk failure')
    monkeypatch.setattr(national, 'install_base', failed)
    with pytest.raises(OSError, match='disk failure'): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()
    assert not list(tmp_path.glob('.bdt-national-*'))


def test_sidecar_appearing_before_publication_is_not_ignored(inputs, tmp_path, monkeypatch):
    target = tmp_path / 'out.db'; original = national.append_school_catalog
    sidecar = Path(str(target) + '-wal')
    def add_sidecar(*args):
        shared = original(*args); sidecar.write_bytes(b'Other writer'); return shared
    monkeypatch.setattr(national, 'append_school_catalog', add_sidecar)
    with pytest.raises(FileExistsError): run(inputs, target)
    assert not target.exists() and sidecar.read_bytes() == b'Other writer'
