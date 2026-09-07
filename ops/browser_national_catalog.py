# SPDX-License-Identifier: AGPL-3.0-or-later
"""Native browser acceptance of a freshly installed, mixed public database.

Called by national_catalog_acceptance, which owns and deletes the database.
No accounts, contributions, fabricated records or intercepted API replies.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit

import httpx
from sqlalchemy import func, select
from bdt.storage import Database, Place
from browser_public_catalog import LABELS, file_sha

CATEGORIES = {'pt-BR': {'health': 'Saúde', 'school': 'Educação'},
              'en': {'health': 'Health', 'school': 'Education'},
              'es': {'health': 'Salud', 'school': 'Educación'}}


def select_mixed_samples(database):
    """At most four exact records, preserving both kinds and missing geometry."""
    result = {'counts': {}, 'samples': []}
    with database.session() as session:
        for kind in ('health', 'school'):
            conditions = (Place.kind == kind, Place.catalogue_eligible.is_(True))
            count = session.scalar(select(func.count()).select_from(Place).where(*conditions))
            if not count:
                raise ValueError('national_browser_missing_kind')
            result['counts'][kind] = count
            for has_geometry in (False, True):
                geometry = Place.latitude.is_not(None) if has_geometry else Place.latitude.is_(None)
                item = session.scalars(select(Place).where(*conditions, geometry).order_by(Place.id).limit(1)).first()
                if item:
                    result['samples'].append(item.payload)
    return result


def exercise_new_installation(destination, receipt, static, output):
    """Use only the isolated database owned by the acceptance command."""
    from playwright.sync_api import expect, sync_playwright
    destination, static, output = Path(destination), Path(static), Path(output)
    if not (static / 'index.html').is_file():
        raise ValueError('national_browser_build_missing')
    output.mkdir(parents=True, exist_ok=False)
    database = Database('sqlite:///' + str(destination.resolve()))
    try:
        selection = select_mixed_samples(database)
    finally:
        database.engine.dispose()
    if selection['counts'] != receipt['by_kind']:
        raise ValueError('national_browser_selection_mismatch')
    samples = selection['samples']
    identifiers = [item['id'] for item in samples]
    report = {'schema': 'bdt.national-browser.v1', 'status': 'started',
              'revision': os.environ.get('GITHUB_SHA', 'development'),
              'ui_index_sha256': file_sha(static / 'index.html'),
              'counts': selection['counts'], 'sample_ids': identifiers,
              'api_replies_mocked': False, 'records_modified': False,
              'new_upstream_collection': False, 'public_deployment': False, 'checks': []}
    origin = 'http://127.0.0.1:8064'
    env = os.environ | {'BDT_DATABASE_URL': 'sqlite:///' + str(destination.resolve()),
                        'BDT_PUBLIC_ORIGIN': origin, 'BDT_STATIC_DIR': str(static.resolve()),
                        'BDT_DATA_DIR': str(destination.parent.resolve()), 'BDT_ALLOW_REGISTRATION': '0'}
    with (output / 'server.log').open('w') as log:
        server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'bdt.api:create_app', '--factory',
                                   '--host', '127.0.0.1', '--port', '8064'], env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('national_browser_server_exited')
                try:
                    if httpx.get(origin + '/api/health', timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            else:
                raise RuntimeError('national_browser_server_not_ready')
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'), headless=True)
                try:
                    for width in (320, 390, 1440):
                        for locale, labels in LABELS.items():
                            context = browser.new_context(viewport={'width': width, 'height': 1000}, accept_downloads=True)
                            page = context.new_page()
                            errors, external = [], []
                            page.on('pageerror', lambda error: errors.append(type(error).__name__))
                            page.on('request', lambda request: external.append(urlsplit(request.url).hostname)
                                    if urlsplit(request.url).scheme in ('http', 'https') and not request.url.startswith(origin + '/') else None)
                            page.add_init_script('localStorage.setItem("bdt:locale",' + json.dumps(json.dumps(locale)) + ');')
                            try:
                                page.goto(origin, wait_until='domcontentloaded')
                                expect(page.locator('.place-card').first).to_be_visible()
                                for kind, count in selection['counts'].items():
                                    with page.expect_response(lambda response, kind=kind: urlsplit(response.url).path == '/api/places'
                                            and parse_qs(urlsplit(response.url).query).get('kind') == [kind]) as selected:
                                        page.locator('.category-tabs').get_by_role('button', name=CATEGORIES[locale][kind], exact=True).click()
                                    assert selected.value.status == 200 and selected.value.json()['total'] == count
                                    expect(page.locator('.place-card').first).to_be_visible()
                                # Search the school sample through the real input, retaining the school filter.
                                school = next(item for item in samples if item['kind'] == 'school')
                                query = school['name'][:200]
                                with page.expect_response(lambda response: urlsplit(response.url).path == '/api/places'
                                        and parse_qs(urlsplit(response.url).query).get('q') == [query]) as found:
                                    page.get_by_role('searchbox', name=labels['search'], exact=True).fill(query)
                                assert found.value.status == 200 and found.value.json()['total'] > 0
                                # Only local test preferences are written, never source records or server accounts.
                                page.evaluate('(ids)=>localStorage.setItem("bdt:favorites",JSON.stringify(ids))', identifiers)
                                page.reload(wait_until='domcontentloaded')
                                page.get_by_role('button', name=labels['saved'], exact=True).click()
                                expect(page.locator('.watch-card')).to_have_count(len(samples))
                                for index, item in enumerate(samples):
                                    card = page.locator('.watch-card').nth(index)
                                    expect(card.get_by_role('button', name=item['name'], exact=True)).to_be_visible()
                                    if item['latitude'] is None:
                                        expect(card.get_by_text(labels['no_geo'], exact=True)).to_be_visible()
                                    card.get_by_role('button', name=item['name'], exact=True).click()
                                    expect(page.get_by_role('heading', name=item['name'], exact=True)).to_be_visible()
                                    expect(page.locator('.source strong')).to_have_text(item['source']['dataset'])
                                    page.locator('.tabs').get_by_role('button', name=labels['source'], exact=True).click()
                                    expect(page.locator('.detail')).to_contain_text(item['id'])
                                    with page.expect_download() as downloading:
                                        page.get_by_role('button', name=labels['export'], exact=True).click()
                                    downloaded = destination.parent / f'export-{locale}-{width}-{index}.json'
                                    downloading.value.save_as(downloaded)
                                    exported = json.loads(downloaded.read_text())
                                    assert exported['place'] == item and exported['observations'] == []
                                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                                    page.get_by_role('button', name=labels['saved'], exact=True).click()
                                    expect(page.locator('.watch-card')).to_have_count(len(samples))
                                page.reload(wait_until='domcontentloaded')
                                page.get_by_role('button', name=labels['saved'], exact=True).click()
                                expect(page.locator('.watch-card')).to_have_count(len(samples))
                                assert json.loads(page.evaluate('localStorage.getItem("bdt:favorites")')) == identifiers
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                                assert not errors and not external, (errors, external)
                                page.screenshot(path=str(output / f'mixed-{locale}-{width}.png'), full_page=True)
                                report['checks'].append({'locale': locale, 'width': width, 'both_kind_filters': True,
                                    'exact_sources_and_exports': True, 'mixed_favorites_survive_reload': True,
                                    'missing_geometry_preserved': True, 'horizontal_overflow': False, 'external_requests': 0})
                            except Exception:
                                page.screenshot(path=str(output / f'failed-{locale}-{width}.png'), full_page=True)
                                raise
                            finally:
                                context.close()
                    report['status'] = 'passed'
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            if report['status'] != 'passed':
                report['status'] = 'failed'
            (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
