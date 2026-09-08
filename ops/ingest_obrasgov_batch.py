# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run batch ingestion of official Obrasgov open data into the national catalog.

Enriches the national catalog with verified public works, physical execution percentages,
official GPS pins, and planned execution dates across multiple Brazilian states.
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
    parser = argparse.ArgumentParser(description='Batch ingest official Obrasgov projects.')
    parser.add_argument('--database', default='data/bdt_national.db', help='Path to SQLite database')
    parser.add_argument('--states', nargs='+', default=['RR', 'AP', 'AC', 'SE', 'RO'], help='States to ingest')
    parser.add_argument('--max-pages', type=int, default=1, help='Max pages (100 items per page) per state')
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

    logger.info(f'Finished batch ingestion in {t1 - t0:.2f}s:')
    for k, v in stats.items():
        logger.info(f'  {k}: {v}')


if __name__ == '__main__':
    main()
