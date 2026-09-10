# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validate cached Transferegov financial archives; ingest only into a new operator sqlite.

Freeze/validate mode checks cached zip bytes, SHA-256 against receipts.json, zip
member names and CSV headers. It never downloads, never writes data/bdt.db, and
never sums financial phases. Full import is operator-only on an explicit
``--database`` that is not the live application sqlite. The ingest operator
returns an uncertified receipt with row counts, never a summed financial total.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import time
from typing import Iterator
import zipfile

from bdt.domain import Source, now
from bdt.ingest import municipality_lookup
from bdt.storage import Database
from bdt.sync import atomic_json, download_retry, file_hash
from bdt.transferegov_finance import (
    EXCLUDED_SENSITIVE_KEYS,
    REQUIRED_ADITIVO,
    REQUIRED_CONVENIO,
    REQUIRED_CROSSWALK,
    REQUIRED_DESEMBOLSO,
    import_transferegov_financial,
    load_municipality_crosswalk,
    normalize_agreements,
    normalize_amendments,
    normalize_disbursements,
    parse_brl_cents,
)

BASE = 'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/'
LIVE_APP_DB_NAME = 'bdt.db'

TARGET_FILES = {
    'siconv_prop_inst_indicadores_municipios.zip': {
        'max_bytes': 32 * 1024 * 1024,
        'member': 'siconv_prop_inst_indicadores_municipios.csv',
        'required_columns': REQUIRED_CROSSWALK,
        'kind': 'crosswalk',
    },
    'siconv_convenio.zip': {
        'max_bytes': 48 * 1024 * 1024,
        'member': 'siconv_convenio.csv',
        'required_columns': REQUIRED_CONVENIO,
        'kind': 'convenio',
    },
    'siconv_termo_aditivo.zip': {
        'max_bytes': 80 * 1024 * 1024,
        'member': 'siconv_termo_aditivo.csv',
        'required_columns': REQUIRED_ADITIVO,
        'kind': 'aditivo',
    },
    'siconv_desembolso.zip': {
        'max_bytes': 48 * 1024 * 1024,
        'member': 'siconv_desembolso.csv',
        'required_columns': REQUIRED_DESEMBOLSO,
        'kind': 'desembolso',
    },
}


def refuse_live_app_database(db_path: Path | None) -> Path:
    """Operator ingest requires a new sqlite; the live application db is forbidden."""
    if db_path is None:
        raise ValueError('database_required_for_ingest')
    path = Path(db_path)
    if path.name == LIVE_APP_DB_NAME:
        raise ValueError('refuse_live_app_database:data/bdt.db')
    try:
        resolved = path.expanduser().resolve()
    except OSError as error:
        raise ValueError('refuse_live_app_database:unresolvable') from error
    if resolved.name == LIVE_APP_DB_NAME:
        raise ValueError('refuse_live_app_database:data/bdt.db')
    return path


def download_all(dest_dir: Path) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)
    receipts = {}
    for name, meta in TARGET_FILES.items():
        target = dest_dir / name
        url = BASE + name
        if target.is_file() and target.stat().st_size > 0:
            receipts[name] = {
                'url': url,
                'path': str(target),
                'bytes': target.stat().st_size,
                'sha256': file_hash(target),
                'status': 'cached',
            }
        else:
            receipt = download_retry(url, target, meta['max_bytes'])
            receipts[name] = {
                'url': url,
                'path': str(target),
                'bytes': receipt['bytes'],
                'sha256': receipt['sha256'],
                'collected_at': receipt['collected_at'],
                'status': 'downloaded',
            }
    atomic_json(dest_dir / 'receipts.json', receipts)
    return receipts


def stream_csv_zip(archive_path: Path, member_name: str, encoding: str = 'utf-8-sig') -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(archive_path) as z:
        with z.open(member_name) as stream:
            with io.TextIOWrapper(stream, encoding=encoding, errors='replace', newline='') as text:
                reader = csv.DictReader(text, delimiter=';')
                for row in reader:
                    yield row


def _csv_header(archive: zipfile.ZipFile, member: str) -> list[str]:
    info = archive.getinfo(member)
    if info.flag_bits & 1:
        raise ValueError(f'encrypted_zip:{member}')
    last_error: Exception | None = None
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            with archive.open(member) as stream:
                with io.TextIOWrapper(stream, encoding=encoding, errors='strict', newline='') as text:
                    reader = csv.reader(text, delimiter=';')
                    header = next(reader, None)
            if not header or any(not cell.strip() for cell in header):
                raise ValueError(f'invalid_csv_header:{member}')
            if len(header) != len(set(header)):
                raise ValueError(f'duplicate_csv_header:{member}')
            return header
        except UnicodeDecodeError as error:
            last_error = error
            continue
    raise ValueError(f'unreadable_csv_header:{member}') from last_error


def validate_cached_archive(archive_path: Path, name: str, receipt: dict, meta: dict) -> dict:
    if not archive_path.is_file():
        raise ValueError(f'missing_cached_archive:{name}')
    size = archive_path.stat().st_size
    expected_bytes = receipt.get('bytes')
    expected_hash = receipt.get('sha256')
    if not isinstance(expected_bytes, int) or expected_bytes <= 0:
        raise ValueError(f'invalid_receipt_bytes:{name}')
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise ValueError(f'invalid_receipt_sha256:{name}')
    if size != expected_bytes:
        raise ValueError(f'archive_size_mismatch:{name}')
    if size > meta['max_bytes']:
        raise ValueError(f'archive_over_budget:{name}')
    digest = file_hash(archive_path)
    if digest != expected_hash.lower():
        raise ValueError(f'archive_hash_mismatch:{name}')
    member = meta['member']
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if member not in names:
            raise ValueError(f'missing_zip_member:{name}:{member}')
        header = _csv_header(archive, member)
    required = meta['required_columns']
    missing = sorted(required.difference(header))
    if missing:
        raise ValueError(f'missing_required_columns:{name}:{",".join(missing)}')
    return {
        'name': name,
        'bytes': size,
        'sha256': digest,
        'member': member,
        'header_field_count': len(header),
        'required_columns_present': sorted(required),
        'status': 'validated',
    }


def _limited(rows: Iterator[dict[str, str]], sample_limit: int | None) -> Iterator[dict[str, str]]:
    if sample_limit is None:
        yield from rows
        return
    for index, row in enumerate(rows):
        if index >= sample_limit:
            break
        yield row


def _count_crosswalk(rows: Iterator[dict[str, str]]) -> tuple[set[str], dict[str, int]]:
    ids: set[str] = set()
    seen = mapped = 0
    for row in rows:
        seen += 1
        nr = (row.get('NR_CONVENIO') or '').strip()
        code = (row.get('COD_MUNIC_IBGE') or '').strip()
        if nr and code:
            ids.add(nr)
            mapped += 1
    return ids, {'rows_seen': seen, 'mapped': mapped}


def _count_convenio(rows: Iterator[dict[str, str]], crosswalk_ids: set[str]) -> dict[str, int]:
    seen = signed = preconvenio = orphan = 0
    for row in rows:
        seen += 1
        nr = (row.get('NR_CONVENIO') or '').strip()
        if (row.get('IND_ASSINADO') or '').strip().upper() == 'SIM':
            signed += 1
        else:
            preconvenio += 1
        if nr and nr not in crosswalk_ids:
            orphan += 1
    return {
        'rows_seen': seen,
        'signed': signed,
        'preconvenio': preconvenio,
        'orphan_instruments': orphan,
    }


def _count_aditivo(rows: Iterator[dict[str, str]], crosswalk_ids: set[str]) -> dict[str, int]:
    seen = negative = zero = positive = unparsed = orphan = 0
    for row in rows:
        seen += 1
        nr = (row.get('NR_CONVENIO') or '').strip()
        if nr and nr not in crosswalk_ids:
            orphan += 1
        try:
            cents = parse_brl_cents(row.get('VL_GLOBAL_TA'))
        except ValueError:
            unparsed += 1
            continue
        if cents < 0:
            negative += 1
        elif cents > 0:
            positive += 1
        else:
            zero += 1
    return {
        'rows_seen': seen,
        'negative': negative,
        'zero': zero,
        'positive': positive,
        'unparsed': unparsed,
        'orphan_instruments': orphan,
    }


def _count_desembolso(rows: Iterator[dict[str, str]], crosswalk_ids: set[str]) -> dict[str, int]:
    seen = orphan = 0
    for row in rows:
        seen += 1
        nr = (row.get('NR_CONVENIO') or '').strip()
        if nr and nr not in crosswalk_ids:
            orphan += 1
    return {'rows_seen': seen, 'orphan_instruments': orphan}


def _honesty(report: dict) -> dict:
    report['records_imported'] = 0
    report['financial_total_computed'] = False
    report['national_catalog_certified'] = False
    report['public_data_v1_unchanged'] = True
    report['phases_summed'] = False
    if 'total_cents' in report or 'combined_cents' in report or 'financial_total' in report:
        raise ValueError('phases_must_not_be_summed')
    counts = report.get('counts')
    if isinstance(counts, dict):
        if 'total_cents' in counts or 'combined_cents' in counts or 'financial_total' in counts:
            raise ValueError('phases_must_not_be_summed')
        for value in counts.values():
            if isinstance(value, dict) and (
                'cents' in value or 'total_cents' in value or 'combined_cents' in value or 'financial_total' in value
            ):
                raise ValueError('phases_must_not_be_summed')
    return report


def _ingest_honesty(report: dict) -> dict:
    """Ingest persisted rows; still forbid phase totals and catalog certification."""
    counts = report.get('counts')
    imported = counts.get('total') if isinstance(counts, dict) else None
    _honesty(report)
    if not isinstance(imported, int):
        raise ValueError('ingest_counts_total_required')
    report['records_imported'] = imported
    return report


def _download_archives(receipts: dict) -> list[dict]:
    archives = []
    for name in TARGET_FILES:
        receipt = receipts[name]
        archives.append({
            'name': name,
            'url': receipt['url'],
            'bytes': receipt['bytes'],
            'sha256': receipt['sha256'],
            'status': receipt['status'],
        })
    return archives


def freeze_cached_archives(
    downloads_dir: Path,
    *,
    sample_limit: int | None = None,
    output: Path | None = None,
) -> dict:
    """Validate cached zips and count signed/preconvenio/negative/orphan rows without import."""
    started = now()
    receipts_path = downloads_dir / 'receipts.json'
    report: dict = {
        'schema': 'bdt.transferegov-finance-freeze.v1',
        'started_at': started,
        'mode': 'freeze',
        'downloads': str(downloads_dir).replace('\\', '/'),
        'count_scope': 'header_counter_pass' if sample_limit is None else 'bounded_sample',
        'sample_limit': sample_limit,
        'archives': [],
        'full_import': 'operator_only_new_sqlite',
        'live_app_database_refused': 'data/bdt.db',
        'public_deployment': False,
    }
    if not receipts_path.is_file():
        report['status'] = 'failed'
        report['reason'] = 'missing_receipts'
        return _honesty(report)
    receipts = json.loads(receipts_path.read_text(encoding='utf-8'))
    if not isinstance(receipts, dict) or not receipts:
        report['status'] = 'failed'
        report['reason'] = 'invalid_receipts'
        return _honesty(report)

    failed = False
    validated: dict[str, dict] = {}
    for name, meta in TARGET_FILES.items():
        receipt = receipts.get(name)
        try:
            if not isinstance(receipt, dict):
                raise ValueError(f'missing_receipt_entry:{name}')
            row = validate_cached_archive(downloads_dir / name, name, receipt, meta)
            validated[name] = row
            report['archives'].append(row)
        except (ValueError, OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as error:
            failed = True
            reason = str(error) if isinstance(error, ValueError) else type(error).__name__
            report['archives'].append({'name': name, 'status': 'failed', 'reason': reason})

    if failed:
        report['status'] = 'failed'
        report['counts'] = {}
        report['finished_at'] = now()
        return _honesty(report)

    crosswalk_meta = TARGET_FILES['siconv_prop_inst_indicadores_municipios.zip']
    crosswalk_ids, crosswalk_counts = _count_crosswalk(_limited(
        stream_csv_zip(downloads_dir / 'siconv_prop_inst_indicadores_municipios.zip', crosswalk_meta['member']),
        sample_limit,
    ))
    convenio_meta = TARGET_FILES['siconv_convenio.zip']
    aditivo_meta = TARGET_FILES['siconv_termo_aditivo.zip']
    desembolso_meta = TARGET_FILES['siconv_desembolso.zip']
    report['counts'] = {
        'crosswalk': crosswalk_counts,
        'convenio': _count_convenio(_limited(
            stream_csv_zip(downloads_dir / 'siconv_convenio.zip', convenio_meta['member']),
            sample_limit,
        ), crosswalk_ids),
        'aditivo': _count_aditivo(_limited(
            stream_csv_zip(downloads_dir / 'siconv_termo_aditivo.zip', aditivo_meta['member']),
            sample_limit,
        ), crosswalk_ids),
        'desembolso': _count_desembolso(_limited(
            stream_csv_zip(downloads_dir / 'siconv_desembolso.zip', desembolso_meta['member']),
            sample_limit,
        ), crosswalk_ids),
        'orphan_counts_relative_to_loaded_crosswalk_ids': True,
    }
    report['status'] = 'validated'
    report['finished_at'] = now()
    _honesty(report)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output, report)
        report['output'] = str(output).replace('\\', '/')
    return report


def run_ingest(db_path: Path, downloads_dir: Path, *, limit_agreements: int | None = None, limit_amendments: int | None = None, limit_disbursements: int | None = None) -> dict:
    db_path = refuse_live_app_database(db_path)
    t0 = time.time()
    receipts = download_all(downloads_dir)
    database = Database(f'sqlite:///{db_path.resolve()}')
    database.initialize()
    try:
        lookup = municipality_lookup(database)

        # 1. Load crosswalk
        cw_path = downloads_dir / 'siconv_prop_inst_indicadores_municipios.zip'
        cw_rows = stream_csv_zip(cw_path, 'siconv_prop_inst_indicadores_municipios.csv')
        crosswalk = load_municipality_crosswalk(cw_rows, lookup)

        # Source provenance
        conv_receipt = receipts['siconv_convenio.zip']
        source = Source(
            dataset='transferegov',
            url=conv_receipt['url'],
            record_id='transferegov-national-financial',
            collected_at=now(),
            snapshot_sha256=conv_receipt['sha256'],
            reference_date='2026',
        )

        # 2. Normalize agreements
        conv_path = downloads_dir / 'siconv_convenio.zip'
        conv_rows = stream_csv_zip(conv_path, 'siconv_convenio.csv')
        if limit_agreements is not None:
            conv_rows = (row for _, row in zip(range(limit_agreements), conv_rows))
        agreements = list(normalize_agreements(conv_rows, crosswalk, source))

        # 3. Normalize amendments
        adit_path = downloads_dir / 'siconv_termo_aditivo.zip'
        adit_rows = stream_csv_zip(adit_path, 'siconv_termo_aditivo.csv')
        if limit_amendments is not None:
            adit_rows = (row for _, row in zip(range(limit_amendments), adit_rows))
        amendments = list(normalize_amendments(adit_rows, crosswalk, source))

        # 4. Normalize disbursements
        disb_path = downloads_dir / 'siconv_desembolso.zip'
        disb_rows = stream_csv_zip(disb_path, 'siconv_desembolso.csv')
        if limit_disbursements is not None:
            disb_rows = (row for _, row in zip(range(limit_disbursements), disb_rows))
        disbursements = list(normalize_disbursements(disb_rows, crosswalk, source))

        # 5. Import transactionally
        events = agreements + amendments + disbursements
        imported = import_transferegov_financial(database, events, source)
        crosswalk_entries = len(crosswalk)
    finally:
        database.engine.dispose()

    counts = {
        'agreed': imported['agreed'],
        'amendments': imported['amendments'],
        'transferred': imported['transferred'],
        'total': imported['total'],
        'unchanged': imported['unchanged'],
        'crosswalk_entries': crosswalk_entries,
        'elapsed_seconds': round(time.time() - t0, 2),
    }
    report = {
        'schema': 'bdt.transferegov-finance-ingest.v1',
        'mode': 'ingest',
        'database': str(db_path).replace('\\', '/'),
        'downloads': str(downloads_dir).replace('\\', '/'),
        'archives': _download_archives(receipts),
        'counts': counts,
        'exclusions': {
            'sensitive_keys': sorted(EXCLUDED_SENSITIVE_KEYS),
            'preconvenio_not_imported': True,
            'orphans_not_imported': True,
            'facility_id': None,
        },
        'records_imported': counts['total'],
        'financial_total_computed': False,
        'national_catalog_certified': False,
        'phases_summed': False,
        'live_app_database_refused': 'data/bdt.db',
        'public_deployment': False,
        'full_import': 'operator_only_new_sqlite',
        'limits': {
            'agreements': limit_agreements,
            'amendments': limit_amendments,
            'disbursements': limit_disbursements,
        },
    }
    return _ingest_honesty(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('freeze', 'validate', 'ingest'), default='freeze')
    parser.add_argument('--database', type=Path, default=None, help='Required for ingest; refused if named bdt.db')
    parser.add_argument('--downloads', type=Path, default=Path('data/downloads/transferegov'))
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--sample-limit', type=int, default=0, help='Row cap for freeze counts; 0 = header+counter pass of every row')
    parser.add_argument('--limit-agreements', type=int, default=None)
    parser.add_argument('--limit-amendments', type=int, default=None)
    parser.add_argument('--limit-disbursements', type=int, default=None)
    args = parser.parse_args(argv)
    if args.mode in {'freeze', 'validate'}:
        sample_limit = None if args.sample_limit == 0 else args.sample_limit
        result = freeze_cached_archives(args.downloads, sample_limit=sample_limit, output=args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get('status') != 'validated':
            raise SystemExit(1)
        return
    if args.database is None:
        parser.error('database_required_for_ingest')
    result = run_ingest(
        args.database,
        args.downloads,
        limit_agreements=args.limit_agreements,
        limit_amendments=args.limit_amendments,
        limit_disbursements=args.limit_disbursements,
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output, result)
        result['output'] = str(args.output).replace('\\', '/')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
