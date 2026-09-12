# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded Obrasgov collector on resource_sync rails.

A finished page window is not a national census. Geometry and execution are
joined only by id_projeto_investimento. School names and buyer addresses never
become pins or facility_id. HTTP stays on https + ingest.HOSTS.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .domain import Source, digest, now
from .evidence import Resource
from .ingest import HOSTS
from .json_codec import decode
from .resource_profiles import STATES, normalize_resource
from .resource_sync import ResourceRevision, changed_fields, initialize_resource_versions, semantic
from .storage import Database, Ingestion, Municipality

logger = logging.getLogger('bdt.obrasgov_batch')

OBRASGOV_HOST = 'api-publica.obrasgov.gestao.gov.br'
OBRASGOV_BASE = f'https://{OBRASGOV_HOST}/obras'
USER_AGENT = 'BrasilDeTodos/0.3 (+https://github.com/rafaelob/brasildetodos)'
MAX_JSON_BYTES = 8 * 1024 * 1024
DEFAULT_SAMPLE_STATES = ('RR', 'AP', 'AC', 'SE', 'RO')
ALLOWED_ENDPOINTS = frozenset({
    '/projeto-investimento',
    '/geometria',
    '/execucao-fisica',
})
ALLOWED_PATHS = frozenset(f'/obras{endpoint}' for endpoint in ALLOWED_ENDPOINTS)


def payload_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def assert_reviewed_obrasgov_url(url: str) -> str:
    """Reject anything that is not https to the reviewed Obrasgov host/path."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https'
            or parsed.hostname not in HOSTS
            or parsed.hostname != OBRASGOV_HOST
            or parsed.port not in {None, 443}
            or parsed.username or parsed.password
            or parsed.path not in ALLOWED_PATHS):
        raise ValueError('obrasgov_source_not_allowlisted')
    return url


def reviewed_obrasgov_url(endpoint: str, params: dict[str, Any]) -> str:
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ValueError('obrasgov_endpoint_not_allowlisted')
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f'{OBRASGOV_BASE}{endpoint}?{query}' if query else f'{OBRASGOV_BASE}{endpoint}'
    return assert_reviewed_obrasgov_url(url)


def _http_client(timeout: int) -> httpx.Client:
    connect = timeout if timeout < 15 else 15
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=connect),
        follow_redirects=False,
        trust_env=False,
        headers={'User-Agent': USER_AGENT},
    )


def fetch_api_json(endpoint: str, params: dict[str, Any], timeout: int = 30,
                   *, client: httpx.Client | None = None) -> dict:
    """HTTPS GET of a reviewed Obrasgov path. Never urllib, never other hosts."""
    url = reviewed_obrasgov_url(endpoint, params)
    owns = client is None
    http = client or _http_client(timeout)
    try:
        response = http.get(url, timeout=timeout)
        if response.status_code != 200:
            raise ValueError(f'obrasgov_http_error_{response.status_code}')
        declared = response.headers.get('content-length')
        if declared and declared.isdigit() and int(declared) > MAX_JSON_BYTES:
            raise ValueError('obrasgov_response_byte_budget')
        raw = response.content
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError('obrasgov_response_byte_budget')
        if not raw:
            raise ValueError('obrasgov_empty_response')
        try:
            payload = decode(raw, parse_float=Decimal)
        except UnicodeDecodeError as exc:
            raise ValueError('obrasgov_response_not_utf8') from exc
        except json.JSONDecodeError as exc:
            raise ValueError('obrasgov_invalid_json') from exc
        if not isinstance(payload, dict):
            raise ValueError('obrasgov_response_schema_changed')
        return payload
    except httpx.HTTPError as exc:
        raise ValueError('obrasgov_http_transport_error') from exc
    finally:
        if owns:
            http.close()


def fetch_obrasgov_projects(state: str | None = None, year: int | None = None,
                            page: int = 1, page_size: int = 100, timeout: int = 30,
                            *, client: httpx.Client | None = None) -> dict:
    """Fetch a page of investment projects from Obrasgov."""
    params: dict[str, Any] = {'pagina': page, 'tamanho_da_pagina': page_size}
    if state:
        if state not in STATES:
            raise ValueError('invalid_project_state')
        params['uf_principal'] = state
    if year:
        params['ano_cadastro'] = year
    payload = fetch_api_json('/projeto-investimento', params, timeout=timeout, client=client)
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise ValueError('obrasgov_projects_schema_changed')
    return payload


def _rows_for_project(endpoint: str, project_id: str, *, schema_error: str,
                      timeout: int, client: httpx.Client | None) -> list[dict]:
    pid = str(project_id or '').strip()
    if not pid:
        raise ValueError('obrasgov_missing_project_id')
    payload = fetch_api_json(endpoint, {'id_projeto_investimento': pid}, timeout=timeout, client=client)
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise ValueError(schema_error)
    return rows


def fetch_project_geometries(project_id: str, timeout: int = 15,
                             *, client: httpx.Client | None = None) -> list[dict]:
    """Official geometries for one project. Transport/schema failures raise."""
    return _rows_for_project(
        '/geometria', project_id, schema_error='obrasgov_geometry_schema_changed',
        timeout=timeout, client=client,
    )


def fetch_project_execution(project_id: str, timeout: int = 15,
                            *, client: httpx.Client | None = None) -> list[dict]:
    """Official physical execution for one project. Transport/schema failures raise."""
    return _rows_for_project(
        '/execucao-fisica', project_id, schema_error='obrasgov_execution_schema_changed',
        timeout=timeout, client=client,
    )


def _collect_by_project(fetch, project_ids: list[str], *, client: httpx.Client,
                        timeout: int) -> tuple[dict[str, list], list[str], dict[str, str]]:
    found: dict[str, list] = {}
    failed: list[str] = []
    hashes: dict[str, str] = {}
    for pid in project_ids:
        try:
            rows = fetch(pid, timeout=timeout, client=client)
        except (ValueError, httpx.HTTPError) as exc:
            failed.append(pid)
            logger.warning(
                'obrasgov_collector_failed project_id=%s collector=%s error_type=%s',
                pid, getattr(fetch, '__name__', 'collector'), type(exc).__name__,
            )
            continue
        found[pid] = rows
        hashes[pid] = payload_sha256(rows)
    return found, failed, hashes


def _merge_geometry(proj: dict, pid: str, geom_map: dict[str, list], failed: set[str]) -> None:
    if pid in failed:
        return
    geoms = geom_map.get(pid) or []
    if not geoms:
        return
    if not proj.get('cod_ibge'):
        for row in geoms:
            if isinstance(row, dict) and row.get('cod_ibge'):
                proj['cod_ibge'] = row['cod_ibge']
                break
    if not proj.get('pins'):
        proj['pins'] = geoms


def _merge_execution(proj: dict, pid: str, exec_map: dict[str, list], failed: set[str]) -> None:
    if pid in failed:
        return
    execs = exec_map.get(pid) or []
    if not execs or not isinstance(execs[0], dict):
        return
    first = execs[0]
    if first.get('percentual_execucao_fisica') is not None:
        proj['percentual_execucao_fisica'] = first['percentual_execucao_fisica']
    if first.get('dt_atualizacao_execucao'):
        proj['dt_atualizacao_execucao'] = first['dt_atualizacao_execucao']


def _upsert_resource(session, resource_input, stats: dict) -> None:
    if resource_input.attributes.get('facility_id') is not None:
        stats['errors'] += 1
        logger.warning('obrasgov_facility_link_forbidden resource_id=%s', resource_input.id)
        return
    payload = resource_input.model_dump(mode='json')
    fingerprint = digest(semantic(payload))
    existing = session.scalar(select(Resource).where(Resource.id == resource_input.id))
    last_rev = session.scalar(
        select(ResourceRevision).where(ResourceRevision.resource_id == resource_input.id)
        .order_by(ResourceRevision.revision.desc()).limit(1)
    )
    nested = session.begin_nested()
    try:
        if existing is not None:
            if last_rev and last_rev.fingerprint == fingerprint:
                nested.commit()
                stats['unchanged'] += 1
                return
            version = (last_rev.revision + 1) if last_rev else 1
            fields = changed_fields(existing.payload, payload) if last_rev else ['updated']
            existing.title = resource_input.title
            existing.kind = resource_input.kind
            existing.municipality_id = resource_input.municipality_id
            existing.payload = payload
            existing.source = payload['source']
            session.add(ResourceRevision(
                resource_id=resource_input.id,
                revision=version,
                fingerprint=fingerprint,
                payload=payload,
                observed_at=now(),
                changed_fields=fields,
            ))
            outcome = 'updated'
        else:
            session.add(Resource(
                id=resource_input.id,
                kind=resource_input.kind,
                municipality_id=resource_input.municipality_id,
                title=resource_input.title,
                payload=payload,
                source=payload['source'],
            ))
            session.add(ResourceRevision(
                resource_id=resource_input.id,
                revision=1,
                fingerprint=fingerprint,
                payload=payload,
                observed_at=now(),
                changed_fields=['initial_import'],
            ))
            outcome = 'created'
        session.flush()
        nested.commit()
    except IntegrityError:
        nested.rollback()
        stats['errors'] += 1
        logger.warning('obrasgov_resource_conflict resource_id=%s', resource_input.id)
        return
    stats[outcome] += 1


def batch_ingest_obrasgov(database: Database, *, states: list[str] | None = None,
                           year: int | None = None, max_pages_per_state: int = 2,
                           page_size: int = 100, enrich_details: bool = True,
                           delay_seconds: float = 0.2) -> dict:
    """Ingest a bounded Obrasgov page window into the resource ledger.

    Defaults are a sample of UFs and pages, never a Brazil census. Geometry
    and execution HTTP failures are counted; they are not stored as empty
    success. facility_id stays unset.
    """
    initialize_resource_versions(database)
    if not 1 <= max_pages_per_state <= 100:
        raise ValueError('invalid_obrasgov_page_bound')
    if not 1 <= page_size <= 200:
        raise ValueError('invalid_obrasgov_page_size')
    target_states = list(states) if states is not None else list(DEFAULT_SAMPLE_STATES)
    for state in target_states:
        if state not in STATES:
            raise ValueError('invalid_project_state')
    stats = {
        'started_at': now(),
        'states': target_states,
        'read': 0,
        'created': 0,
        'updated': 0,
        'unchanged': 0,
        'with_pins': 0,
        'with_execution': 0,
        'with_municipality': 0,
        'errors': 0,
        'geometry_errors': 0,
        'execution_errors': 0,
        'pages_fetched': 0,
        'national_catalog_certified': False,
        'max_pages_per_state': max_pages_per_state,
        'page_size': page_size,
    }

    with database.session() as session:
        territories = {row.id: (row.name, row.state) for row in session.scalars(select(Municipality))}

    with _http_client(30) as client:
        for state in target_states:
            for page_num in range(1, max_pages_per_state + 1):
                if page_num > 1 and delay_seconds:
                    time.sleep(delay_seconds)
                try:
                    response = fetch_obrasgov_projects(
                        state=state, year=year, page=page_num, page_size=page_size, client=client,
                    )
                except (ValueError, httpx.HTTPError) as exc:
                    stats['errors'] += 1
                    logger.warning(
                        'obrasgov_page_fetch_failed state=%s page=%s error_type=%s',
                        state, page_num, type(exc).__name__,
                    )
                    break

                stats['pages_fetched'] += 1
                projects = response.get('data')
                if not isinstance(projects, list):
                    stats['errors'] += 1
                    logger.warning('obrasgov_page_schema_changed state=%s page=%s', state, page_num)
                    break
                if not projects:
                    break

                pids = [str(p.get('id_projeto_investimento')) for p in projects if p.get('id_projeto_investimento')]
                geom_map: dict[str, list] = {}
                exec_map: dict[str, list] = {}
                geom_failed: set[str] = set()
                exec_failed: set[str] = set()
                if enrich_details and pids:
                    geom_map, geom_fail_list, _geom_hashes = _collect_by_project(
                        fetch_project_geometries, pids, client=client, timeout=15,
                    )
                    exec_map, exec_fail_list, _exec_hashes = _collect_by_project(
                        fetch_project_execution, pids, client=client, timeout=15,
                    )
                    geom_failed = set(geom_fail_list)
                    exec_failed = set(exec_fail_list)
                    stats['geometry_errors'] += len(geom_failed)
                    stats['execution_errors'] += len(exec_failed)
                    stats['errors'] += len(geom_failed) + len(exec_failed)

                try:
                    with database.session() as session:
                        for proj in projects:
                            if not isinstance(proj, dict):
                                stats['errors'] += 1
                                continue
                            stats['read'] += 1
                            pid = str(proj.get('id_projeto_investimento') or '')
                            if not pid:
                                continue
                            if enrich_details:
                                _merge_geometry(proj, pid, geom_map, geom_failed)
                                _merge_execution(proj, pid, exec_map, exec_failed)
                            src_url = f'{OBRASGOV_BASE}/projeto-investimento?id_projeto_investimento={pid}'
                            src = Source(
                                dataset='obrasgov_projects',
                                record_id=pid,
                                url=src_url,
                                reference_date=str(proj.get('ano_cadastro')) if proj.get('ano_cadastro') else None,
                                collected_at=now(),
                                snapshot_sha256=payload_sha256(proj),
                            )
                            try:
                                resource_input = normalize_resource('obrasgov_projects', proj, src, territories)
                            except Exception as norm_err:
                                stats['errors'] += 1
                                logger.warning(
                                    'obrasgov_normalize_skipped project_id=%s error_type=%s',
                                    pid, type(norm_err).__name__,
                                )
                                continue
                            attrs = resource_input.attributes
                            if attrs.get('project_geometries'):
                                stats['with_pins'] += 1
                            if attrs.get('physical_execution_percentage') is not None:
                                stats['with_execution'] += 1
                            if resource_input.municipality_id:
                                stats['with_municipality'] += 1
                            _upsert_resource(session, resource_input, stats)
                except IntegrityError:
                    stats['errors'] += 1
                    logger.warning('obrasgov_page_conflict state=%s page=%s', state, page_num)

                total_p = response.get('total_pages', 1)
                if isinstance(total_p, int) and page_num >= total_p:
                    break

    stats['finished_at'] = now()
    mutated = stats['created'] + stats['updated'] + stats['unchanged']
    if stats['errors'] > 0 and mutated == 0:
        status = 'failed'
    elif stats['errors'] > 0:
        status = 'partial_quality'
    else:
        status = 'completed_file'
    with database.session() as session:
        load = Ingestion(
            dataset='obrasgov_projects',
            started_at=stats['started_at'],
            finished_at=stats['finished_at'],
            status=status,
            counts={
                'read': stats['read'],
                'created': stats['created'],
                'updated': stats['updated'],
                'unchanged': stats['unchanged'],
                'without_geometry': stats['read'] - stats['with_pins'],
                'pages_fetched': stats['pages_fetched'],
                'geometry_errors': stats['geometry_errors'],
                'execution_errors': stats['execution_errors'],
            },
            source={
                'url': f'{OBRASGOV_BASE}/projeto-investimento',
                'states': target_states,
                'pages_fetched': stats['pages_fetched'],
                'max_pages_per_state': max_pages_per_state,
                'national_catalog_certified': False,
                'stats': stats,
            },
        )
        session.add(load)
    return stats
