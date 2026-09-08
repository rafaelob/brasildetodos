"""Public, bounded coverage of this installation, not of real-world services.

Only reviewed source families and explicit aggregate fields are exposed. Import
queries, raw source objects, paths, free-text errors and personal records never
form part of these responses. A failed import cannot erase the loaded totals.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import Query
from sqlalchemy import and_, case, func, select

from .catalog_release import consistent_read
from .domain import now
from .evidence import Resource
from .storage import Ingestion, Municipality, Place

SourceFilter = Literal['all', 'ibge', 'inep', 'cnes', 'pncp', 'transferegov', 'obrasgov', 'other']
StatusFilter = Literal['all', 'completed', 'partial', 'failed', 'running', 'unknown']
STATES = tuple('AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split())
SOURCES = {
    'ibge': ('https://servicodados.ibge.gov.br/api/docs/localidades', ('ibge', 'ibge-municipalities')),
    'inep': ('https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar', ('inep', 'inep-schools-2025')),
    'cnes': ('https://cnes.datasus.gov.br/', ('cnes', 'cnes-national-bulk')),
    'pncp': ('https://www.gov.br/pncp/pt-br/acesso-a-informacao/copy_of_dados-abertos', ('pncp_contracts', 'pncp')),
    'transferegov': ('https://www.gov.br/transferegov/pt-br', ('transferegov_special_plans', 'transferegov', 'transferegov-national-financial')),
    'obrasgov': ('https://www.gov.br/obrasgov/pt-br', ('obrasgov_projects', 'obrasgov')),
    'other': (None, ()),
}
STATUS_ALIASES = {
    'completed': ('success', 'completed_file'),
    'partial': ('partial_quality',),
    'failed': ('failed',),
    'running': ('running',),
}
MAX_SAFE_INTEGER = 2**53 - 1


def source_group(column):
    """Do not expose arbitrary dataset labels supplied by an operator."""
    return case(*[(column.in_(aliases), key) for key, (_, aliases) in SOURCES.items() if aliases], else_='other')


def status_group(column):
    return case(*[(column.in_(aliases), key) for key, aliases in STATUS_ALIASES.items()], else_='unknown')


def _count(value):
    return value if type(value) is int and 0 <= value <= MAX_SAFE_INTEGER else None


def _timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _reference(value):
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r'\d{4}', value):
            return value if 1900 <= int(value) <= 2100 else None
        if re.fullmatch(r'\d{4}-\d{2}', value):
            date.fromisoformat(value + '-01')
            return value
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value).isoformat()
        return _timestamp(value)
    except ValueError:
        return None


def public_run(row) -> dict:
    """Project recorded attempt counters, never infer publication from a failed tx."""
    source = next((key for key, (_, aliases) in SOURCES.items() if row['dataset'] in aliases), 'other')
    status = next((key for key, aliases in STATUS_ALIASES.items() if row['status'] in aliases), 'unknown')
    raw = row['counts'] if isinstance(row['counts'], dict) else {}
    counts = {key: _count(raw.get(key)) for key in ('read', 'source_read', 'excluded', 'quarantined', 'unchanged', 'without_geometry')}
    if counts['read'] is None:
        counts['read'] = _count(raw.get('records_attempted'))
    counts['created'] = counts['updated'] = None
    publication = 'unknown'
    if status == 'failed':
        publication = 'not_published'
        counts['created'] = counts['updated'] = 0
        # These can be tentative counters from the rolled-back transaction.
        counts['unchanged'] = counts['without_geometry'] = None
    elif status == 'running':
        publication = 'pending'
        counts['unchanged'] = counts['without_geometry'] = None
    elif status in ('completed', 'partial'):
        publication = 'partial' if status == 'partial' else 'recorded'
        for public, alternatives in [('created', ('created', 'inserted')), ('updated', ('updated',))]:
            present = [raw[key] for key in alternatives if key in raw]
            counts[public] = _count(present[0]) if len(present) == 1 else (0 if not present else None)
        # Successful Counter-based loaders omit counters when their value is zero.
        for key in ('excluded', 'unchanged', 'without_geometry'):
            if key not in raw:
                counts[key] = 0
    try:
        identity = str(UUID(str(row['id'])))
    except ValueError:
        identity = 'run-' + hashlib.sha256(str(row['id']).encode()).hexdigest()[:24]
    return {'id': identity, 'source_id': source, 'dataset': source, 'status': status,
            'started_at': _timestamp(row['started_at']), 'finished_at': _timestamp(row['finished_at']),
            'reference_date': _reference(row.get('reference_date')), 'counts': counts,
            'publication': publication, 'scope': 'recorded_attempt_not_national_release',
            'error_code': 'import_not_published' if status == 'failed' else None}


def _run_columns():
    return (Ingestion.id, Ingestion.dataset, Ingestion.status, Ingestion.started_at, Ingestion.finished_at,
            Ingestion.counts, Ingestion.source['reference_date'].as_string().label('reference_date'))


def read_imports(connection, source: str = 'all', status: str = 'all', page: int = 1, limit: int = 10) -> dict:
    filters = []
    if source != 'all':
        filters.append(source_group(Ingestion.dataset) == source)
    if status != 'all':
        filters.append(status_group(Ingestion.status) == status)
    total = connection.scalar(select(func.count()).select_from(Ingestion).where(*filters))
    records = connection.execute(select(*_run_columns()).where(*filters)
        .order_by(Ingestion.started_at.desc(), Ingestion.id.desc()).offset((page - 1) * limit).limit(limit)).mappings()
    return {'items': [public_run(row) for row in records], 'total': total, 'page': page, 'limit': limit,
            'has_more': page * limit < total, 'source': source, 'status': status,
            'scope': 'recorded_import_attempts_in_this_installation', 'national_catalog_certified': False}


def build_coverage(connection) -> dict:
    family = source_group(Place.dataset)
    state = case((Place.state.in_(STATES), Place.state), else_='unknown')
    located = and_(Place.latitude.is_not(None), Place.longitude.is_not(None))
    groups = connection.execute(select(family.label('source_id'), state.label('state'),
        func.count().label('records'), func.sum(case((located, 1), else_=0)).label('geocoded'))
        .where(Place.catalogue_eligible.is_(True)).group_by(family, state).order_by(family, state)).mappings()
    partitions = [{'dataset': row['source_id'], **row, 'without_geometry': row['records'] - row['geocoded']} for row in groups]
    sources = {key: {'id': key, 'documentation_url': url, 'places': 0, 'geocoded': 0,
        'without_geometry': 0, 'resources': 0, 'last_attempt': None} for key, (url, _) in SOURCES.items()}
    for row in partitions:
        for key in ('places', 'geocoded', 'without_geometry'):
            sources[row['source_id']][key] += row['records' if key == 'places' else key]
    resource_family = source_group(Resource.source['dataset'].as_string())
    for key, count in connection.execute(select(resource_family, func.count()).group_by(resource_family)):
        sources[key]['resources'] = count
    # Latest attempt in each family, independent of the first history page.
    ranked = select(*_run_columns(), func.row_number().over(partition_by=source_group(Ingestion.dataset),
        order_by=(Ingestion.started_at.desc(), Ingestion.id.desc())).label('rank')).subquery()
    for row in connection.execute(select(ranked).where(ranked.c.rank == 1)).mappings():
        projected = public_run(row)
        sources[projected['source_id']]['last_attempt'] = projected
    municipalities = connection.scalar(select(func.count()).select_from(Municipality))
    municipalities_with_places = connection.scalar(select(func.count(func.distinct(Place.municipality_id)))
        .where(Place.catalogue_eligible.is_(True)))
    source_read = read_imports(connection, limit=5)
    loaded = sum(row['records'] for row in partitions)
    geocoded = sum(row['geocoded'] for row in partitions)
    for key, value in sources.items():
        has_data = bool(value['places'] or value['resources'] or (key == 'ibge' and municipalities))
        value['data_state'] = 'loaded' if has_data else 'not_loaded'
    return {'schema_version': 1, 'generated_at': now(), 'scope': 'loaded_records_in_this_installation',
        'national_catalog_certified': False, 'municipalities': municipalities,
        'summary': {'places': loaded, 'geocoded': geocoded, 'without_geometry': loaded - geocoded,
                    'states_with_places': len({row['state'] for row in partitions if row['state'] in STATES}),
                    'municipalities_with_places': municipalities_with_places,
                    'resources': sum(row['resources'] for row in sources.values())},
        'sources': list(sources.values()), 'partitions': partitions, 'runs': source_read['items'],
        'imports_total': source_read['total'], 'reference_dates_scope': 'per_record_not_attempt_date'}


def install(app, database):
    @app.get('/api/coverage')
    def coverage():
        with consistent_read(database) as connection:
            return build_coverage(connection)

    @app.get('/api/imports')
    def imports(source: SourceFilter = 'all', status: StatusFilter = 'all',
                page: int = Query(1, ge=1, le=10000), limit: int = Query(10, ge=1, le=50)):
        with consistent_read(database) as connection:
            return read_imports(connection, source, status, page, limit)
