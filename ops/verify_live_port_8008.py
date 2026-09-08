# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify live container endpoints on port 8008 over real HTTP."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE_URL = 'http://127.0.0.1:8008'


def check_endpoint(name: str, path: str, expected_status: int = 200) -> dict | str:
    url = f'{BASE_URL}{path}'
    req = urllib.request.Request(url, headers={'User-Agent': 'BDT-LiveTest/1.0'})
    print(f'--> [{name}] GET {url} ...')
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == expected_status, f'Expected {expected_status}, got {resp.status}'
        raw = resp.read()
        content_type = resp.headers.get('Content-Type', '')
        if 'application/json' in content_type:
            data = json.loads(raw.decode('utf-8'))
            print(f'    PASS ({resp.status} OK)')
            return data
        else:
            text = raw.decode('utf-8')
            print(f'    PASS ({resp.status} OK, {len(text)} chars)')
            return text


def wait_for_server(max_retries: int = 30, delay: float = 1.0) -> bool:
    url = f'{BASE_URL}/api/health'
    print(f'Waiting for live server at {url}...')
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'BDT-LiveTest/1.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    print(f'Server is ONLINE (attempt {attempt})!')
                    return True
        except Exception:
            time.sleep(delay)
    return False


def main():
    if not wait_for_server():
        print('FAIL: Server did not respond within timeout on port 8008.')
        sys.exit(1)

    # 1. Health check
    health = check_endpoint('Health Check', '/api/health')
    assert health.get('status') == 'ok', f'Unexpected health response: {health}'

    # 2. Obrasgov resources
    resources = check_endpoint('Obrasgov Projects', '/api/resources?profile=obrasgov_projects&limit=5')
    total_works = resources.get('total', 0)
    items = resources.get('items', [])
    print(f'    Total Obrasgov works loaded: {total_works}')
    assert total_works >= 700, f'Expected >= 700 Obrasgov works, found {total_works}'
    assert len(items) > 0, 'No items returned'
    first_work = items[0]
    attrs = first_work.get('attributes', {})
    print(f'    Sample work: "{first_work.get("title")}"')
    print(f'    Execution %: {attrs.get("physical_execution_percentage")}')
    print(f'    Pins: {len(attrs.get("project_geometries") or [])}')

    # 3. Geocoded schools
    schools = check_endpoint('Geocoded Schools (RR)', '/api/places?kind=school&state=RR&limit=5')
    school_items = schools.get('items', [])
    print(f'    School items returned: {len(school_items)}')
    assert len(school_items) > 0, 'No schools returned'
    geocoded = [s for s in school_items if s.get('latitude') is not None]
    print(f'    Geocoded in sample: {len(geocoded)}')
    assert len(geocoded) > 0, 'Expected at least one geocoded school'
    s0 = geocoded[0]
    print(f'    Sample school: "{s0.get("name")}" at ({s0.get("latitude")}, {s0.get("longitude")}), geo_source={s0.get("geo_source")}')
    assert s0.get('geo_source') == 'IBGE-CNEFE-2022'

    # 4. Territory summary for Boa Vista
    summary = check_endpoint('Territory Summary (Boa Vista)', '/api/territories/1400100/summary')
    services = summary.get('services', [])
    res_groups = summary.get('resource_groups', [])
    fin_groups = summary.get('financial_event_groups', [])
    print(f'    Services in Boa Vista: {services}')
    print(f'    Resource groups: {res_groups}')
    print(f'    Financial groups: {fin_groups}')
    assert summary.get('service_records', 0) > 0
    assert summary.get('resource_records', 0) > 0

    # 5. Frontend web bundle
    html = check_endpoint('Frontend HTML Bundle', '/')
    assert '<!DOCTYPE html>' in html or '<div id="root">' in html or '<html' in html
    print('    Frontend HTML bundle verified successfully!')

    print('\n======================================================')
    print('ALL LIVE ENDPOINTS VERIFIED ON PORT 8008 SUCCESSFULLY!')
    print('======================================================\n')


if __name__ == '__main__':
    main()
