import hashlib
import json
import socket
import httpx
import pytest
from bdt.cnes_bulk import convert, converted
from bdt.transport import download_registered

URL = 'https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip'


def record(**changes):
    return {'CO_CNES':'0000123','NO_FANTASIA':'Unidade sintética','CO_IBGE':'123456','CO_AMBULATORIAL_SUS':'SIM',
            'CO_MOTIVO_DESAB':'','NU_LATITUDE':'-22,3','NU_LONGITUDE':'-48,6','NO_EMAIL':'not-imported',
            'NU_CNPJ':'not-imported','NU_TELEFONE':'1234'} | changes


@pytest.mark.parametrize('value,expected',[('SIM','SIM'),('S','SIM'),('sim','SIM'),(' NÃO ','NAO'),('N','NAO'),('', 'NAO'),(None,'NAO'),('NULL','NAO')])
def test_bulk_uses_only_textual_flags(value,expected):
    actual=convert(record(CO_AMBULATORIAL_SUS=value))
    assert actual['estabelecimento_faz_atendimento_ambulatorial_sus']==expected
    assert actual['codigo_cnes']=='0000123'
    assert actual['latitude_estabelecimento_decimo_grau']=='-22,3'
    assert 'data_atualizacao' not in actual and 'NO_EMAIL' not in actual and 'NU_CNPJ' not in actual


@pytest.mark.parametrize('value',['1','2','0','unknown'])
def test_numeric_or_unknown_flags_are_not_guessed(value):
    with pytest.raises(ValueError,match='requires_dictionary_review'):
        convert(record(CO_AMBULATORIAL_SUS=value))


@pytest.mark.parametrize('value,expected',[('',None),('NULL',None),('None',None),('01','01')])
def test_deactivation_reason_is_preserved(value,expected):
    assert convert(record(CO_MOTIVO_DESAB=value))['codigo_motivo_desabilitacao_estabelecimento']==expected


def test_bulk_schema_and_streaming():
    with pytest.raises(ValueError,match='schema_changed'):
        convert({'CO_CNES':'1'})
    assert len(list(converted(iter([record(),record()]))))==2


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr('bdt.transport.socket.getaddrinfo',lambda *args,**kwargs:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])


def install_http(monkeypatch,handler):
    client=httpx.Client
    def build(**kwargs):
        assert kwargs['follow_redirects'] is False and kwargs['trust_env'] is False
        return client(**kwargs,transport=httpx.MockTransport(handler))
    monkeypatch.setattr('bdt.transport.httpx.Client',build)


def test_exact_official_object_download(monkeypatch,tmp_path,public_dns):
    content=b'PK-synthetic-archive-content'
    install_http(monkeypatch,lambda req:httpx.Response(200,content=content,headers={'etag':'synthetic-etag','last-modified':'Wed, 02 Sep 2026 12:00:00 GMT'}))
    target=tmp_path/'file.zip'
    result=download_registered(URL,target)
    assert target.read_bytes()==content
    assert result['sha256']==hashlib.sha256(content).hexdigest() and result['bytes']==len(content)
    assert result['url']==URL and result['last_modified'].startswith('Wed')
    assert json.loads((tmp_path/'file.zip.manifest.json').read_text())==result
    assert not list(tmp_path.glob('*.part-*'))


@pytest.mark.parametrize('status',[302,403,206])
def test_redirect_partial_and_failure_preserve_previous_file(monkeypatch,tmp_path,public_dns,status):
    install_http(monkeypatch,lambda req:httpx.Response(status,content=b'changed',headers={'location':'https://example.org'}))
    target=tmp_path/'file.zip';target.write_bytes(b'previous')
    with pytest.raises((ValueError,httpx.HTTPStatusError)):
        download_registered(URL,target)
    assert target.read_bytes()==b'previous' and not list(tmp_path.glob('*.part-*'))


@pytest.mark.parametrize('content,budget,message',[(b'',10,'empty_distribution'),(b'abcdef',2,'byte_budget')])
def test_byte_budget_and_empty_download(monkeypatch,tmp_path,public_dns,content,budget,message):
    install_http(monkeypatch,lambda req:httpx.Response(200,content=content))
    target=tmp_path/'file.zip'
    with pytest.raises(ValueError,match=message):
        download_registered(URL,target,budget)
    assert not target.exists() and not list(tmp_path.glob('*.part-*'))


@pytest.mark.parametrize('url',[URL+'?token=anything',URL.replace('/CNES/','/other/'),URL.replace('https:','http:')])
def test_other_shared_cloud_objects_are_not_allowed(tmp_path,url):
    with pytest.raises(ValueError,match='unregistered_cloud_object'):
        download_registered(url,tmp_path/'x')


@pytest.mark.parametrize('addresses',[[],[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]])
def test_private_or_empty_dns_refused(monkeypatch,tmp_path,addresses):
    monkeypatch.setattr('bdt.transport.socket.getaddrinfo',lambda *a,**k:addresses)
    with pytest.raises(ValueError,match='non_public_distribution_address'):
        download_registered(URL,tmp_path/'x')


def test_other_sources_delegate_to_existing_reviewed_downloader(monkeypatch,tmp_path):
    calls=[]
    monkeypatch.setattr('bdt.transport.safe_download',lambda *args:calls.append(args) or {'result':'delegate'})
    assert download_registered('https://servicodados.ibge.gov.br/x',tmp_path/'x',123)=={'result':'delegate'}
    assert len(calls)==1 and calls[0][2]==123
