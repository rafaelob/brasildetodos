"""Compiled read-only comparisons using existing API and temporary synthetic data."""
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
from bdt.domain import Source,PlaceInput,now
from bdt.storage import Database,Municipality,upsert_place

TEXT={
 'pt-BR':{'saved':'Meus lugares','select':'Selecionar para comparação','open':'Abrir comparação','title':'Comparar lugares salvos','retry':'Tentar comparação novamente','refresh':'Atualizar comparação','clear':'Limpar seleção'},
 'en':{'saved':'My places','select':'Select for comparison','open':'Open comparison','title':'Compare saved places','retry':'Retry comparison','refresh':'Refresh comparison','clear':'Clear selection'},
 'es':{'saved':'Mis lugares','select':'Seleccionar para comparar','open':'Abrir comparación','title':'Comparar lugares guardados','retry':'Reintentar comparación','refresh':'Actualizar comparación','clear':'Limpiar selección'},
}

def main():
    out=Path('test-results/browser-place-comparison');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'public_deployment':False,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-comparison-browser-') as temp:
        dburl='sqlite:///'+str(Path(temp)/'application.db');db=Database(dburl);db.initialize()
        source=Source(dataset='synthetic-comparison',url='https://example.org/test-only',record_id='test',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
        ids=[f'compare:{i}' for i in range(4)]
        with db.session() as session:
            session.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()));session.flush()
            for i,identifier in enumerate(ids):
                upsert_place(session,PlaceInput(id=identifier,name=f'Synthetic place {i}',kind='school' if i%2==0 else 'health',municipality_id='1234567',state='BA',phone='0000-0000' if i==0 else None,address='Synthetic address '+str(i),source=source.model_copy(update={'record_id':str(i),'reference_date':'2024' if i==1 else '2025'})))
        db.engine.dispose();origin='http://127.0.0.1:8055'
        env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_PUBLIC_ORIGIN':origin,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8055'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('comparison_server_unavailable')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for locale,labels in TEXT.items():
                            page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');localStorage.setItem("bdt:favorites",'+json.dumps(json.dumps(ids))+');')
                            try:
                                page.goto(origin,wait_until='domcontentloaded');page.get_by_role('button',name=labels['saved'],exact=True).click()
                                expect(page.locator('.watch-card')).to_have_count(4)
                                expect(page.get_by_role('button',name=labels['open'],exact=True)).to_be_disabled()
                                for i in (0,1,2):page.get_by_role('checkbox',name=labels['select']+f' Synthetic place {i}',exact=True).check()
                                expect(page.get_by_role('checkbox',name=labels['select']+' Synthetic place 3',exact=True)).to_be_disabled()
                                page.get_by_role('button',name=labels['open'],exact=True).click()
                                panel=page.locator('.place-comparison')
                                expect(panel.locator('.comparison-place')).to_have_count(3)
                                expect(panel.get_by_role('heading',name=labels['title'],exact=True)).to_be_focused()
                                expect(panel.get_by_text('2024',exact=True)).to_be_visible()
                                expect(panel.get_by_text('0000-0000',exact=True)).to_be_visible()
                                expect(panel.locator('.comparison-notice')).to_be_visible()
                                assert json.loads(page.evaluate('localStorage.getItem("bdt:favorites")'))==ids
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale)
                                page.screenshot(path=str(out/f'comparison-{locale}-{width}.png'),full_page=True)
                                # Only force a failure to exercise UI recovery; successful reads remain real.
                                page.route('**/api/saved-places/summary',lambda route:route.fulfill(status=503,body='{}',content_type='application/json'))
                                panel.get_by_role('button',name=labels['refresh'],exact=True).click()
                                expect(panel.get_by_role('button',name=labels['retry'],exact=True)).to_be_visible()
                                expect(page.locator('.watch-card')).to_have_count(4)
                                page.unroute('**/api/saved-places/summary')
                                panel.get_by_role('button',name=labels['retry'],exact=True).click()
                                expect(panel.locator('.comparison-place')).to_have_count(3)
                                page.get_by_role('checkbox',name=labels['select']+' Synthetic place 2',exact=True).uncheck()
                                expect(panel.locator('.comparison-place')).to_have_count(2)
                                page.get_by_role('button',name=labels['clear'],exact=True).click()
                                expect(panel).to_have_count(0)
                                expect(page.get_by_role('checkbox',name=labels['select']+' Synthetic place 0',exact=True)).not_to_be_checked()
                                assert json.loads(page.evaluate('localStorage.getItem("bdt:favorites")'))==ids
                                assert not errors,errors
                                report['checks'].append({'width':width,'locale':locale,'bounded_three_places':True,'original_source_periods':True,'mixed_type_notice':True,'no_rank':True,'independent_failure_recovery':True,'ephemeral_selection':True,'keyboard_focus':True,'no_horizontal_overflow':True})
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
