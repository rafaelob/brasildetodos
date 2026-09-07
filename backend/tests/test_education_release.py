# SPDX-License-Identifier: AGPL-3.0-or-later
"""Synthetic fixtures isolate the release validator; real data is a separate CI job."""
from pathlib import Path
import hashlib
import json
import stat
import sys
import zipfile

import pytest
from bdt.catalog_release import export_catalog
from bdt.domain import Source, PlaceInput, now
from bdt.storage import Database, Municipality, upsert_place

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
from education_release import read_selection, verified_education, exercise, encode, MEMBERS


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def package(tmp_path):
    db = Database('sqlite:///' + str(tmp_path / 'fixture.db'))
    db.initialize()
    source = Source(dataset='inep-schools-2025', url='https://example.org/synthetic-school-test',
                    record_id='test', reference_date='2025', collected_at=now(), snapshot_sha256='b' * 64)
    try:
        with db.session() as session:
            session.add(Municipality(id='1234567', name='Synthetic city', state='BA', source=source.model_dump()))
            session.flush()
            for identifier in ('test:one', 'test:two'):
                upsert_place(session, PlaceInput(id=identifier, name='Synthetic ' + identifier,
                    kind='school', state='BA', municipality_id='1234567', source=source))
        export_catalog(db, tmp_path / 'public-catalog', 'a' * 40)
    finally:
        db.engine.dispose()
    download = {'sha256': 'b' * 64, 'tls': {'handshake_verified': True, 'partial_chain_allowed': False}}
    counts = {'read': 3, 'eligible': 2, 'excluded': 1, 'without_geometry': 2}
    (tmp_path / 'inep-distribution.zip.manifest.json').write_text(encode(download))
    report = {'status': 'imported', 'year': 2025, 'revision': 'a' * 40, 'distribution': download,
              'validation': {'counts': counts, 'partitions': {'BA': counts}}}
    (tmp_path / 'report.json').write_text(encode(report))
    data = {name: (tmp_path / name).read_bytes() for name in MEMBERS}
    selected = {'schema': 'bdt.education-selection.v1', 'repository': 'rafaelob/brasildetodos',
                'tag': 'education-2025-20260907-v1', 'dataset': 'inep-schools-2025',
                'source_revision': 'a' * 40, 'upstream_sha256': 'b' * 64, 'counts': counts,
                'artifact': {'id': 1, 'run_id': 2, 'bytes': 1, 'sha256': 'c' * 64}, 'members': {}}
    return tmp_path, data, selected


def pack(package, *, duplicate=False, mode=None):
    root, data, selected = package
    path = root / 'selected.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zipped:
        for name, raw in data.items():
            info = zipfile.ZipInfo(name)
            if mode and name == 'report.json':
                info.external_attr = mode << 16
            zipped.writestr(info, raw)
        if duplicate:
            with pytest.warns(UserWarning, match='Duplicate'):
                zipped.writestr('report.json', data['report.json'])
    selected['artifact'].update(bytes=path.stat().st_size, sha256=hash_bytes(path.read_bytes()))
    selected['members'] = {name: {'bytes': len(raw), 'sha256': hash_bytes(raw)} for name, raw in data.items() if name in MEMBERS}
    selection = root / 'selection.json'
    selection.write_text(encode(selected))
    return path, selection


def test_installs_all_selected_schools_and_queries_api_without_users(package):
    archive, selection = pack(package)
    result = exercise(archive, selection)
    assert result['api_checked'] is True and result['browser_checked'] is False
    assert result['counts']['eligible'] == 2 and result['states_checked'] == 1
    assert result['synthetic_records_added'] is False  # Validator never adds records.
    assert result['public_deployment'] is False


def test_preserves_original_bytes_and_removes_private_working_directory(package):
    archive, selection = pack(package)
    before = archive.read_bytes()
    with verified_education(archive, read_selection(selection)) as (root, manifest):
        frozen = root
        assert manifest['files']['places.jsonl']['records'] == 2
        assert (root / 'public-catalog/places.jsonl').read_bytes() == package[1]['public-catalog/places.jsonl']
    assert not frozen.exists() and archive.read_bytes() == before


def test_external_hash_refuses_changed_archive(package):
    archive, selection = pack(package)
    archive.write_bytes(archive.read_bytes() + b'changed')
    with pytest.raises(ValueError):
        with verified_education(archive, read_selection(selection)):
            pytest.fail('changed archive accepted')


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'users.jsonl', 'public-catalog/session.jsonl'])
def test_unexpected_or_traversing_member_is_refused(package, name):
    package[1][name] = b'synthetic forbidden data'
    archive, selection = pack(package)
    with pytest.raises(ValueError, match='archive_members'):
        with verified_education(archive, read_selection(selection)):
            pytest.fail('unexpected archive member accepted')


def test_duplicate_zip_member_is_refused(package):
    archive, selection = pack(package, duplicate=True)
    with pytest.raises(ValueError, match='archive_members'):
        with verified_education(archive, read_selection(selection)):
            pytest.fail('duplicate accepted')


def test_zip_symlink_is_refused(package):
    archive, selection = pack(package, mode=stat.S_IFLNK | 0o777)
    with pytest.raises(ValueError, match='metadata'):
        with verified_education(archive, read_selection(selection)):
            pytest.fail('symlink accepted')


@pytest.mark.parametrize('case', ['year', 'revision', 'count', 'upstream', 'states', 'partition', 'tls'])
def test_inconsistent_source_receipt_is_not_published(package, case):
    report = json.loads(package[1]['report.json'])
    if case == 'year': report['year'] = 2024
    elif case == 'revision': report['revision'] = 'd' * 40
    elif case == 'count': report['validation']['counts']['eligible'] = 999
    elif case == 'upstream': report['distribution']['sha256'] = 'd' * 64
    elif case == 'states': report['validation']['partitions']['SP'] = report['validation']['partitions'].pop('BA')
    elif case == 'partition': report['validation']['partitions']['BA']['read'] = 99
    elif case == 'tls': report['distribution']['tls']['handshake_verified'] = False
    package[1]['report.json'] = encode(report).encode()
    archive, selection = pack(package)
    with pytest.raises(ValueError):
        with verified_education(archive, read_selection(selection)):
            pytest.fail('invalid receipt accepted')


@pytest.mark.parametrize('case', ['count', 'archive_size', 'tag', 'extra', 'missing_member'])
def test_selection_schema_is_closed_and_bounded(package, case):
    archive, path = pack(package)
    selected = json.loads(path.read_text())
    if case == 'count': selected['counts']['eligible'] = True
    elif case == 'archive_size': selected['artifact']['bytes'] = 1024**3
    elif case == 'tag': selected['tag'] = '../latest'
    elif case == 'extra': selected['private'] = 'forbidden'
    elif case == 'missing_member': selected['members'].pop('report.json')
    path.write_text(encode(selected))
    with pytest.raises(ValueError):
        read_selection(path)


def test_duplicate_selection_key_is_refused(package):
    _, path = pack(package)
    raw = path.read_text()
    path.write_text(raw.replace('{', '{"schema": "duplicate",', 1))
    with pytest.raises(ValueError, match='duplicate'):
        read_selection(path)


def test_member_hash_is_independent_of_zip_integrity(package):
    archive, path = pack(package)
    selected = read_selection(path)
    selected['members']['report.json']['sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='integrity'):
        with verified_education(archive, selected):
            pytest.fail('bad member accepted')


def test_symlink_selection_is_not_read(package):
    _, path = pack(package)
    link = path.with_name('link.json'); link.symlink_to(path)
    with pytest.raises(ValueError, match='file'):
        read_selection(link)


def test_production_selection_refers_only_to_reviewed_public_members():
    path = Path(__file__).resolve().parents[2] / 'data/releases/education-2025-20260907-v1.json'
    selected = read_selection(path)
    assert selected['artifact']['id'] == 10003233969
    assert selected['counts']['eligible'] == 138086
    assert set(selected['members']) == MEMBERS
