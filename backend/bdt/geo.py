"""Bounded server-side map queries, independent of list pagination."""
from __future__ import annotations
import math
from sqlalchemy import Integer, cast, func, select
from .domain import fold
from .storage import Place


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = map(float, value.split(','))
    except (TypeError, ValueError):
        raise ValueError('invalid_bbox') from None
    if not all(math.isfinite(v) for v in (west, south, east, north)) or not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError('invalid_bbox')
    return west, south, east, north


def viewport(database, bbox: str, *, zoom: int = 4, q: str = '', kind: str | None = None,
             state: str | None = None, municipality_id: str | None = None, max_features: int = 500) -> dict:
    west, south, east, north = parse_bbox(bbox)
    if not 0 <= zoom <= 20 or not 1 <= max_features <= 1000:
        raise ValueError('invalid_map_budget')
    conditions = [Place.catalogue_eligible.is_(True), Place.longitude.between(west, east), Place.latitude.between(south, north)]
    if q:
        conditions.append(Place.search_name.contains(fold(q), autoescape=True))
    for column, value in ((Place.kind, kind), (Place.state, state), (Place.municipality_id, municipality_id)):
        if value:
            conditions.append(column == value)
    features = []
    with database.session() as session:
        total = session.scalar(select(func.count()).select_from(Place).where(*conditions))
        if total <= max_features:
            for row in session.scalars(select(Place).where(*conditions).order_by(Place.id)):
                features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [row.longitude, row.latitude]},
                                 'properties': {'id': row.id, 'kind': row.kind, 'name': row.name, 'count': 1, 'cluster': False}})
            aggregated = False
        else:
            # Aggregate centroids are explicitly labelled, never facility coordinates.
            level = min(zoom + 2, 18)
            while True:
                step = 360 / (2 ** level)
                gx = cast((Place.longitude + 180) / step, Integer)
                gy = cast((Place.latitude + 90) / step, Integer)
                rows = session.execute(select(gx, gy, func.count(), func.avg(Place.longitude), func.avg(Place.latitude),
                    func.min(Place.id), func.min(Place.name), func.min(Place.kind), func.min(Place.longitude),
                    func.min(Place.latitude), func.max(Place.longitude), func.max(Place.latitude))
                    .where(*conditions).group_by(gx, gy).order_by(gx, gy).limit(max_features + 1)).all()
                if len(rows) <= max_features:
                    break
                level -= 1
            for x, y, count, lon, lat, identity, name, category, w, s, e, n in rows:
                properties = {'count': count, 'cluster': count > 1, 'west': w, 'south': s, 'east': e, 'north': n}
                if count == 1:
                    properties.update(id=identity, name=name, kind=category)
                else:
                    properties.update(id=f'grid:{level}:{x}:{y}', location_kind='aggregate_not_facility')
                features.append({'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': properties})
            aggregated = True
    return {'type': 'FeatureCollection', 'features': features, 'matched_records': total,
            'represented_records': sum(f['properties']['count'] for f in features),
            'aggregated': aggregated, 'bbox': [west, south, east, north], 'scope': 'loaded_geocoded_records'}
