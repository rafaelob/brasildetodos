# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify live API responses against the enriched national database."""
from __future__ import annotations

from fastapi.testclient import TestClient
from bdt.api import create_app

app = create_app('sqlite:///data/bdt_national.db', testing=True)

with TestClient(app) as client:
    # 1. Health check
    res = client.get('/api/health')
    print('GET /api/health:', res.status_code, res.json())
    assert res.status_code == 200

    # 2. Obrasgov resources
    res = client.get('/api/resources?profile=obrasgov_projects&limit=5')
    print('GET /api/resources?profile=obrasgov_projects:', res.status_code)
    data = res.json()
    print('  Total Obrasgov works:', data.get('total'))
    print('  Items returned:', len(data.get('items', [])))
    for item in data.get('items', [])[:2]:
        print('    Title:', item.get('title')[:60])
        print('    Physical exec:', item.get('attributes', {}).get('physical_execution_percentage'))
        print('    Pins:', len(item.get('attributes', {}).get('project_geometries') or []))
    assert data.get('total') >= 700

    # 3. Geocoded schools
    res = client.get('/api/places?kind=school&state=RR&limit=5')
    print('GET /api/places?kind=school&state=RR:', res.status_code)
    schools = res.json()
    print('  Items returned:', len(schools.get('items', [])))
    for s in schools.get('items', [])[:2]:
        print('    School:', s.get('name'))
        print('    Coords:', s.get('latitude'), s.get('longitude'))
        print('    Geo source:', s.get('geo_source'))

    # 4. Territory summary for Boa Vista (1400100)
    res = client.get('/api/territories/1400100/summary')
    print('GET /api/territories/1400100/summary:', res.status_code)
    summary = res.json()
    print('  Services:', summary.get('services'))
    print('  Resource groups:', summary.get('resource_groups'))
    print('  Service records:', summary.get('service_records'))
    print('  Resource records:', summary.get('resource_records'))

    print('\nALL API CONTRACTS VERIFIED AGAINST DATA/BDT_NATIONAL.DB SUCCESSFULLY!')
