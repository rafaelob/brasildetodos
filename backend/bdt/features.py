"""Application features with explicit authentication and reviewed publication."""
from __future__ import annotations
import os
import secrets
from typing import Literal
from fastapi import Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import delete, func, select, update
from .domain import StrictModel, now
from .evidence import (Audit, Decision, Document, DocumentInput, Link, LinkInput, Resource,
    ResourceInput, audit, initialize_extensions, link_payload, register_document, validate_excerpt)
from .geo import viewport
from .storage import LoginSession, Municipality, Observation, Place, User
from . import photos


class Note(StrictModel):
    note: str = Field(min_length=20, max_length=1000)


class DeleteAccount(StrictModel):
    password: str = Field(min_length=12, max_length=128)
    confirmed: Literal[True]


def install(app, database, current_user, reviewer, rate_limit, check_password):
    initialize_extensions(database)
    from .groups import account_export as export_groups, install as install_groups
    install_groups(app, database, current_user, rate_limit)
    from .resource_routes import install as install_resource_routes
    install_resource_routes(app, database)

    @app.get('/api/map/viewport')
    def map_view(bbox: str = Query(..., max_length=150), zoom: int = Query(4, ge=0, le=20),
                 q: str = Query('', max_length=200), kind: Literal['school', 'health', 'work'] | None = None,
                 state: str | None = Query(None, pattern=r'^[A-Z]{2}$'),
                 municipality_id: str | None = Query(None, pattern=r'^[0-9]{7}$')):
        try:
            return viewport(database, bbox, zoom=zoom, q=q, kind=kind, state=state, municipality_id=municipality_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.get('/api/resources')
    def resources(municipality_id: str | None = Query(None, pattern=r'^[0-9]{7}$'),
                  kind: Literal['contract', 'instrument', 'proposal', 'work'] | None = None,
                  page: int = Query(1, ge=1, le=100000), limit: int = Query(30, ge=1, le=100),
                  q: str = Query('', max_length=200), profile: str | None = Query(None, max_length=80),
                  state: str | None = Query(None, pattern=r'^[A-Z]{2}$')):
        from .resource_routes import browse
        try:
            return browse(database, municipality_id=municipality_id, kind=kind,
                          page=page, limit=limit, q=q, profile=profile, state=state)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.post('/api/workbench/resources', status_code=201)
    def resource_register(body: ResourceInput, request: Request, user=Depends(reviewer)):
        rate_limit(request, 'evidence_write', 100)
        with database.session() as session:
            if body.municipality_id and not session.get(Municipality, body.municipality_id):
                raise HTTPException(422, 'municipality_not_found')
            payload = body.model_dump(mode='json')
            row = session.get(Resource, body.id)
            if row:
                if row.payload != payload:
                    raise HTTPException(409, 'resource_revision_requires_new_id')
                return row.payload
            session.add(Resource(id=body.id, kind=body.kind, municipality_id=body.municipality_id,
                title=body.title, payload=payload, source=payload['source']))
            audit(session, user['id'], 'resource', body.id, 'registered')
            return payload

    @app.get('/api/workbench/documents')
    def documents(page: int = Query(1, ge=1), user=Depends(reviewer)):
        with database.session() as session:
            rows = session.scalars(select(Document).order_by(Document.created_at.desc(), Document.id).offset((page-1)*50).limit(50))
            return [{'id': d.id, 'title': d.title, 'source': d.source, 'state': d.state,
                     'pages': len((d.extraction or {}).get('pages', []))} for d in rows]

    @app.post('/api/workbench/documents', status_code=201)
    def document_register(body: DocumentInput, request: Request, user=Depends(reviewer)):
        rate_limit(request, 'evidence_write', 100)
        with database.session() as session:
            row = register_document(session, body, user['id'])
            return {'id': row.id, 'state': row.state, 'source': row.source, 'title': row.title}

    @app.get('/api/workbench/documents/{document_id}/pages/{page}')
    def document_page(document_id: str, page: int, user=Depends(reviewer)):
        with database.session() as session:
            row = session.get(Document, document_id)
            if not row:
                raise HTTPException(404, 'document_not_found')
            value = next((p for p in (row.extraction or {}).get('pages', []) if p['page'] == page), None)
            if value is None:
                raise HTTPException(404, 'page_not_found')
            return {'document_id': document_id, 'source': row.source, 'page': value, 'public': False}

    @app.get('/api/workbench/links')
    def link_queue(status: Literal['candidate', 'reviewed', 'rejected', 'retracted'] = 'candidate',
                   page: int = Query(1, ge=1), user=Depends(reviewer)):
        with database.session() as session:
            rows = session.scalars(select(Link).where(Link.status == status).order_by(Link.created_at, Link.id).offset((page-1)*50).limit(50))
            return [link_payload(row) | {'can_review': row.author_id != user['id']} for row in rows]

    @app.post('/api/workbench/links', status_code=201)
    def propose_link(body: LinkInput, request: Request, user=Depends(reviewer)):
        rate_limit(request, 'evidence_write', 100)
        with database.session() as session:
            if not session.get(Place, body.place_id) or not session.get(Resource, body.resource_id):
                raise HTTPException(404, 'place_or_resource_not_found')
            doc = session.get(Document, body.document_id)
            if not doc:
                raise HTTPException(404, 'document_not_found')
            try:
                validate_excerpt(doc, body.page, body.excerpt)
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            row = Link(**body.model_dump(), author_id=user['id'])
            session.add(row); session.flush()
            audit(session, user['id'], 'link', row.id, 'proposed')
            return link_payload(row)

    @app.post('/api/workbench/links/{link_id}/review')
    def review_link(link_id: str, body: Decision, user=Depends(reviewer)):
        with database.session() as session:
            row = session.get(Link, link_id)
            if not row:
                raise HTTPException(404, 'link_not_found')
            if row.author_id == user['id']:
                raise HTTPException(403, 'independent_review_required')
            allowed = (row.status == 'candidate' and body.decision in {'reviewed', 'rejected'}) or (row.status == 'reviewed' and body.decision == 'retracted')
            if not allowed or row.revision != body.expected_revision:
                raise HTTPException(409, 'review_conflict')
            if body.decision == 'reviewed' and not body.public_excerpt_checked:
                raise HTTPException(422, 'public_excerpt_review_required')
            result = session.execute(update(Link).where(Link.id == link_id, Link.revision == body.expected_revision,
                Link.status == row.status).values(status=body.decision, reviewer_id=user['id'], reviewed_at=now(),
                review_note=body.note, revision=body.expected_revision + 1))
            if result.rowcount != 1:
                raise HTTPException(409, 'review_conflict')
            audit(session, user['id'], 'link', link_id, body.decision, revision=body.expected_revision + 1)
            session.refresh(row)
            return link_payload(row)

    @app.get('/api/place-links/{place_id:path}')
    def public_links(place_id: str):
        with database.session() as session:
            if not session.get(Place, place_id):
                raise HTTPException(404, 'place_not_found')
            rows = session.execute(select(Link, Resource, Document).join(Resource, Link.resource_id == Resource.id)
                .join(Document, Link.document_id == Document.id).where(Link.place_id == place_id, Link.status == 'reviewed')
                .order_by(Link.reviewed_at.desc()).limit(100)).all()
            return [link_payload(link, public=True) | {'resource': resource.payload,
                'document': {'title': doc.title, 'source': doc.source}} for link, resource, doc in rows]

    @app.post('/api/observations/{observation_id}/withdraw')
    def withdraw(observation_id: str, user=Depends(current_user)):
        with database.session() as session:
            row = session.get(Observation, observation_id)
            if not row or row.author_id != user['id']:
                raise HTTPException(404, 'observation_not_found')
            if row.status == 'withdrawn':
                return {'id': observation_id, 'status': 'withdrawn'}
            previous_status = row.status
            if previous_status not in {'pending', 'approved', 'rejected'}:
                raise HTTPException(409, 'observation_not_withdrawable')
            result = session.execute(update(Observation).where(
                Observation.id == observation_id,
                Observation.author_id == user['id'],
                Observation.status == previous_status,
            ).values(status='withdrawn'))
            if result.rowcount != 1:
                session.expire(row)
                session.refresh(row)
                if row.status == 'withdrawn':
                    return {'id': observation_id, 'status': 'withdrawn'}
                raise HTTPException(409, 'observation_not_withdrawable')
            photos.erase_observation(session, observation_id)
            audit(session, user['id'], 'observation', observation_id, 'author_withdrawal')
            return {'id': observation_id, 'status': 'withdrawn'}

    @app.post('/api/moderation/observations/{observation_id}/retract')
    def retract(observation_id: str, body: Note, user=Depends(reviewer)):
        with database.session() as session:
            result = session.execute(update(Observation).where(Observation.id == observation_id, Observation.status == 'approved')
                .values(status='retracted', reviewed_at=now(), reviewer_id=user['id'], review_note=body.note))
            if result.rowcount != 1:
                raise HTTPException(409, 'not_published')
            photos.erase_observation(session, observation_id)
            audit(session, user['id'], 'observation', observation_id, 'retracted')
            return {'id': observation_id, 'status': 'retracted'}

    @app.get('/api/account/export')
    def export_account(user=Depends(current_user)):
        with database.session() as session:
            observations = session.scalars(select(Observation).where(Observation.author_id == user['id']).order_by(Observation.created_at))
            links = session.scalars(select(Link).where(Link.author_id == user['id']).order_by(Link.created_at))
            return {'username': user['username'], 'exported_at': now(),
                'observations': [{'id': row.id, 'status': row.status, 'created_at': row.created_at,
                    'observation': row.payload, 'review_note': row.review_note} for row in observations],
                'proposed_links': [link_payload(row) for row in links],
                'photos': photos.export_account(session, user['id']), 'credentials_included': False,
                'collaboration': export_groups(session, user['id'])}

    @app.post('/api/account/delete')
    def delete_account(body: DeleteAccount, request: Request, response: Response, user=Depends(current_user)):
        rate_limit(request, 'account_delete', 3)
        with database.session() as session:
            from .groups import active_actor, deactivate_user
            row = active_actor(session, user['id'], lock=True)
            if not check_password(body.password, row.password_hash):
                raise HTTPException(403, 'reauthentication_failed')
            for observation in session.scalars(select(Observation).where(Observation.author_id == row.id)):
                observation.status = 'withdrawn'
                observation.payload = {'place_id': observation.place_id, 'mode': 'field',
                    'observed_on': observation.payload.get('observed_on'), 'body': '', 'consent': False, 'erased': True}
                observation.review_note = None
            photos.erase_account(session, row.id)
            deactivate_user(session, row.id)
            session.execute(delete(LoginSession).where(LoginSession.user_id == row.id))
            row.username = 'deleted_' + row.id.replace('-', '')
            row.password_hash = 'disabled:' + secrets.token_hex(32)
            row.role = 'disabled'
            audit(session, row.id, 'account', row.id, 'deactivated_and_observations_erased')
        response.delete_cookie('bdt_session', path='/', secure=os.getenv('BDT_ENV') == 'production', httponly=True, samesite='strict')
        return {'status': 'account_deactivated_and_observations_erased',
                'retained': 'Pseudonymous moderation history and reviewed public-source links; backup retention is operator-managed.'}
