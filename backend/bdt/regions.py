# SPDX-License-Identifier: AGPL-3.0-or-later
"""Municipal discovery and snapshot-consistent context, never facility attribution.

The municipality directory is small and normalized in memory so matching has the
same accent semantics on SQLite and PostgreSQL. Service/resource tables are only
aggregated in SQL. Nothing in these read-only endpoints starts a collection.
"""
from __future__ import annotations

from fastapi import HTTPException, Query
from sqlalchemy import and_, case, func, select

from .catalog_release import consistent_read
from .coverage_dashboard import SOURCES, STATES, source_group
from .domain import Source, fold, now
from .evidence import Resource
from .storage import Finance, Municipality, Place

DIRECTORY_BUDGET = 20000


def directory(database, *, q: str = '', state: str | None = None,
              page: int = 1, limit: int = 20) -> dict:
    if len(q) > 200 or state is not None and state not in STATES:
        raise ValueError('invalid_municipality_filter')
    if not 1 <= page <= 100000 or not 1 <= limit <= 100:
        raise ValueError('invalid_municipality_page')
    statement = select(Municipality.id, Municipality.name, Municipality.state)
    if state:
        statement = statement.where(Municipality.state == state)
    with consistent_read(database) as connection:
        rows = connection.execute(statement.limit(DIRECTORY_BUDGET + 1)).mappings().all()
    if len(rows) > DIRECTORY_BUDGET:
        raise RuntimeError('municipality_directory_requires_review')
    needle = fold(q.strip())
    matched = [dict(row) for row in rows if not needle or needle in fold(row['name']) or needle in row['id']]
    matched.sort(key=lambda row: (fold(row['name']), row['state'], row['id']))
    offset = (page - 1) * limit
    return {'items': matched[offset:offset + limit], 'total': len(matched),
            'page': page, 'limit': limit, 'has_more': offset + limit < len(matched),
            'scope': 'imported_municipality_directory', 'q': q.strip(), 'state': state,
            'national_coverage_certified': False}


def _public_source(raw):
    try:
        if not isinstance(raw, dict):
            return None
        return Source.model_validate({key: raw[key] for key in Source.model_fields if key in raw}).model_dump(mode='json')
    except (ValueError, TypeError):
        return None


def summary(database, municipality_id: str) -> dict | None:
    with consistent_read(database) as connection:
        municipality = connection.execute(select(Municipality.__table__).where(
            Municipality.id == municipality_id)).mappings().first()
        if municipality is None:
            return None
        located = and_(Place.latitude.is_not(None), Place.longitude.is_not(None))
        groups = connection.execute(select(Place.kind,
            func.count().label('records'),
            func.sum(case((located, 1), else_=0)).label('with_geometry'))
            .where(Place.municipality_id == municipality_id, Place.catalogue_eligible.is_(True))
            .group_by(Place.kind)).mappings().all()
        by_kind = {row['kind']: dict(row) for row in groups}
        services = []
        for kind in ('school', 'health', 'work'):
            group = by_kind.get(kind, {'records': 0, 'with_geometry': 0})
            services.append({'kind': kind, 'records': group['records'],
                'with_geometry': group['with_geometry'],
                'without_geometry': group['records'] - group['with_geometry']})
        family = source_group(Place.dataset)
        source_rows = connection.execute(select(family.label('id'), func.count().label('records'))
            .where(Place.municipality_id == municipality_id, Place.catalogue_eligible.is_(True))
            .group_by(family).order_by(family)).mappings().all()
        resource_family = source_group(Resource.source['dataset'].as_string())
        basis = case((Resource.payload['attributes']['territorial_basis'].as_string() ==
            'buyer_registered_municipality_not_execution', 'buyer_registered_municipality'),
            else_='municipal_reference_not_facility_assignment')
        resource_rows = connection.execute(select(resource_family.label('source_id'),
            basis.label('territorial_basis'), func.count().label('records'))
            .where(Resource.municipality_id == municipality_id)
            .group_by(resource_family, basis).order_by(resource_family, basis)).mappings().all()
        # These are event RECORD COUNTS, not amounts or a sum of financial phases.
        phase = Finance.payload['phase'].as_string()
        financial_rows = connection.execute(select(phase.label('phase'), func.count().label('records'))
            .where(Finance.municipality_id == municipality_id)
            .group_by(phase).order_by(phase)).mappings().all()
    return {
        'municipality': {'id': municipality['id'], 'name': municipality['name'], 'state': municipality['state'],
            'source': _public_source(municipality['source'])},
        'generated_at': now(), 'scope': 'loaded_records_in_this_installation',
        'services': services, 'service_records': sum(row['records'] for row in services),
        'sources': [{'id': row['id'], 'records': row['records'],
                     'documentation_url': SOURCES[row['id']][0]} for row in source_rows],
        'resource_groups': [dict(row) for row in resource_rows],
        'resource_records': sum(row['records'] for row in resource_rows),
        'financial_event_groups': [{'phase': row['phase'] if row['phase'] in
            {'estimated', 'agreed', 'committed', 'transferred', 'contracted', 'liquidated', 'paid'}
            else 'unknown', 'records': row['records']} for row in financial_rows],
        'financial_total_computed': False, 'facility_assignment_inferred': False,
        'national_coverage_certified': False,
    }


def install(app, database):
    @app.get('/api/territories/search')
    def search(q: str = Query('', max_length=200), state: str | None = Query(None, pattern=r'^[A-Z]{2}$'),
               page: int = Query(1, ge=1, le=100000), limit: int = Query(20, ge=1, le=100)):
        try:
            return directory(database, q=q, state=state, page=page, limit=limit)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError:
            raise HTTPException(503, 'municipality_directory_unavailable') from None

    @app.get('/api/territories/{municipality_id}/summary')
    def context(municipality_id: str):
        import re
        if not re.fullmatch(r'[0-9]{7}', municipality_id):
            raise HTTPException(422, 'invalid_municipality_id')
        result = summary(database, municipality_id)
        if result is None:
            raise HTTPException(404, 'municipality_not_found')
        return result
