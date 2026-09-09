# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a bounded Obrasgov page-window ingest. Not a national census.

Default UFs/pages are a sample. Reports pages_fetched and
national_catalog_certified=false. Geometry is joined by project id only.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from bdt.storage import Database
from bdt.obrasgov_batch import batch_ingest_obrasgov

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('ingest_obrasgov_batch')


def main():
    parser = argparse.ArgumentParser(description='Bounded Obrasgov sample ingest (not a Brazil census).')
    parser.add_argument('--database', default='data/bdt_national.db', help='Path to SQLite database')
    parser.add_argument('--states', nargs='+', default=['RR', 'AP', 'AC', 'SE', 'RO'],
                        help='Sample UFs (default five; not 27-UF coverage)')
    parser.add_argument('--max-pages', type=int, default=1, help='Max pages per state (bounded sample, not census)')
    parser.add_argument('--page-size', type=int, default=100, help='Page size for API queries')
    parser.add_argument('--no-enrich', action='store_true', help='Skip geometry/execution enrichment')
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


if __name__ == '__main__':
    main()
