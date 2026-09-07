import importlib
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'ops'))
    return importlib.import_module('inspect_inep_tls')


def test_certificate_parser_is_bounded_and_does_not_treat_missing_chain_as_trusted(module):
    assert module.certificate_metadata(b'no certificate; private error omitted')==[]
    with pytest.raises(ValueError,match='output_budget'):module.certificate_metadata(b'x'*(module.MAX_OUTPUT+1))
    with pytest.raises(ValueError,match='chain_budget'):module.certificate_metadata(b'-----BEGIN CERTIFICATE-----\na\n-----END CERTIFICATE-----\n'*9)


def test_probe_verifies_hostname_fixed_host_and_sends_no_http(module,monkeypatch):
    seen=[]
    def run(command,**kwargs):
        seen.append((command,kwargs))
        return SimpleNamespace(returncode=1,stdout=b'',stderr=b'verify error:num=20:private diagnostic')
    monkeypatch.setattr(module.subprocess,'run',run)
    result=module.probe('/trusted/test-only.pem')
    assert not result['tls_verified'] and result['verification_codes']==[20]
    assert result['presented_chain']==[] and not result['http_request_sent']
    args,opts=seen[0]
    assert args[args.index('-connect')+1]=='download.inep.gov.br:443'
    assert '-verify_return_error' in args and '-verify_hostname' in args
    assert opts['input']==b'' and opts['timeout']==30
    assert 'private' not in str(result)


def test_openssl_success_without_certificate_is_not_verification(module,monkeypatch):
    monkeypatch.setattr(module.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=b'Verify return code: 0',stderr=b''))
    assert not module.probe(None)['tls_verified']


def test_timeout_is_bounded(module,monkeypatch):
    def run(*a,**kw):raise module.subprocess.TimeoutExpired('fixed host',30)
    monkeypatch.setattr(module.subprocess,'run',run)
    assert module.probe(None)['status']=='timeout'


def test_metadata_parses_public_certificate_without_granting_trust(module):
    from datetime import datetime,timedelta,timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID,AuthorityInformationAccessOID
    key=ec.generate_private_key(ec.SECP256R1())
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'SYNTHETIC TEST CERTIFICATE')])
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(1).not_valid_before(datetime.now(timezone.utc)).not_valid_after(datetime.now(timezone.utc)+timedelta(days=1)).add_extension(x509.AuthorityInformationAccess([x509.AccessDescription(AuthorityInformationAccessOID.CA_ISSUERS,x509.UniformResourceIdentifier('https://example.org/synthetic-ca'))]),False).sign(key,hashes.SHA256())
    result=module.certificate_metadata(cert.public_bytes(serialization.Encoding.PEM))[0]
    assert result['trusted_by_observation_alone'] is False
    assert result['issuer_locations_untrusted']==['https://example.org/synthetic-ca']
    assert result['sha256']==cert.fingerprint(hashes.SHA256()).hex()
