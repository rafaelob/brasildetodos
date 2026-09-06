"""Bounded public resource exports. No users, observations, links or raw documents."""
from __future__ import annotations

import csv
import io
import json
from typing import Literal

from fastapi import HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from .domain import digest
from .evidence import Resource
from .resource_money import MAX_CENTS, metadata_amount
from .resource_sync import ResourceRevision, semantic

FIELDS = ('profile', 'territorial_basis', 'state', 'budget_direction', 'declared_status',
          'buyer_cnpj', 'buyer_name', 'contract_number', 'source_control_number',
          'purchase_control_number', 'published_at', 'upstream_updated_at', 'signed_on',
          'starts_on', 'ends_on', 'plan_code', 'year', 'accepted_on', 'program_id',
          'planned_starts_on', 'planned_ends_on', 'version_basis')
SOURCES = ('dataset', 'record_id', 'url', 'reference_date', 'collected_at', 'snapshot_sha256')
AMOUNTS = ('initial', 'global', 'accumulated', 'planned_operating', 'planned_investment')
COPY = {
    'pt-BR': ('Resumo público do recurso', 'Valores cadastrais ou previstos, não pagamentos. Não somar fases. A localização do comprador não comprova o local de execução. A versão é a observada pela plataforma; não certifica entrega ou cobertura nacional.'),
    'en': ('Public resource summary', 'Registration or planned amounts, not payments. Do not add stages. Buyer location does not establish execution location. This is a platform-observed version, not delivery or national coverage certification.'),
    'es': ('Resumen público del recurso', 'Importes de registro o previstos, no pagos. No sumar etapas. La ubicación del comprador no demuestra el lugar de ejecución. Es una versión observada por la plataforma, no una certificación de entrega ni de cobertura nacional.'),
}


def cents_text(value):
    if type(value) is not int or not 0 <= value <= MAX_CENTS:
        raise ValueError('invalid_public_resource_amount')
    return f'{value // 100}.{value % 100:02d}'


def public_resource(payload):
    """Allowlisted, typed projection; adding an internal field cannot export it."""
    attrs = payload.get('attributes', {})
    fields = {key: attrs[key] for key in FIELDS if key in attrs
              and (attrs[key] is None or type(attrs[key]) in (str, int, bool))}
    amounts = []
    precise = attrs.get('precise_amounts', {}) if attrs.get('profile') == 'pncp_contracts' else {}
    if not isinstance(precise, dict):
        raise ValueError('invalid_public_resource_amount')
    for key in AMOUNTS:
        cents = attrs.get(key + '_cents')
        if key in precise and key in ('initial', 'global', 'accumulated'):
            _, value = metadata_amount(precise[key])
            if value is None or value != precise[key] or cents is not None:
                raise ValueError('conflicting_public_resource_amount')
            amounts.append({'field': key, 'currency': 'BRL', 'decimal': value, 'cents': None})
        elif cents is not None:
            amounts.append({'field': key, 'currency': 'BRL', 'decimal': cents_text(cents), 'cents': cents})
    planned = attrs.get('planned_investments', [])
    if not isinstance(planned, list) or len(planned) > 100:
        raise ValueError('invalid_public_resource_investments')
    for i, entry in enumerate(planned):
        if not isinstance(entry, dict):
            raise ValueError('invalid_public_resource_investments')
        value = entry.get('planned_cents')
        source_name = entry.get('source_name')
        if source_name is not None and not isinstance(source_name, str):
            raise ValueError('invalid_public_resource_investments')
        amounts.append({'field': f'planned_investments.{i}', 'currency': 'BRL',
                        'decimal': cents_text(value) if value is not None else None,
                        'cents': value, 'source_name': source_name})
    return {key: payload.get(key) for key in ('id', 'kind', 'title', 'municipality_id')} | {
        'source': {key: payload.get('source', {}).get(key) for key in SOURCES},
        'attributes': fields, 'amounts': amounts,
    }


def snapshot(database, resource_id, revision=None, locale='pt-BR'):
    if locale not in COPY:
        raise ValueError('unsupported_export_locale')
    with database.session() as session:
        row = session.scalar(select(Resource).where(Resource.id == resource_id).with_for_update(read=True))
        if row is None:
            raise HTTPException(404, 'resource_not_found')
        query = select(ResourceRevision).where(ResourceRevision.resource_id == resource_id)
        if revision is not None:
            query = query.where(ResourceRevision.revision == revision)
        version = session.scalar(query.order_by(ResourceRevision.revision.desc()).limit(1))
        if revision is not None and version is None:
            raise HTTPException(404, 'resource_revision_not_found')
        if version is not None and (digest(semantic(version.payload)) != version.fingerprint or
                (revision is None and digest(semantic(row.payload)) != version.fingerprint)):
            raise HTTPException(409, 'resource_revision_integrity_failure')
        projected = public_resource(version.payload if version is not None else row.payload)
        return {'schema': 'bdt.public-resource.v1', 'locale': locale,
                'title': COPY[locale][0], 'notice': COPY[locale][1],
                'revision': version.revision if version is not None else None,
                'observed_at': version.observed_at if version is not None else None,
                'scope': 'one_public_metadata_version_no_private_documents_or_financial_total',
                'resource': projected, 'content_sha256': digest(projected)}


def flat_rows(report):
    rows = [(key, report[key]) for key in ('schema', 'locale', 'title', 'notice', 'revision',
                                         'observed_at', 'scope', 'content_sha256')]
    resource = report['resource']
    rows.extend((key, resource[key]) for key in ('id', 'kind', 'title', 'municipality_id'))
    for prefix in ('source', 'attributes'):
        rows.extend((prefix + '.' + key, value) for key, value in resource[prefix].items())
    for entry in resource['amounts']:
        for key in ('currency', 'decimal', 'cents', 'source_name'):
            if key in entry:
                rows.append((f"amounts.{entry['field']}.{key}", entry[key]))
    return rows


def csv_cell(value):
    value = '' if value is None else str(value)
    # Defense for spreadsheet consumers. JSON retains the exact original text.
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def render(report, format):
    if format == 'json':
        return json.dumps(report, ensure_ascii=False, indent=2), 'application/json'
    if format == 'text':
        return '\n'.join(f'{key}: {value if value is not None else "—"}' for key, value in flat_rows(report)) + '\n', 'text/plain'
    if format != 'csv':
        raise ValueError('unsupported_export_format')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['field', 'value'])
    for key, value in flat_rows(report):
        writer.writerow([key, csv_cell(value)])
    return '\ufeff' + stream.getvalue(), 'text/csv'


def install(app, database):
    @app.get('/api/resource-export/{resource_id:path}')
    def export(resource_id: str, format: Literal['json', 'text', 'csv'] = 'json',
               locale: Literal['pt-BR', 'en', 'es'] = 'pt-BR',
               revision: int | None = Query(None, ge=1, le=100000)):
        if len(resource_id) > 200:
            raise HTTPException(422, 'invalid_resource_id')
        try:
            report = snapshot(database, resource_id, revision, locale)
            content, media = render(report, format)
        except ValueError:
            raise HTTPException(409, 'resource_export_requires_review') from None
        suffix = 'txt' if format == 'text' else format
        name = f"brasildetodos-resource-{digest(resource_id)[:12]}-v{report['revision'] or 'unversioned'}.{suffix}"
        return Response(content, media_type=media, headers={
            'Content-Disposition': f'attachment; filename="{name}"',
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
