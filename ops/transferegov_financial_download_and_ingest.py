# SPDX-License-Identifier: AGPL-3.0-or-later
"""Download official Transferegov archives and ingest verified financial records into bdt_national.db.

Downloads:
- siconv_prop_inst_indicadores_municipios.zip (crosswalk)
- siconv_convenio.zip (agreed instruments)
- siconv_desembolso.zip (disbursements)

Normalizes into MoneyEvent and transactionally imports into the finance table.
Excludes natural person identities and bank accounts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen
import zipfile

from bdt.domain import Source, now
from bdt.ingest import municipality_lookup
from bdt.storage import Database
from bdt.sync import atomic_json, download_retry, file_hash
from bdt.transferegov_finance import (
    load_municipality_crosswalk,
    normalize_agreements,
    normalize_amendments,
    normalize_disbursements,
    import_transferegov_financial,
)

BASE = 'https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/'

TARGET_FILES = {
    'siconv_prop_inst_indicadores_municipios.zip': {
        'max_bytes': 32 * 1024 * 1024,
        'member': 'siconv_prop_inst_indicadores_municipios.csv',
    },
    'siconv_convenio.zip': {
        'max_bytes': 48 * 1024 * 1024,
        'member': 'siconv_convenio.csv',
    },
    'siconv_termo_aditivo.zip': {
        'max_bytes': 80 * 1024 * 1024,
        'member': 'siconv_termo_aditivo.csv',
    },
    'siconv_desembolso.zip': {
        'max_bytes': 48 * 1024 * 1024,
        'member': 'siconv_desembolso.csv',
    },
}



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


def run_ingest(db_path: Path, downloads_dir: Path, *, limit_agreements: int | None = None, limit_amendments: int | None = None, limit_disbursements: int | None = None) -> dict:
    t0 = time.time()
    receipts = download_all(downloads_dir)
    database = Database(f'sqlite:///{db_path.resolve()}')
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
    if limit_agreements:
        conv_rows = (row for _, row in zip(range(limit_agreements), conv_rows))
    agreements = list(normalize_agreements(conv_rows, crosswalk, source))

    # 3. Normalize amendments
    adit_path = downloads_dir / 'siconv_termo_aditivo.zip'
    adit_rows = stream_csv_zip(adit_path, 'siconv_termo_aditivo.csv')
    if limit_amendments:
        adit_rows = (row for _, row in zip(range(limit_amendments), adit_rows))
    amendments = list(normalize_amendments(adit_rows, crosswalk, source))

    # 4. Normalize disbursements
    disb_path = downloads_dir / 'siconv_desembolso.zip'
    disb_rows = stream_csv_zip(disb_path, 'siconv_desembolso.csv')
    if limit_disbursements:
        disb_rows = (row for _, row in zip(range(limit_disbursements), disb_rows))
    disbursements = list(normalize_disbursements(disb_rows, crosswalk, source))

    # 5. Import transactionally
    events = agreements + amendments + disbursements
    counts = import_transferegov_financial(database, events, source)
    counts['elapsed_seconds'] = round(time.time() - t0, 2)
    counts['crosswalk_entries'] = len(crosswalk)
    database.engine.dispose()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('data/bdt_national.db'))
    parser.add_argument('--downloads', type=Path, default=Path('data/downloads/transferegov'))
    parser.add_argument('--limit-agreements', type=int, default=None)
    parser.add_argument('--limit-amendments', type=int, default=None)
    parser.add_argument('--limit-disbursements', type=int, default=None)
    args = parser.parse_args()

    result = run_ingest(
        args.database,
        args.downloads,
        limit_agreements=args.limit_agreements,
        limit_amendments=args.limit_amendments,
        limit_disbursements=args.limit_disbursements,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))



if __name__ == '__main__':
    main()
