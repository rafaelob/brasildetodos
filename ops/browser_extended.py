"""Compiled UI against a real API, using explicitly synthetic isolated records."""
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
from reportlab.pdfgen import canvas
from bdt.api import password_hash
from bdt.document_job import ingest_document
from bdt.domain import PlaceInput, Source, now
from bdt.storage import Database, Municipality, User, upsert_place

URL='http://127.0.0.1:8036'


def main():
    out=Path('test-results/browser-extended');out.mkdir(parents=True,exist_ok=True)
    result={'synthetic_test_only':True,'checks':[],'real_government_ocr_tested':False}
    password=secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix='bdt-document-browser-') as temp:
        db_url='sqlite:///'+str(Path(temp)/'test.db');db=Database(db_url);db.initialize()
        src=Source(dataset='synthetic-browser',url='https://example.org/synthetic-document',record_id='synthetic',
            collected_at=now(),reference_date='2025',snapshot_sha256='a'*64)
        place=PlaceInput(id='test:document-browser',kind='school',name='Escola de Teste Documental',state='BA',municipality_id='1234567',address='Endereço sintético',source=src)
        with db.session() as session:
            session.add(Municipality(id='1234567',name='Município Sintético',state='BA',source=src.model_dump()));session.flush()
            upsert_place(session,place)
            for username,role in [('editor','reviewer'),('secondreviewer','reviewer'),('citizen','contributor')]:
                session.add(User(username=username,role=role,password_hash=password_hash(password)))
        document=Path(temp)/'synthetic.pdf';pdf=canvas.Canvas(str(document))
        excerpt='Contract SYNTHETIC-2025 serves test:document-browser.'
        pdf.drawString(40,700,excerpt);pdf.save()
        registered=ingest_document(db,document,operator='editor',title='Synthetic evidence document',dataset='synthetic-document',url='https://example.org/synthetic-document.pdf',reference_date='2025')
        db.engine.dispose()
        env=os.environ|{'BDT_DATABASE_URL':db_url,'BDT_PUBLIC_ORIGIN':URL,'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
        with (out/'server.log').open('w') as log:
            process=subprocess.Popen(['python','-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8036'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(80):
                    try:
                        if httpx.get(URL+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('API readiness failed')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True,args=['--no-sandbox'])
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(URL,wait_until='domcontentloaded')
                    def login(name):
                        page.get_by_role('button',name='Participar',exact=True).click()
                        page.get_by_label('Nome de usuário',exact=True).fill(name)
                        page.get_by_label('Senha (mínimo 12 caracteres)',exact=True).fill(password)
                        page.get_by_role('button',name='Entrar',exact=True).click()
                        page.get_by_role('button',name=name,exact=True).wait_for()
                    def logout(name):
                        page.get_by_role('button',name=name,exact=True).click();page.get_by_role('button',name='Sair',exact=True).click()
                        page.get_by_role('button',name='Participar',exact=True).wait_for()
                    def detail():
                        page.get_by_role('button',name='Explorar',exact=True).click()
                        page.get_by_role('button',name=place.name,exact=True).click()
                    login('editor');page.get_by_role('button',name='Revisão documental',exact=True).click()
                    page.get_by_role('heading',name='Revisão documental',exact=True).wait_for()
                    resource_panel=page.locator('details').filter(has=page.locator('summary',has_text='Registrar instrumento ou contratação'))
                    resource_panel.locator('summary').click()
                    resource_panel.get_by_label('Identificador do instrumento ou contratação',exact=True).fill('pncp:synthetic/2025')
                    resource_panel.get_by_label('Título',exact=True).fill('Synthetic renovation contract')
                    resource_panel.get_by_label('Código IBGE do município',exact=True).fill('1234567')
                    resource_panel.get_by_label('Conjunto de dados de origem',exact=True).fill('synthetic-browser')
                    resource_panel.get_by_label('Identificador na origem',exact=True).fill('synthetic-contract')
                    resource_panel.get_by_label('Endereço da fonte',exact=True).fill('https://example.org/synthetic-contract')
                    resource_panel.get_by_label('SHA-256 dos bytes do documento',exact=True).fill('a'*64)
                    resource_panel.get_by_label('Data ou período de referência',exact=True).fill('2025')
                    resource_panel.get_by_label('Data de coleta',exact=True).fill('2026-09-05T12:00')
                    resource_panel.get_by_role('button',name='Registrar instrumento ou contratação',exact=True).click()
                    expect(page.get_by_role('status')).to_contain_text('Registro salvo.')
                    page.get_by_label('Documento selecionado',exact=True).select_option(registered['document_id'])
                    page.get_by_role('button',name='Abrir texto extraído',exact=True).click()
                    expect(page.locator('pre.extracted-text')).to_contain_text(excerpt)
                    page.get_by_label('Identificador do lugar',exact=True).fill(place.id)
                    page.get_by_label('Identificador do instrumento ou contratação',exact=True).last.fill('pncp:synthetic/2025')
                    page.get_by_label('Trecho literal da página',exact=True).fill(excerpt)
                    page.get_by_label('Justificativa da associação',exact=True).fill('The synthetic document explicitly identifies the selected synthetic place.')
                    page.get_by_role('button',name='Propor vínculo para revisão',exact=True).click()
                    page.locator('blockquote').filter(has_text=excerpt).wait_for()
                    assert httpx.get(URL+'/api/place-links/'+place.id).json()==[]
                    for locale,title in [('en','Document review'),('es','Revisión documental'),('pt-BR','Revisão documental')]:
                        page.get_by_label('Idioma / Language / Idioma').select_option(locale)
                        page.get_by_role('heading',name=title,exact=True).wait_for()
                    for width in [320,390,1440]:
                        page.set_viewport_size({'width':width,'height':1000})
                        assert not page.evaluate('document.documentElement.scrollWidth>window.innerWidth')
                        page.screenshot(path=str(out/f'workbench-{width}.png'),full_page=True)
                    result['checks'].append('native PDF -> private text -> exact excerpt -> candidate relationship; three languages and three viewports')
                    logout('editor');login('secondreviewer')
                    page.get_by_role('button',name='Revisão documental',exact=True).click()
                    card=page.locator('article.panel').filter(has=page.locator('blockquote',has_text=excerpt))
                    card.get_by_label('Justificativa da revisão',exact=True).fill('Independently reviewed the literal source and public excerpt for this synthetic test.')
                    card.get_by_role('checkbox').check()
                    card.get_by_role('button',name='Enviar para revisão',exact=True).click()
                    expect(page.locator('blockquote').filter(has_text=excerpt)).to_have_count(0)
                    detail();page.get_by_role('button',name='Melhorias e recursos',exact=True).click()
                    expect(page.locator('blockquote')).to_contain_text(excerpt)
                    assert page.get_by_role('heading',name='Synthetic renovation contract',exact=True).count()==1
                    page.screenshot(path=str(out/'public-reviewed-relationship.png'),full_page=True)
                    result['checks'].append('independent review -> public sourced relationship; no automatic finance allocation')
                    logout('secondreviewer');login('citizen');detail()
                    page.get_by_role('button',name='Contribuições da comunidade',exact=True).click()
                    page.get_by_label('Data da observação',exact=True).fill('2025-01-01')
                    page.get_by_label('O que você observou?',exact=True).fill('Synthetic observation created solely for the privacy browser test.')
                    page.get_by_role('checkbox').check();page.get_by_role('button',name='Enviar para revisão',exact=True).click()
                    expect(page.get_by_role('status')).to_contain_text('Sua contribuição foi salva')
                    page.get_by_role('button',name='citizen',exact=True).click()
                    with page.expect_download() as downloaded:
                        page.get_by_role('button',name='Exportar meus dados',exact=True).click()
                    exported=json.loads(Path(downloaded.value.path()).read_text())
                    assert exported['username']=='citizen' and len(exported['observations'])==1 and exported['credentials_included'] is False
                    page.get_by_role('button',name='Retirar contribuição',exact=True).click()
                    page.get_by_text('Contribuição retirada pelo autor',exact=True).wait_for()
                    page.locator('summary',has_text='Desativar minha conta').click()
                    page.get_by_label('Confirme sua senha',exact=True).fill(password)
                    page.get_by_label('Entendi o que será removido e o que será mantido.',exact=True).check()
                    page.get_by_role('button',name='Desativar e remover minhas observações',exact=True).click()
                    page.get_by_role('button',name='Participar',exact=True).wait_for()
                    assert not errors,errors
                    result['checks'].append('own data export -> observation withdrawal -> account deactivation and session invalidation')
                    browser.close()
            finally:
                process.terminate();process.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
