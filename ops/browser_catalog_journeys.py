"""Compiled coverage/favorites journeys with real API and isolated synthetic data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import httpx
from playwright.sync_api import sync_playwright, expect
from bdt.domain import Source, PlaceInput, now
from bdt.storage import Database, Municipality, Ingestion, upsert_place

TEXT={
 'pt-BR':{'saved':'Meus lugares','coverage':'Dados e cobertura','heading':'Conheça os dados disponíveis','source':'Fonte das importações','status':'Resultado das importações','retry':'Tentar histórico novamente','watchRetry':'Tentar meus lugares novamente','compare':'Ver o que mudou','next':'Próxima','remove':'Remover dos meus lugares'},
 'en':{'saved':'My places','coverage':'Data and coverage','heading':'Understand the available data','source':'Import source','status':'Import outcome','retry':'Retry history','watchRetry':'Retry my places','compare':'See what changed','next':'Next','remove':'Remove from my places'},
 'es':{'saved':'Mis lugares','coverage':'Datos y cobertura','heading':'Conozca los datos disponibles','source':'Fuente de importaciones','status':'Resultado de importaciones','retry':'Reintentar historial','watchRetry':'Reintentar mis lugares','compare':'Ver qué cambió','next':'Siguiente','remove':'Quitar de mis lugares'},
}


def seed(db):
    source=Source(dataset='inep-schools-2025',url='https://example.org/synthetic',record_id='fixture',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
    ids=[f'test:school{i}' for i in range(13)]+['missing:kept']
    with db.session() as session:
        session.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()));session.flush()
        for i,identifier in enumerate(ids[:-1]):
            place=PlaceInput(id=identifier,name=f'Synthetic School {i}',kind='school',municipality_id='1234567',state='BA',source=source)
            upsert_place(session,place)
            if i==0:
                upsert_place(session,place.model_copy(update={'address':'Updated address in fixture'}))
            if i==1:
                upsert_place(session,place.model_copy(update={'catalogue_eligible':False}))
        for i in range(7):
            session.add(Ingestion(dataset='inep-schools-2025',source={'private':'DO_NOT_EXPORT'},status='failed' if i==0 else 'completed_file',counts={'read':13,'created':13},error='DO_NOT_EXPORT'))
    return ids


def main():
    out=Path('test-results/browser-catalog');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'public_deployment':False,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-catalog-browser-') as temp:
        dburl='sqlite:///'+str(Path(temp)/'test.db');db=Database(dburl);db.initialize()
        try:ids=seed(db)
        finally:db.engine.dispose()
        origin='http://127.0.0.1:8052';env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_PUBLIC_ORIGIN':origin,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8052'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('catalog_api_not_ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for locale,labels in TEXT.items():
                            page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                            page.on('pageerror',lambda e:errors.append(str(e)))
                            page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');localStorage.setItem("bdt:favorites",'+json.dumps(json.dumps(ids))+');')
                            try:
                                page.goto(origin,wait_until='domcontentloaded')
                                page.get_by_role('button',name=labels['saved'],exact=True).click()
                                expect(page.locator('.watch-card')).to_have_count(12)
                                first=page.locator('.watch-card').first
                                expect(first.get_by_role('button',name='Synthetic School 0',exact=True)).to_be_visible()
                                first.get_by_text(labels['compare'],exact=True).click()
                                expect(first.get_by_text('Updated address in fixture',exact=True)).to_be_visible()
                                expect(page.locator('.watch-card').nth(1).locator('.watch-warning').first).to_be_visible()
                                page.locator('.watch-page .pager').get_by_role('button',name=labels['next'],exact=True).click()
                                expect(page.locator('.watch-card')).to_have_count(2)
                                missing=page.locator('.watch-card').filter(has=page.get_by_role('heading',name='missing:kept',exact=True))
                                expect(missing).to_be_visible();missing.locator('.watch-remove').click()
                                expect(page.locator('.watch-card')).to_have_count(1)
                                stored=json.loads(page.evaluate('localStorage.getItem("bdt:favorites")'))
                                assert len(stored)==13 and 'missing:kept' not in stored
                                page.screenshot(path=str(out/f'favorites-{locale}-{width}.png'),full_page=True)
                                page.get_by_role('button',name=labels['coverage'],exact=True).click()
                                expect(page.get_by_role('heading',name=labels['heading'],exact=True)).to_be_visible()
                                expect(page.locator('.coverage-metric').first.locator('strong')).to_have_text('12')
                                expect(page.locator('.coverage-run')).to_have_count(5)
                                page.get_by_label(labels['source'],exact=True).select_option('inep')
                                page.get_by_label(labels['status'],exact=True).select_option('failed')
                                expect(page.locator('.coverage-run')).to_have_count(1)
                                expect(page.locator('.coverage-run .callout')).to_be_visible()
                                assert 'DO_NOT_EXPORT' not in page.locator('body').inner_text()
                                page.screenshot(path=str(out/f'coverage-{locale}-{width}.png'),full_page=True)
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale)
                                # Independent history failure must not hide loaded counts.
                                page.route('**/api/imports?**',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
                                page.get_by_label(labels['status'],exact=True).select_option('all')
                                expect(page.get_by_role('button',name=labels['retry'],exact=True)).to_be_visible()
                                expect(page.locator('.coverage-metric').first.locator('strong')).to_have_text('12')
                                page.unroute('**/api/imports?**');page.get_by_role('button',name=labels['retry'],exact=True).click()
                                expect(page.locator('.coverage-run')).to_have_count(5)
                                assert not errors,errors
                                report['checks'].append({'width':width,'locale':locale,'favorite_history':True,'missing_removable':True,'outside_profile_visible':True,'pagination_preserves_favorites':True,'public_import_filters':True,'independent_failure_retry':True,'no_horizontal_overflow':True,'javascript_errors':errors})
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
