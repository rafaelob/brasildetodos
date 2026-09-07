"""Selection receipts and archived bytes are tested separately from source truth."""
import importlib
import json
from pathlib import Path
import shutil

import pytest
from test_bundle_installation import bundler, bundle_input, selected_bundle

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def checker(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'ops'))
    return importlib.import_module('verify_published_data')

@pytest.fixture
def selection(checker, selected_bundle, tmp_path):
    archive, result = selected_bundle
    value = json.loads((ROOT / 'data/releases/public-data-20260906-v1.json').read_text())
    value['archive']['bytes'] = archive.stat().st_size
    value['archive']['sha256'] = result['archive_sha256']
    value['selected_inputs'] = result['selected_inputs']
    value['counts'] = result['counts']
    path = tmp_path / 'selection.json'; path.write_text(json.dumps(value))
    return path


def test_selection_drives_actual_installation_and_api(checker, selected_bundle, selection):
    archive, _ = selected_bundle
    result = checker.check(archive, selection)
    assert result['api_checked_now'] and result['private_routes_protected']
    assert result['counts']['places'] == 1 and result['counts']['resources'] == 2
    assert not result['synthetic_records_added'] and not result['public_deployment']


@pytest.mark.parametrize('key,value', [
    ('public_deployment', True), ('fresh_collection', 0), ('national_coverage_certified', True),
    ('repository', 'other/repository'), ('tag', '../bad'), ('release_id', True),
    ('code_revision', 'main'), ('archive', []), ('selected_inputs', []), ('counts', []),
])
def test_invalid_selection_is_refused(checker, selection, key, value):
    data = json.loads(selection.read_text()); data[key] = value; selection.write_text(json.dumps(data))
    with pytest.raises(ValueError): checker.read_selection(selection)


@pytest.mark.parametrize('mutation', ['duplicate', 'unknown', 'private', 'hash', 'count', 'path', 'size'])
def test_selection_cannot_broaden_the_public_contract(checker, selection, mutation):
    data = json.loads(selection.read_text())
    if mutation == 'duplicate':
        selection.write_text(selection.read_text()[:-1] + ', "counts": {}}')
    else:
        if mutation == 'unknown': data['credentials'] = 'never'
        elif mutation == 'private': data['counts']['users'] = 1
        elif mutation == 'hash': data['archive']['sha256'] = 'not-a-hash'
        elif mutation == 'count': data['counts']['places'] = True
        elif mutation == 'path': data['archive']['name'] = '../private.db'
        else: data['archive']['bytes'] = -1
        selection.write_text(json.dumps(data))
    with pytest.raises(ValueError): checker.read_selection(selection)


@pytest.mark.parametrize('mutation', ['wrong-archive', 'wrong-input', 'wrong-count'])
def test_consistent_bundle_still_needs_external_selection(checker, selection, selected_bundle, mutation):
    archive, _ = selected_bundle; data = json.loads(selection.read_text())
    if mutation == 'wrong-archive': data['archive']['sha256'] = 'b' * 64
    elif mutation == 'wrong-input': data['selected_inputs']['report_sha256'] = 'b' * 64
    else: data['counts']['places'] += 1
    selection.write_text(json.dumps(data))
    with pytest.raises(ValueError): checker.check(archive, selection)


def test_checked_in_corpus_is_reproducible_without_network_or_ocr(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'ops'))
    archive = importlib.import_module('archive_ocr_evidence')
    import bdt.documents, socket
    def forbidden(*args, **kwargs): pytest.fail('offline corpus verification cannot fetch or run OCR')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(bdt.documents, 'ocr_page', forbidden)
    before = {path.name: path.read_bytes() for path in (ROOT / 'tests/corpus/ocr-reviewed').iterdir()}
    result = archive.verify(ROOT / 'tests/corpus/ocr-reviewed')
    assert result['files'] == 6 and result['originals'] == 4
    assert result['official_corpus'] is False and result['ocr_executed'] is False
    assert before == {path.name: path.read_bytes() for path in (ROOT / 'tests/corpus/ocr-reviewed').iterdir()}


def test_the_committed_release_selection_has_external_archive_identity(checker):
    result = checker.read_selection(ROOT / 'data/releases/public-data-20260906-v1.json')
    assert result['archive']['asset_id'] == 547868908
    assert result['github_immutable'] is False  # no unsupported immutability claim
    assert result['counts']['places'] == 96123 and result['counts']['resources'] == 6679
