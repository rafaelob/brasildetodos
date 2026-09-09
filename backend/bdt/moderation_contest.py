# SPDX-License-Identifier: AGPL-3.0-or-later
"""Author contest of a rejected observation. Re-review only; never auto-publish."""
from __future__ import annotations
import logging
from fastapi import Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select, update
from .domain import StrictModel
from .evidence import audit
from .storage import Observation

log = logging.getLogger('bdt.moderation_contest')


class Contest(StrictModel):
    note: str = Field(min_length=20, max_length=1000)


def install(app, database, current_user, rate_limit):
    @app.post('/api/observations/{observation_id}/contest')
    def contest(observation_id: str, body: Contest, request: Request, user=Depends(current_user)):
        rate_limit(request, 'observation_contest', 5)
        with database.session() as session:
            row = session.scalar(select(Observation).where(Observation.id == observation_id).with_for_update())
            # Same 404 as missing: do not leak that another author's observation exists.
            if not row or row.author_id != user['id']:
                log.info('observation.contest denied observation_id=%s reason=unavailable', observation_id)
                raise HTTPException(404, 'observation_not_found')
            if row.contest_count >= 1:
                log.info('observation.contest denied observation_id=%s reason=already_contested', observation_id)
                raise HTTPException(409, 'already_contested')
            if row.status != 'rejected':
                log.info('observation.contest denied observation_id=%s reason=not_rejected status=%s',
                         observation_id, row.status)
                raise HTTPException(409, 'not_rejected')
            changed = session.execute(
                update(Observation).where(
                    Observation.id == observation_id,
                    Observation.author_id == user['id'],
                    Observation.status == 'rejected',
                    Observation.contest_count == 0,
                ).values(
                    status='pending',
                    contest_count=Observation.contest_count + 1,
                    previous_reviewer_id=Observation.reviewer_id,
                    reviewer_id=None,
                    reviewed_at=None,
                ))
            if changed.rowcount != 1:
                session.refresh(row)
                if row.contest_count >= 1:
                    raise HTTPException(409, 'already_contested')
                if row.status != 'rejected':
                    raise HTTPException(409, 'not_rejected')
                raise HTTPException(409, 'already_contested')
            # Contest note is request friction only; do not copy observation body into the audit row.
            audit(session, user['id'], 'observation', observation_id, 'contest_requested')
            session.refresh(row)
            log.info('observation.contest ok observation_id=%s contest_count=%s note_chars=%s',
                     observation_id, row.contest_count, len(body.note))
            return {'id': row.id, 'place_id': row.place_id, 'status': row.status,
                    'created_at': row.created_at, 'reviewed_at': row.reviewed_at,
                    'observation': row.payload, 'contested': True}
