# SPDX-License-Identifier: AGPL-3.0-or-later
"""Single-use account recovery codes. Digest only; consume never issues a session."""
from __future__ import annotations
import hashlib
import hmac
import logging
import secrets
import time
from fastapi import Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from .domain import StrictModel
from .evidence import audit
from .storage import LoginSession, RecoveryCode, User

log = logging.getLogger('bdt.recovery')
CODE_BYTES = 32
SCHEME = 1
TTL_SECONDS = 365 * 24 * 60 * 60
DUMMY_DIGEST = hashlib.sha256(b'bdt-recovery-dummy').hexdigest()


class Reauth(StrictModel):
    password: str = Field(min_length=12, max_length=128)


class Consume(StrictModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_-]{3,40}$')
    code: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


def code_digest(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def revoke_codes(session, user_id: str) -> int:
    return session.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user_id)).rowcount


def issue_code(session, user_id: str, *, now_ts: int | None = None) -> tuple[str, RecoveryCode]:
    now_ts = int(time.time() if now_ts is None else now_ts)
    revoke_codes(session, user_id)
    plaintext = secrets.token_urlsafe(CODE_BYTES)
    row = RecoveryCode(user_id=user_id, digest=code_digest(plaintext),
                       expires_at=now_ts + TTL_SECONDS, version=SCHEME, created_at=now_ts)
    session.add(row)
    session.flush()
    return plaintext, row


def take_code(session, user_id: str, digest: str, now_ts: int) -> bool:
    taken = session.execute(delete(RecoveryCode).where(
        RecoveryCode.user_id == user_id, RecoveryCode.digest == digest,
        RecoveryCode.expires_at > now_ts))
    return taken.rowcount == 1


def _lock_active_user(session, user_id: str) -> bool:
    locked = session.execute(update(User).where(User.id == user_id, User.role != 'disabled')
                             .values(role=User.role))
    return locked.rowcount == 1


def install(app, database, current_user, rate_limit, check_password, password_hash):
    @app.post('/api/auth/recovery/prepare')
    def prepare(body: Reauth, request: Request, user=Depends(current_user)):
        rate_limit(request, 'recovery_prepare', 10)
        with database.session() as session:
            if not _lock_active_user(session, user['id']):
                raise HTTPException(401, 'login_required')
            row = session.get(User, user['id'])
            if not row or row.role == 'disabled':
                raise HTTPException(401, 'login_required')
            if not check_password(body.password, row.password_hash):
                log.info('recovery.prepare rejected user_id=%s reason=reauthentication', user['id'])
                raise HTTPException(403, 'reauthentication_failed')
            try:
                plaintext, issued = issue_code(session, row.id)
            except IntegrityError:
                log.info('recovery.prepare conflict user_id=%s', row.id)
                raise HTTPException(409, 'recovery_conflict') from None
            audit(session, row.id, 'account', row.id, 'recovery_prepared', version=issued.version)
            log.info('recovery.prepare ok user_id=%s version=%s', row.id, issued.version)
            return {'code': plaintext, 'expires_at': issued.expires_at, 'version': issued.version,
                    'ttl_seconds': TTL_SECONDS}

    @app.post('/api/auth/recovery/revoke')
    def revoke(body: Reauth, request: Request, user=Depends(current_user)):
        rate_limit(request, 'recovery_revoke', 10)
        with database.session() as session:
            if not _lock_active_user(session, user['id']):
                raise HTTPException(401, 'login_required')
            row = session.get(User, user['id'])
            if not row or row.role == 'disabled':
                raise HTTPException(401, 'login_required')
            if not check_password(body.password, row.password_hash):
                log.info('recovery.revoke rejected user_id=%s reason=reauthentication', user['id'])
                raise HTTPException(403, 'reauthentication_failed')
            removed = revoke_codes(session, row.id)
            audit(session, row.id, 'account', row.id, 'recovery_revoked', removed=removed)
            log.info('recovery.revoke ok user_id=%s removed=%s', row.id, removed)
            return {'status': 'revoked'}

    @app.post('/api/auth/recovery/consume')
    def consume(body: Consume, request: Request):
        rate_limit(request, 'recovery_consume', 20)
        provided = code_digest(body.code)
        now_ts = int(time.time())
        with database.session() as session:
            user = session.scalar(select(User).where(User.username == body.username.lower()))
            stored = DUMMY_DIGEST
            if user is not None:
                live = session.scalar(select(RecoveryCode.digest).where(RecoveryCode.user_id == user.id))
                if live is not None:
                    stored = live
            matched = hmac.compare_digest(provided, stored)
            if (user is None or user.role == 'disabled' or not matched
                    or not _lock_active_user(session, user.id)
                    or not take_code(session, user.id, provided, now_ts)):
                log.info('recovery.consume rejected user_present=%s', user is not None)
                raise HTTPException(401, 'invalid_credentials')
            session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            revoke_codes(session, user.id)
            user.password_hash = password_hash(body.new_password)
            audit(session, user.id, 'account', user.id, 'recovery_consumed')
            log.info('recovery.consume ok user_id=%s', user.id)
        return {'status': 'password_reset'}
