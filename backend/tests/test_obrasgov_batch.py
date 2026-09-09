# SPDX-License-Identifier: AGPL-3.0-or-later
import json
from urllib.parse import urlsplit

import httpx
import pytest

from bdt.domain import Source, now
from bdt.evidence import Resource
from bdt.obrasgov_batch import (
    DEFAULT_SAMPLE_STATES,
    OBRASGOV_HOST,
    assert_reviewed_obrasgov_url,
    batch_ingest_obrasgov,
    fetch_api_json,
    fetch_obrasgov_projects,
    fetch_project_geometries,
    reviewed_obrasgov_url,
)
from bdt.resource_profiles import collection_plan
from bdt.resource_sync import ResourceRevision
from bdt.storage import Database, Ingestion, Municipality, Place


def json_response(payload, status=200):
    return httpx.Response(
        status,
        content=json.dumps(payload, default=str).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / 'test_obras.db'
    db = Database(f'sqlite:///{db_path}')
    db.initialize()
    with db.session() as session:
        src = Source(dataset='ibge', record_id='1400100', url='https://example.org', snapshot_sha256='a'*64, collected_at=now()).model_dump()
        session.add(Municipality(id='1400100', name='Boa Vista', state='RR', source=src))
        session.add(Place(
            id='inep:14001890',
            kind='school',
            name='CONSTRUÇÃO DE CRECHE MUNICIPAL EM BOA VISTA',
            search_name='construcao de creche municipal em boa vista',
            municipality_id='1400100',
            state='RR',
            latitude=2.825457,
            longitude=-60.781688,
            dataset='inep',
            payload={'name': 'CONSTRUÇÃO DE CRECHE MUNICIPAL EM BOA VISTA'},
            fingerprint='b' * 64,
            updated_at=now(),
        ))
    return db


@pytest.fixture(autouse=True)
def http_guard(monkeypatch):
    original = httpx.Client
    state = {'handler': None, 'calls': []}

    def factory(**kwargs):
        state['calls'].append(kwargs)
        if state['handler'] is None:
            raise AssertionError('live HTTP is forbidden in obrasgov_batch tests')
        return original(transport=httpx.MockTransport(state['handler']), **kwargs)

    monkeypatch.setattr('bdt.obrasgov_batch.httpx.Client', factory)

    def install(handler):
        state['handler'] = handler
        return state

    return install, state


def sample_projects():
    return {
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


def projects_only_handler(payload):
    def handler(request: httpx.Request):
        host = request.url.host
        if host != OBRASGOV_HOST:
            raise AssertionError(f'non-allowlisted host {host}')
        if request.url.path.endswith('/projeto-investimento'):
            return json_response(payload)
        raise AssertionError(f'unexpected path {request.url.path}')
    return handler


def test_collection_plan_obrasgov_state():
    plan = collection_plan('obrasgov_projects', state='RR', page_size=50, max_pages=5)
    assert plan.parameters['uf_principal'] == 'RR'
    assert plan.page_size == 50

    with pytest.raises(ValueError, match='invalid_resource_state'):
        collection_plan('obrasgov_projects', state='INVALID')

    with pytest.raises(ValueError, match='invalid_pncp_parameters'):
        collection_plan('pncp_contracts', start='20260904', end='20260904', state='RR')


@pytest.mark.parametrize('url', [
    'http://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento',
    'https://evil.example/obras/projeto-investimento',
    'https://user:pass@api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento',
    'https://api-publica.obrasgov.gestao.gov.br:8443/obras/projeto-investimento',
    'https://pncp.gov.br/obras/projeto-investimento',
    'https://api-publica.obrasgov.gestao.gov.br/obras/../../../etc/passwd',
])
def test_reviewed_url_rejects_hosts_outside_obrasgov_https(url):
    with pytest.raises(ValueError, match='obrasgov_source_not_allowlisted'):
        assert_reviewed_obrasgov_url(url)


def test_reviewed_url_accepts_allowlisted_https_paths():
    url = 'https://api-publica.obrasgov.gestao.gov.br/obras/projeto-investimento?pagina=1'
    assert assert_reviewed_obrasgov_url(url) == url
    built = reviewed_obrasgov_url('/geometria', {'id_projeto_investimento': '99001.14-01'})
    parsed = urlsplit(built)
    assert parsed.hostname == OBRASGOV_HOST
    assert parsed.scheme == 'https'


def test_unknown_endpoint_is_rejected_without_http(http_guard):
    with pytest.raises(ValueError, match='obrasgov_endpoint_not_allowlisted'):
        fetch_api_json('/not-registered', {'pagina': 1})
    assert http_guard[1]['calls'] == []


def test_fetch_uses_httpx_without_redirects_or_trust_env(http_guard):
    install, state = http_guard
    install(projects_only_handler({'data': [], 'total_pages': 1, 'page_number': 1, 'total_items': 0}))
    payload = fetch_obrasgov_projects(state='RR', page=1, page_size=10)
    assert payload['data'] == []
    assert state['calls'][0]['follow_redirects'] is False
    assert state['calls'][0]['trust_env'] is False


def test_fetch_does_not_follow_redirect_off_allowlist(http_guard):
    install, _state = http_guard
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'https://evil.example/steal'})

    install(handler)
    with pytest.raises(ValueError, match='obrasgov_http_error_302'):
        fetch_obrasgov_projects(state='RR', page=1)
    assert len(seen) == 1
    assert 'evil.example' not in ''.join(seen)


def test_geometry_http_error_is_not_empty_success(http_guard):
    install, _state = http_guard
    install(lambda req: httpx.Response(500, content=b'{}'))
    with pytest.raises(ValueError, match='obrasgov_http_error_500'):
        fetch_project_geometries('99001.14-01')


def test_geometry_schema_change_is_not_empty_success(http_guard):
    install, _state = http_guard
    install(lambda req: json_response({'total_items': 0}))
    with pytest.raises(ValueError, match='obrasgov_geometry_schema_changed'):
        fetch_project_geometries('99001.14-01')


def test_batch_ingest_obrasgov_mocked(test_db, http_guard):
    install, _state = http_guard
    install(projects_only_handler(sample_projects()))
    stats = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=False, delay_seconds=0)

    assert stats['read'] == 2
    assert stats['created'] == 2
    assert stats['with_pins'] == 1
    assert stats['with_execution'] == 1
    assert stats['with_municipality'] == 1
    assert stats['pages_fetched'] == 1
    assert stats['national_catalog_certified'] is False

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
        assert r1.payload['attributes']['facility_id'] is None
        revs = session.query(ResourceRevision).filter(ResourceRevision.resource_id == r1.id).all()
        assert len(revs) == 1
        assert revs[0].revision == 1
        load = session.query(Ingestion).filter(Ingestion.dataset == 'obrasgov_projects').one()
        assert load.source['national_catalog_certified'] is False
        assert load.source['pages_fetched'] == 1
        assert load.status == 'completed_file'

    stats2 = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=False, delay_seconds=0)
    assert stats2['read'] == 2
    assert stats2['created'] == 0
    assert stats2['unchanged'] == 2
    assert stats2['national_catalog_certified'] is False


def test_school_name_does_not_attach_facility_or_pin(test_db, http_guard):
    install, _state = http_guard
    payload = {
        'total_items': 1,
        'total_pages': 1,
        'page_number': 1,
        'page_size': 10,
        'data': [{
            'id_projeto_investimento': 'name-only-01',
            'desc_nome': 'CONSTRUÇÃO DE CRECHE MUNICIPAL EM BOA VISTA',
            'situacao': 'Em Execução',
            'uf_principal': 'RR',
            'ano_cadastro': 2026,
            'investimentos_previstos': [],
            'endereco_comprador': 'Rua das Escolas, 100, Boa Vista-RR',
        }],
    }
    install(projects_only_handler(payload))
    stats = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=False, delay_seconds=0)
    assert stats['created'] == 1
    assert stats['with_pins'] == 0
    with test_db.session() as session:
        row = session.get(Resource, 'obrasgov_projects:name-only-01')
        assert row is not None
        assert row.payload['attributes']['facility_id'] is None
        assert row.municipality_id is None
        assert 'latitude' not in row.payload['attributes']
        assert 'longitude' not in row.payload['attributes']
        assert not row.payload['attributes'].get('project_geometries')
        assert row.payload['attributes']['territorial_basis'] == 'state_only_municipality_unresolved'


def test_geometry_fetch_failure_is_partial_not_empty_success(test_db, http_guard):
    install, _state = http_guard
    payload = {
        'total_items': 1,
        'total_pages': 1,
        'page_number': 1,
        'page_size': 10,
        'data': [{
            'id_projeto_investimento': 'geom-fail-01',
            'desc_nome': 'OBRA SEM PIN NA PAGINA',
            'situacao': 'Em Execução',
            'uf_principal': 'RR',
            'ano_cadastro': 2026,
            'investimentos_previstos': [],
        }],
    }

    def handler(request: httpx.Request):
        assert request.url.host == OBRASGOV_HOST
        if request.url.path.endswith('/projeto-investimento'):
            return json_response(payload)
        if request.url.path.endswith('/geometria'):
            return httpx.Response(500, content=b'{"error":"upstream"}')
        if request.url.path.endswith('/execucao-fisica'):
            return json_response({'data': []})
        raise AssertionError(request.url.path)

    install(handler)
    stats = batch_ingest_obrasgov(test_db, states=['RR'], max_pages_per_state=1, enrich_details=True, delay_seconds=0)
    assert stats['geometry_errors'] == 1
    assert stats['errors'] >= 1
    assert stats['created'] == 1
    assert stats['with_pins'] == 0
    assert stats['national_catalog_certified'] is False
    with test_db.session() as session:
        row = session.get(Resource, 'obrasgov_projects:geom-fail-01')
        assert row is not None
        assert not row.payload['attributes'].get('project_geometries')
        load = session.query(Ingestion).filter(Ingestion.dataset == 'obrasgov_projects').one()
        assert load.status == 'partial_quality'
        assert load.counts['geometry_errors'] == 1


def test_default_bounds_are_sample_not_census(test_db, http_guard):
    install, _state = http_guard
    seen_ufs = []

    def handler(request: httpx.Request):
        assert request.url.host == OBRASGOV_HOST
        seen_ufs.append(request.url.params.get('uf_principal'))
        return json_response({'data': [], 'total_pages': 1, 'page_number': 1, 'total_items': 0})

    install(handler)
    stats = batch_ingest_obrasgov(test_db, max_pages_per_state=1, enrich_details=False, delay_seconds=0)
    assert stats['national_catalog_certified'] is False
    assert stats['pages_fetched'] == len(DEFAULT_SAMPLE_STATES)
    assert stats['states'] == list(DEFAULT_SAMPLE_STATES)
    assert len(stats['states']) != 27
    assert seen_ufs == list(DEFAULT_SAMPLE_STATES)
