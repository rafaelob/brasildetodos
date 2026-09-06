"""Read-only public metadata and immutable resource history, without raw files."""
from fastapi import HTTPException, Query
from sqlalchemy import func, select
from .evidence import Resource
from .resource_profiles import PROFILES, STATES
from .resource_sync import ResourceRevision, initialize_resource_versions


def browse(database, *, municipality_id=None, kind=None, page=1, limit=30, q='', profile=None, state=None):
    if profile is not None and profile not in PROFILES:
        raise ValueError('unknown_resource_profile')
    if state is not None and state not in STATES:
        raise ValueError('invalid_resource_state')
    statement = select(Resource)
    if municipality_id:
        statement = statement.where(Resource.municipality_id == municipality_id)
    if kind:
        statement = statement.where(Resource.kind == kind)
    if q.strip():
        statement = statement.where(func.lower(Resource.title).contains(q.strip().lower(), autoescape=True))
    if profile:
        statement = statement.where(Resource.source['dataset'].as_string() == profile)
    if state:
        statement = statement.where(Resource.payload['attributes']['state'].as_string() == state)
    with database.session() as session:
        count = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = session.scalars(statement.order_by(Resource.id).offset((page-1)*limit).limit(limit))
        return {'total': count, 'page': page, 'limit': limit, 'items': [row.payload for row in rows],
                'scope': 'loaded_resource_metadata_not_all_public_spending'}


def install(app, database):
    initialize_resource_versions(database)

    @app.get('/api/resource-history/{resource_id:path}')
    def history(resource_id: str, page: int = Query(1, ge=1, le=100000), limit: int = Query(10, ge=1, le=30)):
        with database.session() as session:
            resource = session.get(Resource, resource_id)
            if resource is None:
                raise HTTPException(404, 'resource_not_found')
            query = select(ResourceRevision).where(ResourceRevision.resource_id == resource_id)
            count = session.scalar(select(func.count()).select_from(query.subquery()))
            versions = session.scalars(query.order_by(ResourceRevision.revision.desc()).offset((page-1)*limit).limit(limit))
            return {'resource': resource.payload, 'total': count, 'page': page, 'limit': limit,
                'versions': [{'revision': v.revision, 'observed_at': v.observed_at,
                              'changed_fields': v.changed_fields, 'resource': v.payload} for v in versions],
                'scope': 'versions_observed_by_this_installation_not_complete_official_history'}
