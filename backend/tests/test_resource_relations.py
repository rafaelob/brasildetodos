"""Synthetic tests for read-only official-row consumers; no network is used."""
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from bdt.api import create_app, password_hash
from bdt.domain import PlaceInput, Source, now
from bdt.evidence import Resource
from bdt.pdde import PddePayment
from bdt.pncp_documents import PncpContractDocument
from bdt.storage import Municipality, User, upsert_place
from bdt.transferegov_especiais import TransferegovEspeciaisEmpenho, _item_row
from test_transferegov_especiais import make_item

PASSWORD = 'test-only-reviewer-password'
HEAD = {'x-bdt-client': 'web'}


def source(dataset):
    return Source(dataset=dataset, url='https://example.org/synthetic', record_id='1',
                  reference_date='2026', collected_at=now(), snapshot_sha256='a' * 64)


@pytest.fixture
def relations(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'relations.db'}", testing=True)
    database = app.state.database
    territory = source('synthetic-territory')
    place = PlaceInput(id='test:school', kind='school', name='Synthetic school',
                       municipality_id='1234567', state='BA', source=territory)
    with database.session() as session:
        session.add(User(username='reviewer', password_hash=password_hash(PASSWORD), role='reviewer'))
        session.add(Municipality(id='1234567', name='Synthetic town', state='BA',
                                 source=territory.model_dump()))
        upsert_place(session, place)
        session.add(Resource(
            id='transferegov_special_plans:101', kind='instrument', title='Synthetic plan',
            payload={'id': 'transferegov_special_plans:101', 'title': 'Synthetic plan'},
            source={'dataset': 'transferegov_special_plans', 'record_id': '101',
                    'url': 'https://example.org/plan', 'reference_date': '2026'}))
        empenho = _item_row(make_item(id_plano_acao=101), {
            'url': 'https://example.org/empenhos', 'sha256': 'b' * 64,
            'collected_at': now(), 'reference_date': None})
        session.add(TransferegovEspeciaisEmpenho(**empenho))
        second = _item_row(make_item(empenho_id=3, id_plano_acao=101), {
            'url': 'https://example.org/empenhos', 'sha256': 'b' * 64,
            'collected_at': now(), 'reference_date': None})
        session.add(TransferegovEspeciaisEmpenho(**second))
        other = _item_row(make_item(empenho_id=2, id_plano_acao=202), {
            'url': 'https://example.org/empenhos', 'sha256': 'b' * 64,
            'collected_at': now(), 'reference_date': None})
        session.add(TransferegovEspeciaisEmpenho(**other))
        session.add(PddePayment(
            key='pdde-1', product_id=66, exercise='2026', state='BA',
            municipality_name='Synthetic town', municipality_id='1234567',
            school_code='12345678', school_place_id='test:school',
            recipient_cnpj='00.000.000/0001-00', recipient_name='Synthetic executing unit',
            values={'valor_total': '100,00'}, payload={},
            source={'url': 'https://example.org/pdde', 'sha256': 'c' * 64}))
        control = '12345678000199-2-000001/2026'
        session.add(Resource(
            id='pncp_contracts:' + control, kind='contract', title='Synthetic PNCP contract',
            payload={'id': 'pncp_contracts:' + control},
            source={'dataset': 'pncp_contracts', 'record_id': control,
                    'url': 'https://pncp.gov.br/api/consulta/v1/contratos'}))
        session.add(PncpContractDocument(
            id='pncp-doc:12345678000199:2026:1:1', cnpj='12345678000199',
            ano_contract=2026, sequencial_contract=1, sequencial_document=1,
            title='Synthetic official document', document_type='Contrato',
            published_at='2026-09-04T00:00:00Z',
            source_url='https://pncp.gov.br/app/contratos/12345678000199/2026/1',
            snapshot_sha256='d' * 64, byte_size=1234, status='present', revision=1,
            first_seen_at=now(), last_seen_at=now(), metadata_json={}))
    client = TestClient(app)
    response = client.post('/api/auth/login', headers=HEAD, json={'username': 'reviewer', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    yield app, client, database
    database.engine.dispose()


def test_special_plan_consumer_returns_only_exact_rows_and_no_total(relations):
    _, client, _ = relations
    response = client.get('/api/workbench/resources/' + quote(
        'transferegov_special_plans:101', safe='') + '/empenhos')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['plan_id'] == 101 and body['count'] == 2 and body['aggregate'] is None
    assert [row['empenho_id'] for row in body['items']] == [1, 3]
    assert body['items'][0]['valor_empenho_publicado'] == 1234.56
    assert body['items'][0]['source']['url'] == 'https://example.org/empenhos'
    assert body['total_rows'] == 2 and body['has_more'] is False
    assert 'total' not in body and 'sum' not in body
    page = client.get('/api/workbench/resources/' + quote(
        'transferegov_special_plans:101', safe='') + '/empenhos?limit=1')
    assert page.json()['count'] == 1 and page.json()['has_more'] is True
    assert page.json()['total_rows'] == 2


def test_special_plan_consumer_rejects_non_plan_and_anonymous(relations):
    app, client, database = relations
    with database.session() as session:
        session.add(Resource(id='pncp_contracts:1', kind='contract', title='Synthetic contract',
                             payload={'id': 'pncp_contracts:1'}, source={'dataset': 'pncp_contracts'}))
    anonymous = TestClient(app)
    assert anonymous.get('/api/workbench/resources/transferegov_special_plans%3A101/empenhos').status_code == 401
    assert client.get('/api/workbench/resources/pncp_contracts%3A1/empenhos').status_code == 404
    assert client.get('/api/workbench/resources/transferegov_special_plans%3A999/empenhos').status_code == 404


def test_pncp_document_consumer_links_contract_metadata_without_bytes(relations):
    _, client, _ = relations
    control = '12345678000199-2-000001/2026'
    response = client.get('/api/workbench/resources/' + quote(
        'pncp_contracts:' + control, safe='') + '/documentos')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['count'] == 1 and body['total_rows'] == 1
    assert body['contract'] == {'cnpj': '12345678000199', 'ano': 2026, 'sequencial': 1}
    assert body['items'][0]['snapshot_sha256'] == 'd' * 64
    assert body['items'][0]['source_url'].startswith('https://pncp.gov.br/')
    assert body['publication_allowed'] is False and body['review_required'] is True
    assert 'content' not in body['items'][0] and 'bytes' not in body['items'][0]


def test_pncp_document_consumer_rejects_non_contract(relations):
    _, client, _ = relations
    response = client.get('/api/workbench/resources/' + quote(
        'transferegov_special_plans:101', safe='') + '/documentos')
    assert response.status_code == 404


def test_pdde_consumer_returns_exact_values_for_school_only(relations):
    _, client, _ = relations
    response = client.get('/api/workbench/places/test%3Aschool/pdde')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['count'] == 1 and body['aggregate'] is None
    assert body['items'][0]['values'] == {'valor_total': '100,00'}
    assert body['items'][0]['recipient_name'] == 'Synthetic executing unit'
    assert 'total' not in body and 'sum' not in body
    missing = client.get('/api/workbench/places/test%3Amissing/pdde')
    assert missing.status_code == 404
