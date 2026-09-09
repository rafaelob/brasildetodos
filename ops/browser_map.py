"""Real compiled MapLibre/worker/WebGL + API, with isolated synthetic map fixtures.

Default mode intercepts only basemap content; no government network requests.
--live separately verifies the configured external basemap, not national coverage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlsplit

import httpx
from PIL import Image
from playwright.sync_api import expect, sync_playwright
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Database, Municipality, upsert_place
from map_test_support import style, tile


def open_opt_in_map(panel) -> None:
    expect(panel.locator('.map-collapsed-bar')).to_be_visible()
    button = panel.locator('.map-reopen-btn')
    expect(button).to_be_visible()
    button.click()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    out = Path('test-results/map-live' if args.live else 'test-results/browser-map')
    out.mkdir(parents=True, exist_ok=True)
    report = {'status': 'started', 'python': platform.python_version(),
        'revision': os.environ.get('GITHUB_SHA'), 'synthetic_places_only': True,
        'synthetic_basemap': not args.live, 'public_deployment': False,
        'national_coverage_verified': False, 'checks': [], 'external_map_verified': False}
    with tempfile.TemporaryDirectory(prefix='bdt-map-test-') as temporary:
        root = Path(temporary); url = 'sqlite:///' + str(root/'map.db')
        db = Database(url); db.initialize()
        source = Source(dataset='synthetic-map-test', record_id='map-test',
            url='https://example.org/synthetic-map-only', reference_date='2026',
            collected_at=now(), snapshot_sha256='b'*64)
        item = PlaceInput(id='test:map-point', kind='school', name='Escola Sintética Mapa',
            state='BA', municipality_id='1234567', latitude=-15, longitude=-51,
            geo_source='synthetic_test_only', source=source)
        with db.session() as session:
            session.add(Municipality(id='1234567', name='Território Sintético', state='BA', source=source.model_dump()))
            session.flush(); upsert_place(session,item)
        db.engine.dispose()
        port=8043 if args.live else 8042; origin=f'http://127.0.0.1:{port}'
        env=os.environ|{'BDT_DATABASE_URL':url,'BDT_PUBLIC_ORIGIN':origin,
            'BDT_STATIC_DIR':str(Path('web/dist').resolve()), 'BDT_DATA_DIR':temporary, 'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory',
                '--host','127.0.0.1','--port',str(port)],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('map_test_api_unavailable')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),
                        headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
                    for width in ((1440,) if args.live else (320,390,1440)):
                        page=browser.new_page(viewport={'width':width,'height':1000},reduced_motion='reduce')
                        errors=[];workers=[];requests=[];tile_responses=[];basemap_requests=[]
                        flags={'fail_data':False,'bad_counts':False,'no_buildings':False,'fail_style':False}
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        page.on('worker',lambda worker:workers.append(worker.url))
                        page.on('request',lambda request:basemap_requests.append(request.url) if urlsplit(request.url).hostname=='tiles.openfreemap.org' else None)
                        page.on('response',lambda response:tile_responses.append({'url':response.url.split('?')[0],'status':response.status}) if urlsplit(response.url).hostname=='tiles.openfreemap.org' else None)
                        def basemap(route):
                            if '/styles/' in route.request.url:
                                if flags['fail_style']:route.fulfill(status=503,body='test outage')
                                else:route.fulfill(json=style(buildings=not flags['no_buildings']))
                            elif '/test/building/' in route.request.url:
                                route.fulfill(body=tile(),content_type='application/vnd.mapbox-vector-tile')
                            elif '/test/font/' in route.request.url:
                                route.fulfill(body=b'',content_type='application/x-protobuf')
                            else:route.abort()
                        def viewport(route):
                            requests.append(parse_qs(urlsplit(route.request.url).query))
                            if flags['fail_data']:route.fulfill(status=503,body='test outage')
                            elif flags['bad_counts']:
                                response=route.fetch(); value=response.json();value['represented_records']+=1
                                route.fulfill(response=response,json=value)
                            else:route.continue_()
                        if not args.live:page.route('https://tiles.openfreemap.org/**',basemap)
                        page.route('**/api/map/viewport?*',viewport)
                        try:
                            page.goto(origin,wait_until='domcontentloaded')
                            expect(page.get_by_role('button',name=item.name,exact=True)).to_be_visible()
                            assert not basemap_requests and not workers, 'Map must be opt-in and lazy'
                            panel=page.locator('.map-panel')
                            open_opt_in_map(panel)
                            expect(panel.locator('.map-caption')).to_contain_text('1 registros',timeout=35000)
                            expect(panel.locator('.map-canvas canvas')).to_be_visible()
                            assert workers and all(origin in worker for worker in workers),workers
                            expect(panel.locator('.map-feedback .callout')).to_have_count(0)
                            if args.live:
                                expect(panel.get_by_role('button',name='Vista 3D',exact=True)).to_be_enabled()
                            # Readiness of own points exercises a real bundled worker; basemap is independent.
                            canvas=panel.locator('.map-canvas canvas')
                            canvas.screenshot(path=str(out/f'map-2d-{width}.png'))
                            with Image.open(out/f'map-2d-{width}.png') as image:
                                assert len(image.convert('RGB').getcolors(image.width*image.height) or [])>4
                            if width in (390,1440):
                                for _ in range(12):
                                    page.locator('.maplibregl-ctrl-zoom-in').click()
                                    page.wait_for_timeout(330)
                                page.wait_for_function("document.querySelector('.map-caption') && !document.querySelector('.map-feedback').textContent.includes('Atualizando')")
                                # Wait for the final moveend, not an unrelated network-idle event.
                                for _ in range(50):
                                    if requests and int(requests[-1].get('zoom',['0'])[0])>=15:break
                                    page.wait_for_timeout(100)
                                else:raise AssertionError('map_never_reached_building_zoom')
                                panel.get_by_role('button',name='Vista 3D',exact=True).click()
                                expect(panel.get_by_role('button',name='Vista 3D',exact=True)).to_have_attribute('aria-pressed','true')
                                expect(panel.locator('.map-caption')).to_be_visible()
                                for _ in range(50):
                                    if any('/test/building/' in row['url'] and row['status']==200 for row in tile_responses) or args.live:break
                                    page.wait_for_timeout(100)
                                else:raise AssertionError('synthetic_vector_tiles_not_loaded')
                                page.wait_for_timeout(500)  # render settling for the captured evidence only
                                canvas.screenshot(path=str(out/f'map-3d-{width}.png'))
                                assert (out/f'map-3d-{width}.png').read_bytes()!=(out/f'map-2d-{width}.png').read_bytes()
                            if args.live:
                                report['external_map_verified']=any(row['status']==200 and '/styles/' not in row['url'] for row in tile_responses)
                                assert report['external_map_verified'], 'External map was not independently verified'
                                report['external_responses']=tile_responses[:100]
                            else:
                                for lang,hide in [('en','Close map'),('es','Cerrar mapa'),('pt-BR','Fechar mapa')]:
                                    page.get_by_label('Idioma / Language / Idioma').select_option(lang)
                                    expect(panel.get_by_role('button',name=hide,exact=True)).to_be_visible()
                                # A newer failing query must clear the previous count and clickable points.
                                flags['fail_data']=True
                                page.get_by_role('searchbox',name='Busque por nome ou endereço',exact=True).fill('Filtro Sintético')
                                expect(panel.locator('.map-caption')).to_have_count(0)
                                expect(panel.get_by_role('button',name='Atualizar',exact=True)).to_be_visible()
                                flags['fail_data']=False
                                page.get_by_role('searchbox',name='Busque por nome ou endereço',exact=True).fill('')
                                expect(panel.locator('.map-caption')).to_contain_text('1 registros')
                                flags['bad_counts']=True
                                page.get_by_role('searchbox',name='Busque por nome ou endereço',exact=True).fill('Escola')
                                expect(panel.get_by_role('button',name='Atualizar',exact=True)).to_be_visible()
                                expect(panel.locator('.map-caption')).to_have_count(0)
                                flags['bad_counts']=False
                                panel.get_by_role('button',name='Atualizar',exact=True).click()
                                expect(panel.locator('.map-caption')).to_contain_text('1 registros')
                                panel.get_by_role('button',name='Fechar mapa',exact=True).click()
                                expect(panel.locator('canvas')).to_have_count(0)
                                flags['no_buildings']=True
                                open_opt_in_map(panel)
                                expect(panel.locator('.map-caption')).to_contain_text('1 registros')
                                expect(panel.get_by_role('button',name='Vista 3D',exact=True)).to_be_disabled()
                                expect(panel.get_by_text('O estilo atual não fornece uma camada de edificações compatível com 3D.',exact=True)).to_be_visible()
                                if width==320:
                                    panel.get_by_role('button',name='Fechar mapa',exact=True).click()
                                    flags['fail_style']=True
                                    open_opt_in_map(panel)
                                    expect(panel.get_by_role('button',name='Recarregar mapa',exact=True)).to_be_visible(timeout=25000)
                                    expect(page.get_by_role('button',name=item.name,exact=True)).to_be_visible()
                                    flags['fail_style']=False
                                    panel.get_by_role('button',name='Recarregar mapa',exact=True).click()
                                    expect(panel.locator('.map-caption')).to_contain_text('1 registros')
                            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),width
                            assert not errors,errors
                            page.screenshot(path=str(out/f'map-page-{width}.png'),full_page=True)
                            report['checks'].append({'width':width,'worker_loaded':True,'webgl_rendered':True,
                                'list_independent':True,'source_accounting_validated':True,
                                'external_basemap':args.live,'javascript_errors':errors})
                        except Exception:
                            page.screenshot(path=str(out/f'failure-{width}.png'),full_page=True)
                            report['failure_stage']='browser_assertion';raise
                        finally:page.close()
                    browser.close()
                report['status']='passed'
            finally:
                server.terminate();server.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
