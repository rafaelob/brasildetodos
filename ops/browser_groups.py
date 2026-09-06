"""Compiled UI + actual private group API, two browser accounts, synthetic DB.

No real citizens, external sources, tokens in reports, or production writes.
"""
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
from bdt.api import password_hash
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Database, Municipality, User, upsert_place

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'synthetic-group-browser-password'
TEXT = {
 'pt-BR': {'nav':'Grupos','create':'Criar grupo','name':'Nome do grupo','description':'Descrição','invite':'Gerar convite de uso único','token':'Código do convite','join':'Entrar com convite','refresh':'Atualizar','new_task':'Criar tarefa','search':'Pesquisar lugar do catálogo','title':'Título da tarefa','instructions':'Instruções','save_task':'Salvar tarefa','claim':'Assumir tarefa','new_obs':'Registrar observação para esta tarefa','date':'Data da observação','body':'O que você observou','save_obs':'Salvar observação privada','select_obs':'Selecionar observação própria','submit':'Compartilhar entrega com o grupo','note':'Justificativa da revisão','accept':'Aceitar entrega','submitted':'Aguardando revisão do grupo','accepted':'Aceita pelo grupo','missing':'Evidência não está mais disponível','leave':'Sair do grupo','empty':'Você ainda não participa de grupos.'},
 'en': {'nav':'Groups','create':'Create group','name':'Group name','description':'Description','invite':'Generate single-use invitation','token':'Invitation code','join':'Join with invitation','refresh':'Refresh','new_task':'Create task','search':'Search catalogued places','title':'Task title','instructions':'Instructions','save_task':'Save task','claim':'Claim task','new_obs':'Record an observation for this task','date':'Observation date','body':'What you observed','save_obs':'Save private observation','select_obs':'Select your own observation','submit':'Share submission with group','note':'Review explanation','accept':'Accept submission','submitted':'Awaiting group review','accepted':'Accepted by the group','missing':'Evidence is no longer available','leave':'Leave group','empty':'You have not joined any groups.'},
 'es': {'nav':'Grupos','create':'Crear grupo','name':'Nombre del grupo','description':'Descripción','invite':'Generar invitación de un solo uso','token':'Código de invitación','join':'Entrar con invitación','refresh':'Actualizar','new_task':'Crear tarea','search':'Buscar lugar del catálogo','title':'Título de la tarea','instructions':'Instrucciones','save_task':'Guardar tarea','claim':'Asumir tarea','new_obs':'Registrar observación para esta tarea','date':'Fecha de observación','body':'Lo que observó','save_obs':'Guardar observación privada','select_obs':'Seleccionar observación propia','submit':'Compartir entrega con el grupo','note':'Justificación de la revisión','accept':'Aceptar entrega','submitted':'Pendiente de revisión del grupo','accepted':'Aceptada por el grupo','missing':'La evidencia ya no está disponible','leave':'Salir del grupo','empty':'Todavía no participa en grupos.'}
}


def main():
    out=Path('test-results/browser-groups');out.mkdir(parents=True,exist_ok=True)
    report={'status':'started','synthetic_test_only':True,'public_deployment':False,'checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-groups-browser-') as temp:
        dburl='sqlite:///'+str(Path(temp)/'test.db');db=Database(dburl);db.initialize()
        source=Source(dataset='synthetic-groups',url='https://example.org/test-only',record_id='fixture',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
        with db.session() as session:
            session.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()));session.flush()
            upsert_place(session,PlaceInput(id='group:school',kind='school',name='Synthetic group school',municipality_id='1234567',state='BA',source=source))
            for username in ('groupowner','groupmember'):
                session.add(User(username=username,password_hash=password_hash(PASSWORD),role='citizen'))
        db.engine.dispose()
        origin='http://127.0.0.1:8061'
        env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_DATA_DIR':temp,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_PUBLIC_ORIGIN':origin,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8061'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(80):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('groups_api_not_ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    for width in (320,390,1440):
                        for locale,text in TEXT.items():
                            contexts=[browser.new_context(viewport={'width':width,'height':1000}) for _ in range(2)]
                            pages=[];errors=[];urls=[]
                            try:
                                for context,username in zip(contexts,('groupowner','groupmember')):
                                    assert context.request.post(origin+'/api/auth/login',headers=HEAD,data={'username':username,'password':PASSWORD}).status==200
                                    context.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');')
                                    page=context.new_page();pages.append(page)
                                    page.on('pageerror',lambda error:errors.append(str(error)))
                                    page.on('request',lambda request:urls.append(request.url))
                                    page.goto(origin,wait_until='domcontentloaded')
                                    page.get_by_role('button',name=text['nav'],exact=True).click()
                                owner,member=pages
                                name=f'Synthetic community {locale} {width}'
                                owner.get_by_label(text['name'],exact=True).fill(name)
                                owner.get_by_label(text['description'],exact=True).fill('Private group used only in this test.')
                                owner.get_by_role('button',name=text['create'],exact=True).click()
                                expect(owner.get_by_role('heading',name=name,exact=True)).to_be_visible()
                                groups=contexts[0].request.get(origin+'/api/groups').json()['items'];g=next(x['id'] for x in groups if x['name']==name)
                                assert contexts[1].request.get(origin+'/api/groups/'+g).status==404
                                owner.get_by_role('button',name=text['invite'],exact=True).click()
                                token=owner.locator('.group-token').input_value()
                                assert len(token)==43
                                member.get_by_label(text['token'],exact=True).fill(token)
                                member.locator('.group-start').get_by_role('checkbox').check()
                                member.get_by_role('button',name=text['join'],exact=True).click()
                                expect(member.get_by_role('heading',name=name,exact=True)).to_be_visible()
                                owner.locator('.group-toolbar').get_by_role('button',name=text['refresh'],exact=True).click()
                                expect(owner.locator('.group-member')).to_have_count(2)
                                owner.locator('.group-new-task summary').click()
                                owner.get_by_label(text['search'],exact=True).fill('Synthetic group school')
                                owner.locator('.group-place-results button').click()
                                owner.get_by_label(text['title'],exact=True).fill('Check the public school notice')
                                owner.get_by_label(text['instructions'],exact=True).fill('Observe from a public area without personal data.')
                                owner.get_by_role('button',name=text['save_task'],exact=True).click()
                                expect(owner.locator('.group-task')).to_have_count(1)
                                member.locator('.group-toolbar').get_by_role('button',name=text['refresh'],exact=True).click()
                                member.get_by_role('button',name=text['claim'],exact=True).click()
                                member.get_by_text(text['new_obs'],exact=True).click()
                                member.get_by_label(text['date'],exact=True).fill('2025-01-01')
                                member.get_by_label(text['body'],exact=True).fill('Synthetic school entrance notice observed from public space. No personal data.')
                                member.locator('.group-submission details').get_by_role('checkbox').check()
                                member.get_by_role('button',name=text['save_obs'],exact=True).click()
                                expect(member.get_by_label(text['select_obs'],exact=True).locator('option')).to_have_count(2)
                                rows=contexts[1].request.get(origin+'/api/observations/mine').json()
                                obs=rows[0]['id']
                                member.get_by_label(text['select_obs'],exact=True).select_option(obs)
                                member.locator('.group-submission>form').get_by_role('checkbox').check()
                                member.get_by_role('button',name=text['submit'],exact=True).click()
                                expect(member.locator('.group-task-state')).to_have_text(text['submitted'])
                                expect(member.get_by_role('button',name=text['accept'],exact=True)).to_have_count(0)
                                assert contexts[0].request.get(origin+'/api/places/group:school').json()['observations']==[]
                                owner.locator('.group-toolbar').get_by_role('button',name=text['refresh'],exact=True).click()
                                owner.get_by_label(text['note'],exact=True).fill('Independent task review of this synthetic submission.')
                                owner.get_by_role('button',name=text['accept'],exact=True).click()
                                expect(owner.locator('.group-task-state')).to_have_text(text['accepted'])
                                assert contexts[1].request.get(origin+'/api/places/group:school').json()['observations']==[]
                                # Native reload must recover persisted membership and task state.
                                owner.reload(wait_until='domcontentloaded');owner.get_by_role('button',name=text['nav'],exact=True).click()
                                owner.get_by_role('button',name=name,exact=True).click()
                                expect(owner.locator('.group-task-state')).to_have_text(text['accepted'])
                                assert not owner.evaluate('document.documentElement.scrollWidth > innerWidth')
                                owner.screenshot(path=str(out/f'groups-{locale}-{width}.png'),full_page=True)
                                # Withdrawal revokes shared evidence without reclassifying it as public.
                                assert contexts[1].request.post(origin+'/api/observations/'+obs+'/withdraw',headers=HEAD).status==200
                                owner.locator('.group-toolbar').get_by_role('button',name=text['refresh'],exact=True).click()
                                expect(owner.locator('.group-task-state')).to_have_text(text['missing'])
                                expect(owner.locator('.group-evidence')).to_have_count(0)
                                member.locator('.group-toolbar').get_by_role('button',name=text['refresh'],exact=True).click()
                                expect(member.locator('.group-task-state')).to_have_text(text['missing'])
                                member.get_by_role('button',name=text['leave'],exact=True).click()
                                member.locator('.group-confirm').get_by_role('checkbox').check()
                                member.locator('.group-confirm').get_by_role('button',name=text['leave'],exact=True).click()
                                expect(member.get_by_text(text['empty'],exact=True)).to_be_visible()
                                assert contexts[1].request.get(origin+'/api/groups/'+g).status==404
                                exported=contexts[0].request.get(origin+'/api/account/export').text()
                                assert token not in exported and not any(token in url for url in urls)
                                assert not errors,errors
                                report['checks'].append({'locale':locale,'width':width,'two_accounts':True,'persistent_membership':True,'private_invite':True,'task_created_via_catalog_search':True,'observation_created_via_ui':True,'independent_review':True,'no_automatic_publication':True,'withdrawal_revokes_evidence':True,'leave_revokes_access':True,'no_horizontal_overflow':True,'no_secret_in_urls_or_export':True})
                            except Exception:
                                # Invitation codes are never included in failure screenshots.
                                for page in pages:
                                    page.locator('.group-secret').evaluate_all('(nodes)=>nodes.forEach(n=>n.remove())')
                                for i,page in enumerate(pages):page.screenshot(path=str(out/f'failure-{locale}-{width}-{i}.png'),full_page=True)
                                raise
                            finally:
                                for context in contexts:context.close()
                    browser.close();report['status']='passed'
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()
                (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
