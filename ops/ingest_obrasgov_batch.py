# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a bounded Obrasgov page-window ingest. Not a national census.

Default UFs/pages are a sample. Reports pages_fetched and
national_catalog_certified=false. Geometry is joined by project id only.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from bdt.obrasgov_batch import DEFAULT_SAMPLE_STATES, batch_ingest_obrasgov
from bdt.storage import Database

SAMPLE_RECEIPT_SCHEMA = 'bdt.obrasgov-sample.v1'
_FORBIDDEN_TOTAL_KEYS = frozenset({
    'combined_cents',
    'financial_total',
    'summed_cents',
    'total_cents',
    'total_valor',
    'valor_total',
})
_OPTIONAL_RECEIPT_STATS = (
    'status',
    'reason',
    'started_at',
    'finished_at',
    'max_pages_per_state',
    'page_size',
    'errors',
    'geometry_errors',
    'execution_errors',
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ingest_obrasgov_batch')


def _reject_financial_totals(payload: dict) -> None:
    for key in _FORBIDDEN_TOTAL_KEYS:
        if key in payload:
            raise ValueError('obrasgov_sample_must_not_sum_financial_totals')
    counts = payload.get('counts')
    if isinstance(counts, dict):
        for value in counts.values():
            if isinstance(value, dict) and (
                _FORBIDDEN_TOTAL_KEYS & value.keys() or 'cents' in value
            ):
                raise ValueError('obrasgov_sample_must_not_sum_financial_totals')


def _sample_states_from_stats(stats: dict) -> list[str]:
    if 'sample_states' in stats:
        raw = stats['sample_states']
    elif 'states' in stats:
        raw = stats['states']
    else:
        return list(DEFAULT_SAMPLE_STATES)
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError('invalid_sample_states')
    states: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError('invalid_sample_states')
        states.append(item)
    return states


def _pages_fetched_from_stats(stats: dict) -> int:
    if 'pages_fetched' not in stats:
        return 0
    pages = stats['pages_fetched']
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 0:
        raise ValueError('invalid_pages_fetched')
    return pages


def write_sample_receipt(stats: dict, output: Path) -> dict:
    """Write a bounded-sample honesty receipt. Never a Brazil census or money total."""
    if not isinstance(stats, dict):
        raise ValueError('invalid_obrasgov_sample_stats')
    _reject_financial_totals(stats)
    if stats.get('facility_id_invented') is True:
        raise ValueError('obrasgov_facility_id_invented')

    pages_fetched = _pages_fetched_from_stats(stats)
    sample_states = _sample_states_from_stats(stats)
    if stats.get('national_catalog_certified') is True:
        logger.warning(
            'obrasgov_sample_receipt_uncertified pages_fetched=%s sample_states=%s',
            pages_fetched, ','.join(sample_states),
        )
    if stats.get('brazil_census') is True:
        logger.warning(
            'obrasgov_sample_receipt_not_census pages_fetched=%s sample_states=%s',
            pages_fetched, ','.join(sample_states),
        )

    receipt: dict = {
        'schema': SAMPLE_RECEIPT_SCHEMA,
        'national_catalog_certified': False,
        'brazil_census': False,
        'public_deployment': False,
        'sample_states': sample_states,
        'pages_fetched': pages_fetched,
        'facility_id_invented': False,
    }
    for key in _OPTIONAL_RECEIPT_STATS:
        if key in stats:
            receipt[key] = stats[key]
    _reject_financial_totals(receipt)

    path = Path(output)
    if path.exists() and path.is_dir():
        raise ValueError('obrasgov_sample_receipt_output_is_directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        tmp.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise

    logger.info(
        'obrasgov_sample_receipt schema=%s path=%s pages_fetched=%s sample_states=%s '
        'national_catalog_certified=%s brazil_census=%s public_deployment=%s '
        'facility_id_invented=%s status=%s',
        receipt['schema'], path, receipt['pages_fetched'], ','.join(receipt['sample_states']),
        receipt['national_catalog_certified'], receipt['brazil_census'],
        receipt['public_deployment'], receipt['facility_id_invented'], receipt.get('status'),
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description='Bounded Obrasgov sample ingest (not a Brazil census).')
    parser.add_argument('--database', default='data/bdt_national.db', help='Path to SQLite database')
    parser.add_argument('--states', nargs='+', default=list(DEFAULT_SAMPLE_STATES),
                        help='Sample UFs (default five; not 27-UF coverage)')
    parser.add_argument('--max-pages', type=int, default=1, help='Max pages per state (bounded sample, not census)')
    parser.add_argument('--page-size', type=int, default=100, help='Page size for API queries')
    parser.add_argument('--no-enrich', action='store_true', help='Skip geometry/execution enrichment')
    parser.add_argument('--output', type=Path, default=None,
                        help='Write sample honesty receipt JSON (not a Brazil census)')
    args = parser.parse_args()

    db_path = Path(args.database)
    if not db_path.exists():
        logger.error(f'Database file not found: {db_path}')
        sys.exit(1)

    logger.info(f'Connecting to database: {db_path}')
    database = Database(f'sqlite:///{db_path}')

    logger.info(f'Starting Obrasgov batch ingestion for states {args.states} (max {args.max_pages} pages of {args.page_size} items)...')
    t0 = time.time()
    stats = batch_ingest_obrasgov(
        database,
        states=args.states,
        max_pages_per_state=args.max_pages,
        page_size=args.page_size,
        enrich_details=not args.no_enrich
    )
    t1 = time.time()

    logger.info(
        'Finished bounded Obrasgov sample in %.2fs pages_fetched=%s national_catalog_certified=%s',
        t1 - t0, stats.get('pages_fetched'), stats.get('national_catalog_certified'),
    )
    for k, v in stats.items():
        logger.info('  %s: %s', k, v)

    if args.output is not None:
        receipt = write_sample_receipt(stats, args.output)
        logger.info(
            'Wrote Obrasgov sample receipt path=%s pages_fetched=%s national_catalog_certified=%s brazil_census=%s',
            args.output, receipt['pages_fetched'], receipt['national_catalog_certified'], receipt['brazil_census'],
        )


if __name__ == '__main__':
    main()
