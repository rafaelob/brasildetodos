"""Compiled interface: independent import status and bounded selection downloads.

Records are explicitly synthetic and temporary; no LLM or external source calls.
"""
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
import httpx
from playwright.sync_api import expect, sync_playwright
from bdt.domain import now
from bdt.storage import Database, Ingestion
from browser_resources import seed
from browser_resource_sharing import add_precise

TEXT={
 'pt-BR':('Dados carregados por fonte','Exportar esta seleção','Baixar texto da seleção','Baixar CSV da seleção','Baixar JSON da seleção','Tentar painel novamente'),
 'en':('Data loaded by source','Export this selection','Download selection text','Download selection CSV','Download selection JSON','Retry panel'),
 'es':('Datos cargados por fuente','Exportar esta selección','Descargar texto de selección','Descargar CSV de selección','Descargar JSON de selección','Reintentar panel')}

def main():
    out=Path('test-results/browser-resource-status');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'public_deployment':False,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-status-browser-') as temporary:
        root=Path(temporary);dburl='sqlite:///'+str(root/'test.db');db=Database(dburl);db.initialize()
        try:
            seed(db,root/'seed');add_precise(db,root/'precise')
            with db.session() as session:
                session.add(Ingestion(dataset='pncp_contracts',source={'private':'DO_NOT_EXPORT'},status='failed',
                    error='DO_NOT_EXPORT',started_at=now(),finished_at=now(),counts={'rolled_back':True}))
        finally:db.engine.dispose()
        origin='http://127.0.0.1:8042';env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_PUBLIC_ORIGIN':origin,
          'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temporary,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8042'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('status_test_api_unavailable')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        page=browser.new_page(viewport={'width':width,'height':1000});errors=[]
                        page.on('pageerror',lambda error:errors.append(str(error)))
                        try:
                            for locale,labels in TEXT.items():
                                page.goto(origin+'#resources?'+urlencode({'q':'SYNTHETIC','profile':'pncp_contracts','locale':locale}),wait_until='domcontentloaded')
                                page.reload(wait_until='domcontentloaded')
                                expect(page.locator('.resource-card')).to_have_count(3)
                                panel=page.locator('.resource-status summary');panel.focus();panel.press('Enter')
                                expect(page.locator('.resource-status-grid article')).to_have_count(3)
                                expect(page.locator('.resource-status .import-failed')).to_be_visible()
                                page.locator('.collection-downloads summary').click()
                                for fmt,label in zip(('text','csv','json'),labels[2:5]):
                                    with page.expect_download() as download:
                                        page.get_by_role('button',name=label,exact=True).click()
                                    body=Path(download.value.path()).read_text(encoding='utf-8-sig')
                                    assert '100.0001' in body and 'DO_NOT_EXPORT' not in body
                                    if fmt=='json':
                                        data=json.loads(body);assert data['total']==data['included']==3 and not data['truncated']
                                        assert data['filters']['profile']=='pncp_contracts'
                                    elif fmt=='csv':assert len(list(csv.DictReader(io.StringIO(body))))==3
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale)
                            page.route('**/api/resource-coverage',lambda route:route.fulfill(status=503,body='{}',content_type='application/json'))
                            page.reload(wait_until='domcontentloaded');page.locator('.resource-status summary').click()
                            expect(page.get_by_role('button',name=TEXT['es'][5],exact=True)).to_be_visible()
                            expect(page.locator('.resource-card')).to_have_count(3)
                            page.unroute('**/api/resource-coverage');page.get_by_role('button',name=TEXT['es'][5],exact=True).click()
                            expect(page.locator('.resource-status-grid article')).to_have_count(3)
                            page.screenshot(path=str(out/f'source-status-{width}.png'),full_page=True)
                            assert not errors,errors
                            report['checks'].append({'width':width,'locales':3,'keyboard_panel':True,
                              'failed_import_keeps_data':True,'panel_failure_does_not_block_search':True,
                              'selection_exports':['text','csv','json'],'exact_amounts':True,'no_private_import_data':True})
                        except Exception:
                            page.screenshot(path=str(out/f'failure-{width}.png'),full_page=True);raise
                        finally:page.close()
                    browser.close()
                report['status']='passed'
            finally:
                server.terminate();server.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
