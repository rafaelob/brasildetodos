"""An empty official query must not look like an outage or delete prior rows."""
import hashlib
import json
import socket

import httpx
import pytest

from bdt.ingest import safe_download
from bdt.sync import collect, download_retry
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import import_resources
from test_resource_sync import contract, current, save_collection


def empty_loader(url, path, max_bytes):
    path.write_bytes(b'')
    return {'url':url,'bytes':0,'sha256':hashlib.sha256(b'').hexdigest(),
            'status_code':204,'collected_at':'2026-09-06T12:00:00+00:00'}


def plan():
    return collection_plan('pncp_contracts',start='20260904',end='20260904')


def test_empty_pncp_query_is_idempotent_and_preserves_previous(database,tmp_path):
    save_collection(tmp_path/'old',[contract()]);import_resources(database,tmp_path/'old')
    folder=tmp_path/'empty'
    report=collect(plan(),folder,loader=empty_loader)
    assert report['terminal']=='http_204_no_content' and report['expected_records']==0
    assert (folder/'page-000000.json').read_bytes()==b''
    assert import_resources(database,folder)['read']==0
    assert len(current(database))==1
    resumed=collect(plan(),folder,loader=lambda *a:pytest.fail('cached empty response should be verified'))
    assert resumed['status']=='complete' and import_resources(database,folder)['read']==0


def test_late_no_content_does_not_hide_missing_pages(tmp_path):
    def loader(url,path,budget):
        if path.name!='page-000000.json':return empty_loader(url,path,budget)
        raw=json.dumps({'data':[contract()],'totalPaginas':2,'totalRegistros':2,'numeroPagina':1}).encode()
        path.write_bytes(raw)
        return {'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'collected_at':'2026-09-06T12:00:00+00:00'}
    with pytest.raises(ValueError,match='unexpected_no_content'):
        collect(plan(),tmp_path,loader=loader,sleep=lambda _:None)
    assert json.loads((tmp_path/'collection.json').read_text())['status']=='failed'


def test_other_source_cannot_claim_empty_204(tmp_path):
    p=collection_plan('obrasgov_projects')
    with pytest.raises(ValueError,match='unexpected_no_content'):
        collect(p,tmp_path,loader=empty_loader)


@pytest.mark.parametrize('field,value',[('records',1),('expected_records',1),('terminal','empty_page')])
def test_tampered_empty_manifest_is_refused(database,tmp_path,field,value):
    collect(plan(),tmp_path,loader=empty_loader)
    file=tmp_path/'collection.json';report=json.loads(file.read_text());report[field]=value
    file.write_text(json.dumps(report))
    with pytest.raises(ValueError):import_resources(database,tmp_path)


def test_zero_length_http_200_is_not_no_content(tmp_path):
    def loader(url,path,budget):return empty_loader(url,path,budget)|{'status_code':200}
    with pytest.raises(ValueError):collect(plan(),tmp_path,loader=loader)


def test_http_downloader_records_204_only_when_enabled(monkeypatch,tmp_path):
    monkeypatch.setattr('bdt.ingest.socket.getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    client=httpx.Client
    monkeypatch.setattr('bdt.ingest.httpx.Client',lambda **kwargs:client(transport=httpx.MockTransport(lambda req:httpx.Response(204))))
    target=tmp_path/'page'
    with pytest.raises(ValueError):safe_download(plan().url,target)
    metadata=download_retry(plan().url,target,100)
    assert metadata['status_code']==204 and target.read_bytes()==b''
    assert metadata['sha256']==hashlib.sha256(b'').hexdigest()
