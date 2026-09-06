"""Public sharing/export journey against the real compiled UI and local API.

Every record is synthetic and isolated. No provider key, LLM, or live map is
used. This is browser behavior evidence, not national data or deployment proof.
"""
from __future__ import annotations
import hashlib
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
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import import_resources
from bdt.storage import Database
from bdt.sync import collect
from browser_resources import seed


def add_precise(database, folder):
    row = {'numeroControlePNCP':'12345678000199-2-000004/2026','anoContrato':2026,'sequencialContrato':4,
           'orgaoEntidade':{'cnpj':'12345678000199','razaoSocial':'SYNTHETIC buyer'},
           'unidadeOrgao':{'codigoIbge':'1234567','ufSigla':'BA'},
           'objetoContrato':'SYNTHETIC precise metadata', 'dataAtualizacao':'2026-09-04T12:00:00',
           'dataPublicacaoPncp':'2026-09-04T12:00:00','valorInicial':'100.0001',
           'valorGlobal':'200.0123','receita':False}
    plan=collection_plan('pncp_contracts',start='20260904',end='20260904')
    def loader(url,path,budget):
        raw=json.dumps({'data':[row],'numeroPagina':1,'totalPaginas':1,'totalRegistros':1}).encode()
        path.write_bytes(raw)
        return {'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'collected_at':now()}
    collect(plan,folder,loader=loader);import_resources(database,folder)


def open_downloads(container):
    # Hash navigation is same-document: React preserves an open disclosure
    # when only the locale changes. Open it if necessary; never toggle it shut.
    details = container.locator('.resource-downloads').first
    if details.get_attribute('open') is None:
        details.locator(':scope > summary').click()
    expect(details).to_have_attribute('open', '')


def main():
    out=Path('test-results/browser-sharing');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'live_map_verified':False,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-sharing-') as temporary:
        root=Path(temporary);database_url='sqlite:///'+str(root/'test.db')
        database=Database(database_url);database.initialize()
        try:seed(database,root/'seed');add_precise(database,root/'precise')
        finally:database.engine.dispose()
        origin='http://127.0.0.1:8040'
        env=os.environ|{'BDT_DATABASE_URL':database_url,'BDT_PUBLIC_ORIGIN':origin,
                        'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temporary}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory',
                '--host','127.0.0.1','--port','8040'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('sharing_api_unavailable')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        page=browser.new_page(viewport={'width':width,'height':1000})
                        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                        try:
                            params=urlencode({'profile':'pncp_contracts','state':'BA','q':'%','locale':'pt-BR'})
                            page.goto(origin+'?private=DO_NOT_SHARE#resources?'+params,wait_until='domcontentloaded')
                            expect(page.get_by_label('Buscar objeto ou título',exact=True)).to_have_value('%')
                            expect(page.get_by_label('Fonte dos recursos',exact=True)).to_have_value('pncp_contracts')
                            expect(page.locator('.resource-card')).to_have_count(1)
                            page.get_by_role('button',name='Compartilhar esta consulta',exact=True).click()
                            share=page.get_by_label('Link para compartilhar',exact=True).input_value()
                            assert 'DO_NOT_SHARE' not in share and 'private=' not in share
                            page.goto(share,wait_until='domcontentloaded')
                            expect(page.get_by_label('Buscar objeto ou título',exact=True)).to_have_value('%')
                            expect(page.locator('.resource-card')).to_have_count(1)
                            card=page.locator('.resource-card')
                            card.get_by_role('button',name='Compartilhar este recurso',exact=True).click()
                            record_link=card.get_by_label('Link para compartilhar',exact=True).input_value()
                            page.goto(record_link,wait_until='domcontentloaded')
                            expect(page.get_by_text('Recurso compartilhado',exact=True)).to_be_visible()
                            expect(page.locator('.resource-card')).to_have_count(1)
                            card=page.locator('.resource-card')
                            card.get_by_role('button',name='Ver versões e mudanças',exact=True).click()
                            version=card.locator('article.source').filter(has=page.get_by_role('heading',name='Versão 1',exact=True))
                            open_downloads(version)
                            with page.expect_download() as download:
                                version.get_by_role('link',name='JSON',exact=True).click()
                            data=json.loads(Path(download.value.path()).read_text())
                            assert data['revision']==1
                            assert any(a['decimal']=='150.02' for a in data['resource']['amounts'])
                            precise='pncp_contracts:12345678000199-2-000004/2026'
                            for locale,title,fraction in [('pt-BR','Obras e recursos','100,0001'),('en','Works and resources','100.0001'),('es','Obras y recursos','100,0001')]:
                                page.goto(origin+'#resources?'+urlencode({'id':precise,'locale':locale}),wait_until='domcontentloaded')
                                expect(page.get_by_role('heading',name=title,exact=True)).to_be_visible()
                                card=page.locator('.resource-card')
                                expect(card.locator('.money h3').first).to_contain_text(fraction)
                                open_downloads(card)
                                for format in ('CSV','JSON'):
                                    with page.expect_download() as download:
                                        card.get_by_role('link',name=format,exact=True).first.click()
                                    text=Path(download.value.path()).read_text(encoding='utf-8-sig')
                                    assert '100.0001' in text and '200.0123' in text and 'snapshot_sha256' in text
                                    assert 'DO_NOT_SHARE' not in text
                                    if format=='JSON':assert json.loads(text)['locale']==locale
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale)
                            page.screenshot(path=str(out/f'public-resource-{width}.png'),full_page=True)
                            assert not errors,errors
                            report['checks'].append({'width':width,'locales':3,'query_roundtrip':True,
                                'no_private_query_copied':True,'resource_deep_link':True,'revision_export':True,
                                'exact_subcent_downloads':True,'horizontal_overflow':False,'javascript_errors':errors})
                        except Exception:
                            page.screenshot(path=str(out/f'failure-{width}.png'),full_page=True)
                            raise
                        finally:page.close()
                    browser.close()
                report['status']='passed'
            finally:
                server.terminate();server.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
