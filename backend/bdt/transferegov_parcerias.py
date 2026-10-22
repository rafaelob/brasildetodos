"""Bounded raw connector for the official Transferegov Parcerias API.

The API publishes partnership headers and related financial rows. This module
collects only the ``/parceria`` page, preserves every page with URL, bytes and
SHA-256, and imports exact payloads for reviewer-only consumption. It does not
sum values, link a partnership to a school or work, or claim national coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from pathlib import Path

import httpx
from sqlalchemy import JSON, BigInteger, Column, String, select

from .domain import now
from .ingest import safe_download
from .json_codec import decode
from .storage import Base, Database, Ingestion

DATASET = 'transferegov_parcerias'
BASE_URL = 'https://api-publica.transferegov.gestao.gov.br/parcerias/parceria'
MAX_PAGE_SIZE = 200
MAX_PAGES = 100
PAGES_DIR = 'pages'


def initialize_transferegov_parcerias(database: Database) -> None:
    TransferegovParceria.__table__.create(database.engine, checkfirst=True)


class TransferegovParceria(Base):
    __tablename__ = 'transferegov_parcerias'
    id = Column(String(80), primary_key=True)
    cd_parceria = Column(BigInteger, index=True)
    id_proposta = Column(String(80), index=True)
    situacao = Column(String(80))
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


def page_url(page: int, page_size: int) -> str:
    return f'{BASE_URL}?pagina={page}&tamanho_da_pagina={page_size}'


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                         encoding='utf-8')
    os.replace(temporary, path)


def _positive_int(value, field: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 1:
        raise ValueError(f'transferegov_parcerias_{field}_invalid')
    if maximum is not None and value > maximum:
        raise ValueError(f'transferegov_parcerias_{field}_invalid')
    return value


def collect(folder: Path, *, page_size: int = MAX_PAGE_SIZE, max_pages: int = 1,
            delay_seconds: float = 1.0) -> dict:
    page_size = _positive_int(page_size, 'page_size', MAX_PAGE_SIZE)
    max_pages = _positive_int(max_pages, 'max_pages', MAX_PAGES)
    if (isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float))
            or not math.isfinite(float(delay_seconds)) or float(delay_seconds) < 1.0):
        raise ValueError('transferegov_parcerias_delay_invalid')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if (folder / 'collection.json').exists() or (folder / PAGES_DIR).exists():
        raise ValueError('transferegov_parcerias_folder_not_empty')
    pages = folder / PAGES_DIR
    pages.mkdir()
    report = {'schema': 'bdt.transferegov-parcerias.v1', 'dataset': DATASET,
              'status': 'bounded', 'terminal': 'max_pages_bound',
              'plan': {'page_size': page_size, 'max_pages': max_pages,
                       'delay_seconds': float(delay_seconds)},
              'started_at': now(), 'pages': [], 'not_national_coverage': True,
              'national_catalog_certified': False}
    total_pages = total_items = None
    for page in range(1, max_pages + 1):
        if page > 1:
            time.sleep(float(delay_seconds))
        url = page_url(page, page_size)
        path = pages / f'page-{page}.json'
        try:
            metadata = safe_download(url, path)
        except httpx.HTTPStatusError as error:
            raise ValueError(f'transferegov_parcerias_http_{error.response.status_code}') from None
        payload = decode(path.read_bytes())
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise ValueError('transferegov_parcerias_schema_changed')
        rows = payload['data']
        number = payload.get('page_number')
        declared_pages = payload.get('total_pages')
        declared_items = payload.get('total_items')
        declared_size = payload.get('page_size')
        if (type(number) is not int or number != page or type(declared_pages) is not int
                or declared_pages < 0 or type(declared_items) is not int or declared_items < 0
                or type(declared_size) is not int or declared_size < 0
                or len(rows) > page_size or (rows and declared_size != page_size)):
            raise ValueError('transferegov_parcerias_page_totals_invalid')
        if total_pages is None:
            total_pages, total_items = declared_pages, declared_items
        elif rows and (declared_pages != total_pages or declared_items != total_items):
            raise ValueError('transferegov_parcerias_page_totals_changed')
        report['pages'].append({'index': page, 'url': metadata['url'],
                                'sha256': metadata['sha256'], 'bytes': metadata['bytes'],
                                'records': len(rows)})
        _write_json(folder / 'collection.json', report)
        if not rows:
            report['status'] = 'complete'
            report['terminal'] = 'empty_page'
            break
    report['finished_at'] = now()
    report['total_pages_declared'] = total_pages
    report['total_items_declared'] = total_items
    _write_json(folder / 'collection.json', report)
    return report


def _row(raw: dict, source: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError('transferegov_parcerias_row_not_object')
    identifier = raw.get('id_parceria')
    if isinstance(identifier, bool) or type(identifier) is not int or identifier < 1:
        raise ValueError('transferegov_parcerias_id_invalid')
    cd = raw.get('cd_parceria')
    if cd is not None and (isinstance(cd, bool) or type(cd) is not int):
        raise ValueError('transferegov_parcerias_cd_invalid')
    proposal = raw.get('id_proposta')
    if proposal is not None and (isinstance(proposal, bool) or type(proposal) is not int):
        raise ValueError('transferegov_parcerias_proposal_invalid')
    situation = raw.get('in_situacao_parceria')
    if situation is not None and (not isinstance(situation, str) or len(situation) > 80):
        raise ValueError('transferegov_parcerias_situation_invalid')
    return {'id': str(identifier), 'cd_parceria': cd,
            'id_proposta': str(proposal) if proposal is not None else None,
            'situacao': situation, 'payload': raw, 'source': dict(source)}


def import_collection(database: Database, folder: Path) -> dict:
    folder = Path(folder)
    report = decode((folder / 'collection.json').read_bytes())
    if (not isinstance(report, dict) or report.get('dataset') != DATASET
            or report.get('status') not in {'complete', 'bounded'}):
        raise ValueError('transferegov_parcerias_manifest_invalid')
    rows = []
    for entry in report.get('pages', []):
        if not isinstance(entry, dict):
            raise ValueError('transferegov_parcerias_page_invalid')
        path = folder / PAGES_DIR / f"page-{entry['index']}.json"
        raw = path.read_bytes()
        if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('transferegov_parcerias_page_integrity')
        payload = decode(raw)
        if not isinstance(payload.get('data'), list):
            raise ValueError('transferegov_parcerias_page_schema_changed')
        source = {'url': entry['url'], 'sha256': entry['sha256'],
                  'collected_at': report['started_at'], 'reference_date': None}
        rows.extend(_row(item, source) for item in payload['data'])
    created = updated = unchanged = 0
    with database.session() as session:
        existing = {row.id: row for row in session.scalars(select(TransferegovParceria))}
        for item in rows:
            current = existing.get(item['id'])
            if current is None:
                session.add(TransferegovParceria(**item))
                created += 1
            elif current.payload == item['payload'] and current.source.get('sha256') == item['source']['sha256']:
                unchanged += 1
            else:
                current.cd_parceria = item['cd_parceria']
                current.id_proposta = item['id_proposta']
                current.situacao = item['situacao']
                current.payload = item['payload']
                current.source = item['source']
                updated += 1
        counts = {'read': len(rows), 'created': created, 'updated': updated,
                  'unchanged': unchanged}
        session.add(Ingestion(dataset=DATASET, status='completed', counts=counts,
                              source={'collection_status': report['status'],
                                      'pages': len(report['pages']),
                                      'total_items_declared': report.get('total_items_declared')},
                              finished_at=now()))
    return {'status': 'imported', 'dataset': DATASET, 'counts': counts,
            'collection_status': report['status'], 'pages': len(report['pages']),
            'not_national_coverage': True, 'national_catalog_certified': False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    collect_parser = sub.add_parser('collect')
    collect_parser.add_argument('--folder', type=Path, required=True)
    collect_parser.add_argument('--page-size', type=int, default=MAX_PAGE_SIZE)
    collect_parser.add_argument('--max-pages', type=int, default=1)
    import_parser = sub.add_parser('import')
    import_parser.add_argument('--database', required=True)
    import_parser.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'collect':
        result = collect(args.folder, page_size=args.page_size, max_pages=args.max_pages)
    else:
        database = Database(args.database)
        try:
            database.initialize()
            initialize_transferegov_parcerias(database)
            result = import_collection(database, args.folder)
        finally:
            database.engine.dispose()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
