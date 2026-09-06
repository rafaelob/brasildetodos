"""Explicit local OCR for already inspected, privately registered PDF pages.

No network fetch, no automatic publication, no LLM. Originals and native text
remain unchanged. A compare-and-swap lease prevents concurrent OCR overwrites.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

from .documents import candidates, ocr_page
from .domain import now
from .evidence import Document, audit, initialize_extensions
from .storage import Database, User
from .sync import file_hash


def _reviewer(session, username: str):
    user = session.scalar(select(User).where(User.username == username, User.role == 'reviewer'))
    if not user:
        raise ValueError('active_reviewer_operator_required')
    return user


def process_ocr(database, document_id: str, path: Path, *, operator: str, pages: list[int],
                language: str = 'por', timeout: int = 90, engine=ocr_page) -> dict:
    """Only inspected OCR candidates are eligible; all selected pages commit together."""
    if (not pages or len(pages) > 10 or len(set(pages)) != len(pages)
            or any(type(p) is not int or p < 1 or p > 1000 for p in pages)):
        raise ValueError('explicit_unique_ocr_pages_required')
    if not re.fullmatch(r'[a-z]{3}(?:\+[a-z]{3})*', language) or type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError('invalid_ocr_language_or_timeout')
    if not path.is_file() or path.stat().st_size > 32 * 1024 ** 2:
        raise ValueError('ocr_input_missing_or_too_large')
    original_hash = file_hash(path)
    lease = 'ocr_' + uuid4().hex[:12]
    initialize_extensions(database)
    with database.session() as session:
        user = _reviewer(session, operator)
        actor_id = user.id
        doc = session.get(Document, document_id)
        if not doc or doc.state != 'extracted' or not doc.extraction:
            raise ValueError('document_must_have_completed_native_inspection')
        if doc.source['snapshot_sha256'] != original_hash or doc.extraction.get('sha256') != original_hash:
            raise ValueError('document_ocr_hash_mismatch')
        extraction = copy.deepcopy(doc.extraction)
        selected = {page['page']: page for page in extraction.get('pages', [])}
        for number in pages:
            if number not in selected or selected[number].get('route') not in {'ocr_candidate', 'review_encoding'}:
                raise ValueError('selected_page_is_not_an_inspected_ocr_candidate')
            if selected[number].get('ocr_candidate_text'):
                raise ValueError('page_already_has_ocr_requires_explicit_review')
        claimed = session.execute(update(Document).where(Document.id == document_id, Document.state == 'extracted')
                                  .values(state=lease))
        if claimed.rowcount != 1:
            raise ValueError('document_ocr_already_running')
        audit(session, actor_id, 'document', document_id, 'ocr_started', pages=pages, language=language, lease=lease)
    try:
        for number in pages:
            text = engine(path, number, language=language, timeout=timeout)
            if not isinstance(text, str) or not text.strip() or len(text) > 200_000:
                raise ValueError('ocr_text_missing_or_budget')
            page = selected[number]
            page['ocr_candidate_text'] = text
            page['ocr_candidates'] = candidates(text)
            page['ocr_provenance'] = {'original_sha256': original_hash, 'page': number,
                'language': language, 'method': 'operator_selected_local_ocr',
                'completed_at': now(), 'review_required': True, 'publication_allowed': False}
        if file_hash(path) != original_hash:
            raise ValueError('document_changed_during_ocr')
        with database.session() as session:
            _reviewer(session, operator)  # A revoked operator cannot complete publication to the workbench.
            claimed = session.execute(update(Document).where(Document.id == document_id, Document.state == lease)
                                      .values(extraction=extraction, state='extracted'))
            if claimed.rowcount != 1:
                raise ValueError('document_ocr_lease_lost')
            audit(session, actor_id, 'document', document_id, 'ocr_completed', pages=pages, language=language)
    except BaseException as error:
        with database.session() as session:
            session.execute(update(Document).where(Document.id == document_id, Document.state == lease).values(state='extracted'))
            audit(session, actor_id, 'document', document_id, 'ocr_failed', error_type=type(error).__name__)
        raise
    return {'document_id': document_id, 'pages': pages, 'state': 'extracted',
            'original_sha256': original_hash, 'original_preserved': True, 'public': False,
            'review_required': True}


def recover_lease(database, document_id: str, *, operator: str, expected_lease: str) -> dict:
    """Operator must first stop the abandoned process. Exact token prevents blind resets."""
    if not re.fullmatch(r'ocr_[a-f0-9]{12}', expected_lease):
        raise ValueError('invalid_expected_ocr_lease')
    initialize_extensions(database)
    with database.session() as session:
        actor = _reviewer(session, operator)
        changed = session.execute(update(Document).where(Document.id == document_id, Document.state == expected_lease)
                                  .values(state='extracted'))
        if changed.rowcount != 1:
            raise ValueError('ocr_lease_not_current')
        audit(session, actor.id, 'document', document_id, 'ocr_lease_recovered', expected_lease=expected_lease)
    return {'document_id': document_id, 'state': 'extracted', 'public': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--document', required=True)
    parser.add_argument('--operator', required=True)
    parser.add_argument('--path', type=Path)
    parser.add_argument('--pages', type=int, nargs='+')
    parser.add_argument('--language', default='por')
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--recover-lease')
    args = parser.parse_args(argv)
    if bool(args.recover_lease) == bool(args.path or args.pages):
        parser.error('select recovery OR an existing PDF and explicit pages')
    if not args.recover_lease and (not args.path or not args.pages):
        parser.error('--path and --pages are required together')
    database = Database(args.database)
    database.initialize()
    try:
        if args.recover_lease:
            result = recover_lease(database, args.document, operator=args.operator, expected_lease=args.recover_lease)
        else:
            result = process_ocr(database, args.document, args.path, operator=args.operator,
                                 pages=args.pages, language=args.language, timeout=args.timeout)
        print(json.dumps(result, ensure_ascii=False))
    finally:
        database.engine.dispose()


if __name__ == '__main__':
    main()
