"""Portable, verified public catalog releases; never exports community or credentials.

This operator module deliberately does not replace an active application database.
It exports a consistent snapshot of explicit public tables and installs into a NEW
SQLite database. Updating production requires a separate reviewed deployment.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from sqlalchemy import inspect, select
from .domain import MoneyEvent, PlaceInput, Source, digest, fold, now
from .evidence import Resource, ResourceInput, initialize_extensions
from .json_codec import decode
from .storage import Change, Database, Finance, Municipality, Place, SchemaVersion

FORMAT = 'brasildetodos-public-catalog-v1'
# Ordering is also the foreign-key import order. Never enumerate all DB tables.
TABLES = (Municipality.__table__, Place.__table__, Finance.__table__, Resource.__table__, Change.__table__)
FILES = tuple(table.name + '.jsonl' for table in TABLES)
MAX_LINE_BYTES = 1024 * 1024
MAX_FILE_BYTES = 4 * 1024**3
MAX_TOTAL_BYTES = 8 * 1024**3
MAX_RECORDS = 5_000_000
EXCLUDED = ['accounts', 'sessions', 'rate_limits', 'citizen_observations',
            'moderation_audit', 'document_originals', 'document_extractions', 'reviewer_identities',
            'document_links', 'recovery_codes', 'evidence_photos', 'photo_content']
SOURCE_ID_FIELDS = ('dataset', 'url', 'snapshot_sha256', 'reference_date')
SOURCE_FIELDS = SOURCE_ID_FIELDS + ('collected_at',)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def timestamp(value):
    if not isinstance(value, str) or len(value) > 80:
        raise ValueError('invalid_catalog_timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('timestamp_requires_timezone')
    return value


def validate_record(table, row: dict) -> dict:
    """Validate published schema AND consistency of denormalized query columns."""
    if not isinstance(row, dict) or set(row) != {c.name for c in table.columns}:
        raise ValueError('unexpected_catalog_columns')
    if table is Municipality.__table__:
        if not isinstance(row['id'], str) or not re.fullmatch(r'[0-9]{7}', row['id']):
            raise ValueError('invalid_municipality_id')
        if not isinstance(row['name'], str) or not 1 <= len(row['name']) <= 200:
            raise ValueError('invalid_municipality_name')
        if not re.fullmatch(r'[A-Z]{2}', row['state']):
            raise ValueError('invalid_state')
        Source.model_validate(row['source'])
    elif table is Place.__table__:
        place = PlaceInput.model_validate(row['payload'])
        payload = place.model_dump(mode='json')
        for key in ('id', 'kind', 'catalogue_eligible', 'name', 'municipality_id', 'state', 'latitude', 'longitude'):
            if row[key] != payload[key]:
                raise ValueError('inconsistent_place_columns')
        if row['dataset'] != place.source.dataset or row['search_name'] != fold(place.name + ' ' + place.address):
            raise ValueError('inconsistent_place_index')
        semantic = payload | {'source': {k: v for k, v in payload['source'].items()
                                        if k not in {'collected_at', 'snapshot_sha256'}}}
        if row['fingerprint'] != digest(semantic):
            raise ValueError('inconsistent_place_fingerprint')
        timestamp(row['updated_at'])
    elif table is Finance.__table__:
        item = MoneyEvent.model_validate(row['payload'])
        if (row['key'] != digest([item.source.dataset, item.id]) or row['cents'] != item.cents
                or row['municipality_id'] != item.municipality_id or row['facility_id'] != item.facility_id):
            raise ValueError('inconsistent_financial_columns')
    elif table is Resource.__table__:
        item = ResourceInput.model_validate(row['payload'])
        if any(row[k] != getattr(item, k) for k in ('id', 'kind', 'municipality_id', 'title')):
            raise ValueError('inconsistent_resource_columns')
        if row['source'] != item.source.model_dump(mode='json'):
            raise ValueError('inconsistent_resource_source')
    elif table is Change.__table__:
        timestamp(row['at'])
        if not isinstance(row['id'], str) or not 1 <= len(row['id']) <= 36:
            raise ValueError('invalid_history_id')
        for value in (row['before'], row['after']):
            if value is not None and PlaceInput.model_validate(value).id != row['place_id']:
                raise ValueError('inconsistent_history_identity')
        if row['after'] is None or not isinstance(row['fields'], list) or any(
                not isinstance(field, str) or len(field) > 100 for field in row['fields']):
            raise ValueError('invalid_history_fields')
    return row


@contextmanager
def consistent_read(database):
    # SQLite's legacy driver does not BEGIN on SELECT. Explicit BEGIN pins a snapshot.
    with database.engine.connect() as connection:
        if database.engine.dialect.name == 'postgresql':
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
            with connection.begin():
                yield connection
        elif database.engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN')
            try:
                yield connection
            finally:
                connection.rollback()
        else:
            raise ValueError('unsupported_catalog_database')


def public_row_source(table, row):
    if table is Municipality.__table__ or table is Resource.__table__:
        return row['source']
    if table in (Place.__table__, Finance.__table__):
        return row['payload']['source']
    return row['after']['source']


def remember_source(sources: dict, table, row) -> None:
    source = public_row_source(table, row)
    source_key = digest({key: source.get(key) for key in SOURCE_ID_FIELDS})
    sources[source_key] = {key: source.get(key) for key in SOURCE_FIELDS}


def check_sources(manifest: dict, sources: dict) -> None:
    if manifest.get('sources') != list(sources.values()):
        raise ValueError('catalog_source_manifest_mismatch')


def export_catalog(database: Database, destination: Path, revision: str = 'development') -> dict:
    """No source-table mutation. Refuse existing destination and partial output."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('catalog_destination_exists')
    if revision != 'development' and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('invalid_revision')
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.bdt-catalog-', dir=destination.parent))
    try:
        files, counts, sources = {}, Counter(), {}
        total_bytes = 0
        with consistent_read(database) as connection:
            present = set(inspect(connection).get_table_names())
            if not {t.name for t in (SchemaVersion.__table__, Municipality.__table__, Place.__table__)}.issubset(present):
                raise ValueError('uninitialized_catalog_database')
            if connection.execute(select(SchemaVersion.version).where(SchemaVersion.id == 1)).scalar() != 1:
                raise ValueError('unsupported_catalog_database_version')
            for table in TABLES:
                name = table.name + '.jsonl'
                h, size, count = hashlib.sha256(), 0, 0
                with (staging/name).open('xb') as stream:
                    if table.name in present:
                        statement = select(table).order_by(*table.primary_key.columns)
                        rows = connection.execution_options(stream_results=True).execute(statement).mappings()
                        for mapping in rows:
                            row = validate_record(table, dict(mapping))
                            line = canonical(row) + b'\n'
                            if len(line) > MAX_LINE_BYTES:
                                raise ValueError('catalog_line_budget')
                            size += len(line); total_bytes += len(line); count += 1
                            if size > MAX_FILE_BYTES or total_bytes > MAX_TOTAL_BYTES or count > MAX_RECORDS:
                                raise ValueError('catalog_export_budget')
                            stream.write(line); h.update(line)
                            remember_source(sources, table, row)
                            if table is Place.__table__:
                                counts[(row['dataset'], row['state'], row['catalogue_eligible'], row['latitude'] is not None)] += 1
                    stream.flush(); os.fsync(stream.fileno())
                files[name] = {'sha256': h.hexdigest(), 'bytes': size, 'records': count}
        partitions = [{'dataset': k[0], 'state': k[1], 'eligible': k[2], 'with_geometry': k[3], 'records': v}
                      for k, v in sorted(counts.items())]
        manifest = {'format': FORMAT, 'generated_at': now(), 'revision': revision, 'files': files,
            'partitions': partitions, 'sources': list(sources.values()), 'excluded': EXCLUDED,
            'national_catalog_certified': False,
            'scope': 'only records included in this release; counts do not certify nationwide completeness',
            'hashes_prove_integrity_not_authenticity': True}
        manifest_bytes = canonical(manifest)
        if len(manifest_bytes) > 8*1024*1024:
            raise ValueError('catalog_manifest_budget')
        with (staging/'manifest.json').open('xb') as stream:
            stream.write(manifest_bytes); stream.flush(); os.fsync(stream.fileno())
        # No overwrite: another exporter must not win the same destination name.
        if destination.exists():
            raise FileExistsError('catalog_destination_exists')
        staging.rename(destination)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def load_manifest(folder: Path) -> dict:
    path = folder/'manifest.json'
    if folder.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > 8*1024*1024:
        raise ValueError('invalid_catalog_manifest')
    manifest = decode(path.read_bytes())
    if (not isinstance(manifest, dict) or manifest.get('format') != FORMAT
            or not isinstance(manifest.get('files'), dict) or set(manifest['files']) != set(FILES)):
        raise ValueError('unsupported_catalog_format')
    if manifest.get('national_catalog_certified') is not False:
        raise ValueError('unsupported_national_certification')
    timestamp(manifest.get('generated_at'))
    revision = manifest.get('revision')
    if revision != 'development' and (not isinstance(revision, str) or not re.fullmatch(r'[a-f0-9]{40}', revision)):
        raise ValueError('invalid_revision')
    total = 0
    for name, entry in manifest['files'].items():
        if not isinstance(entry, dict) or set(entry) != {'sha256', 'bytes', 'records'}:
            raise ValueError('invalid_catalog_file_metadata')
        if any(type(entry[k]) is not int or entry[k] < 0 for k in ('bytes', 'records')):
            raise ValueError('invalid_catalog_file_counts')
        if entry['bytes'] > MAX_FILE_BYTES or entry['records'] > MAX_RECORDS:
            raise ValueError('catalog_file_budget')
        if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']):
            raise ValueError('invalid_catalog_file_hash')
        path = folder/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['bytes']:
            raise ValueError('catalog_file_size_mismatch')
        total += entry['bytes']
    if total > MAX_TOTAL_BYTES:
        raise ValueError('catalog_total_budget')
    return manifest


def records(folder: Path, table, manifest: dict) -> Iterator[dict]:
    name = table.name + '.jsonl'
    expected = manifest['files'][name]
    h, count, size = hashlib.sha256(), 0, 0
    with (folder/name).open('rb') as stream:
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LINE_BYTES:
                raise ValueError('catalog_line_budget')
            count += 1; size += len(line); h.update(line)
            if count > expected['records'] or size > expected['bytes']:
                raise ValueError('catalog_count_mismatch')
            yield validate_record(table, decode(line))
    if count != expected['records'] or size != expected['bytes'] or h.hexdigest() != expected['sha256']:
        raise ValueError('catalog_integrity_mismatch')


def check_partitions(manifest, counts):
    actual = [{'dataset': k[0], 'state': k[1], 'eligible': k[2], 'with_geometry': k[3], 'records': v}
              for k, v in sorted(counts.items())]
    if manifest.get('partitions') != actual:
        raise ValueError('catalog_partition_mismatch')


def count_partition(counts, table, row):
    if table is Place.__table__:
        counts[(row['dataset'], row['state'], row['catalogue_eligible'], row['latitude'] is not None)] += 1


def verify_catalog(folder: Path) -> dict:
    folder = Path(folder); manifest = load_manifest(folder)
    counts, sources = Counter(), {}
    for table in TABLES:
        for row in records(folder, table, manifest):
            count_partition(counts, table, row)
            remember_source(sources, table, row)
    check_partitions(manifest, counts)
    check_sources(manifest, sources)
    return manifest


def install_catalog(folder: Path, destination: Path) -> dict:
    """Build a NEW DB atomically. Never replaces existing accounts or live data."""
    folder, destination = Path(folder), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('database_destination_exists')
    manifest = load_manifest(folder)
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='.bdt-install-', dir=destination.parent))
    database = Database('sqlite:///' + str((work/'catalog.db').resolve()))
    try:
        database.initialize(); initialize_extensions(database)
        counts, sources = Counter(), {}
        with database.engine.begin() as connection:
            for table in TABLES:
                batch = []
                for row in records(folder, table, manifest):
                    count_partition(counts, table, row)
                    remember_source(sources, table, row)
                    batch.append(row)
                    if len(batch) == 500:
                        connection.execute(table.insert(), batch); batch.clear()
                if batch:
                    connection.execute(table.insert(), batch)
            check_partitions(manifest, counts)
            check_sources(manifest, sources)
            # Relationship consistency is checked in the same transaction.
            mismatch = connection.execute(select(Place.id).join(Municipality, Place.municipality_id == Municipality.id)
                .where(Place.state != Municipality.state).limit(1)).first()
            if mismatch:
                raise ValueError('catalog_municipality_state_mismatch')
            if connection.exec_driver_sql('PRAGMA foreign_key_check').first():
                raise ValueError('catalog_foreign_key_failure')
        with database.engine.connect() as connection:
            if connection.exec_driver_sql('PRAGMA integrity_check').scalar() != 'ok':
                raise ValueError('catalog_database_integrity_failure')
            connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        database.engine.dispose()
        path = work/'catalog.db'; path.chmod(0o600)
        # link() is an atomic no-clobber publication in the same filesystem.
        os.link(path, destination)
        return {'status': 'installed_new_database', 'files': manifest['files'],
                'national_catalog_certified': False, 'accounts_imported': False,
                'observations_imported': False, 'revision': manifest['revision']}
    finally:
        database.engine.dispose()
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export'); export.add_argument('--database', required=True)
    export.add_argument('--output', type=Path, required=True); export.add_argument('--revision', default='development')
    check = commands.add_parser('verify'); check.add_argument('folder', type=Path)
    install = commands.add_parser('install'); install.add_argument('folder', type=Path)
    install.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'export':
        database = Database(args.database)
        try:
            result = export_catalog(database, args.output, args.revision)
        finally:
            database.engine.dispose()
    elif args.command == 'verify':
        result = verify_catalog(args.folder)
    else:
        result = install_catalog(args.folder, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
