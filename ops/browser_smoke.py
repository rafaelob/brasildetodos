"""Exercise the compiled UI against a real local API with isolated synthetic records."""
import json
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
from bdt.api import password_hash
from bdt.domain import PlaceInput, Source, now
from bdt.ingest import import_finance
from bdt.storage import Database, Municipality, User, upsert_place


def main():
    out = Path('test-results/browser'); out.mkdir(parents=True, exist_ok=True)
    report = {'synthetic_test_only': True, 'checks': [], 'live_map_verified': False}
    password = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix='bdt-browser-') as temp:
        url = f'sqlite:///{Path(temp) / "test.db"}'
        db = Database(url); db.initialize()
        source = Source(dataset='synthetic-browser-test', url='https://example.org/synthetic-test-only', record_id='browser', reference_date='2025', collected_at=now(), snapshot_sha256='a'*64)
        item = PlaceInput(id='test:browser', kind='school', name='Escola Sintética para Testes', municipality_id='1234567', state='BA', address='Endereço sintético de teste', source=source)
        with db.session() as session:
            session.add(Municipality(id='1234567', name='Município Sintético', state='BA', source=source.model_dump())); session.flush()
            upsert_place(session, item)
            session.add_all([User(username='participant', password_hash=password_hash(password), role='contributor'), User(username='reviewer', password_hash=password_hash(password), role='reviewer')])
        for phase, cents in [('transferred', 100000), ('paid', 30000)]:
            import_finance(db, [{'id':phase, 'municipality_id':'1234567', 'instrument_id':'SYNTHETIC-2025', 'phase':phase, 'cents':cents, 'period':'2025', 'recipient':'Synthetic recipient', 'perspective':'federal', 'facility_id':item.id, 'relation_state':'reviewed', 'evidence':'Synthetic association for browser test only.'}], source)
        db.engine.dispose()
        env = os.environ | {'BDT_DATABASE_URL':url, 'BDT_PUBLIC_ORIGIN':'http://127.0.0.1:8034', 'BDT_STATIC_DIR':str(Path('web/dist').resolve()), 'BDT_ALLOW_REGISTRATION':'0', 'BDT_DATA_DIR':temp}
        with (out/'server.log').open('w') as log:
            server = subprocess.Popen(['python','-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8034'], env=env, stdout=log, stderr=log)
            try:
                for _ in range(60):
                    try:
                        if httpx.get('http://127.0.0.1:8034/api/health', timeout=1).status_code == 200: break
                    except httpx.HTTPError: pass
                    time.sleep(.25)
                else: raise RuntimeError('Local API did not start')
                with sync_playwright() as playwright:
                    executable = shutil.which('google-chrome') or shutil.which('chromium')
                    browser = playwright.chromium.launch(executable_path=executable, headless=True, args=['--no-sandbox'])
                    for width in [320, 390, 1440]:
                        page = browser.new_page(viewport={'width':width, 'height':1000})
                        errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                        # UI assertions, not network-idle, establish application readiness.
                        page.goto('http://127.0.0.1:8034', wait_until='domcontentloaded')
                        page.get_by_role('button', name=item.name, exact=True).wait_for()
                        assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth'), f'Horizontal overflow at {width}'
                        page.get_by_text('Localização no mapa não confirmada', exact=True).wait_for()
                        for locale, heading in [('en','A living map of public services.'), ('es','El mapa vivo de lo público.'), ('pt-BR','O mapa vivo do que é público.')]:
                            page.get_by_label('Idioma / Language / Idioma').select_option(locale)
                            page.get_by_role('heading', name=heading, exact=True).wait_for()
                        page.screenshot(path=str(out/f'explore-{width}.png'), full_page=True)
                        page.get_by_role('button', name='Acompanhar '+item.name, exact=True).click()
                        page.get_by_role('button', name='Meus lugares', exact=True).click()
                        page.get_by_role('button', name=item.name, exact=True).wait_for()
                        page.reload(wait_until='domcontentloaded')
                        page.get_by_role('button', name='Meus lugares', exact=True).click()
                        page.get_by_role('button', name=item.name, exact=True).click()
                        page.get_by_role('heading', name=item.name, exact=True).wait_for()
                        page.get_by_role('button', name='Melhorias e recursos', exact=True).click()
                        page.get_by_role('heading', name=re.compile(r'1\.000,00')).wait_for()
                        page.get_by_role('heading', name=re.compile(r'300,00')).wait_for()
                        assert page.get_by_role('heading', name=re.compile(r'1\.300,00')).count() == 0
                        assert not errors, errors
                        report['checks'].append({'viewport':width, 'languages':3, 'favorites_persisted':True, 'financial_stages_separate':True, 'javascript_errors':errors})
                        page.close()
                    page = browser.new_page(viewport={'width':1440, 'height':1000})
                    page.goto('http://127.0.0.1:8034', wait_until='domcontentloaded')
                    def login(username):
                        page.get_by_role('button', name='Participar', exact=True).click()
                        page.get_by_label('Nome de usuário', exact=True).fill(username)
                        page.get_by_label('Senha (mínimo 12 caracteres)', exact=True).fill(password)
                        page.get_by_role('button', name='Entrar', exact=True).click()
                        page.get_by_role('button', name=username, exact=True).wait_for()
                    def community():
                        page.get_by_role('button', name='Explorar', exact=True).click()
                        page.get_by_role('button', name=item.name, exact=True).click()
                        page.get_by_role('button', name='Contribuições da comunidade', exact=True).click()
                    login('participant'); community()
                    text = 'Observação inteiramente sintética para testar o fluxo compartilhado.'
                    page.get_by_label('Data da observação', exact=True).fill('2025-01-01')
                    page.get_by_label('O que você observou?', exact=True).fill(text)
                    page.get_by_role('checkbox').check()
                    page.get_by_role('button', name='Enviar para revisão', exact=True).click()
                    # The live region also contains a close button; match its message, not the entire element text.
                    expect(page.get_by_role('status')).to_contain_text('Sua contribuição foi salva e aguarda revisão. Ainda não está pública.')
                    page.get_by_text('Ainda não há contribuições aprovadas para este lugar.', exact=True).wait_for()
                    page.get_by_role('button', name='participant', exact=True).click()
                    page.get_by_role('button', name='Sair', exact=True).click()
                    login('reviewer')
                    page.get_by_role('button', name='Revisão', exact=True).click()
                    page.get_by_text(text, exact=True).wait_for()
                    page.get_by_label('Justificativa da revisão', exact=True).fill('Revisão independente de observação sintética para o teste.')
                    page.get_by_role('button', name='Enviar para revisão', exact=True).click()
                    page.get_by_text('Nenhuma contribuição pendente.', exact=True).wait_for()
                    community(); page.get_by_text(text, exact=True).wait_for()
                    page.screenshot(path=str(out/'collaboration-approved.png'), full_page=True)
                    report['checks'].append({'collaboration':'submitted_private_then_independently_approved_and_public'})
                    browser.close()
            finally:
                server.terminate(); server.wait(timeout=10)
                (out/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
