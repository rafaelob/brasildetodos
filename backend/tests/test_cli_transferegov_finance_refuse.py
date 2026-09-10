# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

import pytest
from bdt.cli import main

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ops.transferegov_financial_download_and_ingest as tg_ops


def test_import_transferegov_finance_refuses_default_live_app_database(monkeypatch, tmp_path):
    def forbidden(*_a, **_k):
        raise AssertionError('live_http_forbidden')

    monkeypatch.setattr(tg_ops, 'download_all', forbidden)
    monkeypatch.delenv('BDT_DATABASE_URL', raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', ['bdt', 'import-transferegov-finance'])
    with pytest.raises(ValueError, match='refuse_live_app_database'):
        main()
    assert not (tmp_path / 'data' / 'bdt.db').exists()
