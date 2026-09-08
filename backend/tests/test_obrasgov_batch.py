# SPDX-License-Identifier: AGPL-3.0-or-later
import json
import pytest
from unittest.mock import patch, MagicMock

from bdt.domain import Source, now
from bdt.evidence import Resource
from bdt.obrasgov_batch import batch_ingest_obrasgov, fetch_obrasgov_projects
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import ResourceRevision
from bdt.storage import Database, Municipality


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / 'test_obras.db'
    db = Database(f'sqlite:///{db_path}')
    db.initialize()
    with db.session() as session:
        src = Source(dataset='ibge', record_id='1400100', url='https://example.org', snapshot_sha256='a'*64, collected_at=now()).model_dump()
        session.add(Municipality(id='1400100', name='Boa Vista', state='RR', source=src))
        session.commit()
    return db


def test_collection_plan_obrasgov_state():
    plan = collection_plan('obrasgov_projects', state='RR', page_size=50, max_pages=5)
    assert plan.parameters['uf_principal'] == 'RR'
    assert plan.page_size == 50

    with pytest.raises(ValueError, match='invalid_resource_state'):
        collection_plan('obrasgov_projects', state='INVALID')

    with pytest.raises(ValueError, match='invalid_pncp_parameters'):
        collection_plan('pncp_contracts', start='20260904', end='20260904', state='RR')


def test_batch_ingest_obrasgov_mocked(test_db):
    sample_response = {
        'total_items': 2,
        'total_pages': 1,
        'page_number': 1,
        'page_size': 10,
        'data': [
            {
                'id_projeto_investimento': '99001.14-01',
                'desc_nome': 'CONSTRUÇÃO DE CRECHE MUNICIPAL EM BOA VISTA',
                'situacao': 'Em Execução',
                'uf_principal': 'RR',
                'ano_cadastro': 2026,
                'dt_inicial_prevista': '2026-01-10',
                'dt_final_prevista': '2027-06-30',
                'investimentos_previstos': [
                    {'vl_investimento_previsto': 1500000.0, 'desc_nome_fonte_recurso': 'Federal'}
                ],
                'pins': [
                    {'pin': 'POINT(-60.781688 2.825457)', 'latitude': '2.825457', 'longitude': '.825457)'}
                ],
                'perc_execucao_fisica': 45.5,
                'dt_medicao': '2026-08-15',
                'cod_ibge': '1400100',
            },
            {
                'id_projeto_investimento': '99002.14-02',
                'desc_nome': 'REFORMA DE RODOVIA ESTADUAL',
                'situacao': 'Cadastrada',
                'uf_principal': 'RR',
                'ano_cadastro': 2026,
                'investimentos_previstos': [],
                'pins': [],
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(sample_response).encode('utf-8')
    mock_resp.__enter__.return_value = mock_resp

    with patch('urllib.request.urlopen', return_value=mock_resp):
        stats = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=False)

    assert stats['read'] == 2
    assert stats['created'] == 2
    assert stats['with_pins'] == 1
    assert stats['with_execution'] == 1
    assert stats['with_municipality'] == 1

    with test_db.session() as session:
        r1 = session.get(Resource, 'obrasgov_projects:99001.14-01')
        assert r1 is not None
        assert r1.municipality_id == '1400100'
        assert r1.payload['attributes']['territorial_basis'] == 'reviewed_project_geometry_municipality'
        assert r1.payload['attributes']['physical_execution_percentage'] == 45.5
        assert r1.payload['attributes']['last_measurement_on'] == '2026-08-15'
        assert len(r1.payload['attributes']['project_geometries']) == 1
        assert r1.payload['attributes']['latitude'] == 2.825457
        assert r1.payload['attributes']['longitude'] == -60.781688

        # Verify revision ledger
        revs = session.query(ResourceRevision).filter(ResourceRevision.resource_id == r1.id).all()
        assert len(revs) == 1
        assert revs[0].revision == 1

    # Idempotent second run
    mock_resp2 = MagicMock()
    mock_resp2.status = 200
    mock_resp2.read.return_value = json.dumps(sample_response).encode('utf-8')
    mock_resp2.__enter__.return_value = mock_resp2
    with patch('urllib.request.urlopen', return_value=mock_resp2):
        stats2 = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=False)

    assert stats2['read'] == 2
    assert stats2['created'] == 0
    assert stats2['unchanged'] == 2
