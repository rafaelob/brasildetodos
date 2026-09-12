"""Document provenance and independently reviewed place/resource relationships.

Full extraction remains restricted. Reviewed links never allocate money or
replace official place records automatically.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field, model_validator
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text, select, update
from .domain import Source, StrictModel, digest, now
from .storage import Base


class ExtensionVersion(Base):
    __tablename__ = 'extension_version'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)


class Resource(Base):
    __tablename__ = 'resources'
    id = Column(String(200), primary_key=True)
    kind = Column(String(20), nullable=False, index=True)
    municipality_id = Column(String(7), ForeignKey('municipalities.id'), index=True)
    title = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False)
    source = Column(JSON, nullable=False)


class Document(Base):
    __tablename__ = 'evidence_documents'
    id = Column(String(64), primary_key=True)
    title = Column(String(300), nullable=False)
    source = Column(JSON, nullable=False)
    author_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    created_at = Column(String(40), nullable=False, default=now)
    state = Column(String(20), nullable=False, default='registered')
    extraction = Column(JSON)


class Link(Base):
    __tablename__ = 'evidence_links'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    place_id = Column(String(180), ForeignKey('places.id'), nullable=False, index=True)
    resource_id = Column(String(200), ForeignKey('resources.id'), nullable=False, index=True)
    document_id = Column(String(64), ForeignKey('evidence_documents.id'), nullable=False)
    page = Column(Integer, nullable=False)
    excerpt = Column(Text, nullable=False)
    justification = Column(Text, nullable=False)
    author_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    reviewer_id = Column(String(36), ForeignKey('users.id'))
    status = Column(String(20), nullable=False, default='candidate', index=True)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(String(40), nullable=False, default=now)
    reviewed_at = Column(String(40))
    review_note = Column(Text)


class Audit(Base):
    __tablename__ = 'moderation_audit'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    entity = Column(String(30), nullable=False)
    entity_id = Column(String(200), nullable=False, index=True)
    action = Column(String(40), nullable=False)
    at = Column(String(40), nullable=False, default=now)
    detail = Column(JSON, nullable=False, default=dict)


MAX_PNCP_OBJECT_CHARS = 16384  # Local processing budget, not a claimed PNCP maximum.


class ResourceInput(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9_-]+:[A-Za-z0-9._/-]+$', max_length=200)
    kind: Literal['contract', 'instrument', 'proposal', 'work']
    title: str = Field(min_length=1, max_length=MAX_PNCP_OBJECT_CHARS)
    municipality_id: str | None = Field(default=None, pattern=r'^[0-9]{7}$')
    source: Source
    attributes: dict = Field(default_factory=dict)

    @model_validator(mode='after')
    def bounded_attributes(self):
        if not 5 <= len(self.title) <= 4000 and not (self.kind == 'contract'
                and self.source.dataset == 'pncp_contracts'
                and self.attributes.get('profile') == 'pncp_contracts'):
            raise ValueError('resource_title_profile_limit')
        if len(json.dumps(self.attributes, ensure_ascii=False)) > 16000:
            raise ValueError('resource_metadata_too_large')
        return self


class DocumentInput(StrictModel):
    title: str = Field(min_length=5, max_length=300)
    source: Source


class LinkInput(StrictModel):
    place_id: str = Field(max_length=180)
    resource_id: str = Field(max_length=200)
    document_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    page: int = Field(ge=1, le=1000, strict=True)
    excerpt: str = Field(min_length=10, max_length=1500)
    justification: str = Field(min_length=20, max_length=2000)


class Decision(StrictModel):
    decision: Literal['reviewed', 'rejected', 'retracted']
    note: str = Field(min_length=20, max_length=2000)
    expected_revision: int = Field(ge=1, strict=True)
    public_excerpt_checked: bool = False


def initialize_extensions(database):
    """Additive migration; never replace existing data."""
    with database.engine.begin() as connection:
        ExtensionVersion.__table__.create(connection, checkfirst=True)
        version = connection.execute(select(ExtensionVersion.version).where(ExtensionVersion.id == 1)).scalar_one_or_none()
        if version not in (None, 1):
            raise RuntimeError('Unsupported extension schema; reviewed migration required')
        for table in (Resource.__table__, Document.__table__, Link.__table__, Audit.__table__):
            table.create(connection, checkfirst=True)
        if version is None:
            connection.execute(ExtensionVersion.__table__.insert().values(id=1, version=1))


def audit(session, user_id: str, entity: str, identity: str, action: str, **detail):
    session.add(Audit(actor_id=user_id, entity=entity, entity_id=identity, action=action, detail=detail))


def register_document(session, body: DocumentInput, author_id: str) -> Document:
    identity = digest([body.source.dataset, body.source.record_id, body.source.snapshot_sha256])
    existing = session.get(Document, identity)
    if existing:
        return existing
    row = Document(id=identity, title=body.title, source=body.source.model_dump(mode='json'), author_id=author_id)
    session.add(row)
    session.flush()
    audit(session, author_id, 'document', identity, 'registered')
    return row


def store_extraction(database, document_id: str, path: Path, *, max_pages: int = 100) -> dict:
    """Operator-only extraction; hashes verify bytes, not legal authenticity."""
    from .documents import inspect_pdf
    with database.session() as session:
        doc = session.get(Document, document_id)
        if not doc:
            raise ValueError('document_not_found')
        expected = doc.source['snapshot_sha256']
        author_id = doc.author_id
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    if h.hexdigest() != expected:
        raise ValueError('document_hash_mismatch')

    def receipt(extraction):
        if (not isinstance(extraction, dict) or extraction.get('sha256') != expected
                or not isinstance(extraction.get('pages'), list)):
            raise ValueError('stored_document_extraction_invalid')
        return {'document_id': document_id, 'pages': len(extraction['pages']),
                'state': 'extracted', 'public': False}

    with database.session() as session:
        doc = session.get(Document, document_id)
        if doc.state == 'extracted':
            return receipt(doc.extraction)
        if doc.state != 'registered' or doc.extraction is not None:
            raise ValueError('document_extraction_state_conflict')
    extraction = inspect_pdf(path, max_pages=max_pages)
    if extraction['sha256'] != expected:
        raise ValueError('document_changed_during_extraction')
    extraction.pop('filename', None)
    with database.session() as session:
        changed = session.execute(update(Document).where(
            Document.id == document_id, Document.state == 'registered').values(
                extraction=extraction, state='extracted'))
        if changed.rowcount != 1:
            current = session.get(Document, document_id)
            if current is not None:
                session.refresh(current)
            if current is not None and current.state == 'extracted':
                return receipt(current.extraction)
            raise ValueError('document_extraction_state_conflict')
        audit(session, author_id, 'document', document_id, 'native_extracted', pages=len(extraction['pages']))
    return receipt(extraction)


def validate_excerpt(document: Document, page: int, excerpt: str):
    if document.state != 'extracted' or not document.extraction:
        raise ValueError('document_not_extracted')
    selected = next((p for p in document.extraction.get('pages', []) if p['page'] == page), None)
    if not selected:
        raise ValueError('page_not_found')
    normalize = lambda value: re.sub(r'\s+', ' ', value).strip()
    texts = [selected.get('text', ''), selected.get('ocr_candidate_text', '')]
    if not any(normalize(excerpt) in normalize(text) for text in texts):
        raise ValueError('excerpt_not_found')


def link_payload(row: Link, *, public: bool = False) -> dict:
    value = {'id': row.id, 'place_id': row.place_id, 'resource_id': row.resource_id, 'document_id': row.document_id,
             'page': row.page, 'excerpt': row.excerpt, 'status': row.status, 'revision': row.revision,
             'created_at': row.created_at, 'reviewed_at': row.reviewed_at}
    if not public:
        value.update(justification=row.justification, review_note=row.review_note)
    return value
