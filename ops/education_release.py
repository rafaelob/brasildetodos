# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the exact reviewed school artifact, install it and exercise its API.

No data collection, inferred coordinates, active-database replacement or source
microdata extraction takes place. The original artifact is distributed unchanged.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import stat
import tempfile
import zipfile

from bdt.catalog_release import FILES, verify_catalog, install_catalog
from bdt.resource_release import _copy_pinned

MEMBERS = frozenset('public-catalog/' + name for name in (*FILES, 'manifest.json')) | {
    'report.json', 'inep-distribution.zip.manifest.json'}
MAX_ARCHIVE = 128 * 1024**2
MAX_MEMBER = 256 * 1024**2
MAX_TOTAL = 512 * 1024**2
COUNT_KEYS = {'read', 'eligible', 'excluded', 'without_geometry'}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('education_duplicate_key')
        result[key] = value
    return result


def sha_ok(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def read_selection(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError('education_selection_file')
    result = json.loads(path.read_text(), object_pairs_hook=unique)
    keys = {'schema', 'repository', 'tag', 'dataset', 'source_revision', 'artifact',
            'members', 'counts', 'upstream_sha256'}
    if not isinstance(result, dict) or set(result) != keys:
        raise ValueError('education_selection_schema')
    if (result['schema'] != 'bdt.education-selection.v1'
            or result['repository'] != 'rafaelob/brasildetodos'
            or not isinstance(result['tag'], str)
            or not re.fullmatch(r'education-2025-\d{8}-v[1-9]\d*', result['tag'])
            or result['dataset'] != 'inep-schools-2025'
            or not isinstance(result['source_revision'], str)
            or not re.fullmatch(r'[0-9a-f]{40}', result['source_revision'])
            or not sha_ok(result['upstream_sha256'])):
        raise ValueError('education_selection_identity')
    artifact = result['artifact']
    if (not isinstance(artifact, dict) or set(artifact) != {'id', 'run_id', 'bytes', 'sha256'}
            or any(type(artifact[k]) is not int or artifact[k] <= 0 for k in ('id', 'run_id', 'bytes'))
            or artifact['bytes'] > MAX_ARCHIVE or not sha_ok(artifact['sha256'])):
        raise ValueError('education_selection_artifact')
    members = result['members']
    if not isinstance(members, dict) or set(members) != MEMBERS:
        raise ValueError('education_selection_members')
    for entry in members.values():
        if (not isinstance(entry, dict) or set(entry) != {'bytes', 'sha256'}
                or type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= MAX_MEMBER
                or not sha_ok(entry['sha256'])):
            raise ValueError('education_selection_member')
    if sum(x['bytes'] for x in members.values()) > MAX_TOTAL:
        raise ValueError('education_selection_budget')
    counts = result['counts']
    if (not isinstance(counts, dict) or set(counts) != COUNT_KEYS
            or any(type(v) is not int or v < 0 for v in counts.values())
            or counts['eligible'] <= 0 or counts['read'] != counts['eligible'] + counts['excluded']
            or counts['without_geometry'] > counts['eligible']):
        raise ValueError('education_selection_counts')
    return result


@contextmanager
def verified_education(archive, selected):
    """Freeze first; extract only pinned public members within fixed budgets."""
    with tempfile.TemporaryDirectory(prefix='bdt-education-release-') as temp:
        root = Path(temp)
        frozen = root / 'selected.zip'
        expected = selected['artifact']
        _copy_pinned(Path(archive), frozen, expected['sha256'], expected['bytes'])
        if frozen.stat().st_size != expected['bytes']:
            raise ValueError('education_archive_size')
        with zipfile.ZipFile(frozen) as zipped:
            entries = zipped.infolist()
            if len(entries) != len(MEMBERS) or {x.filename for x in entries} != MEMBERS:
                raise ValueError('education_archive_members')
            for info in entries:
                mode = stat.S_IFMT(info.external_attr >> 16)
                item = selected['members'][info.filename]
                if (info.flag_bits & 1 or mode not in (0, stat.S_IFREG)
                        or info.file_size != item['bytes']):
                    raise ValueError('education_archive_member_metadata')
                target = root / info.filename
                target.parent.mkdir(exist_ok=True)
                digest = hashlib.sha256()
                length = 0
                with zipped.open(info) as source, target.open('xb') as output:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        length += len(block)
                        if length > item['bytes']:
                            raise ValueError('education_member_size')
                        digest.update(block)
                        output.write(block)
                if length != item['bytes'] or digest.hexdigest() != item['sha256']:
                    raise ValueError('education_member_integrity')
        manifest = verify_catalog(root / 'public-catalog')
        report = json.loads((root / 'report.json').read_text(), object_pairs_hook=unique)
        download = json.loads((root / 'inep-distribution.zip.manifest.json').read_text(), object_pairs_hook=unique)
        counts = selected['counts']
        if (report.get('status') != 'imported' or report.get('year') != 2025
                or report.get('revision') != selected['source_revision']
                or manifest['revision'] != selected['source_revision']
                or report.get('validation', {}).get('counts') != counts
                or report.get('distribution') != download
                or download.get('sha256') != selected['upstream_sha256']
                or download.get('tls', {}).get('handshake_verified') is not True
                or download['tls'].get('partial_chain_allowed') is not False):
            raise ValueError('education_report_mismatch')
        if (manifest['files']['places.jsonl']['records'] != counts['eligible']
                or any(manifest['files'][name]['records'] != 0 for name in ('finance.jsonl', 'resources.jsonl'))):
            raise ValueError('education_catalog_counts')
        partitions = manifest['partitions']
        if any(p['dataset'] != selected['dataset'] or p['eligible'] is not True for p in partitions):
            raise ValueError('education_catalog_profile')
        states = {p['state'] for p in partitions}
        declared = report['validation']['partitions']
        if set(declared) != states:
            raise ValueError('education_partition_states')
        for state in states:
            parts = [p for p in partitions if p['state'] == state]
            if sum(p['records'] for p in parts) != declared[state].get('eligible', 0):
                raise ValueError('education_partition_counts')
        if (sum(p['records'] for p in partitions if not p['with_geometry']) != counts['without_geometry']
                or any(sum(p.get(k, 0) for p in declared.values()) != counts[k] for k in COUNT_KEYS)):
            raise ValueError('education_partition_totals')
        yield root, manifest


def exercise(archive, selection, *, browser=False):
    from fastapi.testclient import TestClient
    from bdt.api import create_app
    selected = read_selection(selection)
    with verified_education(archive, selected) as (root, manifest):
        database = root / 'verified.db'
        install_catalog(root / 'public-catalog', database)
        with TestClient(create_app('sqlite:///' + str(database), testing=True)) as client:
            response = client.get('/api/places', params={'kind': 'school', 'limit': 1})
            if response.status_code != 200 or response.json()['total'] != selected['counts']['eligible']:
                raise ValueError('education_api_total')
            for partition in manifest['partitions']:
                state = client.get('/api/places', params={'kind': 'school', 'state': partition['state'], 'limit': 1})
                if state.status_code != 200 or state.json()['total'] != partition['records']:
                    raise ValueError('education_api_partition')
            for route in ('/api/groups', '/api/workbench/documents', '/api/observations/mine'):
                if client.get(route).status_code != 401:
                    raise ValueError('education_private_route')
        if browser:
            from browser_public_catalog import main
            main(['--catalog', str(root / 'public-catalog'), '--manifest-sha256',
                  selected['members']['public-catalog/manifest.json']['sha256'],
                  '--dataset', selected['dataset'], '--output', 'test-results/browser-education'])
        return {'schema': 'bdt.education-acceptance.v1', 'status': 'passed',
                'tested_revision': os.getenv('GITHUB_SHA', 'development'), 'python': platform.python_version(),
                'archive_sha256': selected['artifact']['sha256'], 'source_revision': selected['source_revision'],
                'source_run': selected['artifact']['run_id'], 'tag': selected['tag'],
                'counts': selected['counts'], 'states_checked': len(manifest['partitions']),
                'api_checked': True, 'browser_checked': browser, 'fresh_collection': False,
                'public_deployment': False, 'national_completeness_certified': False,
                'original_artifact_preserved': True, 'synthetic_records_added': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = exercise(args.archive, args.selection, browser=args.browser)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encode(result))
    print(encode(result))


if __name__ == '__main__':
    main()
