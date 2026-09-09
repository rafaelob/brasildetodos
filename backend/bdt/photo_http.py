# SPDX-License-Identifier: AGPL-3.0-or-later
"""HTTP for private photo evidence. Off unless BDT_PHOTO_UPLOADS=1. Never auto-published."""
from __future__ import annotations
import os
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from . import photos
from .evidence import audit
from .storage import Observation, User


def uploads_enabled() -> bool:
    return os.getenv('BDT_PHOTO_UPLOADS') == '1'


def require_uploads():
    if not uploads_enabled():
        raise HTTPException(404, 'photo_uploads_disabled')


def _http(error: ValueError) -> HTTPException:
    code = str(error)
    if code in {'observation_not_found', 'photo_not_found'}:
        return HTTPException(404, code)
    if code == 'self_review_forbidden':
        return HTTPException(403, code)
    if 'quota' in code or 'revision' in code:
        return HTTPException(409, code)
    return HTTPException(422, code)


def _private_access(user, photo: photos.Photo):
    if user['id'] != photo.author_id and user['role'] != 'reviewer':
        raise HTTPException(404, 'photo_not_found')


def _jpeg(content: bytes) -> Response:
    return Response(content=content, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})


def install(app, database, current_user, reviewer, rate_limit):
    photos.initialize(database)

    @app.post('/api/photos', status_code=201)
    def upload(body: photos.PhotoInput, request: Request, _=Depends(require_uploads),
               user=Depends(current_user)):
        rate_limit(request, 'photo_upload', 10)
        try:
            with database.session() as session:
                photo = photos.submit(session, body, user['id'])
                audit(session, user['id'], 'photo', photo.id, 'submitted')
                observation = session.get(Observation, photo.observation_id)
                author = session.get(User, photo.author_id)
                return photos.metadata(photo, observation, author, private=True)
        except ValueError as error:
            raise _http(error) from None

    @app.get('/api/photos/{photo_id}')
    def private_metadata(photo_id: str, _=Depends(require_uploads), user=Depends(current_user)):
        try:
            with database.session() as session:
                photo, observation, author = photos.load(session, photo_id)
                _private_access(user, photo)
                return photos.metadata(photo, observation, author, private=True)
        except ValueError as error:
            raise _http(error) from None

    @app.get('/api/photos/{photo_id}/image')
    def private_image(photo_id: str, _=Depends(require_uploads), user=Depends(current_user)):
        try:
            with database.session() as session:
                photo, _observation, _author = photos.load(session, photo_id)
                _private_access(user, photo)
                return _jpeg(photos.stored_bytes(session, photo))
        except ValueError as error:
            raise _http(error) from None

    @app.get('/api/public/photos/{photo_id}/image')
    def public_image(photo_id: str, _=Depends(require_uploads)):
        try:
            with database.session() as session:
                photo, observation, author = photos.load(session, photo_id)
                if not photos.visible(photo, observation, author):
                    raise ValueError('photo_not_found')
                return _jpeg(photos.stored_bytes(session, photo))
        except ValueError as error:
            raise _http(error) from None

    @app.post('/api/photos/{photo_id}/review')
    def review(photo_id: str, body: photos.PhotoReview, _=Depends(require_uploads),
               user=Depends(reviewer)):
        try:
            with database.session() as session:
                photo = photos.review_photo(session, photo_id, body, user['id'])
                audit(session, user['id'], 'photo', photo.id, body.decision, revision=photo.revision)
                observation = session.get(Observation, photo.observation_id)
                author = session.get(User, photo.author_id)
                return photos.metadata(photo, observation, author, private=True)
        except ValueError as error:
            raise _http(error) from None

    @app.post('/api/photos/{photo_id}/remove')
    def remove(photo_id: str, body: photos.PhotoRemoval, _=Depends(require_uploads),
               user=Depends(current_user)):
        try:
            with database.session() as session:
                photo = photos.remove_photo(session, photo_id, body, user['id'])
                audit(session, user['id'], 'photo', photo.id, 'removed')
                observation = session.get(Observation, photo.observation_id)
                author = session.get(User, photo.author_id)
                return photos.metadata(photo, observation, author, private=True)
        except ValueError as error:
            raise _http(error) from None
