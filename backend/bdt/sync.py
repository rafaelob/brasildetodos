"""Operator-controlled collection with resumable pages and explicit completeness.

A successful HTTP response, a short page or an exhausted budget is not proof
that the national dataset was collected. Source profiles are explicit inputs.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import httpx
from pydantic import Field, model_validator
from .domain import Source, StrictModel, digest, now
from .ingest import HOSTS, import_places, safe_download


class PagePlan(StrictModel):
    dataset: str = Field(pattern=r'^[a-z0-9_-]{2,80}$')
    url: str
    root: str
    identity: str
    page_parameter: str = 'pagina'
    size_parameter: str = 'tamanhoPagina'
    page_size: int = Field(default=100, ge=1, le=1000)
    start: int = Field(default=1, ge=0)
    step: int = Field(default=1, ge=1)
    max_pages: int = Field(default=100, ge=1, le=50000)
    max_bytes_per_page: int = Field(default=8*1024*1024, ge=1, le=64*1024*1024)
    total_pages_field: str | None = None
    total_records_field: str | None = None
    response_page_field: str | None = None
    reference_date: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    delay_seconds: float = Field(default=.25, ge=0, le=60)

    @model_validator(mode='after')
    def reviewed_source(self):
        url = urlsplit(self.url)
        if url.scheme != 'https' or url.hostname not in HOSTS or url.username or url.password or url.port not in (None, 443):
            raise ValueError('source_not_allowlisted')
        if self.page_parameter == self.size_parameter or self.page_parameter in self.parameters or self.size_parameter in self.parameters:
            raise ValueError('ambiguous_pagination_parameters')
        response_metadata = (self.total_pages_field, self.total_records_field, self.response_page_field)
        configured_response_metadata = [field for field in response_metadata if field is not None]
        if any(not key or len(key) > 80 for key in (
                self.root, self.identity, self.page_parameter, self.size_parameter,
                *configured_response_metadata)):
            raise ValueError('invalid_profile_field')
        response_fields = [self.root, *configured_response_metadata]
        if len(response_fields) != len(set(response_fields)):
            raise ValueError('ambiguous_response_fields')
        return self


def atomic_json(path: Path, content: dict):
    target = path.with_suffix(path.suffix + '.tmp')
    target.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(target, path)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def page_url(plan: PagePlan, index: int) -> str:
    parsed = urlsplit(plan.url)
    parameters = dict(parse_qsl(parsed.query, keep_blank_values=True)) | plan.parameters
    parameters[plan.page_parameter] = str(plan.start + index * plan.step)
    parameters[plan.size_parameter] = str(plan.page_size)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(parameters), ''))


def download_retry(url: str, target: Path, max_bytes: int, *, attempts: int = 3, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            parsed = urlsplit(url)
            # Only the documented PNCP contract endpoints may use a bodyless
            # HTTP 204 as query evidence; ordinary file downloads remain strict.
            if parsed.hostname == 'pncp.gov.br' and parsed.path in {
                    '/api/consulta/v1/contratos', '/api/consulta/v1/contratos/atualizacao'}:
                return safe_download(url, target, max_bytes, allow_no_content=True)
            return safe_download(url, target, max_bytes)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as error:
            retryable = not isinstance(error, httpx.HTTPStatusError) or error.response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt + 1 == attempts:
                raise
            sleep(min(2 ** attempt, 8))
    raise ValueError('retry_budget_must_be_positive')


def collect(plan: PagePlan, folder: Path, *, loader=download_retry, sleep=time.sleep) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    checkpoint = folder / 'collection.json'
    fingerprint = digest(plan.model_dump())
    old = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if old and old.get('plan_sha256') != fingerprint:
        raise ValueError('resume_profile_changed_use_new_collection')
    report = {'dataset': plan.dataset, 'plan_sha256': fingerprint, 'plan': plan.model_dump(),
              'started_at': old['started_at'] if old else now(), 'status': 'running', 'pages': [],
              'records': 0, 'national_catalog_certified': False, 'terminal': None}
    cached = {p['index']: p for p in (old or {}).get('pages', [])}
    identities, hashes = set(), set()
    expected_pages, expected_records = None, None
    try:
        for index in range(plan.max_pages):
            path = folder / f'page-{index:06}.json'
            url = page_url(plan, index)
            if index in cached:
                metadata = cached[index]
                if metadata['url'] != url or not path.is_file() or file_hash(path) != metadata['sha256']:
                    raise ValueError('cached_page_integrity_failure')
            else:
                if index:
                    sleep(plan.delay_seconds)
                metadata = loader(url, path, plan.max_bytes_per_page)
                if file_hash(path) != metadata['sha256']:
                    raise ValueError('download_hash_mismatch')
            if metadata.get('url') != url:
                raise ValueError('download_url_mismatch')
            if type(metadata.get('bytes')) is not int or metadata['bytes'] != path.stat().st_size:
                raise ValueError('download_size_mismatch')
            if metadata.get('status_code') == 204:
                if (plan.dataset != 'pncp_contracts' or index != 0 or report['records'] != 0
                        or urlsplit(plan.url).hostname != 'pncp.gov.br'
                        or urlsplit(plan.url).path not in {'/api/consulta/v1/contratos', '/api/consulta/v1/contratos/atualizacao'}
                        or path.stat().st_size != 0 or metadata.get('bytes') != 0):
                    raise ValueError('unexpected_no_content_response')
                report['pages'].append({key: metadata.get(key) for key in
                    ('url', 'sha256', 'bytes', 'collected_at', 'etag', 'status_code')} |
                    {'index': 0, 'file': path.name, 'records': 0})
                report.update(status='complete', terminal='http_204_no_content',
                              expected_records=0, finished_at=now())
                atomic_json(checkpoint, report)
                return report
            if metadata.get('status_code', 200) != 200:
                raise ValueError('unexpected_page_http_status')
            payload = json.loads(path.read_text(encoding='utf-8-sig'))
            rows = payload.get(plan.root) if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError('response_schema_changed')
            if plan.response_page_field and payload.get(plan.response_page_field) != plan.start + index * plan.step:
                raise ValueError('unexpected_response_page')
            for field, previous in ((plan.total_pages_field, expected_pages), (plan.total_records_field, expected_records)):
                if field:
                    value = payload.get(field)
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (previous is not None and value != previous):
                        raise ValueError('changing_or_invalid_total')
                    if field == plan.total_pages_field:
                        expected_pages = value
                    if field == plan.total_records_field:
                        expected_records = value
            if rows and expected_pages is not None and expected_pages < index + 1:
                raise ValueError('declared_total_pages_before_current_page')
            if rows and metadata['sha256'] in hashes:
                raise ValueError('repeated_page')
            hashes.add(metadata['sha256'])
            for row in rows:
                identity = row.get(plan.identity) if isinstance(row, dict) else None
                if isinstance(identity, bool) or not isinstance(identity, (str, int)) or str(identity) == '':
                    raise ValueError('missing_source_identity')
                identity = str(identity)
                if identity in identities:
                    raise ValueError('duplicate_source_identity_across_pages')
                identities.add(identity)
            entry = {key: metadata.get(key) for key in ('url', 'sha256', 'bytes', 'collected_at', 'etag')}
            if 'status_code' in metadata:
                entry['status_code'] = metadata['status_code']
            entry.update(index=index, file=path.name, records=len(rows))
            report['pages'].append(entry)
            report['records'] += len(rows)
            if expected_records is not None and report['records'] > expected_records:
                raise ValueError('record_count_exceeds_declared_total')
            terminal = not rows or (expected_pages is not None and index + 1 >= expected_pages)
            if terminal:
                if expected_records is not None and report['records'] != expected_records:
                    raise ValueError('terminal_count_mismatch')
                if expected_pages is not None and index + 1 < expected_pages:
                    raise ValueError('premature_empty_page')
                report.update(status='complete', terminal='empty_page' if not rows else 'declared_total_pages',
                    expected_records=expected_records, finished_at=now())
                atomic_json(checkpoint, report)
                return report
            atomic_json(checkpoint, report)
        report.update(status='partial_budget', finished_at=now())
        atomic_json(checkpoint, report)
        return report
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__,
            error_code=str(error) if isinstance(error, ValueError) else 'transport_failure', finished_at=now())
        atomic_json(checkpoint, report)
        raise


def collected_rows(folder: Path, report: dict):
    plan = PagePlan.model_validate(report['plan'])
    entries = report.get('pages')
    if (report.get('status') != 'complete' or not isinstance(entries, list)
            or not entries or len(entries) > plan.max_pages):
        raise ValueError('invalid_collection_page_manifest')
    report_records = report.get('records')
    report_expected_records = report.get('expected_records')
    if (type(report_records) is not int or report_records < 0
            or report_expected_records is not None
            and (type(report_expected_records) is not int or report_expected_records < 0)):
        raise ValueError('invalid_collection_numeric_manifest')
    identities, total = set(), 0
    expected_pages, expected_records, actual_terminal = None, None, None
    for index, entry in enumerate(entries):
        filename = f'page-{index:06}.json'
        if not isinstance(entry, dict):
            raise ValueError('collection_page_reference_mismatch')
        entry_index = entry.get('index')
        entry_bytes = entry.get('bytes')
        entry_records = entry.get('records')
        if (type(entry_index) is not int or entry_index < 0
                or type(entry_bytes) is not int or entry_bytes < 0
                or type(entry_records) is not int or entry_records < 0):
            raise ValueError('invalid_collection_numeric_manifest')
        if (entry_index != index
                or entry.get('file') != filename or entry.get('url') != page_url(plan, index)):
            raise ValueError('collection_page_reference_mismatch')
        # Paths are generated, not accepted from an untrusted manifest.
        path = folder / filename
        if path.is_symlink() or not path.is_file():
            raise ValueError('collection_page_not_regular_or_too_large')
        actual_bytes = path.stat().st_size
        if actual_bytes != entry_bytes:
            raise ValueError('page_changed_after_collection')
        if actual_bytes > plan.max_bytes_per_page:
            raise ValueError('collection_page_not_regular_or_too_large')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry.get('sha256'):
            raise ValueError('page_changed_after_collection')
        if entry.get('status_code', 200) != 200:
            raise ValueError('collection_page_integrity_failure')
        payload = json.loads(raw.decode('utf-8-sig'))
        rows = payload.get(plan.root) if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError('collection_page_schema_changed')
        if plan.response_page_field and payload.get(plan.response_page_field) != plan.start + index * plan.step:
            raise ValueError('collection_response_page_mismatch')
        for field, previous in ((plan.total_pages_field, expected_pages),
                                (plan.total_records_field, expected_records)):
            if field:
                value = payload.get(field)
                if (type(value) is not int or value < 0
                        or previous is not None and value != previous):
                    raise ValueError('collection_page_totals_invalid')
                if field == plan.total_pages_field:
                    expected_pages = value
                if field == plan.total_records_field:
                    expected_records = value
        if rows and expected_pages is not None and expected_pages < index + 1:
            raise ValueError('collection_page_totals_invalid')
        if len(rows) != entry_records:
            raise ValueError('collection_page_record_count_mismatch')
        for row in rows:
            identity = row.get(plan.identity) if isinstance(row, dict) else None
            if (isinstance(identity, bool) or not isinstance(identity, (str, int))
                    or str(identity) == '' or str(identity) in identities):
                raise ValueError('collection_identity_mismatch')
            identities.add(str(identity))
        total += len(rows)
        terminal = not rows or expected_pages is not None and index + 1 >= expected_pages
        if terminal:
            if (index + 1 != len(entries) or expected_records is not None and total != expected_records
                    or expected_pages is not None and index + 1 < expected_pages):
                raise ValueError('collection_terminal_reconciliation_failure')
            actual_terminal = 'empty_page' if not rows else 'declared_total_pages'
        elif index + 1 == len(entries):
            raise ValueError('collection_terminal_reconciliation_failure')
        yield from rows
    if (report_records != total or report_expected_records != expected_records
            or report.get('terminal') != actual_terminal):
        raise ValueError('collection_terminal_reconciliation_failure')


def import_collection(database, folder: Path, adapter: Literal['cnes', 'inep']) -> dict:
    checkpoint = folder / 'collection.json'
    report = json.loads(checkpoint.read_text())
    plan = PagePlan.model_validate(report['plan'])
    if report.get('status') != 'complete' or report.get('plan_sha256') != digest(plan.model_dump()):
        raise ValueError('incomplete_collection_cannot_be_published')
    if report['records'] == 0:
        raise ValueError('empty_collection_cannot_replace_catalogue')
    source = Source(dataset=plan.dataset, url=plan.url, record_id='collection',
        reference_date=plan.reference_date, collected_at=report['finished_at'], snapshot_sha256=file_hash(checkpoint))
    result = import_places(database, collected_rows(folder, report), source, adapter)
    result.update(collection_terminal=report['terminal'], records_collected=report['records'],
                  national_catalog_certified=False)
    return result
