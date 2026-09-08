# SPDX-License-Identifier: AGPL-3.0-or-later
"""Batch collector and ingestor for official Obrasgov open data.

Populates the national catalog with verified public works, physical execution
percentages, georeferenced pin coordinates, and official planned dates across
Brazilian municipalities.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import time
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select

from .domain import Source, digest, now
from .evidence import Resource, initialize_extensions
from .resource_profiles import PROFILES, STATES, normalize_resource
from .resource_sync import ResourceRevision, changed_fields, initialize_resource_versions, semantic
from .storage import Database, Ingestion, Municipality

logger = logging.getLogger('bdt.obrasgov_batch')

OBRASGOV_BASE = 'https://api-publica.obrasgov.gestao.gov.br/obras'
USER_AGENT = 'BrasilDeTodos/0.3 (+https://github.com/rafaelob/brasildetodos)'


def fetch_api_json(endpoint: str, params: dict[str, Any], timeout: int = 30) -> dict:
    """Perform a secure HTTP GET request to the official Obrasgov open data API."""
    query = urlencode({k: v for k, v in params.items() if v is not None})
    url = f'{OBRASGOV_BASE}{endpoint}?{query}' if query else f'{OBRASGOV_BASE}{endpoint}'
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f'obrasgov_http_error_{response.status}')
        raw = response.read()
        return json.loads(raw.decode('utf-8'), parse_float=Decimal)


def fetch_obrasgov_projects(state: str | None = None, year: int | None = None,
                            page: int = 1, page_size: int = 100, timeout: int = 30) -> dict:
    """Fetch a page of investment projects from Obrasgov."""
    params = {'pagina': page, 'tamanho_da_pagina': page_size}
    if state:
        if state not in STATES:
            raise ValueError('invalid_project_state')
        params['uf_principal'] = state
    if year:
        params['ano_cadastro'] = year
    return fetch_api_json('/projeto-investimento', params, timeout=timeout)


def fetch_project_geometries(project_id: str, timeout: int = 15) -> list[dict]:
    """Fetch official geometry and municipality links for a specific project."""
    try:
        data = fetch_api_json('/geometria', {'id_projeto_investimento': project_id}, timeout=timeout)
        return data.get('data', [])
    except Exception:
        return []


def fetch_project_execution(project_id: str, timeout: int = 15) -> list[dict]:
    """Fetch official physical execution records for a specific project."""
    try:
        data = fetch_api_json('/execucao-fisica', {'id_projeto_investimento': project_id}, timeout=timeout)
        return data.get('data', [])
    except Exception:
        return []


def batch_ingest_obrasgov(database: Database, *, states: list[str] | None = None,
                           year: int | None = None, max_pages_per_state: int = 2,
                           page_size: int = 100, enrich_details: bool = True,
                           delay_seconds: float = 0.2) -> dict:
    """Ingest batches of official Obrasgov projects into the database.

    Maintains strict data integrity:
    - Never fabricates coordinates or municipality bindings.
    - Sets verified geometry pins directly from official project coordinates.
    - Sets physical execution percentage from official execution measurements.
    - Sets IBGE municipality from official geometry registrations.
    """
    initialize_resource_versions(database)
    target_states = states or ['RR', 'AP', 'AC', 'SE', 'RO']
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
    }

    with database.session() as session:
        territories = {row.id: (row.name, row.state) for row in session.scalars(select(Municipality))}

    ingestion_records = []

    for state in target_states:
        geom_map: dict[str, str] = {}
        if enrich_details:
            try:
                for g_page in range(1, 3):
                    g_res = fetch_api_json('/geometria', {'sg_uf': state, 'pagina': g_page, 'tamanho_da_pagina': 200})
                    for g in g_res.get('data', []):
                        if g.get('id_projeto_investimento') and g.get('cod_ibge'):
                            geom_map[str(g['id_projeto_investimento'])] = str(g['cod_ibge'])
                    if g_page >= g_res.get('total_pages', 1):
                        break
            except Exception as e:
                logger.debug(f'Prefetch geometries failed for {state}: {e}')

        for page_num in range(1, max_pages_per_state + 1):
            try:
                response = fetch_obrasgov_projects(state=state, year=year, page=page_num, page_size=page_size)
            except Exception as exc:
                stats['errors'] += 1
                logger.warning(f'Failed to fetch Obrasgov page {page_num} for state {state}: {exc}')
                break

            projects = response.get('data', [])
            if not projects:
                break

            # Concurrently fetch executions for projects in this page if enriching
            exec_map: dict[str, list[dict]] = {}
            if enrich_details:
                pids_to_fetch = [str(p.get('id_projeto_investimento')) for p in projects if p.get('id_projeto_investimento')]
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        exec_futures = {executor.submit(fetch_project_execution, pid): pid for pid in pids_to_fetch}
                        for future in concurrent.futures.as_completed(exec_futures, timeout=30):
                            pid = exec_futures[future]
                            try:
                                res_exec = future.result()
                                if res_exec:
                                    exec_map[pid] = res_exec
                            except Exception:
                                pass
                except Exception as ex:
                    logger.debug(f'Concurrent execution fetch error: {ex}')

            with database.session() as session:
                for proj in projects:
                    stats['read'] += 1
                    pid = str(proj.get('id_projeto_investimento') or '')
                    if not pid:
                        continue

                    if enrich_details:
                        if pid in geom_map:
                            proj['cod_ibge'] = geom_map[pid]
                        elif not proj.get('cod_ibge'):
                            geoms = fetch_project_geometries(pid)
                            if geoms and isinstance(geoms[0], dict):
                                if geoms[0].get('cod_ibge'):
                                    proj['cod_ibge'] = geoms[0]['cod_ibge']
                                if not proj.get('pins'):
                                    proj['pins'] = geoms

                        execs = exec_map.get(pid)
                        if execs and isinstance(execs[0], dict):
                            first_exec = execs[0]
                            if first_exec.get('percentual_execucao_fisica') is not None:
                                proj['percentual_execucao_fisica'] = first_exec['percentual_execucao_fisica']
                            if first_exec.get('dt_atualizacao_execucao'):
                                proj['dt_atualizacao_execucao'] = first_exec['dt_atualizacao_execucao']

                    # Create source descriptor
                    src_url = f'{OBRASGOV_BASE}/projeto-investimento?id_projeto_investimento={pid}'
                    raw_bytes = json.dumps(proj, sort_keys=True, default=str).encode('utf-8')
                    src = Source(
                        dataset='obrasgov_projects',
                        record_id=pid,
                        url=src_url,
                        reference_date=str(proj.get('ano_cadastro')) if proj.get('ano_cadastro') else None,
                        collected_at=now(),
                        snapshot_sha256=hashlib.sha256(raw_bytes).hexdigest(),
                    )

                    try:
                        resource_input = normalize_resource('obrasgov_projects', proj, src, territories)
                    except Exception as norm_err:
                        stats['errors'] += 1
                        logger.debug(f'Normalization skipped for {pid}: {norm_err}')
                        continue

                    attrs = resource_input.attributes
                    if attrs.get('project_geometries'):
                        stats['with_pins'] += 1
                    if attrs.get('physical_execution_percentage') is not None:
                        stats['with_execution'] += 1
                    if resource_input.municipality_id:
                        stats['with_municipality'] += 1

                    payload = resource_input.model_dump(mode='json')
                    fingerprint = digest(semantic(payload))

                    existing = session.scalar(select(Resource).where(Resource.id == resource_input.id))
                    last_rev = session.scalar(select(ResourceRevision).where(ResourceRevision.resource_id == resource_input.id)
                                              .order_by(ResourceRevision.revision.desc()).limit(1))

                    if existing is not None:
                        if last_rev and last_rev.fingerprint == fingerprint:
                            stats['unchanged'] += 1
                            continue

                        stats['updated'] += 1
                        version = (last_rev.revision + 1) if last_rev else 1
                        fields = changed_fields(existing.payload, payload) if last_rev else ['updated']
                        existing.title = resource_input.title
                        existing.kind = resource_input.kind
                        existing.municipality_id = resource_input.municipality_id
                        existing.payload = payload
                        existing.source = payload['source']

                        rev = ResourceRevision(
                            resource_id=resource_input.id,
                            revision=version,
                            fingerprint=fingerprint,
                            payload=payload,
                            observed_at=now(),
                            changed_fields=fields,
                        )
                        session.add(rev)
                    else:
                        stats['created'] += 1
                        new_res = Resource(
                            id=resource_input.id,
                            kind=resource_input.kind,
                            municipality_id=resource_input.municipality_id,
                            title=resource_input.title,
                            payload=payload,
                            source=payload['source'],
                        )
                        session.add(new_res)
                        rev = ResourceRevision(
                            resource_id=resource_input.id,
                            revision=1,
                            fingerprint=fingerprint,
                            payload=payload,
                            observed_at=now(),
                            changed_fields=['initial_import'],
                        )
                        session.add(rev)

                session.commit()


            total_p = response.get('total_pages', 1)
            if page_num >= total_p:
                break

    stats['finished_at'] = now()
    status = 'failed' if stats['errors'] > 0 and (stats['created'] + stats['updated'] + stats['unchanged'] == 0) else (
        'partial_quality' if stats['errors'] > 0 else 'completed_file'
    )
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
            },
            source={
                'url': f'{OBRASGOV_BASE}/projeto-investimento',
                'states': target_states,
                'stats': stats,
            },
        )
        session.add(load)
        session.commit()

    return stats
