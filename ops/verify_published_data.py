# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check a downloaded public release against independently versioned selection.

No network request, cloud deployment, OCR or existing database is used. The
complete ZIP is frozen before verification and installed in a temporary database.
"""
from __future__ import annotations
import argparse
import json
import platform
from pathlib import Path
import re
import tempfile

from bdt.resource_release import _copy_pinned
from public_data_bundle import MAX_BYTES, install, verify

KEYS = {'schema', 'repository', 'tag', 'release_id', 'code_revision', 'prerelease',
        'github_immutable', 'archive', 'selected_inputs', 'counts', 'fresh_collection',
        'public_deployment', 'national_coverage_certified'}
COUNTS = {'places', 'resources', 'resource_revisions', 'finance', 'users', 'observations'}
INPUTS = {'catalog_manifest_sha256', 'report_sha256', 'resources_sha256'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('selection_duplicate_key')
        result[key] = value
    return result


def read_selection(path: Path) -> dict:
    from archive_ocr_evidence import read_regular
    raw = read_regular(Path(path))
    if len(raw) > 64 * 1024:
        raise ValueError('selection_size_budget')
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != KEYS:
        raise ValueError('selection_schema_invalid')
    if (value['schema'] != 'bdt.published-data-selection.v1'
        or value['repository'] != 'rafaelob/brasildetodos'
        or not isinstance(value['tag'], str)
        or not re.fullmatch(r'public-data-\d{8}-v[1-9]\d*', value['tag'])
        or not isinstance(value['code_revision'], str)
        or not re.fullmatch(r'[a-f0-9]{40}', value['code_revision'])):
        raise ValueError('selection_identity_invalid')
    for key in ('release_id',):
        if type(value[key]) is not int or value[key] <= 0:
            raise ValueError('selection_identity_invalid')
    if (value['prerelease'] is not True or type(value['github_immutable']) is not bool
        or any(value[key] is not False for key in ('fresh_collection', 'public_deployment', 'national_coverage_certified'))):
        raise ValueError('selection_scope_invalid')
    archive = value['archive']
    if (not isinstance(archive, dict) or set(archive) != {'name', 'asset_id', 'bytes', 'sha256'}
        or archive['name'] != 'public-data.zip' or type(archive['asset_id']) is not int
        or archive['asset_id'] <= 0 or type(archive['bytes']) is not int
        or not 0 < archive['bytes'] <= MAX_BYTES):
        raise ValueError('selection_archive_invalid')
    inputs = value['selected_inputs']
    if not isinstance(inputs, dict) or set(inputs) != INPUTS:
        raise ValueError('selection_inputs_invalid')
    if any(not isinstance(item, str) or not re.fullmatch(r'[a-f0-9]{64}', item)
           for item in (archive['sha256'], *inputs.values())):
        raise ValueError('selection_hash_invalid')
    counts = value['counts']
    if (not isinstance(counts, dict) or set(counts) != COUNTS
        or any(type(n) is not int or n < 0 for n in counts.values())
        or counts['users'] != 0 or counts['observations'] != 0):
        raise ValueError('selection_counts_invalid')
    return value


def check(archive: Path, selection: Path) -> dict:
    selected = read_selection(selection)
    expected = selected['archive']
    with tempfile.TemporaryDirectory(prefix='bdt-published-acceptance-') as temporary:
        root = Path(temporary)
        frozen = root / 'public-data.zip'
        _copy_pinned(Path(archive), frozen, expected['sha256'], expected['bytes'])
        if frozen.stat().st_size != expected['bytes']:
            raise ValueError('selection_archive_size_mismatch')
        checked = verify(frozen, expected['sha256'])
        if checked['selected_inputs'] != selected['selected_inputs'] or checked['counts'] != selected['counts']:
            raise ValueError('selection_content_mismatch')
        database = root / 'application.db'
        installed = install(frozen, expected['sha256'], database)
        from fastapi.testclient import TestClient
        from bdt.api import create_app
        with TestClient(create_app('sqlite:///' + str(database), testing=True)) as client:
            for route, name in (('/api/places', 'places'), ('/api/resources', 'resources')):
                response = client.get(route, params={'limit': 1})
                if response.status_code != 200 or response.json()['total'] != selected['counts'][name]:
                    raise ValueError('published_api_counts_mismatch')
            for route in ('/api/groups', '/api/workbench/documents', '/api/observations/mine'):
                if client.get(route).status_code != 401:
                    raise ValueError('published_private_route_regression')
        return {'schema': 'bdt.published-data-acceptance.v1', 'status': 'passed',
                'tag': selected['tag'], 'python': platform.python_version(),
                'archive_sha256': expected['sha256'], 'archive_bytes': expected['bytes'],
                'selected_inputs': checked['selected_inputs'], 'counts': installed['counts'],
                'api_checked_now': True, 'private_routes_protected': True,
                'fresh_collection': False, 'public_deployment': False,
                'existing_database_modified': False, 'synthetic_records_added': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--selection', type=Path, required=True)
    args = parser.parse_args(argv)
    result = check(args.archive, args.selection)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
