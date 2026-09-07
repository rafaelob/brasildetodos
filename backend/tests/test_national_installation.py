# SPDX-License-Identifier: AGPL-3.0-or-later
"""Real ZIPs, transactions and API; all test data is isolated synthetic content."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from sqlalchemy.exc import IntegrityError
from bdt.domain import PlaceInput, digest
from bdt.storage import upsert_place
from test_public_data_bundle import bundler, bundle_input
from test_education_release import package, pack, encode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ops'))
import install_national_catalog as national


@pytest.fixture
def stored(database, source):
    place = PlaceInput(id='test:health', name='Synthetic health', kind='health',
        municipality_id='1234567', state='BA', latitude=-12.5, longitude=-38.5, geo_source='synthetic-test', source=source)
    with database.session() as session:
        upsert_place(session, place)
    return place


def update_school_member(school, name, data):
    school[1][name] = data
    manifest = json.loads(school[1]['public-catalog/manifest.json'])
    entry = manifest['files'][name.removeprefix('public-catalog/')]
    entry['sha256'] = hashlib.sha256(data).hexdigest()
    entry['bytes'] = len(data)
    school[1]['public-catalog/manifest.json'] = encode(manifest).encode()


@pytest.fixture
def inputs(bundler, bundle_input, package, tmp_path):
    catalog, resources, pins = bundle_input
    health = tmp_path / 'base.zip'
    result = bundler.build(catalog, resources, health, **pins, revision='a' * 40)
    selection = json.loads((ROOT / 'data/releases/public-data-20260906-v1.json').read_text())
    selection['archive'].update(bytes=health.stat().st_size, sha256=result['archive_sha256'])
    selection['selected_inputs'] = result['selected_inputs']
    selection['counts'] = result['counts']
    health_selection = tmp_path / 'health-selection.json'
    health_selection.write_text(encode(selection))
    update_school_member(package, 'public-catalog/municipalities.jsonl',
                         (catalog / 'municipalities.jsonl').read_bytes())
    return health, health_selection, package


def run(inputs, target):
    health, health_selection, school = inputs
    archive, selection = pack(school)
    return national.install(health, archive, target, health_selection=health_selection,
                            education_selection=selection)


def test_combines_catalogs_without_losing_sources_histories_or_resource_precision(inputs, tmp_path):
    target = tmp_path / 'output.db'
    result = run(inputs, target)
    assert result['counts'] == {'places': 3, 'resources': 2, 'resource_revisions': 2,
                               'finance': 0, 'users': 0, 'observations': 0}
    assert result['by_kind'] == {'health': 1, 'school': 2}
    assert result['without_geometry'] == 2 and result['shared_municipalities'] == 1
    assert result['history_records'] == 3 and result['source_records_rewritten'] is False
    assert result['database_sha256'] == hashlib.sha256(target.read_bytes()).hexdigest()
    checked = national.accept_api(target, result)
    assert checked['kinds_checked'] == ['health', 'school']
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute('SELECT count(*) FROM municipalities').fetchone()[0] == 1
        school = connection.execute('SELECT payload FROM places WHERE id=?', ('test:one',)).fetchone()[0]
        assert json.loads(school)['source']['reference_date'] == '2025'
        amounts = connection.execute('SELECT payload FROM resources').fetchall()
        assert any('100.0001' in item[0] for item in amounts)
        before = connection.execute('SELECT "before" FROM changes').fetchall()
        assert len(before) == 3 and all(json.loads(row[0]) is None for row in before)


@pytest.mark.parametrize('kind', ['database', 'directory', 'symlink', 'wal', 'shm', 'journal'])
def test_refuses_existing_destination_without_modifying_it(inputs, tmp_path, kind):
    target = tmp_path / 'existing.db'; keep = target
    if kind == 'directory':
        target.mkdir(); keep = target / 'original'
    elif kind == 'symlink':
        keep = tmp_path / 'private'; target.symlink_to(keep)
    elif kind in ('wal', 'shm', 'journal'):
        keep = Path(str(target) + '-' + kind)
    keep.write_bytes(b'Existing private bytes')
    with pytest.raises(FileExistsError): run(inputs, target)
    assert keep.read_bytes() == b'Existing private bytes'


@pytest.mark.parametrize('field', ['name', 'source'])
def test_territorial_metadata_conflict_never_uses_last_writer_wins(inputs, tmp_path, field):
    school = inputs[2]
    row = json.loads(school[1]['public-catalog/municipalities.jsonl'])
    if field == 'source': row['source']['record_id'] = 'different-origin'
    else: row['name'] = 'Different synthetic city'
    update_school_member(school, 'public-catalog/municipalities.jsonl', (json.dumps(row) + '\n').encode())
    with pytest.raises(ValueError, match='territory_conflict'):
        run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()
    assert not list(tmp_path.glob('.bdt-national-*'))


def test_late_school_failure_discards_staged_health_and_resources(inputs, tmp_path, monkeypatch):
    original = national.append_school_catalog
    def fail_after_valid_append(*args):
        original(*args)
        raise ValueError('injected_late_failure')
    monkeypatch.setattr(national, 'append_school_catalog', fail_after_valid_append)
    with pytest.raises(ValueError, match='late_failure'):
        run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()
    assert not list(tmp_path.glob('.bdt-national-*'))


def test_destination_race_cannot_overwrite_other_operator(inputs, tmp_path, monkeypatch):
    target = tmp_path / 'out.db'; original = national.os.link
    def race(source, destination):
        if Path(destination) == target: target.write_bytes(b'Other operator')
        return original(source, destination)
    monkeypatch.setattr(national.os, 'link', race)
    with pytest.raises(FileExistsError): run(inputs, target)
    assert target.read_bytes() == b'Other operator'


def test_bad_health_hash_never_installs_schools(inputs, tmp_path):
    inputs[0].write_bytes(b'changed source')
    with pytest.raises(ValueError): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()


def test_replaced_archive_after_freeze_does_not_change_result(inputs, tmp_path, monkeypatch):
    original = national.append_school_catalog
    health, _, school = inputs
    def replace(*args):
        health.write_bytes(b'replaced input outside snapshot')
        (school[0] / 'selected.zip').write_bytes(b'replaced school archive')
        return original(*args)
    monkeypatch.setattr(national, 'append_school_catalog', replace)
    assert run(inputs, tmp_path / 'out.db')['counts']['places'] == 3


def test_count_failure_cannot_publish_partially_accepted_database(inputs, tmp_path, monkeypatch):
    original = national.append_school_catalog
    def remove_one(database, *args):
        shared = original(database, *args)
        with database.engine.begin() as connection:
            connection.exec_driver_sql("DELETE FROM changes WHERE place_id='test:two'")
            connection.exec_driver_sql("DELETE FROM places WHERE id='test:two'")
        return shared
    monkeypatch.setattr(national, 'append_school_catalog', remove_one)
    with pytest.raises(ValueError, match='counts_mismatch'): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()


def test_selection_count_conflict_is_not_hidden_by_valid_archive(inputs, tmp_path):
    path = inputs[1]; selected = json.loads(path.read_text()); selected['counts']['places'] = 99
    path.write_text(encode(selected))
    with pytest.raises(ValueError, match='selection_mismatch'): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()


def test_mixed_api_counter_mismatch_is_visible(inputs, tmp_path):
    target = tmp_path / 'out.db'; result = run(inputs, target)
    result['counts']['places'] = 99
    with pytest.raises(ValueError, match='api_total'): national.accept_api(target, result)


def test_cli_receipt_omits_local_paths_and_private_data(inputs, tmp_path, capsys):
    health, selected, school = inputs; archive, education_selected = pack(school)
    national.main(['--health', str(health), '--education', str(archive), '--health-selection', str(selected),
        '--education-selection', str(education_selected), '--output', str(tmp_path / 'target.db')])
    text = capsys.readouterr().out; result = json.loads(text)
    assert result['status'] == 'installed_new_database'
    assert str(tmp_path) not in text and 'private_not_in_bundle' not in text


def rows_bytes(rows):
    return b''.join((json.dumps(row, ensure_ascii=False) + '\n').encode() for row in rows)


def test_school_identity_collision_does_not_overwrite_health(inputs, tmp_path):
    school = inputs[2]
    rows = [json.loads(line) for line in school[1]['public-catalog/places.jsonl'].splitlines()]
    rows[0]['id'] = rows[0]['payload']['id'] = 'test:health'
    payload = rows[0]['payload']
    rows[0]['fingerprint'] = digest(payload | {'source': {k: v for k, v in payload['source'].items()
                                                   if k not in {'collected_at', 'snapshot_sha256'}}})
    update_school_member(school, 'public-catalog/places.jsonl', rows_bytes(rows))
    before = inputs[0].read_bytes()
    with pytest.raises(IntegrityError): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists() and inputs[0].read_bytes() == before


def test_school_history_cannot_reference_health_identity(inputs, tmp_path):
    school = inputs[2]
    rows = [json.loads(line) for line in school[1]['public-catalog/changes.jsonl'].splitlines()]
    rows[0]['place_id'] = rows[0]['after']['id'] = 'test:health'
    update_school_member(school, 'public-catalog/changes.jsonl', rows_bytes(rows))
    with pytest.raises(ValueError, match='history_mismatch'): run(inputs, tmp_path / 'out.db')
    assert not (tmp_path / 'out.db').exists()


def test_publication_permissions_and_original_archives_remain_unchanged(inputs, tmp_path):
    import os
    health, health_selection, school = inputs
    archive, selection = pack(school)
    original_health, original_school = health.read_bytes(), archive.read_bytes()
    target = tmp_path / 'readonly.db'
    national.install(health, archive, target, health_selection=health_selection, education_selection=selection)
    if os.name != 'nt': assert target.stat().st_mode & 0o777 == 0o600
    assert health.read_bytes() == original_health and archive.read_bytes() == original_school
    with pytest.raises(FileExistsError):
        national.install(health, archive, target, health_selection=health_selection, education_selection=selection)
