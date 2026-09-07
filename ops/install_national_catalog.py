# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install the reviewed health/resources and school releases into ONE new database.

No source matching, public-data downloads or live-database writes. Identical IBGE
rows can be shared; all other overlapping identities are rejected, never replaced.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import tempfile

from sqlalchemy import func, select, case
from bdt.catalog_release import canonical, records, count_partition, check_partitions
from bdt.resource_release import _copy_pinned
from bdt.storage import Change, Database, Finance, Municipality, Observation, Place, User
from bdt.evidence import Resource
from bdt.resource_sync import ResourceRevision
from education_release import read_selection as school_selection, verified_education
from public_data_bundle import install as install_base, require_new_database, sha, verify
from verify_published_data import read_selection as base_selection


def append_school_catalog(database, folder, manifest):
    """Preserve exact rows; a collision or mismatch rolls back the whole append.

    Called only against an unpublished staging database created by this module.
    No reconciliation policy is guessed for differing territorial metadata.
    """
    with database.engine.begin() as connection:
        existing = {row['id']: canonical(dict(row)) for row in
                    connection.execute(select(Municipality.__table__)).mappings()}
        shared = 0
        seen_municipalities = set()
        for row in records(folder, Municipality.__table__, manifest):
            if row['id'] in seen_municipalities:
                raise ValueError('national_duplicate_territory')
            seen_municipalities.add(row['id'])
            if existing.get(row['id']) != canonical(row):
                raise ValueError('national_territory_conflict')
            shared += 1
        if seen_municipalities != set(existing):
            raise ValueError('national_territory_coverage_mismatch')
        counts = Counter()
        new_ids = set()
        for table in (Place.__table__, Change.__table__):
            batch = []
            for row in records(folder, table, manifest):
                if table is Place.__table__:
                    if row['kind'] != 'school':
                        raise ValueError('national_school_kind_mismatch')
                    new_ids.add(row['id'])
                elif row['place_id'] not in new_ids:
                    raise ValueError('national_school_history_mismatch')
                count_partition(counts, table, row)
                batch.append(row)
                if len(batch) == 500:
                    connection.execute(table.insert(), batch)
                    batch.clear()
            if batch:
                connection.execute(table.insert(), batch)
        check_partitions(manifest, counts)
        mismatch = connection.execute(select(Place.id).join(Municipality)
            .where(Place.state != Municipality.state).limit(1)).first()
        if mismatch or connection.exec_driver_sql('PRAGMA foreign_key_check').first():
            raise ValueError('national_territorial_integrity_failure')
    return shared


def install(health_archive, school_archive, destination, *, health_selection, education_selection):
    """All-or-nothing publication into a path that must not already exist."""
    destination = Path(destination)
    require_new_database(destination)
    health = base_selection(Path(health_selection))
    schools = school_selection(Path(education_selection))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.bdt-national-', dir=destination.parent) as temporary:
        work = Path(temporary)
        frozen = work / 'health-selected.zip'
        _copy_pinned(Path(health_archive), frozen, health['archive']['sha256'], health['archive']['bytes'])
        if frozen.stat().st_size != health['archive']['bytes']:
            raise ValueError('national_base_size_mismatch')
        checked = verify(frozen, health['archive']['sha256'])
        if checked['counts'] != health['counts'] or checked['selected_inputs'] != health['selected_inputs']:
            raise ValueError('national_base_selection_mismatch')
        with verified_education(Path(school_archive), schools) as (inputs, manifest):
            staged = work / 'application.db'
            base = install_base(frozen, health['archive']['sha256'], staged)
            database = Database('sqlite:///' + str(staged.resolve()))
            try:
                with database.session() as session:
                    old_history = session.scalar(select(func.count()).select_from(Change))
                    old_missing = session.scalar(select(func.count()).select_from(Place).where(Place.latitude.is_(None)))
                shared = append_school_catalog(database, inputs / 'public-catalog', manifest)
                expected = base['counts'] | {'places': base['counts']['places'] + schools['counts']['eligible']}
                with database.session() as session:
                    counts = {model.__tablename__: session.scalar(select(func.count()).select_from(model))
                              for model in (Place, Resource, ResourceRevision, Finance, User, Observation)}
                    history = session.scalar(select(func.count()).select_from(Change))
                    missing = session.scalar(select(func.count()).select_from(Place).where(Place.latitude.is_(None)))
                    by_kind = dict(session.execute(select(Place.kind, func.count()).group_by(Place.kind)).all())
                    partitions = [dict(row) for row in session.execute(select(
                        Place.dataset, Place.kind, Place.state, func.count().label('records'),
                        func.sum(case((Place.latitude.is_(None), 1), else_=0)).label('without_geometry')
                    ).group_by(Place.dataset, Place.kind, Place.state)
                     .order_by(Place.dataset, Place.kind, Place.state)).mappings()]
                if (counts != expected or counts['users'] or counts['observations']
                        or history != old_history + manifest['files']['changes.jsonl']['records']
                        or missing != old_missing + schools['counts']['without_geometry']):
                    raise ValueError('national_installed_counts_mismatch')
                with database.engine.connect() as connection:
                    if connection.exec_driver_sql('PRAGMA integrity_check').scalar() != 'ok':
                        raise ValueError('national_database_integrity_failure')
                    if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                        raise ValueError('national_database_foreign_key_failure')
                    checkpoint = connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)').one()
                    if checkpoint[0] != 0 or checkpoint[1] != checkpoint[2]:
                        raise ValueError('national_database_checkpoint_busy')
            finally:
                database.engine.dispose()
            staged.chmod(0o600)
            with staged.open('rb') as stream:
                os.fsync(stream.fileno())
            database_hash = sha(staged)
            database_bytes = staged.stat().st_size
            require_new_database(destination)
            os.link(staged, destination)
            return {'schema': 'bdt.national-install.v1', 'status': 'installed_new_database',
                    'health_tag': health['tag'], 'education_tag': schools['tag'],
                    'health_sha256': health['archive']['sha256'],
                    'education_sha256': schools['artifact']['sha256'],
                    'database_sha256': database_hash, 'database_bytes': database_bytes,
                    'counts': counts, 'by_kind': by_kind, 'partitions': partitions,
                    'shared_municipalities': shared,
                    'history_records': history, 'without_geometry': missing,
                    'automatic_links_created': 0, 'financial_events_created_from_metadata': 0,
                    'source_records_rewritten': False, 'existing_database_modified': False,
                    'fresh_collection': False, 'public_deployment': False}


def accept_api(destination, result):
    """Check the real mixed installation and source-preserving detail responses."""
    from fastapi.testclient import TestClient
    from bdt.api import create_app
    with TestClient(create_app('sqlite:///' + str(Path(destination).resolve()), testing=True)) as client:
        for path, total in (('/api/places', result['counts']['places']),
                            ('/api/resources', result['counts']['resources'])):
            response = client.get(path, params={'limit': 1})
            if response.status_code != 200 or response.json()['total'] != total:
                raise ValueError('national_api_total_mismatch')
        for kind, count in result['by_kind'].items():
            response = client.get('/api/places', params={'kind': kind, 'limit': 1})
            if response.status_code != 200 or response.json()['total'] != count:
                raise ValueError('national_api_kind_mismatch')
            item = response.json()['items'][0]
            detail = client.get('/api/places/' + item['id'])
            if (detail.status_code != 200 or detail.json()['place'] != item
                    or detail.json()['observations'] != []):
                raise ValueError('national_detail_failed')
        for partition in result['partitions']:
            response = client.get('/api/places', params={
                'kind': partition['kind'], 'state': partition['state'], 'limit': 1})
            # These reviewed inputs contain one source per service kind.
            if response.status_code != 200 or response.json()['total'] != partition['records']:
                raise ValueError('national_api_partition_mismatch')
        for route in ('/api/groups', '/api/workbench/documents', '/api/observations/mine'):
            if client.get(route).status_code != 401:
                raise ValueError('national_private_route_failed')
    return {'api_checked': True, 'kinds_checked': sorted(result['by_kind']),
            'partitions_checked': len(result['partitions']),
            'private_routes_protected': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--health', required=True, type=Path)
    parser.add_argument('--education', required=True, type=Path)
    parser.add_argument('--health-selection', type=Path, default=Path('data/releases/public-data-20260906-v1.json'))
    parser.add_argument('--education-selection', type=Path, default=Path('data/releases/education-2025-20260907-v1.json'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    result = install(args.health, args.education, args.output,
                     health_selection=args.health_selection, education_selection=args.education_selection)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
