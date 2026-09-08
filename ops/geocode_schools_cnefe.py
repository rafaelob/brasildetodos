# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run school geocoding against the national catalog using official IBGE CNEFE 2022 coordinates.

Resolves school coordinates (LATITUDE, LONGITUDE) with official IBGE census GPS survey pins,
recording provenance as 'IBGE-CNEFE-2022' in the audit ledger.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from bdt.storage import Database
from bdt.school_geocoder import (
    download_cnefe_state_zip,
    geocode_schools_for_state,
    parse_cnefe_schools,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('geocode_schools_cnefe')


def main():
    parser = argparse.ArgumentParser(description='Geocode public schools using official IBGE CNEFE 2022.')
    parser.add_argument('--database', default='data/bdt_national.db', help='Path to SQLite database')
    parser.add_argument('--states', nargs='+', default=['RR', 'AP', 'AC', 'SE', 'RO'], help='States to geocode')
    parser.add_argument('--cache-dir', default='data/cnefe_cache', help='Local cache directory for CNEFE zips')
    args = parser.parse_args()

    db_path = Path(args.database)
    if not db_path.exists():
        logger.error(f'Database file not found: {db_path}')
        sys.exit(1)

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f'Connecting to database: {db_path}')
    database = Database(f'sqlite:///{db_path}')

    total_matched = 0
    total_schools = 0

    for state in args.states:
        state_upper = state.upper()
        logger.info(f'=== Processing state {state_upper} ===')
        t0 = time.time()
        try:
            zip_bytes = download_cnefe_state_zip(state_upper, cache_dir=cache_dir)
            logger.info(f'Parsing CNEFE archive for {state_upper} ({len(zip_bytes)/(1024*1024):.2f} MB)...')
            cnefe_by_mun = parse_cnefe_schools(zip_bytes)
            num_est = sum(len(v) for v in cnefe_by_mun.values())
            logger.info(f'Found {num_est} educational establishments across {len(cnefe_by_mun)} municipalities in CNEFE for {state_upper}')

            stats = geocode_schools_for_state(database, state_upper, cnefe_by_mun)
            t1 = time.time()
            logger.info(f'Geocoded {state_upper} in {t1 - t0:.2f}s:')
            for k, v in stats.items():
                logger.info(f'  {k}: {v}')
            total_matched += stats.get('matched', 0)
            total_schools += stats.get('total_schools', 0)
        except Exception as exc:
            logger.error(f'Failed processing state {state_upper}: {exc}', exc_info=True)

    logger.info(f'All done! Matched {total_matched} / {total_schools} schools across {args.states}.')


if __name__ == '__main__':
    main()
