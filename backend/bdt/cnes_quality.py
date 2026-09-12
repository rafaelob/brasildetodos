"""Quarantine isolated CNES record defects without weakening the strict importer.

A whole-file schema change, unknown code meaning, or duplicate identity still
blocks the load. Only explicit, bounded quality budgets permit publishing the
valid subset; its ingestion is labelled partial_quality, never national-complete.
"""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from pathlib import Path
from pydantic import ValidationError
from .cnes_bulk import convert
from .domain import Source, digest, now
from .ingest import cnes_record, import_places, municipality_lookup, official_id
from .json_codec import decode
from .storage import Ingestion
from .sync import atomic_json, file_hash

MAX_ROWS = 2_000_000
MAX_ROW_BYTES = 64 * 1024


class QualityBudgetExceeded(ValueError):
    """The report is preserved; no records are published."""


def prepare(database, rows, source: Source, folder: Path, *, max_rejected: int = 0,
            max_rejected_fraction: float = 0.0) -> dict:
    if type(max_rejected) is not int or not 0 <= max_rejected <= 10000:
        raise ValueError('invalid_quarantine_count_budget')
    if isinstance(max_rejected_fraction, bool) or not 0 <= max_rejected_fraction <= .01:
        raise ValueError('invalid_quarantine_fraction_budget')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    lookup, seen, counts, reasons, partitions = municipality_lookup(database), set(), Counter(), Counter(), Counter()
    report = {'format': 'bdt-cnes-quality-v1', 'status': 'running', 'started_at': now(),
        'source': source.model_dump(mode='json'), 'national_catalog_certified': False,
        'policy': {'max_rejected': max_rejected, 'max_rejected_fraction': max_rejected_fraction},
        'counts': {}, 'reasons': {}, 'partitions': [], 'rejection_details_include_raw_rows': False}
    data_hash, data_bytes = hashlib.sha256(), 0
    try:
        with (folder/'prepared.jsonl').open('xb') as accepted, (folder/'quarantine.jsonl').open('x', encoding='utf-8') as quarantine:
            for index, original in enumerate(rows, 1):
                if index > MAX_ROWS:
                    raise ValueError('source_row_budget')
                if len(json.dumps(original, ensure_ascii=False).encode()) > MAX_ROW_BYTES:
                    raise ValueError('source_row_size_budget')
                counts['source_read'] += 1
                # Schema and meaning errors abort, rather than being reclassified as outliers.
                row = convert(original)
                identity, problems, outcome, state = None, [], None, 'unknown'
                try:
                    identity = official_id(row['codigo_cnes'], 7)
                except ValueError:
                    problems.append('invalid_cnes_identifier')
                if identity is not None:
                    if identity in seen:
                        raise ValueError('duplicate_cnes_identity_requires_reconciliation')
                    seen.add(identity)
                    row['codigo_cnes'] = identity
                    try:
                        item = cnes_record(row, source, lookup)
                        if item:
                            state = item.state
                            outcome = 'eligible'
                            counts['without_geometry'] += int(item.latitude is None)
                        else:
                            outcome = 'excluded_profile'
                            match = lookup.get(str(row['codigo_municipio']))
                            state = match[1] if match else 'unknown'
                    except KeyError:
                        problems.append('municipality_not_in_loaded_crosswalk')
                    except ValidationError as error:
                        problems.extend('.'.join(map(str, issue['loc'])) + ':' + issue['type']
                                        for issue in error.errors(include_input=False, include_url=False))
                if problems:
                    counts['quarantined'] += 1
                    reasons.update(problems)
                    partitions[(state, 'quarantined')] += 1
                    # Institutional identifier + row hash allows finding the source record.
                    # Do not publish full source rows, names, emails, or exception payloads.
                    if counts['quarantined'] <= 10000:
                        quarantine.write(json.dumps({'row': index, 'source_id': identity,
                            'row_sha256': digest(original), 'reasons': sorted(problems)}, ensure_ascii=False) + '\n')
                    continue
                counts[outcome] += 1
                counts['prepared'] += 1
                partitions[(state, outcome)] += 1
                encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode() + b'\n'
                accepted.write(encoded); data_hash.update(encoded); data_bytes += len(encoded)
        report['counts'] = dict(counts)
        report['reasons'] = dict(reasons)
        report['partitions'] = [{'state': k[0], 'classification': k[1], 'records': n}
                                for k, n in sorted(partitions.items())]
        if not counts['source_read'] or not counts['eligible']:
            raise QualityBudgetExceeded('no_eligible_records')
        ratio = counts['quarantined'] / counts['source_read']
        report.update(prepared_sha256=data_hash.hexdigest(), prepared_bytes=data_bytes,
            quarantined_fraction=ratio, finished_at=now())
        if counts['quarantined'] > max_rejected or ratio > max_rejected_fraction:
            raise QualityBudgetExceeded('quarantine_budget_exceeded')
        report['status'] = 'ready_with_quarantine' if counts['quarantined'] else 'ready'
        atomic_json(folder/'quality.json', report)
        return report
    except Exception as error:
        report.update(status='blocked', counts=dict(counts), reasons=dict(reasons), finished_at=now(),
            error_code=str(error) if isinstance(error, ValueError) else 'preparation_failed')
        atomic_json(folder/'quality.json', report)
        raise


def prepared_rows(folder: Path):
    with (folder/'prepared.jsonl').open('rb') as stream:
        while True:
            line = stream.readline(MAX_ROW_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_ROW_BYTES:
                raise ValueError('prepared_row_size_budget')
            yield decode(line)


def publish(database, folder: Path) -> dict:
    folder = Path(folder)
    if folder.is_symlink() or (folder/'quality.json').is_symlink() or (folder/'prepared.jsonl').is_symlink():
        raise ValueError('quality_artifact_symlink')
    report = decode((folder/'quality.json').read_bytes())
    if report.get('format') != 'bdt-cnes-quality-v1' or report.get('status') not in {'ready', 'ready_with_quarantine'}:
        raise ValueError('quality_report_not_ready')
    if report.get('national_catalog_certified') is not False:
        raise ValueError('unsupported_national_certification')
    counts, policy = report['counts'], report['policy']
    rejected = counts.get('quarantined', 0)
    if (rejected > policy['max_rejected'] or rejected / counts['source_read'] > policy['max_rejected_fraction']
            or counts['source_read'] != counts['prepared'] + rejected
            or counts['prepared'] != counts.get('eligible', 0) + counts.get('excluded_profile', 0)):
        raise ValueError('quality_counts_or_policy_mismatch')
    path = folder/'prepared.jsonl'
    if path.stat().st_size != report['prepared_bytes'] or file_hash(path) != report['prepared_sha256']:
        raise ValueError('prepared_artifact_integrity_failure')
    # Revalidate all rows with the unchanged strict importer. The preflight is not
    # permission to skip errors that appear during publication.
    actual = sum(1 for _ in prepared_rows(folder))
    if actual != counts['prepared']:
        raise ValueError('prepared_count_mismatch')
    result = import_places(database, prepared_rows(folder), Source.model_validate(report['source']), 'cnes')
    with database.session() as session:
        run = session.get(Ingestion, result['run_id'])
        run.status = 'partial_quality' if rejected else 'completed_file'
        run.counts = dict(run.counts) | {'source_read': counts['source_read'], 'quarantined': rejected}
        run.error = 'See minimized quality report for quarantined records.' if rejected else None
    return result | {'quarantined': rejected, 'source_read': counts['source_read'],
                     'status': 'partial_quality' if rejected else 'completed_file',
                     'national_catalog_certified': False, 'quality_sha256': file_hash(folder/'quality.json')}
