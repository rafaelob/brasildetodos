# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded read-only summaries. Favorites stay on the device, not in this DB.

POST keeps the chosen IDs out of URL/access-log query strings. The server still
receives those IDs to answer the request; deployments must not log request bodies.
Timeline times mean detection in stored records, never a confirmed real-world event.
"""
from collections import defaultdict
from typing import Annotated

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .domain import PlaceInput, Source, StrictModel, digest, now
from .catalog_release import consistent_read
from .coverage_dashboard import _timestamp as public_timestamp
from .storage import Change, Place

PlaceID = Annotated[str, Field(strict=True, max_length=180, pattern=r'^[a-z0-9_-]+:[A-Za-z0-9._/-]+$')]
PUBLIC_FIELDS = ('name', 'kind', 'address', 'phone', 'declared_services', 'municipality_id',
                 'state', 'catalogue_eligible', 'latitude', 'longitude', 'geo_source')


class WatchRequest(StrictModel):
    place_ids: list[PlaceID] = Field(min_length=1, max_length=30)
    versions_per_place: int = Field(default=3, ge=1, le=5, strict=True)


def public_place(raw: dict, expected_id: str) -> dict:
    """Whitelist fields even if a legacy stored payload has extra private keys."""
    if not isinstance(raw, dict) or raw.get('id') != expected_id:
        raise ValueError('place_identity_mismatch')
    source = raw.get('source')
    if not isinstance(source, dict):
        raise ValueError('missing_public_source')
    clean = {key: raw[key] for key in PlaceInput.model_fields if key in raw}
    clean['source'] = {key: source[key] for key in Source.model_fields if key in source}
    return PlaceInput.model_validate(clean).model_dump(mode='json')


def semantic_place(value: dict) -> dict:
    """Match the stored content fingerprint, excluding collection-only changes."""
    return value | {'source': {key: item for key, item in value['source'].items()
                              if key not in {'collected_at', 'snapshot_sha256'}}}


def public_version(row: Change) -> dict:
    after = public_place(row.after, row.place_id)
    fields = []
    previous_source = None
    if row.before is None:
        kind = 'started'
    else:
        before = public_place(row.before, row.place_id)
        previous_source = before['source']
        for key in PUBLIC_FIELDS:
            if before.get(key) != after.get(key):
                fields.append({'key': key, 'before': before.get(key), 'after': after.get(key)})
        changed_content = bool(fields)
        if before['source']['reference_date'] != after['source']['reference_date']:
            fields.append({'key': 'source.reference_date',
                           'before': before['source']['reference_date'],
                           'after': after['source']['reference_date']})
        kind = 'updated' if changed_content else 'source_revision'
    return {'id': row.id, 'recorded_at': public_timestamp(row.at), 'type': kind, 'fields': fields, 'source': after['source'], 'previous_source': previous_source}


def watch_summary(database, request: WatchRequest) -> dict:
    ids = list(dict.fromkeys(request.place_ids))
    with consistent_read(database) as connection, Session(bind=connection) as session:
        places = {row.id: row for row in session.scalars(select(Place).where(Place.id.in_(ids)))}
        # Counts and bounded rows are evaluated in the same query, so a new
        # import cannot make the history count disagree between SELECTs.
        ranked = select(Change.id,
            func.count(Change.id).over(partition_by=Change.place_id).label('total'),
            func.min(Change.at).over(partition_by=Change.place_id).label('first'),
            func.row_number().over(partition_by=Change.place_id,
                order_by=(Change.at.desc(), Change.id.desc())).label('position'))\
            .where(Change.place_id.in_(ids)).subquery()
        changes = defaultdict(list)
        counts = {}
        for row, total, first in session.execute(select(Change, ranked.c.total, ranked.c.first)
                .join(ranked, ranked.c.id == Change.id)
                .where(ranked.c.position <= request.versions_per_place)
                .order_by(Change.place_id, Change.at.desc(), Change.id.desc())):
            changes[row.place_id].append(row)
            counts[row.place_id] = (total, first)
        items = []
        for identifier in ids:
            row = places.get(identifier)
            if row is None:
                items.append({'id': identifier, 'status': 'not_found', 'place': None, 'history': None})
                continue
            try:
                value = public_place(row.payload, identifier)
                columns = ('catalogue_eligible', 'kind', 'municipality_id', 'name',
                           'state', 'latitude', 'longitude')
                if (any(value[key] != getattr(row, key) for key in columns) or
                        value['source']['dataset'] != row.dataset or
                        digest(semantic_place(value)) != row.fingerprint):
                    raise ValueError('stored_place_conflict')
                preserved = changes[identifier]
                if preserved and semantic_place(public_place(preserved[0].after, identifier)) != semantic_place(value):
                    raise ValueError('stored_place_history_conflict')
                versions = [public_version(change) for change in preserved]
                total, first = counts.get(identifier, (0, None))
                items.append({'id': identifier,
                    'status': 'available' if value['catalogue_eligible'] else 'outside_current_profile',
                    'place': value, 'history': {'total_versions': total, 'included': len(versions),
                        'truncated': total > len(versions), 'first_recorded_at': public_timestamp(first), 'versions': versions}})
            except (ValueError, TypeError, KeyError):
                # One damaged stored item must not hide every other saved place.
                items.append({'id': identifier, 'status': 'unavailable', 'place': None, 'history': None})
        return {'generated_at': now(), 'scope': 'loaded_records_only', 'favorites_persisted': False,
                'versions_per_place': request.versions_per_place, 'items': items}


def install(app, database):
    @app.post('/api/saved-places/summary')
    def summary(body: WatchRequest):
        return watch_summary(database, body)
