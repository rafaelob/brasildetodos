"""Real in-memory TLS handshakes; ephemeral test CAs never ship in the product."""
import hashlib
from datetime import datetime, timedelta, timezone
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from bdt.education_tls import HOST, MAX_PEM_BYTES, _context_with_intermediate, inep_download_context, policy_receipt


def issue(name, key, issuer=None, issuer_key=None, *, ca=False, expired=False):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    issuer_key = issuer_key or key
    builder = (x509.CertificateBuilder().subject_name(subject)
               .issuer_name(issuer.subject if issuer else subject)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=3))
               .not_valid_after(now + timedelta(days=-1 if expired else 3))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
               .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
               .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                   key_encipherment=False, data_encipherment=False, key_agreement=False,
                   key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False), critical=True))
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def fingerprint(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


@pytest.fixture
def chain(tmp_path):
    key = lambda: ec.generate_private_key(ec.SECP256R1())
    root_key, middle_key, leaf_key, other_key = (key() for _ in range(4))
    root = issue('test root', root_key, ca=True)
    middle = issue('test intermediate', middle_key, root, root_key, ca=True)
    leaf = issue(HOST, leaf_key, middle, middle_key)
    other = issue('unrelated root', other_key, ca=True)
    roots = tmp_path / 'roots.pem'; roots.write_bytes(pem(root))
    wrong = tmp_path / 'unrelated.pem'; wrong.write_bytes(pem(other))
    keypath = tmp_path / 'leaf.key'
    keypath.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    def server(cert=leaf, full=False):
        path = tmp_path / 'server.pem'; path.write_bytes(pem(cert) + (pem(middle) if full else b''))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(path, keypath)
        return context
    return roots, wrong, middle, leaf, server, middle_key, leaf_key, root, root_key


def handshake(client_context, server_context, host=HOST):
    ci, co, si, so = (ssl.MemoryBIO() for _ in range(4))
    client = client_context.wrap_bio(ci, co, server_hostname=host)
    server = server_context.wrap_bio(si, so, server_side=True)
    cd = sd = False
    for _ in range(30):
        if not cd:
            try: client.do_handshake(); cd = True
            except ssl.SSLWantReadError: pass
        if co.pending: si.write(co.read())
        if not sd:
            try: server.do_handshake(); sd = True
            except ssl.SSLWantReadError: pass
        if so.pending: ci.write(so.read())
        if cd and sd:
            return client.getpeercert(binary_form=True)
    pytest.fail('TLS handshake did not complete')


def test_missing_intermediate_fails_then_complement_verifies_to_original_root(chain):
    roots, _, middle, leaf, server, *_ = chain
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(ssl.create_default_context(cafile=str(roots)), server())
    context = _context_with_intermediate(str(roots), pem(middle), fingerprint(middle))
    assert hashlib.sha256(handshake(context, server())).hexdigest() == fingerprint(leaf)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.verify_flags & ssl.VERIFY_X509_STRICT
    assert not context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN


def test_added_intermediate_is_not_trusted_without_its_root(chain):
    _, wrong, middle, _, server, *_ = chain
    context = _context_with_intermediate(str(wrong), pem(middle), fingerprint(middle))
    with pytest.raises(ssl.SSLCertVerificationError): handshake(context, server())


def test_wrong_hostname_still_fails(chain):
    roots, _, middle, _, server, *_ = chain
    context = _context_with_intermediate(str(roots), pem(middle), fingerprint(middle))
    with pytest.raises(ssl.SSLCertVerificationError): handshake(context, server(), 'wrong.example')


def test_expired_leaf_is_not_accepted(chain):
    roots, _, middle, _, server, middle_key, leaf_key, *_ = chain
    leaf = issue(HOST, leaf_key, middle, middle_key, expired=True)
    context = _context_with_intermediate(str(roots), pem(middle), fingerprint(middle))
    with pytest.raises(ssl.SSLCertVerificationError): handshake(context, server(leaf))


def test_expired_intermediate_is_not_accepted(chain):
    roots, _, _, _, server, middle_key, leaf_key, root, root_key = chain
    middle = issue('expired intermediate', middle_key, root, root_key, ca=True, expired=True)
    leaf = issue(HOST, leaf_key, middle, middle_key)
    context = _context_with_intermediate(str(roots), pem(middle), fingerprint(middle))
    with pytest.raises(ssl.SSLCertVerificationError): handshake(context, server(leaf))


def test_no_global_context_or_root_file_change(chain):
    roots, _, middle, _, server, *_ = chain
    original = roots.read_bytes()
    _context_with_intermediate(str(roots), pem(middle), fingerprint(middle))
    assert roots.read_bytes() == original
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(ssl.create_default_context(cafile=str(roots)), server())
    assert handshake(ssl.create_default_context(cafile=str(roots)), server(full=True))


@pytest.mark.parametrize('content,code', [(b'', 'size'), (b'x'*(MAX_PEM_BYTES+1), 'size'),
    (b'not a certificate', 'format'), (b'\xff', 'format')])
def test_invalid_complement_is_refused(chain, content, code):
    with pytest.raises(ValueError, match='official_tls_intermediate_'+code):
        _context_with_intermediate(str(chain[0]), content, '0'*64)


def test_hash_and_multiple_certificates_rejected(chain):
    roots, _, middle, *_ = chain
    with pytest.raises(ValueError, match='hash'):
        _context_with_intermediate(str(roots), pem(middle), '0'*64)
    with pytest.raises(ValueError, match='format'):
        _context_with_intermediate(str(roots), pem(middle)*2, fingerprint(middle))


@pytest.mark.parametrize('host', ['pncp.gov.br', 'evil.download.inep.gov.br', HOST+'.', HOST+':443', ''])
def test_production_context_is_restricted_to_download_host(host):
    with pytest.raises(ValueError, match='host_not_selected'): inep_download_context(host)


def test_packaged_actual_intermediate_and_receipt():
    context = inep_download_context(HOST)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert not context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2
    receipt = policy_receipt()
    assert receipt['host'] == HOST and not receipt['global_trust_store_changed']
    assert not receipt['partial_chain_allowed']

@pytest.mark.parametrize('host,custom', [(HOST, True), ('pncp.gov.br', False)])
def test_downloader_selects_context_only_for_reviewed_host(tmp_path, monkeypatch, host, custom):
    import httpx
    import bdt.ingest as ingest
    captured = []
    original = httpx.Client
    monkeypatch.setattr(ingest.socket, 'getaddrinfo', lambda *a, **k: [
        (2, 1, 6, '', ('8.8.8.8', 443))])
    def client(**kwargs):
        captured.append(kwargs)
        return original(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b'public bytes')), **kwargs)
    monkeypatch.setattr(ingest.httpx, 'Client', client)
    result = ingest.safe_download('https://'+host+'/reviewed', tmp_path/'data.bin')
    verify = captured[0]['verify']
    if custom:
        assert isinstance(verify, ssl.SSLContext)
        assert verify.check_hostname and verify.verify_mode == ssl.CERT_REQUIRED
        assert not verify.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
        assert result['tls']['handshake_verified'] and not result['tls']['partial_chain_allowed']
    else:
        assert verify is True and 'tls' not in result
    assert captured[0]['trust_env'] is False and captured[0]['follow_redirects'] is False
