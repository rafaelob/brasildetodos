# SPDX-License-Identifier: AGPL-3.0-or-later
"""Inspect the public TLS chain of the fixed INEP download host, not its data.

No application request is sent. A presented certificate is not a trusted CA.
This diagnostic never disables verification for the actual collection pipeline.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import certifi
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.x509.oid import AuthorityInformationAccessOID

HOST = 'download.inep.gov.br'
MAX_OUTPUT = 256 * 1024


def certificate_metadata(output: bytes) -> list[dict]:
    if len(output) > MAX_OUTPUT:
        raise ValueError('tls_diagnostic_output_budget')
    certificates = re.findall(rb'-----BEGIN CERTIFICATE-----\s+.*?-----END CERTIFICATE-----', output, re.S)
    if len(certificates) > 8:
        raise ValueError('tls_diagnostic_chain_budget')
    rows = []
    for pem in certificates:
        item = x509.load_pem_x509_certificate(pem)
        issuers = []
        try:
            for description in item.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value:
                location = description.access_location.value
                if (description.access_method == AuthorityInformationAccessOID.CA_ISSUERS
                    and isinstance(location, str) and len(location) <= 2048):
                    issuers.append(location)
        except x509.ExtensionNotFound:
            pass
        rows.append({'subject': item.subject.rfc4514_string(), 'issuer': item.issuer.rfc4514_string(),
                     'not_before': item.not_valid_before_utc.isoformat(),
                     'not_after': item.not_valid_after_utc.isoformat(),
                     'sha256': item.fingerprint(hashes.SHA256()).hex(),
                     'issuer_locations_untrusted': issuers,
                     'trusted_by_observation_alone': False})
    return rows


def probe(ca_file: str | None) -> dict:
    command = ['openssl', 's_client', '-connect', HOST + ':443', '-servername', HOST,
               '-verify_hostname', HOST, '-verify_return_error', '-showcerts']
    if ca_file:
        command.extend(['-CAfile', ca_file])
    try:
        result = subprocess.run(command, input=b'', capture_output=True, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'tls_verified': False, 'http_request_sent': False}
    output = result.stdout + result.stderr
    rows = certificate_metadata(output)
    codes = re.findall(rb'verify error:num=(\d+):', output)
    codes += re.findall(rb'Verify return code: (\d+)', output)
    unique = sorted({int(code) for code in codes})
    valid = result.returncode == 0 and bool(rows) and unique == [0]
    return {'status': 'verified' if valid else 'verification_failed', 'tls_verified': valid,
            'openssl_returncode': result.returncode, 'verification_codes': unique,
            'presented_chain': rows, 'http_request_sent': False,
            'raw_diagnostic_sha256': hashlib.sha256(output).hexdigest()}


def main(argv=None):
    from datetime import datetime, timezone
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        parser.error('destination_exists')
    report = {'schema': 'bdt.fixed-inep-tls-inspection.v1', 'host': HOST,
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'certifi_version': certifi.__version__,
              'certifi': probe(certifi.where()), 'system': probe(None),
              'trust_store_changed': False, 'collector_verification_disabled': False,
              'downloaded_dataset': False, 'issuer_locations_fetched': False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
