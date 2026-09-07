"""Exercise a compiled UI against an independently selected real catalog snapshot.

Never seeds or modifies catalog records. Favorites are test browser preferences;
no accounts, contributions, API interceptions or fake network replies are used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, parse_qs

import httpx
from sqlalchemy import func, select
from bdt.catalog_release import FILES, install_catalog, verify_catalog
from bdt.resource_release import _copy_pinned
from bdt.storage import Database, Place

LABELS = {
 'pt-BR': {'saved':'Meus lugares','explore':'Explorar','search':'Busque por nome ou endereço',
   'source':'Fonte do cadastro','export':'Exportar ficha JSON','unsave':'Deixar de acompanhar',
   'no_geo':'Localização no mapa não confirmada'},
 'en': {'saved':'My places','explore':'Explore','search':'Search by name or address',
   'source':'Registry source','export':'Export place JSON','unsave':'Unfollow',
   'no_geo':'Map location not confirmed'},
 'es': {'saved':'Mis lugares','explore':'Explorar','search':'Buscar por nombre o dirección',
   'source':'Fuente del registro','export':'Exportar ficha JSON','unsave':'Dejar de seguir',
   'no_geo':'Ubicación en el mapa no confirmada'},
}


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def choose_samples(database, dataset):
    """Deterministic bounded examples, keeping missing geometry when it exists."""
    if not isinstance(dataset,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}',dataset):
        raise ValueError('browser_dataset_not_selected')
    with database.session() as session:
        filters=(Place.dataset==dataset,Place.catalogue_eligible.is_(True))
        total=session.scalar(select(func.count()).select_from(Place).where(*filters))
        if not total:raise ValueError('browser_selected_dataset_is_empty')
        samples=[]
        for has_geo in (False,True):
            condition=Place.latitude.is_not(None) if has_geo else Place.latitude.is_(None)
            row=session.scalars(select(Place).where(*filters,condition).order_by(Place.id).limit(1)).first()
            if row:samples.append(row.payload)
        return {'dataset':dataset,'records':total,'samples':samples}


def freeze_catalog(folder, expected_sha256, destination):
    """Pin all bytes before installing or choosing a browser sample."""
    folder,destination=Path(folder),Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError('browser_snapshot_exists')
    destination.mkdir()
    try:
        _copy_pinned(folder/'manifest.json',destination/'manifest.json',expected_sha256,8*1024*1024)
        manifest=json.loads((destination/'manifest.json').read_text())
        if not isinstance(manifest,dict) or set(manifest.get('files',{}))!=set(FILES):
            raise ValueError('browser_snapshot_invalid_members')
        total=0
        for name in FILES:
            entry=manifest['files'][name]
            if (not isinstance(entry,dict) or type(entry.get('bytes')) is not int
                    or not 0<=entry['bytes']<=1024**3):raise ValueError('browser_snapshot_budget')
            total+=entry['bytes']
            if total>2*1024**3:raise ValueError('browser_snapshot_budget')
            _copy_pinned(folder/name,destination/name,entry['sha256'],entry['bytes'])
        verify_catalog(destination)
        return destination
    except BaseException:
        shutil.rmtree(destination,ignore_errors=True)
        raise


def main(argv=None):
    from playwright.sync_api import expect, sync_playwright
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True)
    parser.add_argument('--dataset',required=True)
    parser.add_argument('--static',type=Path,default=Path('web/dist'))
    parser.add_argument('--output',type=Path,default=Path('test-results/browser-public-catalog'))
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[0-9a-f]{64}',args.manifest_sha256):parser.error('expected SHA-256 required')
    if not (args.static/'index.html').is_file():parser.error('compiled frontend missing')
    if args.output.exists():parser.error('output must be new')
    args.output.mkdir(parents=True)
    report={'status':'started','revision':os.getenv('GITHUB_SHA','development'),
        'catalog_manifest_sha256':args.manifest_sha256,'ui_index_sha256':file_sha(args.static/'index.html'),
        'public_deployment':False,'new_upstream_collection':False,'records_modified':False,
        'api_replies_mocked':False,'scope':'selected public catalog in isolated temporary installation',
        'checks':[]}
    with tempfile.TemporaryDirectory(prefix='bdt-public-browser-') as temp:
        frozen=freeze_catalog(args.catalog,args.manifest_sha256,Path(temp)/'frozen')
        dbpath=Path(temp)/'catalog.db';install_catalog(frozen,dbpath)
        dburl='sqlite:///'+str(dbpath);db=Database(dburl)
        try:selection=choose_samples(db,args.dataset)
        finally:db.engine.dispose()
        samples=selection.pop('samples');ids=[x['id'] for x in samples]
        report['selection']=selection | {'sample_ids':ids,'sample_count':len(ids),
             'without_geometry':sum(x['latitude'] is None for x in samples)}
        origin='http://127.0.0.1:8059'
        env=os.environ|{'BDT_DATABASE_URL':dburl,'BDT_PUBLIC_ORIGIN':origin,
            'BDT_STATIC_DIR':str(args.static.resolve()),'BDT_DATA_DIR':temp,'BDT_ALLOW_REGISTRATION':'0'}
        with (args.output/'server.log').open('w') as log:
            server=subprocess.Popen([sys.executable,'-m','uvicorn','bdt.api:create_app','--factory',
                '--host','127.0.0.1','--port','8059'],env=env,stdout=log,stderr=log)
            try:
                for _ in range(80):
                    try:
                        if httpx.get(origin+'/api/health',timeout=1).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.25)
                else:raise RuntimeError('public_catalog_api_not_ready')
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=shutil.which('google-chrome') or shutil.which('chromium'),headless=True)
                    try:
                        for width in (320,390,1440):
                            for locale,labels in LABELS.items():
                                context=browser.new_context(viewport={'width':width,'height':1000},accept_downloads=True)
                                page=context.new_page();errors=[];external=[]
                                page.on('pageerror',lambda error:errors.append(type(error).__name__))
                                page.on('request',lambda req:external.append(urlsplit(req.url).hostname)
                                    if urlsplit(req.url).scheme in ('http','https') and not req.url.startswith(origin+'/') else None)
                                page.add_init_script('localStorage.setItem("bdt:locale",'+json.dumps(json.dumps(locale))+');')
                                try:
                                    page.goto(origin,wait_until='domcontentloaded')
                                    expect(page.locator('.place-card').first).to_be_visible()
                                    # Search uses real records; no intercepted or fulfilled requests.
                                    query=samples[0]['name'][:200]
                                    with page.expect_response(lambda response: urlsplit(response.url).path=='/api/places'
                                            and parse_qs(urlsplit(response.url).query).get('q')==[query]) as found:
                                        page.get_by_label(labels['search'],exact=True).fill(query)
                                    assert found.value.status==200 and found.value.json()['total']>0
                                    expect(page.locator('.place-card').first).to_be_visible()
                                    page.evaluate('(ids)=>localStorage.setItem("bdt:favorites",JSON.stringify(ids))',ids)
                                    page.reload(wait_until='domcontentloaded')
                                    page.get_by_role('button',name=labels['saved'],exact=True).click()
                                    expect(page.locator('.watch-card')).to_have_count(len(ids))
                                    for index,item in enumerate(samples):
                                        card=page.locator('.watch-card').nth(index)
                                        expect(card.get_by_role('button',name=item['name'],exact=True)).to_be_visible()
                                        if item['latitude'] is None:expect(card.get_by_text(labels['no_geo'],exact=True)).to_be_visible()
                                        card.get_by_role('button',name=item['name'],exact=True).click()
                                        expect(page.get_by_role('heading',name=item['name'],exact=True)).to_be_visible()
                                        expect(page.locator('.source strong')).to_have_text(item['source']['dataset'])
                                        page.locator('.tabs').get_by_role('button',name=labels['source'],exact=True).click()
                                        expect(page.locator('.detail')).to_contain_text(item['id'])
                                        with page.expect_download() as pending:
                                            page.get_by_role('button',name=labels['export'],exact=True).click()
                                        download=pending.value;download_path=Path(temp)/f'export-{width}-{locale}-{index}.json'
                                        download.save_as(download_path)
                                        exported=json.loads(download_path.read_text())
                                        assert exported['place']==item and exported['observations']==[], 'export differs from installed record'
                                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale,'detail')
                                        if index==0:page.screenshot(path=str(args.output/f'catalog-{locale}-{width}.png'),full_page=True)
                                        page.get_by_role('button',name=labels['saved'],exact=True).click()
                                        expect(page.locator('.watch-card')).to_have_count(len(ids))
                                    page.reload(wait_until='domcontentloaded')
                                    page.get_by_role('button',name=labels['saved'],exact=True).click()
                                    expect(page.locator('.watch-card')).to_have_count(len(ids))
                                    assert json.loads(page.evaluate('localStorage.getItem("bdt:favorites")'))==ids
                                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'),(width,locale,'saved')
                                    assert not errors and not external,(errors,external)
                                    report['checks'].append({'width':width,'locale':locale,'source_and_export_match':True,
                                        'missing_geometry_preserved':True,'favorites_survive_reload':True,
                                        'no_horizontal_overflow':True,'external_requests':0})
                                except Exception:
                                    page.screenshot(path=str(args.output/f'failure-{locale}-{width}.png'),full_page=True);raise
                                finally:context.close()
                        report['status']='passed'
                    finally:browser.close()
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait()
                if report['status']!='passed':report['status']='failed'
                (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
