"""Persistent, private OCR queue with quotas, leases, retry and retention.

The queue never stores document bytes or extracted text. A worker must present
the original file, whose SHA-256 is checked again before any recognition. Jobs
are reviewer-only, candidates remain unpublished, and every transition is
audited. No network access, LLM or automatic publication happens here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import BigInteger, Column, ForeignKey, Integer, JSON, String, delete, func, select, update

from .domain import now
from .documents import ocr_eligible
from .evidence import Document, audit, initialize_extensions, validated_extraction_pages
from .storage import Base, Database, User
from .sync import file_hash

VERSION = 1
MAX_PAGES = 10
MAX_ATTEMPTS = 3
MAX_ACTIVE_PER_DOCUMENT = 2
MAX_ACTIVE_PER_OPERATOR = 5
DEFAULT_LEASE_SECONDS = 300
DEFAULT_RETENTION_DAYS = 30
ACTIVE = ('queued', 'running')
TERMINAL = ('succeeded', 'failed', 'cancelled')
LANGUAGE = re.compile(r'[a-z]{3}(?:\+[a-z]{3})*')


class OcrQueueVersion(Base):
    __tablename__ = 'ocr_queue_version'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)


class OcrJob(Base):
    """One explicit OCR request. No document bytes, text or credentials."""

    __tablename__ = 'ocr_jobs'
    id = Column(String(36), primary_key=True)
    document_id = Column(String(36), ForeignKey('evidence_documents.id'), nullable=False, index=True)
    requested_by = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    pages = Column(JSON, nullable=False)
    language = Column(String(32), nullable=False)
    timeout = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='queued', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=2)
    lease_owner = Column(String(36), ForeignKey('users.id'))
    lease_expires_at = Column(BigInteger, index=True)
    original_sha256 = Column(String(64), nullable=False)
    extractor_version = Column(String(80), nullable=False)
    error = Column(String(80))
    result = Column(JSON)
    created_at = Column(String(40), nullable=False, index=True)
    updated_at = Column(String(40), nullable=False, index=True)


def initialize_ocr_queue(database: Database) -> None:
    """Additive migration following the same version-table contract as other modules."""
    initialize_extensions(database)
    with database.engine.begin() as connection:
        OcrQueueVersion.__table__.create(connection, checkfirst=True)
        version = connection.execute(select(OcrQueueVersion.version).where(
            OcrQueueVersion.id == 1)).scalar_one_or_none()
        if version not in (None, VERSION):
            raise RuntimeError('unsupported_ocr_queue_version')
        OcrJob.__table__.create(connection, checkfirst=True)
        if version is None:
            connection.execute(OcrQueueVersion.__table__.insert().values(id=1, version=VERSION))


def _reviewer(session, username: str) -> User:
    user = session.scalar(select(User).where(User.username == username, User.role == 'reviewer'))
    if not user:
        raise ValueError('active_reviewer_operator_required')
    return user


def _pages(value) -> list[int]:
    if (not isinstance(value, list) or not value or len(value) > MAX_PAGES
            or len(set(value)) != len(value)
            or any(type(page) is not int or page < 1 or page > 1000 for page in value)):
        raise ValueError('explicit_unique_ocr_pages_required')
    return list(value)


def _budget(language: str, timeout: int, max_attempts: int) -> tuple[str, int, int]:
    if (not isinstance(language, str) or not LANGUAGE.fullmatch(language)
            or type(timeout) is not int or not 1 <= timeout <= 300
            or type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS):
        raise ValueError('invalid_ocr_language_timeout_or_attempts')
    return language, timeout, max_attempts


def _iso(epoch: int | None) -> str | None:
    return None if epoch is None else datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def job_payload(row: OcrJob, *, viewer_id: str | None = None) -> dict:
    """Expose queue metadata only; never a path, digest of a document or text."""
    return {
        'id': row.id,
        'document_id': row.document_id,
        'pages': list(row.pages),
        'language': row.language,
        'timeout': row.timeout,
        'status': row.status,
        'attempts': row.attempts,
        'max_attempts': row.max_attempts,
        'error': row.error,
        'result': row.result,
        'created_at': row.created_at,
        'updated_at': row.updated_at,
        'lease_expires_at': _iso(row.lease_expires_at),
        'can_cancel': row.status in ACTIVE and (viewer_id is None or viewer_id == row.requested_by),
        'can_retry': row.status in ('failed', 'cancelled'),
    }


def _validate_document(session, document_id: str, pages: list[int]) -> tuple[Document, str, str]:
    document = session.get(Document, document_id)
    if not document or document.state != 'extracted' or not document.extraction:
        raise ValueError('document_must_have_completed_native_inspection')
    expected = document.source.get('snapshot_sha256') if isinstance(document.source, dict) else None
    stored = validated_extraction_pages(document.extraction, expected)
    selected = {page['page']: page for page in stored}
    for number in pages:
        page = selected.get(number)
        if page is None or not ocr_eligible(page):
            raise ValueError('selected_page_is_not_an_inspected_ocr_candidate')
        if page.get('ocr_candidate_text'):
            raise ValueError('page_already_has_ocr_requires_explicit_review')
    version = document.extraction.get('extractor_version')
    if not isinstance(version, str) or not 1 <= len(version) <= 80:
        version = 'native-extractor-unversioned'
    return document, expected, version


def enqueue(database: Database, document_id: str, *, operator: str, pages: list[int],
            language: str = 'por', timeout: int = 90, max_attempts: int = 2,
            max_active_per_document: int = MAX_ACTIVE_PER_DOCUMENT,
            max_active_per_operator: int = MAX_ACTIVE_PER_OPERATOR) -> dict:
    """Queue one explicit OCR request without touching the document or original."""
    pages = _pages(pages)
    language, timeout, max_attempts = _budget(language, timeout, max_attempts)
    if (type(max_active_per_document) is not int or not 1 <= max_active_per_document <= 10
            or type(max_active_per_operator) is not int or not 1 <= max_active_per_operator <= 20):
        raise ValueError('invalid_ocr_quota')
    initialize_ocr_queue(database)
    with database.session() as session:
        user = _reviewer(session, operator)
        document, expected, version = _validate_document(session, document_id, pages)
        active_document = session.scalar(select(func.count()).select_from(OcrJob).where(
            OcrJob.document_id == document_id, OcrJob.status.in_(ACTIVE)))
        active_operator = session.scalar(select(func.count()).select_from(OcrJob).where(
            OcrJob.requested_by == user.id, OcrJob.status.in_(ACTIVE)))
        if active_document >= max_active_per_document:
            raise ValueError('ocr_document_quota_exhausted')
        if active_operator >= max_active_per_operator:
            raise ValueError('ocr_operator_quota_exhausted')
        row = OcrJob(id=os.urandom(16).hex(), document_id=document.id, requested_by=user.id,
                     pages=pages, language=language, timeout=timeout, status='queued', attempts=0,
                     max_attempts=max_attempts, original_sha256=expected, extractor_version=version,
                     created_at=now(), updated_at=now())
        session.add(row)
        session.flush()
        audit(session, user.id, 'document', document.id, 'ocr_queued', job=row.id,
              pages=pages, language=language)
        return job_payload(row, viewer_id=user.id)


def _claim(database: Database, operator: str, lease_seconds: int) -> dict | None:
    initialize_ocr_queue(database)
    with database.session() as session:
        user = _reviewer(session, operator)
        for _ in range(5):
            candidate = session.scalar(select(OcrJob.id).where(
                OcrJob.status == 'queued', OcrJob.attempts < OcrJob.max_attempts
            ).order_by(OcrJob.created_at, OcrJob.id).limit(1))
            if candidate is None:
                return None
            expires = int(time.time()) + lease_seconds
            claimed = session.execute(update(OcrJob).where(
                OcrJob.id == candidate, OcrJob.status == 'queued',
                OcrJob.attempts < OcrJob.max_attempts
            ).values(status='running', attempts=OcrJob.attempts + 1, lease_owner=user.id,
                     lease_expires_at=expires, updated_at=now(), error=None))
            if claimed.rowcount == 1:
                row = session.get(OcrJob, candidate)
                audit(session, user.id, 'document', row.document_id, 'ocr_claimed', job=row.id,
                      attempt=row.attempts)
                return job_payload(row, viewer_id=user.id) | {'original_sha256': row.original_sha256,
                                                              'extractor_version': row.extractor_version}
        raise ValueError('ocr_queue_claim_conflict')


def claim(database: Database, *, operator: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict | None:
    if type(lease_seconds) is not int or not 30 <= lease_seconds <= 3600:
        raise ValueError('invalid_ocr_lease_seconds')
    reap_expired(database)
    return _claim(database, operator, lease_seconds)


def _lease_owner(session, job_id: str, operator: str) -> tuple[OcrJob, User]:
    user = _reviewer(session, operator)
    row = session.get(OcrJob, job_id)
    if not row:
        raise ValueError('ocr_job_not_found')
    if row.status != 'running' or row.lease_owner != user.id:
        raise ValueError('ocr_job_lease_not_held')
    return row, user


def complete(database: Database, job_id: str, *, operator: str, result: dict) -> dict:
    """Complete only the job whose lease this operator still holds."""
    if not isinstance(result, dict):
        raise ValueError('invalid_ocr_job_result')
    initialize_ocr_queue(database)
    with database.session() as session:
        row, user = _lease_owner(session, job_id, operator)
        if row.lease_expires_at is None or row.lease_expires_at < int(time.time()):
            raise ValueError('ocr_job_lease_expired')
        changed = session.execute(update(OcrJob).where(
            OcrJob.id == job_id, OcrJob.status == 'running', OcrJob.lease_owner == user.id
        ).values(status='succeeded', result=result, error=None, lease_owner=None,
                 lease_expires_at=None, updated_at=now()))
        if changed.rowcount != 1:
            raise ValueError('ocr_job_lease_lost')
        audit(session, user.id, 'document', row.document_id, 'ocr_job_succeeded', job=row.id,
              attempts=row.attempts)
        session.refresh(row)
        return job_payload(row, viewer_id=user.id)


def fail(database: Database, job_id: str, *, operator: str, error: str) -> dict:
    """Retry until the declared attempt budget is exhausted; never store text."""
    if not isinstance(error, str) or not 1 <= len(error) <= 80:
        raise ValueError('invalid_ocr_job_error')
    initialize_ocr_queue(database)
    with database.session() as session:
        row, user = _lease_owner(session, job_id, operator)
        status = 'queued' if row.attempts < row.max_attempts else 'failed'
        changed = session.execute(update(OcrJob).where(
            OcrJob.id == job_id, OcrJob.status == 'running', OcrJob.lease_owner == user.id
        ).values(status=status, error=error, lease_owner=None, lease_expires_at=None,
                 updated_at=now()))
        if changed.rowcount != 1:
            raise ValueError('ocr_job_lease_lost')
        audit(session, user.id, 'document', row.document_id,
              'ocr_job_retry_queued' if status == 'queued' else 'ocr_job_failed',
              job=row.id, attempts=row.attempts, error=error)
        session.refresh(row)
        return job_payload(row, viewer_id=user.id)


def cancel(database: Database, job_id: str, *, operator: str) -> dict:
    """Cancel a queued/running job; a running worker cannot publish afterwards."""
    initialize_ocr_queue(database)
    with database.session() as session:
        user = _reviewer(session, operator)
        row = session.get(OcrJob, job_id)
        if not row:
            raise ValueError('ocr_job_not_found')
        if row.status not in ACTIVE:
            raise ValueError('ocr_job_not_cancellable')
        changed = session.execute(update(OcrJob).where(
            OcrJob.id == job_id, OcrJob.status.in_(ACTIVE)
        ).values(status='cancelled', lease_owner=None, lease_expires_at=None, updated_at=now()))
        if changed.rowcount != 1:
            raise ValueError('ocr_job_cancel_conflict')
        audit(session, user.id, 'document', row.document_id, 'ocr_job_cancelled', job=row.id)
        session.refresh(row)
        return job_payload(row, viewer_id=user.id)


def retry(database: Database, job_id: str, *, operator: str) -> dict:
    """Requeue a terminal job with a fresh attempt budget; the original hash is unchanged."""
    initialize_ocr_queue(database)
    with database.session() as session:
        user = _reviewer(session, operator)
        row = session.get(OcrJob, job_id)
        if not row:
            raise ValueError('ocr_job_not_found')
        if row.status not in ('failed', 'cancelled'):
            raise ValueError('ocr_job_not_retryable')
        changed = session.execute(update(OcrJob).where(
            OcrJob.id == job_id, OcrJob.status.in_(('failed', 'cancelled'))
        ).values(status='queued', attempts=0, error=None, result=None, lease_owner=None,
                 lease_expires_at=None, updated_at=now()))
        if changed.rowcount != 1:
            raise ValueError('ocr_job_retry_conflict')
        audit(session, user.id, 'document', row.document_id, 'ocr_job_requeued', job=row.id)
        session.refresh(row)
        return job_payload(row, viewer_id=user.id)


def reap_expired(database: Database, *, now_ts: int | None = None) -> dict:
    """Return expired leases to the queue or exhaust their attempt budget."""
    initialize_ocr_queue(database)
    current = int(time.time() if now_ts is None else now_ts)
    retried = failed = 0
    with database.session() as session:
        rows = list(session.scalars(select(OcrJob).where(
            OcrJob.status == 'running', OcrJob.lease_expires_at.is_not(None),
            OcrJob.lease_expires_at < current)))
        for row in rows:
            status = 'queued' if row.attempts < row.max_attempts else 'failed'
            changed = session.execute(update(OcrJob).where(
                OcrJob.id == row.id, OcrJob.status == 'running'
            ).values(status=status, error='lease_expired', lease_owner=None,
                     lease_expires_at=None, updated_at=now()))
            if changed.rowcount == 1:
                retried += status == 'queued'
                failed += status == 'failed'
                audit(session, row.requested_by, 'document', row.document_id,
                      'ocr_job_lease_reaped', job=row.id, next_status=status)
    return {'requeued': retried, 'failed': failed}


def purge(database: Database, *, older_than_days: int = DEFAULT_RETENTION_DAYS,
          now_ts: int | None = None, dry_run: bool = False) -> dict:
    """Delete terminal job metadata after retention; extracted text is not here."""
    if type(older_than_days) is not int or not 1 <= older_than_days <= 3650:
        raise ValueError('invalid_ocr_retention_days')
    initialize_ocr_queue(database)
    cutoff = (datetime.fromtimestamp(int(time.time() if now_ts is None else now_ts), timezone.utc)
              - timedelta(days=older_than_days)).isoformat()
    with database.session() as session:
        condition = (OcrJob.status.in_(TERMINAL), OcrJob.updated_at < cutoff)
        count = session.scalar(select(func.count()).select_from(OcrJob).where(*condition))
        if not dry_run and count:
            session.execute(delete(OcrJob).where(*condition))
        return {'retention_days': older_than_days, 'cutoff': cutoff, 'matched': count,
                'deleted': 0 if dry_run else count, 'dry_run': dry_run}


def list_jobs(database: Database, *, status: str | None = None, limit: int = 50) -> list[dict]:
    if status is not None and status not in ACTIVE + TERMINAL:
        raise ValueError('invalid_ocr_job_status')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('invalid_ocr_job_limit')
    initialize_ocr_queue(database)
    with database.session() as session:
        statement = select(OcrJob).order_by(OcrJob.created_at.desc(), OcrJob.id).limit(limit)
        if status:
            statement = statement.where(OcrJob.status == status)
        return [job_payload(row) for row in session.scalars(statement)]


def run_once(database: Database, path: Path, *, operator: str,
             lease_seconds: int = DEFAULT_LEASE_SECONDS, engine=None) -> dict | None:
    """Claim one job, verify the original hash, run the existing OCR contract."""
    from .document_ocr import process_ocr

    job = claim(database, operator=operator, lease_seconds=lease_seconds)
    if job is None:
        return None
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 32 * 1024 ** 2:
            raise ValueError('ocr_input_missing_or_too_large')
        if file_hash(path) != job['original_sha256']:
            raise ValueError('document_ocr_hash_mismatch')
        options = {'language': job['language'], 'timeout': job['timeout']}
        if engine is not None:
            options['engine'] = engine
        result = process_ocr(database, job['document_id'], path, operator=operator,
                             pages=job['pages'], **options)
        return complete(database, job['id'], operator=operator,
                        result={'document_id': result['document_id'], 'pages': result['pages'],
                                'review_required': True, 'public': False})
    except BaseException as error:
        try:
            fail(database, job['id'], operator=operator, error=type(error).__name__)
        except ValueError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=os.getenv('BDT_DATABASE_URL', 'sqlite:///data/bdt.db'))
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('enqueue')
    add.add_argument('document')
    add.add_argument('--operator', required=True)
    add.add_argument('--pages', type=int, nargs='+', required=True)
    add.add_argument('--language', default='por')
    add.add_argument('--timeout', type=int, default=90)
    add.add_argument('--max-attempts', type=int, default=2)
    run = commands.add_parser('run')
    run.add_argument('--operator', required=True)
    run.add_argument('--path', type=Path, required=True)
    run.add_argument('--lease-seconds', type=int, default=DEFAULT_LEASE_SECONDS)
    listing = commands.add_parser('list')
    listing.add_argument('--status')
    listing.add_argument('--limit', type=int, default=50)
    for name in ('cancel', 'retry'):
        item = commands.add_parser(name)
        item.add_argument('job')
        item.add_argument('--operator', required=True)
    commands.add_parser('reap')
    clean = commands.add_parser('purge')
    clean.add_argument('--days', type=int, default=DEFAULT_RETENTION_DAYS)
    clean.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    database = Database(args.database)
    database.initialize()
    try:
        if args.command == 'enqueue':
            result = enqueue(database, args.document, operator=args.operator, pages=args.pages,
                             language=args.language, timeout=args.timeout,
                             max_attempts=args.max_attempts)
        elif args.command == 'run':
            result = run_once(database, args.path, operator=args.operator,
                              lease_seconds=args.lease_seconds)
        elif args.command == 'list':
            result = list_jobs(database, status=args.status, limit=args.limit)
        elif args.command == 'cancel':
            result = cancel(database, args.job, operator=args.operator)
        elif args.command == 'retry':
            result = retry(database, args.job, operator=args.operator)
        elif args.command == 'reap':
            result = reap_expired(database)
        else:
            result = purge(database, older_than_days=args.days, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        database.engine.dispose()


if __name__ == '__main__':
    main()
