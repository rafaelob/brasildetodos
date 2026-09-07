"""Simulated transport faults only; production uses the fixed official INEP URL."""
import hashlib
import httpx
import pytest
from bdt import education_transport as transport

@pytest.fixture
def client_factory(monkeypatch):
    original=httpx.Client;calls=[]
    def install(handler):
        def factory(**kwargs):
            calls.append(kwargs)
            return original(transport=httpx.MockTransport(handler),**kwargs)
        monkeypatch.setattr(transport.httpx,'Client',factory)
    return install,calls


def test_transient_failure_recovers_with_exact_fixed_url_and_complete_bytes(client_factory):
    install,calls=client_factory;seen=[];wait=[]
    body='<html>Microdados 2025: ç</html>'.encode()
    def server(req):
        seen.append(str(req.url))
        if len(seen)==1:return httpx.Response(503,headers={'Retry-After':'2'})
        return httpx.Response(200,headers={'Content-Type':'text/html; charset=utf-8'},content=body)
    install(server)
    text,meta=transport.official_anchor(sleep=wait.append)
    assert text.encode()==body and meta['bytes']==len(body)
    assert meta['sha256']==hashlib.sha256(body).hexdigest() and meta['attempts']==2
    assert seen==[transport.ANCHOR]*2 and wait==[2]
    assert calls[0]['trust_env'] is False and calls[0]['follow_redirects'] is False
    assert calls[0]['timeout'].connect==20

@pytest.mark.parametrize('code',[400,401,403,404,301,302])
def test_access_errors_and_redirects_never_retry_or_follow(client_factory,code):
    install,_=client_factory;seen=[]
    def server(req):seen.append(req.url);return httpx.Response(code,headers={'Location':'https://example.org/replacement'})
    install(server)
    with pytest.raises(httpx.HTTPStatusError):transport.official_anchor(sleep=lambda _:pytest.fail('unexpected retry'))
    assert len(seen)==1

@pytest.mark.parametrize('kind',[httpx.ConnectTimeout,httpx.ConnectError,httpx.ReadTimeout,httpx.RemoteProtocolError])
def test_retry_budget_preserves_transport_failure(client_factory,kind):
    install,_=client_factory;seen=[];delays=[]
    def server(req):seen.append(req);raise kind('synthetic transport failure',request=req)
    install(server)
    with pytest.raises(kind):transport.official_anchor(sleep=delays.append)
    assert len(seen)==3 and delays==[1,2]


def test_partial_body_is_discarded_before_retry(client_factory):
    install,_=client_factory;seen=[]
    class Partial(httpx.SyncByteStream):
        def __iter__(self):yield b'incomplete';raise httpx.ReadTimeout('synthetic failure')
    def server(req):
        seen.append(req)
        return httpx.Response(200,headers={'Content-Type':'text/html'},stream=Partial()) if len(seen)==1 else httpx.Response(200,headers={'Content-Type':'text/html'},content=b'complete')
    install(server);text,meta=transport.official_anchor(sleep=lambda _:None)
    assert text=='complete' and meta['sha256']==hashlib.sha256(b'complete').hexdigest()
    assert meta['bytes']==8 and meta['attempts']==2

@pytest.mark.parametrize('body,content_type',[ (b'','text/html'),(b'{}','application/json'),(b'\xff','text/html')])
def test_invalid_content_is_not_retried(client_factory,body,content_type):
    install,_=client_factory;seen=[]
    def server(req):seen.append(req);return httpx.Response(200,headers={'Content-Type':content_type},content=body)
    install(server)
    with pytest.raises((ValueError,UnicodeDecodeError)):transport.official_anchor(sleep=lambda _:pytest.fail('invalid content retry'))
    assert len(seen)==1


def test_body_budget_and_retry_parameters(client_factory,monkeypatch):
    install,_=client_factory;monkeypatch.setattr(transport,'MAX_BYTES',3)
    install(lambda req:httpx.Response(200,headers={'Content-Type':'text/html'},content=b'1234'))
    with pytest.raises(ValueError,match='byte_budget'):transport.official_anchor()
    for attempts in (0,4,True,1.5):
        with pytest.raises(ValueError,match='retry_budget'):transport.official_anchor(attempts=attempts)
    assert transport.retry_delay('99999999999',0)==10
    assert transport.retry_delay('-5',0)==1
    assert transport.retry_delay('not a delay',2)==4


def test_diagnostics_expose_codes_not_messages_or_urls():
    import json,socket,ssl
    cert=ssl.SSLCertVerificationError(1,'secret certificate message')
    cert.verify_code=20;cert.reason='CERTIFICATE_VERIFY_FAILED'
    network=httpx.ConnectError('private url https://example.org/?secret=x');network.__cause__=cert
    report=transport.transport_diagnostics(network)
    assert report['exception_types']==['ConnectError','SSLCertVerificationError']
    assert report['certificate_verify_codes']==[20]
    assert report['tls_reasons']==['CERTIFICATE_VERIFY_FAILED']
    assert report['certificate_verification_error'] and not report['message_or_payload_included']
    assert 'secret' not in json.dumps(report) and 'example.org' not in json.dumps(report)
    network.__cause__=socket.gaierror(-2,'secret host')
    assert transport.transport_diagnostics(network)['dns_error']
    assert transport.transport_diagnostics(network)['os_error_codes']==[-2]


def test_diagnostics_bound_cycles_and_reject_arbitrary_tls_reason():
    import ssl
    a=ValueError('private');b=RuntimeError('private');a.__cause__=b;b.__cause__=a
    assert transport.transport_diagnostics(a)['exception_types']==['ValueError','RuntimeError']
    start=ValueError();node=start
    for _ in range(20):node.__cause__=ValueError();node=node.__cause__
    assert len(transport.transport_diagnostics(start)['exception_types'])==8
    error=ssl.SSLError(1,'private');error.reason='PRIVATE /data/secret.pdf'
    assert transport.transport_diagnostics(error)['tls_reasons']==[]
