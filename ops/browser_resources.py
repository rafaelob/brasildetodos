"""Compiled resource UI against a local API; synthetic records only, no LLM."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright
from bdt.domain import Source, now
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import import_resources
from bdt.storage import Database, Municipality
from bdt.sync import collect


def seed(database: Database, folder: Path) -> None:
    source = Source(dataset='synthetic-browser-test', record_id='territory',
        url='https://example.org/synthetic-only', reference_date='2026',
        collected_at=now(), snapshot_sha256='a'*64)
    with database.session() as session:
        session.add(Municipality(id='1234567', name='Synthetic municipality', state='BA', source=source.model_dump()))
    first = {'numeroControlePNCP': '12345678000199-2-000001/2026',
        'anoContrato': 2026, 'sequencialContrato': 1,
        'orgaoEntidade': {'cnpj': '12345678000199', 'razaoSocial': 'SYNTHETIC buyer'},
        'unidadeOrgao': {'codigoIbge': '1234567', 'ufSigla': 'BA'},
        'objetoContrato': 'SYNTHETIC contract 100%', 'dataAtualizacao': '2026-09-04T12:00:00',
        'dataPublicacaoPncp': '2026-09-04T12:00:00', 'valorInicial': '100.01',
        'valorGlobal': '150.02', 'receita': False}
    second = first | {'numeroControlePNCP': '12345678000199-2-000002/2026',
                      'sequencialContrato': 2, 'objetoContrato': 'SYNTHETIC second contract'}
    project = {'id_projeto_investimento': 'synthetic-1', 'desc_nome': 'SYNTHETIC public project',
               'situacao': 'Synthetic test only', 'uf_principal': 'BA',
               'investimentos_previstos': [{'vl_investimento_previsto': '50.01',
                                            'desc_nome_fonte_recurso': 'SYNTHETIC source'}]}
    cases = [('pncp_contracts', [first, second]),
             ('pncp_contracts', [first | {'dataAtualizacao':'2026-09-05T12:00:00', 'valorGlobal':'200.00'}]),
             ('obrasgov_projects', [project])]
    for index, (profile, rows) in enumerate(cases):
        plan = collection_plan(profile, **({'start':'20260904','end':'20260904'} if profile=='pncp_contracts' else {}))
        def loader(url, path, max_bytes):
            raw=json.dumps({'data':rows, plan.total_pages_field:1, plan.total_records_field:len(rows),
                            plan.response_page_field:1}).encode()
            path.write_bytes(raw)
            return {'url':url,'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw), 'collected_at':now()}
        target=folder/str(index)
        collect(plan,target,loader=loader,sleep=lambda _:None)
        import_resources(database,target)


def main():
    out=Path('test-results/browser-resources');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True, 'checks':[], 'status':'started', 'live_map_verified':False}
    with tempfile.TemporaryDirectory(prefix='bdt-resource-browser-') as temporary:
        root=Path(temporary);url='sqlite:///'+str(root/'test.db')
        database=Database(url);database.initialize()
        try:seed(database,root/'collections')
        finally:database.engine.dispose()
        origin='http://127.0.0.1:8038'
        env=os.environ|{'BDT_DATABASE_URL':url, 'BDT_PUBLIC_ORIGIN':origin,
            'BDT_STATIC_DIR':str(Path('web/dist').resolve()), 'BDT_ALLOW_REGISTRATION':'0', 'BDT_DATA_DIR':temporary}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory',
                '--host','127.0.0.1','--port','8038'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('resource_test_api_unavailable')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        page=browser.new_page(viewport={'width':width,'height':1000})
                        errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                        try:
                            page.goto(origin,wait_until='domcontentloaded')
                            page.get_by_role('button',name='Obras e recursos',exact=True).click()
                            expect(page.locator('.resource-card')).to_have_count(3)
                            # Independent source and territorial filters, not a fabricated place join.
                            page.get_by_label('Fonte dos recursos',exact=True).select_option('pncp_contracts')
                            expect(page.locator('.resource-card')).to_have_count(2)
                            page.get_by_label('Todas as UFs',exact=True).select_option('SP')
                            expect(page.locator('.resource-card')).to_have_count(0)
                            page.get_by_label('Todas as UFs',exact=True).select_option('BA')
                            expect(page.locator('.resource-card')).to_have_count(2)
                            page.get_by_label('Buscar objeto ou título',exact=True).fill('%')
                            expect(page.locator('.resource-card')).to_have_count(1)
                            card=page.locator('.resource-card').filter(has=page.get_by_role('heading',name='SYNTHETIC contract 100%',exact=True))
                            expect(card).to_have_count(1)
                            expect(card.get_by_role('heading',name=re.compile(r'100,01'))).to_have_count(1)
                            expect(card.get_by_role('heading',name=re.compile(r'200,00'))).to_have_count(1)
                            expect(card.get_by_role('heading',name=re.compile(r'300,01'))).to_have_count(0)
                            card.get_by_role('button',name='Ver versões e mudanças',exact=True).click()
                            expect(card.get_by_role('heading',name='Versão 1',exact=True)).to_be_visible()
                            expect(card.get_by_role('heading',name='Versão 2',exact=True)).to_be_visible()
                            expect(card.get_by_text(re.compile(r'150,02'))).to_have_count(1)
                            for locale,heading,version in [('en','Works and resources','Version'),('es','Obras y recursos','Versión'),('pt-BR','Obras e recursos','Versão')]:
                                page.get_by_label('Idioma / Language / Idioma').select_option(locale)
                                expect(page.get_by_role('heading',name=heading,exact=True)).to_be_visible()
                                expect(card.get_by_role('heading',name=version+' 1',exact=True)).to_be_visible()
                                expect(card.get_by_role('heading',name=version+' 2',exact=True)).to_be_visible()
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (width,locale)
                            page.screenshot(path=str(out/f'resources-history-{width}.png'),full_page=True)
                            assert not errors,errors
                            report['checks'].append({'width':width,'locales':3,'source_filter':True,'state_filter':True,
                                'literal_percent_search':True,'immutable_versions':2,'financial_amounts_not_summed':True,
                                'horizontal_overflow':False,'javascript_errors':errors})
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
