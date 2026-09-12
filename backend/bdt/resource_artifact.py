# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reconcile a minimized resource artifact without importing or collecting data.

Hash/row consistency is not an authenticity, national-completeness or deployment
certificate. Original supplier records and document contents are not emitted.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .evidence import ResourceInput
from .json_codec import decode
from .resource_export import public_resource
from .resource_profiles import PROFILES
from .domain import now

MAX_BYTES = 256 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_ROWS = 100000


def verify_resource_artifact(folder: Path) -> dict:
    folder = Path(folder)
    report_path = folder / 'report.json'
    records_path = folder / 'resources.jsonl'
    if report_path.is_symlink() or records_path.is_symlink():
        raise ValueError('resource_artifact_symlink_not_supported')
    if not 0 < report_path.stat().st_size <= 4 * 1024 * 1024:
        raise ValueError('resource_artifact_report_budget')
    with report_path.open('rb') as stream:
        report_bytes = stream.read(4 * 1024 * 1024 + 1)
    if len(report_bytes) > 4 * 1024 * 1024:
        raise ValueError('resource_artifact_report_budget')
    report = decode(report_bytes)
    if not isinstance(report, dict) or report.get('status') != 'passed':
        raise ValueError('resource_artifact_incomplete_report')
    expected = report.get('resources')
    if type(expected) is not int or not 0 <= expected <= MAX_ROWS:
        raise ValueError('resource_artifact_invalid_count')
    if records_path.stat().st_size > MAX_BYTES:
        raise ValueError('resource_artifact_byte_budget')
    digest = hashlib.sha256()
    ids = set()
    profiles, values = Counter(), Counter()
    precise_records = precise_fields = bytes_read = 0
    with records_path.open('rb') as stream:
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES or len(ids) >= MAX_ROWS:
                raise ValueError('resource_artifact_row_budget')
            bytes_read += len(line)
            if bytes_read > MAX_BYTES:
                raise ValueError('resource_artifact_byte_budget')
            digest.update(line)
            raw = decode(line)
            item = ResourceInput.model_validate(raw)
            if item.id in ids:
                raise ValueError('resource_artifact_duplicate_identity')
            ids.add(item.id)
            profile = item.attributes.get('profile')
            if profile not in PROFILES or item.source.dataset != profile or not item.id.startswith(profile + ':'):
                raise ValueError('resource_artifact_profile_mismatch')
            # Reuse the explicit public export projection, including exact amount
            # validation. No raw attributes, URLs or titles enter this report.
            projection = public_resource(item.model_dump(mode='json'))
            profiles[profile] += 1
            precise = 0
            for amount in projection['amounts']:
                values[amount['field']] += 1
                if amount['decimal'] is not None and amount['cents'] is None:
                    precise += 1
            precise_records += bool(precise)
            precise_fields += precise
    if digest.hexdigest() != report.get('resources_sha256'):
        raise ValueError('resource_artifact_hash_mismatch')
    if len(ids) != expected or dict(profiles) != report.get('by_profile'):
        raise ValueError('resource_artifact_count_mismatch')
    return {'schema': 'bdt.resource-artifact-check.v1', 'checked_at': now(),
        'status': 'passed', 'records': len(ids), 'by_profile': dict(sorted(profiles.items())),
        'amount_field_occurrences': dict(sorted(values.items())),
        'subcent_records': precise_records, 'subcent_fields': precise_fields,
        'resources_sha256': digest.hexdigest(),
        'report_sha256': hashlib.sha256(report_bytes).hexdigest(),
        'record_ids_unique': True, 'public_projection_validated': True,
        'financial_total_computed': False, 'fresh_collection': False,
        'production_database_changed': False, 'historical_ledger_verified': False,
        'national_coverage_certified': False, 'public_deployment': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error('evidence_destination_exists')
    result = verify_resource_artifact(args.folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also handles concurrent writers without overwriting.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
