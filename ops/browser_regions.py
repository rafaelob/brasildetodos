"""Real compiled UI/API municipal journey with isolated synthetic fixture data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import expect, sync_playwright
from bdt.domain import Source, PlaceInput, now
from bdt.storage import Database, Municipality, upsert_place

TEXT={
 'pt-BR':('Minha região','Nome ou código do município','Explore sua região','Tentar resumo novamente','Explorar serviços · Saúde','Nenhum serviço elegível foi carregado para este município.'),
 'en':('My region','Municipality name or code','Explore your region','Retry summary','Explore services · Health','No eligible services have been loaded for this municipality.'),
 'es':('Mi región','Nombre o código del municipio','Explore su región','Reintentar resumen','Explorar servicios · Salud','No se cargaron servicios elegibles para este municipio.')}


def main():
    out=Path('test-results/browser-regions');out.mkdir(parents=True,exist_ok=True)
    report={'status':'started','synthetic_test_only':True,'public_deployment':False,'checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-region-browser-') as temp:
        dburl='sqlite:///'+str(Path(temp)/'fixture.db');db=Database(dburl);db.initialize()
        source=Source(dataset='synthetic',url='https://example.org/synthetic-only',record_id='territory',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
        with db.session() as session:
            session.add_all([Municipality(id='1234567',name='São Teste',state='BA',source=source.model_dump()),Municipality(id='7654321',name='Cidade Sem Carga',state='SP',source=source.model_dump())]);session.flush()
            upsert_place(session,PlaceInput(id='test:health',kind='health',name='Synthetic Health Service',municipality_id='1234567',state='BA',source=source))
        db.engine.dispose()
        origin='http://127.0.0.1:8056';env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_DATA_DIR':temp,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_PUBLIC_ORIGIN':origin,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8056'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(80):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('region_api_not_ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for locale,labels in TEXT.items():
                            page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');')
                            try:
                                page.goto(origin,wait_until='domcontentloaded')
                                page.get_by_role('button',name=labels[0],exact=True).click()
                                expect(page.get_by_role('heading',name=labels[2],exact=True)).to_be_visible()
                                page.get_by_label(labels[1],exact=True).fill('sao')
                                expect(page.locator('.region-town')).to_have_count(1)
                                page.locator('.region-town').click()
                                expect(page.locator('.region-content').get_by_role('heading',name='São Teste · BA',exact=True)).to_be_visible()
                                health=page.locator('.region-metric').nth(1)
                                expect(health.locator('strong')).to_have_text('1')
                                expect(health.locator('dd').nth(1)).to_have_text('1')
                                page.screenshot(path=str(out/f'region-{locale}-{width}.png'),full_page=True)
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(locale,width)
                                # Failure of one summary does not hide the independently usable directory.
                                page.route('**/api/territories/7654321/summary',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
                                page.get_by_label(labels[1],exact=True).fill('7654321')
                                expect(page.locator('.region-town')).to_have_count(1);page.locator('.region-town').click()
                                expect(page.get_by_role('button',name=labels[3],exact=True)).to_be_visible()
                                expect(page.locator('.region-town')).to_have_count(1)
                                page.unroute('**/api/territories/7654321/summary');page.get_by_role('button',name=labels[3],exact=True).click()
                                expect(page.get_by_text(labels[5],exact=True)).to_be_visible()
                                page.get_by_label(labels[1],exact=True).fill('sao');expect(page.locator('.region-town')).to_have_count(1);page.locator('.region-town').click()
                                expect(page.locator('.region-metric').nth(1).locator('strong')).to_have_text('1')
                                page.get_by_role('button',name=labels[4],exact=True).click()
                                expect(page.locator('.place-card')).to_have_count(1)
                                expect(page.get_by_role('button',name='Synthetic Health Service',exact=True)).to_be_visible()
                                assert not errors,errors
                                report['checks'].append({'width':width,'locale':locale,'accent_search':True,'directory_survives_summary_failure':True,'retry':True,'empty_city_not_no_services':True,'missing_geometry_included':True,'service_filter_handoff':True,'no_overflow':True})
                            except Exception:
                                page.screenshot(path=str(out/f'failure-{locale}-{width}.png'),full_page=True);raise
                            finally:page.close()
                    browser.close();report['status']='passed'
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()
                (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
