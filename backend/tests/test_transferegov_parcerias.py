"""Synthetic tests for the bounded Transferegov Parcerias connector."""
import hashlib
import json

import pytest

import bdt.transferegov_parcerias as module
from bdt.domain import now
from bdt.storage import Database


def item(identifier=37840):
    return {'id_parceria': identifier, 'cd_parceria': 202500037062,
            'nu_externo': '36000715978202500', 'id_proposta': 37916,
            'in_situacao_parceria': 'Aprovada', 'tp_origem': 'Sistema Externo',
            'publicacoes_parceria': []}


def test_collect_and_import_are_bounded_and_idempotent(tmp_path, monkeypatch):
    def loader(url, target, max_bytes=0):
        payload = {'data': [item()], 'total_pages': 2, 'total_items': 2,
                   'page_number': 1, 'page_size': 200}
        raw = json.dumps(payload).encode()
        target.write_bytes(raw)
        return {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    monkeypatch.setattr(module, 'safe_download', loader)
    folder = tmp_path / 'collection'
    report = module.collect(folder, max_pages=1)
    assert report['status'] == 'bounded' and report['total_items_declared'] == 2

    database = Database(f"sqlite:///{tmp_path / 'app.db'}")
    database.initialize()
    module.initialize_transferegov_parcerias(database)
    first = module.import_collection(database, folder)
    second = module.import_collection(database, folder)
    assert first['counts'] == {'read': 1, 'created': 1, 'updated': 0, 'unchanged': 0}
    assert second['counts'] == {'read': 1, 'created': 0, 'updated': 0, 'unchanged': 1}
    with database.session() as session:
        row = session.get(module.TransferegovParceria, '37840')
        assert row.payload['id_parceria'] == 37840 and row.payload['in_situacao_parceria'] == 'Aprovada'
        assert row.source['sha256'] == report['pages'][0]['sha256']
    database.engine.dispose()


def test_folder_is_never_reused(tmp_path, monkeypatch):
    folder = tmp_path / 'collection'
    folder.mkdir()
    (folder / 'keep.txt').write_text('existing')
    monkeypatch.setattr(module, 'safe_download', lambda *args, **kwargs: None)
    # An unrelated file does not conflict; the connector owns only its markers.
    (folder / 'pages').mkdir()
    with pytest.raises(ValueError, match='folder_not_empty'):
        module.collect(folder)
