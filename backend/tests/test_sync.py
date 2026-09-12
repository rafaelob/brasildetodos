import hashlib
import json
from pathlib import Path
import httpx
import pytest
from sqlalchemy import func, select
from bdt.sync import PagePlan, collect, collected_rows, download_retry, import_collection, page_url
from bdt.storage import Place


def plan(**changes):
    return PagePlan(**({'dataset':'cnes-test','url':'https://apidadosabertos.saude.gov.br/cnes/estabelecimentos',
        'root':'estabelecimentos','identity':'codigo_cnes','page_parameter':'offset','size_parameter':'limit',
        'page_size':2,'start':0,'step':2,'max_pages':5,'delay_seconds':0} | changes))


def loader_for(payloads, calls=None):
    def loader(url, path, max_bytes):
        index = int(path.stem.split('-')[-1])
        if calls is not None:
            calls.append(index)
        value = payloads[index]
        if isinstance(value, Exception):
            raise value
        content = json.dumps(value, sort_keys=True).encode()
        path.write_bytes(content)
        return {'url':url, 'sha256':hashlib.sha256(content).hexdigest(), 'bytes':len(content), 'collected_at':'2026-09-05T12:00:00+00:00'}
    return loader


def payload(*ids, **metadata):
    return {'estabelecimentos':[{'codigo_cnes':i} for i in ids]} | metadata


@pytest.mark.parametrize('changes', [{'url':'http://apidadosabertos.saude.gov.br/cnes'}, {'url':'https://localhost/cnes'},
    {'url':'https://user:secret@apidadosabertos.saude.gov.br/cnes'}, {'url':'https://apidadosabertos.saude.gov.br:8080/cnes'},
    {'size_parameter':'offset'}, {'parameters':{'offset':'1'}}, {'root':''}, {'page_size':0},
    {'total_pages_field':''}, {'total_pages_field':'total','total_records_field':'total'},
    {'total_pages_field':'page','response_page_field':'page'}])
def test_invalid_profile(changes):
    with pytest.raises(ValueError):
        plan(**changes)


def test_page_url_and_empty_terminal(tmp_path):
    p = plan(parameters={'uf':'BA'}, url='https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?format=json')
    assert 'offset=2' in page_url(p,1) and 'limit=2' in page_url(p,1) and 'uf=BA' in page_url(p,1)
    calls=[]
    report = collect(p,tmp_path,loader=loader_for([payload(1),payload(2),payload()],calls),sleep=lambda _:None)
    assert calls == [0,1,2]  # a short page was NOT interpreted as complete
    assert report['status']=='complete' and report['records']==2 and report['terminal']=='empty_page'
    assert report['national_catalog_certified'] is False
    assert len(list(collected_rows(tmp_path,report)))==2
    collect(p,tmp_path,loader=lambda *args:pytest.fail('cache should be used'))


def test_budget_is_partial_and_not_publishable(database,tmp_path):
    report=collect(plan(max_pages=1),tmp_path,loader=loader_for([payload(1,2)]))
    assert report['status']=='partial_budget'
    with pytest.raises(ValueError,match='incomplete_collection'):
        import_collection(database,tmp_path,'cnes')
    with pytest.raises(ValueError,match='resume_profile_changed'):
        collect(plan(max_pages=2),tmp_path,loader=loader_for([]))


def test_resume_after_transport_failure(tmp_path):
    p=plan();calls=[]
    with pytest.raises(OSError):
        collect(p,tmp_path,loader=loader_for([payload(1),OSError('offline')],calls))
    report=json.loads((tmp_path/'collection.json').read_text())
    assert report['status']=='failed' and len(report['pages'])==1
    calls=[]
    report=collect(p,tmp_path,loader=loader_for([None,payload(2),payload()],calls))
    assert calls==[1,2] and report['records']==2
    (tmp_path/'page-000000.json').write_text('{}')
    with pytest.raises(ValueError,match='cached_page_integrity_failure'):
        collect(p,tmp_path,loader=loader_for([]))


@pytest.mark.parametrize('values,changes,error', [
    ([payload(1),payload(1)],{},'repeated_page'),
    ([payload(1),payload(1,note='different bytes')],{},'duplicate_source_identity'),
    ([{'unexpected':[]}],{},'response_schema_changed'),
    ([payload(True)],{},'missing_source_identity'),
    ([{'estabelecimentos':[{}]}],{},'missing_source_identity'),
    ([payload(1,page=10)],{'response_page_field':'page'},'unexpected_response_page'),
    ([payload(1,total=2),payload(2,total=3)],{'total_records_field':'total'},'changing_or_invalid_total'),
    ([payload(1,total=True)],{'total_records_field':'total'},'changing_or_invalid_total'),
    ([payload(1,2,total=1)],{'total_records_field':'total'},'record_count_exceeds'),
    ([payload(1,total=2),payload(total=2)],{'total_records_field':'total'},'terminal_count_mismatch'),
    ([payload(pages=3)],{'total_pages_field':'pages'},'premature_empty_page'),
])
def test_invalid_pages_block_publication(tmp_path,values,changes,error):
    with pytest.raises(ValueError,match=error):
        collect(plan(**changes),tmp_path,loader=loader_for(values))
    assert json.loads((tmp_path/'collection.json').read_text())['status']=='failed'


def test_declared_pages_and_counts_are_reconciled(tmp_path):
    values=[payload(1,2,pages=2,total=3,page=0),payload(3,pages=2,total=3,page=2)]
    report=collect(plan(total_pages_field='pages',total_records_field='total',response_page_field='page'),tmp_path,loader=loader_for(values))
    assert report['status']=='complete' and report['terminal']=='declared_total_pages'
    assert report['records']==report['expected_records']==3


def test_nonempty_page_cannot_claim_zero_total_pages(tmp_path):
    with pytest.raises(ValueError, match='declared_total_pages_before_current_page'):
        collect(plan(total_pages_field='pages'), tmp_path, loader=loader_for([payload(1, pages=0)]))
    assert json.loads((tmp_path/'collection.json').read_text())['status']=='failed'


def test_bad_downloader_hash_is_rejected(tmp_path):
    def bad(url,path,budget):
        path.write_text('{}');return {'sha256':'0'*64}
    with pytest.raises(ValueError,match='download_hash_mismatch'):
        collect(plan(),tmp_path,loader=bad)


@pytest.mark.parametrize(('field', 'error'), [
    ('url', 'download_url_mismatch'), ('bytes', 'download_size_mismatch')])
def test_downloader_receipt_must_match_request_and_file(tmp_path, field, error):
    def bad(url, path, budget):
        content = json.dumps(payload()).encode()
        path.write_bytes(content)
        metadata = {'url': url, 'sha256': hashlib.sha256(content).hexdigest(),
                    'bytes': len(content), 'collected_at': '2026-09-05T12:00:00+00:00'}
        metadata[field] = url + '&receipt=wrong' if field == 'url' else len(content) + 1
        return metadata
    with pytest.raises(ValueError, match=error):
        collect(plan(), tmp_path, loader=bad)


def test_collection_import_and_post_collection_integrity(database,tmp_path):
    row={'codigo_cnes':123,'nome_fantasia':'Unidade sintética','codigo_municipio':'123456',
        'estabelecimento_faz_atendimento_ambulatorial_sus':'SIM'}
    report=collect(plan(),tmp_path,loader=loader_for([{'estabelecimentos':[row]},payload()]))
    result=import_collection(database,tmp_path,'cnes')
    assert result['counts']['inserted']==1 and result['national_catalog_certified'] is False
    result=import_collection(database,tmp_path,'cnes')
    assert result['counts']['unchanged']==1
    (tmp_path/'page-000000.json').write_text('{}')
    with pytest.raises(ValueError,match='page_changed_after_collection'):
        list(collected_rows(tmp_path,report))
    with pytest.raises(ValueError):
        import_collection(database,tmp_path,'cnes')


@pytest.mark.parametrize('mutate', [
    lambda report: report.update(records=2),
    lambda report: report['pages'][0].update(records=0),
    lambda report: report['pages'][0].update(file='../other.json'),
    lambda report: report['pages'][0].update(url='https://example.org/wrong-page'),
    lambda report: report.update(terminal='because_it_looked_complete'),
    lambda report: report['pages'].pop(),
])
def test_collection_manifest_tampering_never_publishes_places(database, tmp_path, mutate):
    row = {'codigo_cnes': 123, 'nome_fantasia': 'Unidade sintética', 'codigo_municipio': '123456',
           'estabelecimento_faz_atendimento_ambulatorial_sus': 'SIM'}
    report = collect(plan(), tmp_path, loader=loader_for([
        {'estabelecimentos': [row]}, payload()]))
    mutate(report)
    (tmp_path / 'collection.json').write_text(json.dumps(report))

    with pytest.raises(ValueError):
        import_collection(database, tmp_path, 'cnes')
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(Place)) == 0


def test_empty_collection_does_not_replace_database(database,tmp_path):
    collect(plan(),tmp_path,loader=loader_for([payload()]))
    with pytest.raises(ValueError,match='empty_collection'):
        import_collection(database,tmp_path,'cnes')


def test_retry_policy(monkeypatch,tmp_path):
    attempts=[];sleeps=[]
    def intermittent(*args):
        attempts.append(1)
        if len(attempts)<3:
            raise httpx.ConnectTimeout('test only')
        return {'ok':True}
    monkeypatch.setattr('bdt.sync.safe_download',intermittent)
    assert download_retry('https://example.test',tmp_path/'x',10,sleep=sleeps.append)=={'ok':True}
    assert len(attempts)==3 and sleeps==[1,2]
    def forbidden(*args):
        request=httpx.Request('GET','https://example.test')
        response=httpx.Response(403,request=request)
        raise httpx.HTTPStatusError('forbidden',request=request,response=response)
    monkeypatch.setattr('bdt.sync.safe_download',forbidden)
    with pytest.raises(httpx.HTTPStatusError):
        download_retry('https://example.test',tmp_path/'x',10,sleep=lambda _:pytest.fail('no retry on 403'))
    with pytest.raises(ValueError,match='retry_budget'):
        download_retry('https://example.test',tmp_path/'x',10,attempts=0)
