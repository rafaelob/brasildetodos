"""Queue contracts: quotas, leases, retry, cancellation and retention."""
import hashlib
import time

import pytest
from sqlalchemy import select

from bdt.evidence import Audit, Document, DocumentInput, initialize_extensions, register_document
from bdt.ocr_queue import (OcrJob, cancel, claim, complete, enqueue, fail, initialize_ocr_queue,
                           list_jobs, purge, reap_expired, retry, run_once)
from bdt.storage import User


@pytest.fixture
def document(database, source, tmp_path):
    initialize_extensions(database)
    initialize_ocr_queue(database)
    path = tmp_path / 'synthetic-queue-not-for-rendering.pdf'
    path.write_bytes(b'%PDF-synthetic-queue-fixture-not-a-real-document')
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with database.session() as session:
        user = User(username='queue_operator', password_hash='not-a-login', role='reviewer')
        session.add(user)
        session.flush()
        doc = register_document(session, DocumentInput(
            title='Synthetic queue fixture',
            source=source.model_copy(update={'snapshot_sha256': sha})), user.id)
        doc.state = 'extracted'
        doc.extraction = {'sha256': sha, 'extractor_version': 'synthetic-v1',
                          'original_preserved': True, 'pages': [
                              {'page': 1, 'route': 'native', 'text': 'native', 'words': [], 'tables': []},
                              {'page': 2, 'route': 'ocr_candidate', 'text': 'stamp', 'words': [], 'tables': []},
                              {'page': 3, 'route': 'ocr_candidate', 'text': '', 'words': [], 'tables': []}]}
        identity = doc.id
    return identity, path


def queue_row(database, job_id):
    with database.session() as session:
        return session.get(OcrJob, job_id)


def test_enqueue_is_private_and_does_not_touch_the_document(database, document):
    identity, path = document
    before = path.read_bytes()
    job = enqueue(database, identity, operator='queue_operator', pages=[2])
    assert job['status'] == 'queued' and job['pages'] == [2]
    assert job['result'] is None and job['can_cancel'] is True
    assert path.read_bytes() == before
    with database.session() as session:
        doc = session.get(Document, identity)
        assert doc.state == 'extracted' and 'ocr_candidate_text' not in doc.extraction['pages'][1]
        assert session.scalar(select(Audit).where(Audit.action == 'ocr_queued')) is not None
    assert 'original_sha256' not in list_jobs(database)[0]
    assert 'text' not in list_jobs(database)[0]


@pytest.mark.parametrize('pages', [[], [2, 2], [True], [0], [1001], list(range(1, 12)), [1]])
def test_enqueue_rejects_invalid_or_ineligible_pages(database, document, pages):
    identity, _ = document
    with pytest.raises(ValueError):
        enqueue(database, identity, operator='queue_operator', pages=pages)


@pytest.mark.parametrize('kwargs', [{'language': 'pt-BR'}, {'language': 'por;cmd'},
                                    {'timeout': 0}, {'timeout': True}, {'max_attempts': 4}])
def test_enqueue_rejects_invalid_budget(database, document, kwargs):
    identity, _ = document
    with pytest.raises(ValueError, match='language_timeout_or_attempts'):
        enqueue(database, identity, operator='queue_operator', pages=[2], **kwargs)


def test_document_quota_is_enforced(database, document):
    identity, _ = document
    enqueue(database, identity, operator='queue_operator', pages=[2])
    enqueue(database, identity, operator='queue_operator', pages=[3])
    with pytest.raises(ValueError, match='document_quota_exhausted'):
        enqueue(database, identity, operator='queue_operator', pages=[2])


def test_claim_complete_and_attempt_accounting(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2])
    claimed = claim(database, operator='queue_operator')
    assert claimed['id'] == job['id'] and claimed['status'] == 'running'
    assert claimed['attempts'] == 1 and claimed['original_sha256']
    done = complete(database, job['id'], operator='queue_operator',
                    result={'document_id': identity, 'pages': [2], 'public': False})
    assert done['status'] == 'succeeded' and done['result']['public'] is False
    assert queue_row(database, job['id']).lease_owner is None


def test_second_operator_cannot_complete_a_foreign_lease(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2])
    claim(database, operator='queue_operator')
    with database.session() as session:
        session.add(User(username='other_reviewer', password_hash='not-a-login', role='reviewer'))
    with pytest.raises(ValueError, match='lease_not_held'):
        complete(database, job['id'], operator='other_reviewer', result={})


def test_run_once_checks_the_original_hash_and_requeues(database, document):
    identity, path = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2], max_attempts=2)
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='hash_mismatch'):
        run_once(database, path, operator='queue_operator')
    row = queue_row(database, job['id'])
    assert row.status == 'queued' and row.attempts == 1 and row.error == 'ValueError'
    with database.session() as session:
        doc = session.get(Document, identity)
        assert 'ocr_candidate_text' not in doc.extraction['pages'][1]


def test_run_once_exhausts_budget_and_fails(database, document):
    identity, path = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2], max_attempts=1)
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError):
        run_once(database, path, operator='queue_operator')
    assert queue_row(database, job['id']).status == 'failed'


def test_cancel_running_job_prevents_publication(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2])
    claim(database, operator='queue_operator')
    assert cancel(database, job['id'], operator='queue_operator')['status'] == 'cancelled'
    with pytest.raises(ValueError, match='lease_not_held'):
        complete(database, job['id'], operator='queue_operator', result={})


def test_retry_requeues_only_terminal_jobs(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2], max_attempts=1)
    claim(database, operator='queue_operator')
    fail(database, job['id'], operator='queue_operator', error='RuntimeError')
    assert queue_row(database, job['id']).status == 'failed'
    assert retry(database, job['id'], operator='queue_operator')['status'] == 'queued'
    assert queue_row(database, job['id']).attempts == 0
    with pytest.raises(ValueError, match='not_retryable'):
        retry(database, job['id'], operator='queue_operator')


def test_expired_lease_is_reaped_without_losing_the_job(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2], max_attempts=2)
    claim(database, operator='queue_operator', lease_seconds=30)
    result = reap_expired(database, now_ts=int(time.time()) + 31)
    assert result == {'requeued': 1, 'failed': 0}
    assert queue_row(database, job['id']).status == 'queued'


def test_retention_only_deletes_terminal_metadata(database, document):
    identity, _ = document
    job = enqueue(database, identity, operator='queue_operator', pages=[2])
    assert purge(database, older_than_days=30, dry_run=True)['matched'] == 0
    claim(database, operator='queue_operator')
    complete(database, job['id'], operator='queue_operator', result={'public': False})
    future = int(time.time()) + 31 * 24 * 60 * 60
    preview = purge(database, older_than_days=30, now_ts=future, dry_run=True)
    assert preview['matched'] == 1 and preview['deleted'] == 0
    assert purge(database, older_than_days=30, now_ts=future)['deleted'] == 1
    assert queue_row(database, job['id']) is None
