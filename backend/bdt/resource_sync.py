"""Atomic, versioned resource metadata from complete, bounded official queries.

No HTTP data are accepted through public write endpoints. Original pages remain
operator-private; only profile-allowlisted metadata are published. A completed
query is not national coverage and absence from a query never removes a record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Column, ForeignKey, Integer, JSON, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError

from .domain import Source, digest, now
from .evidence import Resource, ResourceInput, initialize_extensions
from .resource_profiles import PROFILES, collection_plan, normalize_resource
from .resource_diagnostics import ResourceTextError
from .storage import Base, Database, Ingestion, Municipality
from .sync import PagePlan, atomic_json, collect, file_hash, page_url


class ResourceRevision(Base):
    __tablename__ = 'resource_revisions'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    resource_id = Column(String(200), ForeignKey('resources.id'), nullable=False, index=True)
    revision = Column(Integer, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    observed_at = Column(String(40), nullable=False)
    changed_fields = Column(JSON, nullable=False)
    __table_args__ = (UniqueConstraint('resource_id', 'revision'),)


def initialize_resource_versions(database):
    initialize_extensions(database)
    ResourceRevision.__table__.create(database.engine, checkfirst=True)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('non_finite_json_number')


def decode(raw: bytes):
    return json.loads(raw.decode('utf-8-sig'), parse_float=Decimal,
                      object_pairs_hook=_pairs, parse_constant=_constant)


def semantic(payload):
    # A query URL/page, byte hash or local collection date is provenance, not a
    # change in the contract. Keep the first exact source of an unchanged version.
    source = {k: v for k, v in payload['source'].items()
              if k not in {'url', 'collected_at', 'snapshot_sha256'}}
    attributes = {k: v for k, v in payload['attributes'].items()
                  if k not in {'collection_page_url', 'record_reference_url'}}
    return payload | {'source': source, 'attributes': attributes}


def changed_fields(before, after):
    if before is None:
        return ['initial_import']
    left, right = semantic(before), semantic(after)
    fields = []
    for key in sorted(set(left) | set(right)):
        if left.get(key) == right.get(key):
            continue
        if key in {'attributes', 'source'}:
            fields.extend(f'{key}.{field}' for field in sorted(set(left[key]) | set(right[key]))
                          if left[key].get(field) != right[key].get(field))
        else:
            fields.append(key)
    return fields


def _instant(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _newer(before, after):
    if after['attributes']['version_basis'] == 'publisher_update':
        old = before['attributes'].get('upstream_updated_at')
        new = after['attributes'].get('upstream_updated_at')
    else:
        old, new = before['source']['collected_at'], after['source']['collected_at']
    try:
        if not old or not new or _instant(new) <= _instant(old):
            raise ValueError('resource_version_stale_or_conflicting')
    except TypeError:
        raise ValueError('incomparable_resource_version_clocks') from None


def _check_scope(plan, row, body):
    attributes = body.attributes
    if plan.dataset == 'pncp_contracts':
        if plan.parameters.get('cnpjOrgao') and attributes['buyer_cnpj'] != plan.parameters['cnpjOrgao']:
            raise ValueError('record_outside_requested_buyer')
        value = attributes['upstream_updated_at'] if plan.url.endswith('/atualizacao') else attributes['published_at']
        if not value or not plan.parameters['dataInicial'] <= value[:10].replace('-', '') <= plan.parameters['dataFinal']:
            raise ValueError('record_outside_requested_dates')
    else:
        if plan.identity in plan.parameters and str(row[plan.identity]) != plan.parameters[plan.identity]:
            raise ValueError('record_outside_requested_identity')
        field = 'ano_plano_acao' if plan.dataset == 'transferegov_special_plans' else 'ano_cadastro'
        if field in plan.parameters and str(row.get(field)) != plan.parameters[field]:
            raise ValueError('record_outside_requested_year')


def _reviewed_plan(report):
    plan = PagePlan.model_validate(report['plan'])
    if plan.dataset not in PROFILES:
        raise ValueError('unknown_resource_profile')
    if plan.dataset == 'pncp_contracts':
        expected = collection_plan(plan.dataset, start=plan.parameters.get('dataInicial'),
            end=plan.parameters.get('dataFinal'), identity=plan.parameters.get('cnpjOrgao'),
            updates=plan.url.endswith('/atualizacao'), page_size=plan.page_size, max_pages=plan.max_pages)
    else:
        field = 'ano_plano_acao' if plan.dataset == 'transferegov_special_plans' else 'ano_cadastro'
        year = int(plan.parameters[field]) if field in plan.parameters else None
        expected = collection_plan(plan.dataset, year=year, identity=plan.parameters.get(plan.identity),
            page_size=plan.page_size, max_pages=plan.max_pages)
    if plan.model_dump() != expected.model_dump() or digest(plan.model_dump()) != report.get('plan_sha256'):
        raise ValueError('unreviewed_resource_query_plan')
    if report.get('status') != 'complete':
        raise ValueError('incomplete_collection_cannot_be_published')
    return plan


def verified_resources(folder: Path, report: dict, plan: PagePlan, municipalities: dict):
    entries = report.get('pages')
    if not isinstance(entries, list) or not entries or len(entries) > plan.max_pages:
        raise ValueError('invalid_resource_page_manifest')
    seen, total, declared_pages, declared_records = set(), 0, None, None
    for index, entry in enumerate(entries):
        filename = f'page-{index:06}.json'
        if entry.get('index') != index or entry.get('file') != filename or entry.get('url') != page_url(plan, index):
            raise ValueError('resource_page_reference_mismatch')
        path = folder / filename
        if path.is_symlink() or path.stat().st_size > plan.max_bytes_per_page:
            raise ValueError('resource_page_not_regular_or_too_large')
        raw = path.read_bytes()
        if len(raw) != entry.get('bytes') or hashlib.sha256(raw).hexdigest() != entry.get('sha256'):
            raise ValueError('resource_page_integrity_failure')
        if entry.get('status_code') == 204:
            if (plan.dataset != 'pncp_contracts' or index != 0 or len(entries) != 1
                    or raw != b'' or entry.get('records') != 0 or report.get('records') != 0
                    or report.get('expected_records') != 0 or report.get('terminal') != 'http_204_no_content'):
                raise ValueError('invalid_resource_no_content_evidence')
            return  # Proven empty query, never deletion or national certification.
        if entry.get('status_code', 200) != 200:
            raise ValueError('invalid_resource_http_status')
        payload = decode(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get(plan.root), list):
            raise ValueError('resource_response_schema_changed')
        rows = payload[plan.root]
        page = payload.get(plan.response_page_field)
        pages, records = payload.get(plan.total_pages_field), payload.get(plan.total_records_field)
        if (type(page) is not int or page != index + 1 or type(pages) is not int or type(records) is not int
                or pages < 0 or records < 0 or len(rows) > plan.page_size):
            raise ValueError('invalid_resource_page_totals')
        if declared_pages is not None and (pages != declared_pages or records != declared_records):
            raise ValueError('changing_resource_page_totals')
        declared_pages, declared_records = pages, records
        if len(rows) != entry.get('records'):
            raise ValueError('resource_page_row_count_mismatch')
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('resource_row_not_object')
            identity = str(row.get(plan.identity, ''))
            if not identity or identity in seen:
                raise ValueError('duplicate_or_missing_resource_identity')
            seen.add(identity)
            source = Source(dataset=plan.dataset, record_id=identity, url=entry['url'], reference_date=None,
                collected_at=entry['collected_at'], snapshot_sha256=entry['sha256'])
            try:
                body = normalize_resource(plan.dataset, row, source, municipalities)
            except ResourceTextError as error:
                error.with_reference(plan.dataset, identity, entry["sha256"])
                raise
            _check_scope(plan, row, body)
            yield body
            total += 1
    if (len(entries) != max(declared_pages, 1) or total != declared_records or total != report.get('records')
            or report.get('expected_records') != declared_records):
        raise ValueError('resource_terminal_reconciliation_failure')
    if report.get('terminal') not in {'empty_page', 'declared_total_pages'}:
        raise ValueError('missing_resource_terminal_evidence')


def import_resources(database, folder: Path) -> dict:
    manifest = folder / 'collection.json'
    raw_manifest = manifest.read_bytes()
    report = json.loads(raw_manifest)
    plan = _reviewed_plan(report)
    initialize_resource_versions(database)
    result = {'read': 0, 'created': 0, 'updated': 0, 'unchanged': 0, 'unresolved_municipality': 0,
              'profile': plan.dataset, 'scope': plan.parameters, 'removed': 0,
              'financial_events_created': 0, 'automatic_place_links': 0, 'subcent_records': 0, 'subcent_fields': 0, 'national_catalog_certified': False}
    with database.session() as session:
        load = Ingestion(dataset=plan.dataset, source={'url': plan.url, 'query': plan.parameters,
            'manifest_sha256': hashlib.sha256(raw_manifest).hexdigest()})
        session.add(load); session.flush(); load_id = load.id
    try:
        with database.session() as session:
            territories = {row.id: (row.name, row.state) for row in session.scalars(select(Municipality))}
            for body in verified_resources(folder, report, plan, territories):
                payload = body.model_dump(mode='json')
                fingerprint = digest(semantic(payload))
                row = session.scalar(select(Resource).where(Resource.id == body.id).with_for_update())
                last = session.scalar(select(ResourceRevision).where(ResourceRevision.resource_id == body.id)
                                      .order_by(ResourceRevision.revision.desc()).limit(1))
                result['read'] += 1
                precise = body.attributes.get('precise_amounts', {})
                result['subcent_records'] += bool(precise)
                result['subcent_fields'] += len(precise)
                result['unresolved_municipality'] += body.municipality_id is None
                if row is not None:
                    if last is None or digest(semantic(row.payload)) != last.fingerprint:
                        raise ValueError('resource_current_not_owned_by_version_ledger')
                    if row.source['dataset'] != plan.dataset:
                        raise ValueError('resource_source_collision')
                    if last.fingerprint == fingerprint:
                        result['unchanged'] += 1
                        continue
                    _newer(row.payload, payload)
                    fields = changed_fields(row.payload, payload)
                    version = last.revision + 1
                    row.title, row.kind, row.municipality_id = body.title, body.kind, body.municipality_id
                    row.payload, row.source = payload, payload['source']
                    result['updated'] += 1
                else:
                    version, fields = 1, ['initial_import']
                    session.add(Resource(id=body.id, kind=body.kind, municipality_id=body.municipality_id,
                                         title=body.title, payload=payload, source=payload['source']))
                    session.flush()
                    result['created'] += 1
                session.add(ResourceRevision(resource_id=body.id, revision=version, fingerprint=fingerprint,
                    payload=payload, observed_at=now(), changed_fields=fields))
                session.flush()
            if manifest.read_bytes() != raw_manifest:
                raise ValueError('resource_manifest_changed_during_import')
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at, load.counts = 'success', now(), result
    except Exception as error:
        with database.session() as session:
            load = session.get(Ingestion, load_id)
            load.status, load.finished_at = 'failed', now()
            load.error = str(error)[:160] if type(error) is ValueError else type(error).__name__
            load.counts = {'records_attempted': result['read'], 'published': 0, 'rolled_back': True}
        if isinstance(error, IntegrityError):
            raise ValueError('concurrent_resource_revision_retry_required') from None
        raise
    return result | {'status': 'imported_complete_query', 'ingestion_id': load_id,
                     'manifest_sha256': hashlib.sha256(raw_manifest).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=list(PROFILES))
    parser.add_argument('--folder', required=True, type=Path)
    parser.add_argument('--database-url', required=True)
    parser.add_argument('--start'); parser.add_argument('--end')
    parser.add_argument('--year', type=int); parser.add_argument('--identity')
    parser.add_argument('--updates', action='store_true')
    parser.add_argument('--page-size', type=int, default=100)
    parser.add_argument('--max-pages', type=int, default=100)
    parser.add_argument('--collect', action='store_true', help='Perform official read-only HTTP collection first')
    args = parser.parse_args()
    plan = collection_plan(args.profile, start=args.start, end=args.end, year=args.year, identity=args.identity,
        updates=args.updates, page_size=args.page_size, max_pages=args.max_pages)
    if args.collect:
        collect(plan, args.folder)
    stored = json.loads((args.folder / 'collection.json').read_text())
    if stored.get('plan_sha256') != digest(plan.model_dump()):
        raise ValueError('cli_plan_differs_from_collection')
    database = Database(args.database_url)
    try:
        database.initialize()
        result = import_resources(database, args.folder)
        atomic_json(args.folder / 'import-result.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == '__main__':
    main()
