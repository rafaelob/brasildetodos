# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import transferegov_financial_download_and_ingest as tg_ops


def _main(argv):
    try:
        return tg_ops.main(argv)
    except SystemExit as exc:
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, ValueError):
            raise cause from exc
        raise


def test_ingest_without_database_exits_with_required_error(capsys):
    with pytest.raises(SystemExit) as exc:
        tg_ops.main(['--mode', 'ingest'])
    assert exc.value.code == 2
    assert 'database_required_for_ingest' in capsys.readouterr().err


def test_ingest_refuses_database_named_like_live_app(tmp_path, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError('live_http_forbidden')

    monkeypatch.setattr(tg_ops, 'download_all', forbidden)
    db = tmp_path / 'bdt.db'
    with pytest.raises(ValueError, match='refuse_live_app_database'):
        _main(['--mode', 'ingest', '--database', str(db), '--downloads', str(tmp_path)])
    assert not db.exists()
