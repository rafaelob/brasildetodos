# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import transferegov_financial_download_and_ingest as tg_ops
from test_transferegov_finance import _cached_downloads, _operator_finance_sqlite


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


def test_ingest_cli_writes_output_json_for_new_sqlite(tmp_path, source, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError('live_http_forbidden')

    monkeypatch.setattr(tg_ops, 'download_retry', forbidden)
    db = _operator_finance_sqlite(tmp_path, source)
    downloads = _cached_downloads(tmp_path)
    output = tmp_path / 'ingest-receipt.json'
    assert db.name != 'bdt.db'
    assert output.name != 'bdt.db'
    _main([
        '--mode', 'ingest',
        '--database', str(db),
        '--downloads', str(downloads),
        '--output', str(output),
    ])
    assert output.is_file()
    assert str(output).replace('\\', '/') != 'data/bdt.db'
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['national_catalog_certified'] is False
    assert report['financial_total_computed'] is False
    assert report['database'] != 'data/bdt.db'
    assert Path(report['database']).name != 'bdt.db'
    archives = report['archives']
    assert archives
    for archive in archives:
        assert isinstance(archive.get('url'), str) and archive['url']
        assert isinstance(archive['bytes'], int) and archive['bytes'] > 0
        assert isinstance(archive['sha256'], str) and len(archive['sha256']) == 64
        int(archive['sha256'], 16)
