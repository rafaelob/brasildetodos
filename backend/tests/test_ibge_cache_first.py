# SPDX-License-Identifier: AGPL-3.0-or-later
"""IBGE municipality JSON is HTTPS-allowlisted; CNEFE FTP is not."""
from urllib.parse import urlsplit

import pytest

from bdt.ingest import HOSTS, IBGE_URL, safe_download


def test_ibge_municipality_json_is_https_allowlisted():
    parsed = urlsplit(IBGE_URL)
    assert parsed.scheme == 'https'
    assert parsed.hostname == 'servicodados.ibge.gov.br'
    assert parsed.hostname in HOSTS


def test_cnefe_ftp_is_rejected_by_shipped_allowlist(tmp_path):
    assert 'ftp.ibge.gov.br' not in HOSTS
    with pytest.raises(ValueError, match='allowlist'):
        safe_download('https://ftp.ibge.gov.br/foo', tmp_path / 'x')
