"""Compiled guided visits, real API, moderation and downloads; synthetic DB only."""
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
from bdt.api import password_hash
from bdt.domain import Source, PlaceInput, now
from bdt.storage import Database, Municipality, User, upsert_place

PASSWORD='synthetic-browser-password'
HEAD={'X-BDT-Client':'web'}
TEXT={
 'pt-BR':{'community':'Contribuições da comunidade','open':'Registrar visita guiada','note':'Contexto da sua observação','date':'Data da visita','submit':'Enviar roteiro para revisão','saved':'Roteiro enviado. Suas respostas estão privadas até uma revisão independente.','download':'Baixar observação publicada','yes':'Sim','no':'Não','unknown':'Não sei'},
 'en':{'community':'Community contributions','open':'Record a guided visit','note':'Observation context','date':'Visit date','submit':'Submit guide for review','saved':'Guide submitted. Your answers remain private until independent review.','download':'Download published observation','yes':'Yes','no':'No','unknown':'Unknown'},
 'es':{'community':'Contribuciones de la comunidad','open':'Registrar visita guiada','note':'Contexto de la observación','date':'Fecha de la visita','submit':'Enviar guía para revisión','saved':'Guía enviada. Las respuestas son privadas hasta una revisión independiente.','download':'Descargar observación publicada','yes':'Sí','no':'No','unknown':'No sé'},
}


def seed(db):
    source=Source(dataset='synthetic-guided-visit',url='https://example.org/test-only',record_id='fixture',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
    with db.session() as s:
        s.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()));s.flush()
        for kind in ('school','health','work'):
            upsert_place(s,PlaceInput(id='guided:'+kind,name='Synthetic '+kind,kind=kind,municipality_id='1234567',state='BA',source=source))
        for name,role in (('contributor','citizen'),('reviewer','reviewer')):
            s.add(User(username=name,password_hash=password_hash(PASSWORD),role=role))


def main():
    out=Path('test-results/browser-guided');out.mkdir(parents=True,exist_ok=True)
    report={'synthetic_test_only':True,'public_deployment':False,'status':'started','checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-guided-browser-') as temp:
        url='sqlite:///'+str(Path(temp)/'test.db');db=Database(url);db.initialize();seed(db)
        origin='http://127.0.0.1:8054'
        env=os.environ|{'BDT_DATABASE_URL':url,'BDT_PUBLIC_ORIGIN':origin,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8054'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('guided_api_not_ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for index,(locale,labels) in enumerate(TEXT.items()):
                            kind=('school','health','work')[index];identifier='guided:'+kind
                            context=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True)
                            response=context.request.post(origin+'/api/auth/login',headers=HEAD,data={'username':'contributor','password':PASSWORD})
                            assert response.status==200
                            page=context.new_page();errors=[]
                            page.on('pageerror',lambda error:errors.append(str(error)))
                            page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');')
                            try:
                                page.goto(origin,wait_until='domcontentloaded')
                                page.get_by_role('button',name='Synthetic '+kind,exact=True).click()
                                page.get_by_role('button',name=labels['community'],exact=True).click()
                                page.get_by_role('button',name=labels['open'],exact=True).click()
                                form=page.locator('.guided-visit form')
                                expect(form.locator('.visit-question')).to_have_count(4)
                                assert not form.evaluate('(form)=>form.checkValidity()')
                                def fill():
                                    for i in range(4):
                                        form.locator('.visit-question').nth(i).get_by_label(labels[('yes','no','unknown','unknown')[i]],exact=True).check()
                                    form.get_by_label(labels['date'],exact=True).fill('2025-01-01')
                                    form.get_by_label(labels['note'],exact=True).fill('Synthetic field observation made from a public area; test only.')
                                    form.get_by_role('checkbox').check()
                                fill()
                                page.screenshot(path=str(out/f'guided-form-{locale}-{width}.png'),full_page=True)
                                form.get_by_role('button',name=labels['submit'],exact=True).click()
                                expect(page.get_by_text(labels['saved'],exact=True)).to_be_visible()
                                rows=context.request.get(origin+'/api/observations/mine').json();created=rows[0]
                                assert created['status']=='pending' and ('bdt.'+kind+'.field.v1') in created['observation']['body']
                                obs_id=created['id']
                                assert not any(row['id']==obs_id for row in context.request.get(origin+'/api/places/'+identifier).json()['observations'])
                                reviewer=browser.new_context()
                                try:
                                    assert reviewer.request.post(origin+'/api/auth/login',headers=HEAD,data={'username':'reviewer','password':PASSWORD}).status==200
                                    assert reviewer.request.post(origin+'/api/review/'+obs_id,headers=HEAD,data={'decision':'approved','note':'Independent review for synthetic browser fixture.'}).status==200
                                finally:reviewer.close()
                                page.reload(wait_until='domcontentloaded')
                                page.get_by_role('button',name='Synthetic '+kind,exact=True).click()
                                page.get_by_role('button',name=labels['community'],exact=True).click()
                                result=page.locator('.observations>article').filter(has_text='bdt.'+kind+'.field.v1').first
                                expect(result.locator('.observation-body')).to_contain_text('bdt.'+kind+'.field.v1')
                                result.get_by_text(labels['download'],exact=True).click()
                                with page.expect_download() as downloaded:
                                    result.get_by_role('button',name='JSON',exact=True).click()
                                data=json.loads(Path(downloaded.value.path()).read_text())
                                assert data['locale']==locale and ('bdt.'+kind+'.field.v1') in data['observation']['body']
                                assert 'author_id' not in json.dumps(data)
                                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale)
                                page.screenshot(path=str(out/f'guided-{locale}-{width}.png'),full_page=True)
                                assert context.request.post(origin+'/api/observations/'+obs_id+'/withdraw',headers=HEAD).status==200
                                assert not any(row['id']==obs_id for row in context.request.get(origin+'/api/places/'+identifier).json()['observations'])
                                assert not errors,errors
                                report['checks'].append({'width':width,'locale':locale,'kind':kind,'required_answers':True,'pending_private':True,'independent_review':True,'citizen_text_copy':True,'withdrawal_removes_publication':True,'no_horizontal_overflow':True,'javascript_errors':errors})
                            except Exception:
                                page.screenshot(path=str(out/f'failure-{locale}-{width}.png'),full_page=True);raise
                            finally:context.close()
                    browser.close();report['status']='passed'
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()
                db.engine.dispose()
                (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
