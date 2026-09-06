"""Compiled UI: cancellation, late results and full long objects, with synthetic data."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode

import httpx
from playwright.sync_api import expect, sync_playwright
from bdt.storage import Database
from bdt.domain import now
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import import_resources
from bdt.sync import collect
from browser_resources import seed
from browser_resource_sharing import add_precise

LONG_OBJECT = 'OBJETO LONGO DE TESTE: ' + 'Á'*5098

def add_long_object(database, folder, *, title=LONG_OBJECT, number=5):
    row={'numeroControlePNCP':f'12345678000199-2-{number:06}/2026','anoContrato':2026,'sequencialContrato':number,
        'orgaoEntidade':{'cnpj':'12345678000199','razaoSocial':'SYNTHETIC buyer'},
        'unidadeOrgao':{'codigoIbge':'1234567','ufSigla':'BA'},
        'objetoContrato':title,'dataAtualizacao':'2026-09-04T12:00:00',
        'dataPublicacaoPncp':'2026-09-04T12:00:00','valorInicial':'100.01','receita':False}
    plan=collection_plan('pncp_contracts',start='20260904',end='20260904')
    def loader(url,path,budget):
        raw=json.dumps({'data':[row],'numeroPagina':1,'totalPaginas':1,'totalRegistros':1},ensure_ascii=False).encode()
        path.write_bytes(raw)
        return {'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'collected_at':now()}
    collect(plan,folder,loader=loader);import_resources(database,folder)

COPY={
 'pt-BR':{'export':'Baixar JSON da seleção','cancel':'Cancelar exportação','cancelled':'Exportação cancelada. Nenhum arquivo foi entregue.','ready':'Arquivo preparado.','share':'Compartilhar esta consulta','copy':'Copiar link','copied':'Link copiado.'},
 'en':{'export':'Download selection JSON','cancel':'Cancel export','cancelled':'Export cancelled. No file was delivered.','ready':'File prepared.','share':'Share this search','copy':'Copy link','copied':'Link copied.'},
 'es':{'export':'Descargar JSON de selección','cancel':'Cancelar exportación','cancelled':'Exportación cancelada. No se entregó ningún archivo.','ready':'Archivo preparado.','share':'Compartir esta consulta','copy':'Copiar enlace','copied':'Enlace copiado.'}}
DELAY_SCRIPT="""(() => {
 const original = window.fetch.bind(window);
 window.__bdtExportTasks = [];
 window.fetch = (input, options={}) => {
   if (String(input).startsWith('/api/resource-collection-export?')) {
     return new Promise((resolve,reject) => {
       window.__bdtExportTasks.push({signal:options.signal,
         release:()=>original(input,{...options,signal:undefined}).then(resolve,reject)});
     });
   }
   return original(input,options);
 };
 window.__bdtClipboardTasks=[];
 Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:text=>new Promise(resolve=>window.__bdtClipboardTasks.push({text,resolve}))}});
})();"""


def main():
    out=Path('test-results/browser-resource-lifecycle');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'public_deployment':False,'controlled_client_timing':True,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-lifecycle-') as tmp:
        root=Path(tmp);dburl='sqlite:///'+str(root/'test.db');db=Database(dburl);db.initialize()
        try:seed(db,root/'seed');add_precise(db,root/'precise');add_long_object(db,root/'long');add_long_object(db,root/'short',title='TEST',number=6)
        finally:db.engine.dispose()
        origin='http://127.0.0.1:8044'
        env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_PUBLIC_ORIGIN':origin,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':tmp,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8044'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('lifecycle_test_api_unavailable')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for locale,copy in COPY.items():
                            page=browser.new_page(viewport={'width':width,'height':1000});errors=[];downloads=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.on('download',lambda download:downloads.append(download))
                            page.add_init_script(DELAY_SCRIPT)
                            query=lambda text:origin+'#resources?'+urlencode({'q':text,'profile':'pncp_contracts','locale':locale})
                            try:
                                page.goto(query('SYNTHETIC'),wait_until='domcontentloaded')
                                expect(page.locator('.resource-card')).to_have_count(3)
                                page.locator('.collection-downloads summary').click()
                                button=page.get_by_role('button',name=copy['export'],exact=True)
                                button.click();expect(button).to_be_disabled()
                                page.get_by_role('button',name=copy['cancel'],exact=True).click()
                                expect(page.get_by_text(copy['cancelled'],exact=True)).to_be_visible()
                                assert page.evaluate('window.__bdtExportTasks[0].signal.aborted')
                                page.evaluate('window.__bdtExportTasks[0].release()')
                                expect(button).to_be_enabled()
                                expect(page.get_by_text(copy['ready'],exact=True)).to_have_count(0)
                                assert downloads==[]
                                button.click();expect(button).to_be_disabled()
                                page.goto(query('ABSENT_TEST'),wait_until='domcontentloaded')
                                expect(page.locator('.resource-card')).to_have_count(0)
                                assert page.evaluate('window.__bdtExportTasks[1].signal.aborted')
                                page.evaluate('window.__bdtExportTasks[1].release()')
                                expect(page.get_by_role('button',name=copy['export'],exact=True)).to_be_enabled()
                                expect(page.get_by_text(copy['ready'],exact=True)).to_have_count(0)
                                assert downloads==[]
                                page.get_by_role('button',name=copy['share'],exact=True).click()
                                page.get_by_role('button',name=copy['copy'],exact=True).click()
                                page.goto(query('SYNTHETIC'),wait_until='domcontentloaded')
                                expect(page.locator('.resource-card')).to_have_count(3)
                                page.evaluate('window.__bdtClipboardTasks[0].resolve()')
                                expect(page.get_by_text(copy['copied'],exact=True)).to_have_count(0)
                                expect(page.get_by_role('button',name=copy['copy'],exact=True)).to_be_enabled()
                                expect(page.get_by_role('button',name=copy['export'],exact=True)).to_be_enabled()
                                page.get_by_role('button',name=copy['export'],exact=True).click()
                                with page.expect_download() as event:
                                    page.evaluate('window.__bdtExportTasks[2].release()')
                                data=json.loads(Path(event.value.path()).read_text())
                                assert data['filters']['q']=='SYNTHETIC' and data['included']==3
                                assert len(downloads)==1 and not errors
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                                page.goto(query('OBJETO LONGO'),wait_until='domcontentloaded')
                                expect(page.locator('.resource-card')).to_have_count(1)
                                disclosure=page.locator('.resource-object details')
                                disclosure.locator('summary').focus();page.keyboard.press('Enter')
                                expect(page.locator('.resource-object-full')).to_have_text(LONG_OBJECT)
                                assert len(page.locator('.resource-object h2').inner_text())<250
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                                report['checks'].append({'full_long_object_keyboard_access':True,'width':width,'locale':locale,'cancel_discards_late_export':True,'filter_change_discards_late_export':True,'late_copy_does_not_confirm_new_link':True,'new_export_still_works':True,'return_to_previous_selection_has_no_stuck_busy':True})
                                page.screenshot(path=str(out/f'lifecycle-{locale}-{width}.png'),full_page=True)
                                page.goto(origin+'#resources?'+urlencode({'id':'pncp_contracts:12345678000199-2-000006/2026','locale':locale}),wait_until='domcontentloaded')
                                expect(page.get_by_role('heading',name='TEST',exact=True)).to_be_visible()
                                expect(page.locator('.resource-object-short')).to_be_visible()
                                expect(page.locator('.resource-object details')).to_have_count(0)
                                report['checks'][-1]['short_source_object_preserved_and_flagged']=True
                                page.screenshot(path=str(out/f'short-object-{locale}-{width}.png'),full_page=True)
                            except Exception:
                                page.screenshot(path=str(out/f'failure-{locale}-{width}.png'),full_page=True);raise
                            finally:page.close()
                    browser.close()
                report['status']='passed'
            finally:
                server.terminate();server.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
