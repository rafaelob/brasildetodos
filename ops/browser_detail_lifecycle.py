"""Compiled place navigation with real API data and test-only timing faults.

The timing shim fetches each real response and deliberately ignores abort. It
never fabricates a place, history or HTTP response. Synthetic records are seeded
only into a temporary test database, not a public catalog or production service.
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
from playwright.sync_api import expect,sync_playwright
from bdt.domain import Source,PlaceInput,now
from bdt.storage import Database,Municipality,upsert_place

TEXT={
 'pt-BR':('Explorar','Meus lugares','Cancelar abertura da ficha','Não foi possível concluir. Tente novamente.'),
 'en':('Explore','My places','Cancel opening place','The request could not be completed. Please try again.'),
 'es':('Explorar','Mis lugares','Cancelar apertura de ficha','No se pudo completar la solicitud. Inténtalo de nuevo.')}
TIMING="""(()=>{
 const original=window.fetch.bind(window);
 window.__delayDetails=false;window.__failDetails=false;window.__held=[];
 window.__received=0;window.__released=0;
 window.fetch=async(input,init={})=>{
  const path=decodeURIComponent(new URL(typeof input==='string'?input:input.url,location.href).pathname);
  if(!window.__delayDetails||!path.startsWith('/api/places/test:slow'))return original(input,init);
  const fail=window.__failDetails;
  const response=await original(input,{...init,signal:undefined});
  await response.clone().arrayBuffer();
  window.__received++;
  await new Promise(resolve=>window.__held.push(resolve));
  window.__released++;
  if(fail)throw new Error('Synthetic late transport fault');
  return response;
 };
})()"""


def main():
 out=Path('test-results/browser-detail-lifecycle');out.mkdir(parents=True,exist_ok=True)
 report={'status':'started','synthetic_test_only':True,'public_deployment':False,
    'api_records_are_real_persisted_fixtures':True,'test_only_transport_timing':True,'checks':[]}
 with tempfile.TemporaryDirectory(prefix='bdt-detail-journey-') as temp:
  url='sqlite:///'+str(Path(temp)/'fixture.db');db=Database(url);db.initialize()
  source=Source(dataset='synthetic-detail-test',url='https://example.org/test-only',record_id='fixture',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
  with db.session() as s:
   s.add(Municipality(id='1234567',name='Synthetic municipality',state='BA',source=source.model_dump()));s.flush()
   for identifier,name in [('test:slow','Synthetic delayed place'),('test:fast','Synthetic current place')]:
    upsert_place(s,PlaceInput(id=identifier,name=name,kind='school',municipality_id='1234567',state='BA',source=source))
  db.engine.dispose()
  origin='http://127.0.0.1:8060';env=os.environ|{'BDT_DATABASE_URL':url,'BDT_PUBLIC_ORIGIN':origin,
    'BDT_STATIC_DIR':str(Path('web/dist').resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
  with (out/'server.log').open('w') as log:
   server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory','--host','127.0.0.1','--port','8060'],env=env,stdout=log,stderr=log)
   try:
    for _ in range(80):
     try:
      if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(.25)
    else:raise RuntimeError('detail_api_not_ready')
    with sync_playwright() as pw:
     browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
     try:
      for width in (320,390,1440):
       for locale,(explore,saved,cancel,failure) in TEXT.items():
        context=browser.new_context(viewport={'width':width,'height':1000});page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script(TIMING)
        page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');')
        try:
         page.goto(origin,wait_until='domcontentloaded')
         expect(page.locator('.place-card')).to_have_count(2)
         def start_slow(fail):
          page.evaluate('(fail)=>{window.__delayDetails=true;window.__failDetails=fail;window.__received=0;window.__released=0;}',fail)
          page.get_by_role('button',name='Synthetic delayed place',exact=True).click()
          page.wait_for_function('window.__received===2')
          expect(page.locator('.detail-request-status')).to_be_visible()
         def release():
          page.evaluate('window.__held.splice(0).forEach(done=>done())')
          page.wait_for_function('window.__released===2')
          page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
         # A late failure cannot pollute a newer successful selection.
         start_slow(True)
         page.get_by_role('button',name='Synthetic current place',exact=True).click()
         expect(page.get_by_role('heading',name='Synthetic current place',exact=True)).to_be_visible()
         release()
         expect(page.locator('.notice')).to_have_count(0)
         expect(page.locator('.detail-request-status')).to_have_count(0)
         expect(page.get_by_role('heading',name='Synthetic current place',exact=True)).to_be_visible()
         # A late success cannot reopen a detail after leaving the screen.
         page.get_by_role('button',name=explore,exact=True).click();expect(page.locator('.place-card')).to_have_count(2)
         start_slow(False);page.get_by_role('button',name=saved,exact=True).click();release()
         expect(page.locator('.watch-page')).to_be_visible();expect(page.locator('.detail')).to_have_count(0)
         expect(page.locator('.detail-request-status')).to_have_count(0)
         # Keyboard cancellation also invalidates a non-abortable response.
         page.get_by_role('button',name=explore,exact=True).click();expect(page.locator('.place-card')).to_have_count(2)
         start_slow(False);button=page.get_by_role('button',name=cancel,exact=True);button.focus();page.keyboard.press('Enter')
         expect(page.locator('.detail-request-status')).to_have_count(0);release()
         expect(page.locator('.detail')).to_have_count(0);expect(page.locator('.notice')).to_have_count(0)
         # Current failures remain visible and the next selection recovers.
         start_slow(True);release()
         expect(page.locator('.notice')).to_contain_text(failure)
         expect(page.locator('.detail-request-status')).to_have_count(0)
         page.get_by_role('button',name='Synthetic current place',exact=True).click()
         expect(page.get_by_role('heading',name='Synthetic current place',exact=True)).to_be_visible()
         expect(page.locator('.notice')).to_have_count(0)
         assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),(width,locale)
         assert not errors,errors
         page.screenshot(path=str(out/f'detail-{locale}-{width}.png'),full_page=True)
         report['checks'].append({'width':width,'locale':locale,'late_failure_ignored':True,
           'navigation_cancels':True,'keyboard_cancel':True,'late_success_ignored':True,
           'current_failure_visible':True,'recovery':True,'no_horizontal_overflow':True})
        except Exception:
         page.screenshot(path=str(out/f'failure-{locale}-{width}.png'),full_page=True);raise
        finally:context.close()
      report['status']='passed'
     finally:browser.close()
   finally:
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill();server.wait()
    if report['status']!='passed':report['status']='failed'
    (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))

if __name__=='__main__':main()
