# SPDX-License-Identifier: AGPL-3.0-or-later
"""Supply the reviewed INEP intermediate, never a new trust anchor.

The server previously omitted an intermediate. This context still requires a
complete, valid chain to an existing certifi root, plus the requested hostname.
No AIA download, OS trust-store edit, HTTP downgrade or partial-chain trust.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
import ssl

import certifi

HOST = 'download.inep.gov.br'
INTERMEDIATE_DER_SHA256 = 'e10747d4da7bab09cba9952f019d3534cb9fba070bf13d8791b1699cd2ff59dd'
MAX_PEM_BYTES = 16 * 1024


def _context_with_intermediate(cafile: str, pem: bytes, expected_sha256: str) -> ssl.SSLContext:
    """Explicit roots are a test seam, not a user-configurable production input."""
    if not pem or len(pem) > MAX_PEM_BYTES:
        raise ValueError('official_tls_intermediate_size')
    try:
        text = pem.decode('ascii').strip()
        if (text.count('-----BEGIN CERTIFICATE-----') != 1
                or text.count('-----END CERTIFICATE-----') != 1
                or not text.startswith('-----BEGIN CERTIFICATE-----')
                or not text.endswith('-----END CERTIFICATE-----')):
            raise ValueError('not a single certificate')
        der = ssl.PEM_cert_to_DER_cert(text)
    except (ValueError, UnicodeError) as error:
        raise ValueError('official_tls_intermediate_format') from error
    if hashlib.sha256(der).hexdigest() != expected_sha256:
        raise ValueError('official_tls_intermediate_hash')
    context = ssl.create_default_context(cafile=cafile)
    # Python 3.13+ enables PARTIAL_CHAIN by default. Leaving that enabled would
    # make the added intermediate an anchor. A root must remain necessary.
    context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_verify_locations(cadata=text)
    return context


def inep_download_context(host: str) -> ssl.SSLContext:
    if host != HOST:
        raise ValueError('official_tls_host_not_selected')
    certificate = files('bdt').joinpath('certificates/rnp-icpedu-gr46-2025.pem')
    with certificate.open('rb') as stream:
        pem = stream.read(MAX_PEM_BYTES + 1)
    return _context_with_intermediate(certifi.where(), pem, INTERMEDIATE_DER_SHA256)


def policy_receipt() -> dict:
    """Public configuration, not a claim that a network handshake succeeded."""
    return {'profile': 'inep-reviewed-intermediate-v1', 'host': HOST,
            'intermediate_der_sha256': INTERMEDIATE_DER_SHA256,
            'roots': 'certifi', 'partial_chain_allowed': False,
            'hostname_required': True, 'global_trust_store_changed': False}
