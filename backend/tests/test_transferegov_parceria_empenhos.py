"""Synthetic tests for the bounded Transferegov Parcerias commitment connector."""
import hashlib
import json

import pytest

import bdt.transferegov_parceria_empenhos as module
from bdt.storage import Database


def item(identifier=17292):
    return {'id_empenho_parceria': identifier, 'id_parceria': 38059,
            'nr_empenho': 504312, 'cd_ug_emitente': 257001, 'aa_empenho': 2025,
            'in_situacao_siafi': 'Empenho enviado', 'data_emissao': '2025-11-14T00:00:00',
            'nome_favorecido': 'Synthetic entity', 'identificacao_favorecido': '00000000000100',
            'valor_empenho': 299977.0, 'valor_operacao_empenho': 299977.0}


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
    module.initialize_transferegov_parceria_empenhos(database)
    first = module.import_collection(database, folder)
    second = module.import_collection(database, folder)
    assert first['counts'] == {'read': 1, 'created': 1, 'updated': 0, 'unchanged': 0}
    assert second['counts'] == {'read': 1, 'created': 0, 'updated': 0, 'unchanged': 1}
    with database.session() as session:
        row = session.get(module.TransferegovParceriaEmpenho, hashlib.sha256(b'17292').hexdigest())
        assert row.id_parceria == '38059' and row.valor_empenho == 299977.0
        assert row.payload['id_empenho_parceria'] == 17292
    database.engine.dispose()


def test_folder_is_never_reused(tmp_path):
    folder = tmp_path / 'collection'
    (folder / 'pages').mkdir(parents=True)
    with pytest.raises(ValueError, match='folder_not_empty'):
        module.collect(folder)
