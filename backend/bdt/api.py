"""Read API and moderated community workflow. No LLM or ingestion on web requests."""
from __future__ import annotations
import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__
from .domain import ObservationInput, financial_cells, fold, now
from .storage import Change, Database, Finance, Ingestion, LoginSession, Municipality, Observation, Place, RateBucket, User


def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return salt.hex() + ':' + value.hex()


def check_password(password: str, encoded: str) -> bool:
    try:
        salt, _ = encoded.split(':')
        return hmac.compare_digest(password_hash(password, bytes.fromhex(salt)), encoded)
    except (ValueError, TypeError):
        return False


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(pattern=r'^[a-zA-Z0-9_-]{3,40}$')
    password: str = Field(min_length=12, max_length=128)


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: Literal['approved', 'rejected']
    note: str = Field(min_length=10, max_length=1000)


def public_observation(row: Observation) -> dict:
    return {'id': row.id, 'place_id': row.place_id, 'status': row.status, 'created_at': row.created_at,
            'reviewed_at': row.reviewed_at, 'observation': row.payload}


def create_app(database_url: str | None = None, *, testing: bool = False) -> FastAPI:
    folder = Path(os.getenv('BDT_DATA_DIR', 'data'))
    folder.mkdir(parents=True, exist_ok=True)
    database = Database(database_url or os.getenv('BDT_DATABASE_URL', 'sqlite:///data/bdt.db'))
    database.initialize()

    @asynccontextmanager
    async def lifespan(_):
        yield
        database.engine.dispose()

    app = FastAPI(title='Brasil de Todos', version=__version__, docs_url=None, redoc_url=None,
                  openapi_url='/api/openapi.json', lifespan=lifespan)
    app.state.database = database
    secure = os.getenv('BDT_ENV') == 'production'
    allowed_origin = os.getenv('BDT_PUBLIC_ORIGIN', 'http://localhost:8000').rstrip('/')
    if secure and not allowed_origin.startswith('https://'):
        database.engine.dispose()
        raise RuntimeError('Production requires BDT_PUBLIC_ORIGIN=https://...')
    if not testing:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv('BDT_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(','))
    dummy_hash = password_hash(secrets.token_urlsafe(24))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, error):
        return JSONResponse(status_code=422, content={'detail': 'invalid_request',
            'errors': [{'loc': e['loc'], 'type': e['type']} for e in error.errors()]})

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        length = request.headers.get('content-length')
        if length and (not length.isdigit() or int(length) > 32768):
            return JSONResponse({'detail': 'request_too_large'}, status_code=413)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('x-bdt-client') != 'web':
                return JSONResponse({'detail': 'csrf_header_required'}, status_code=403)
            if request.headers.get('origin') not in {None, allowed_origin}:
                return JSONResponse({'detail': 'origin_not_allowed'}, status_code=403)
            chunks, size = [], 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 32768:
                    return JSONResponse({'detail': 'request_too_large'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(self)'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tiles.openfreemap.org; connect-src 'self' https://tiles.openfreemap.org; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        if secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def rate_limit(request: Request, purpose: str, limit: int, window: int = 900):
        peer = request.client.host if request.client else 'unknown'
        start = int(time.time()) // window * window
        key = hashlib.sha256(f'{peer}:{purpose}:{start}'.encode()).hexdigest()
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        insert = pg_insert if database.engine.dialect.name == 'postgresql' else sqlite_insert
        with database.session() as session:
            session.execute(delete(RateBucket).where(RateBucket.expires_at < int(time.time())))
            statement = insert(RateBucket).values(id=key, count=1, expires_at=start + window)
            statement = statement.on_conflict_do_update(index_elements=[RateBucket.id],
                set_={'count': RateBucket.count + 1}).returning(RateBucket.count)
            count = session.execute(statement).scalar_one()
        if count > limit:
            raise HTTPException(429, 'rate_limited', headers={'Retry-After': str(window)})

    def current_user(request: Request):
        token = request.cookies.get('bdt_session', '')
        with database.session() as session:
            login = session.get(LoginSession, hashlib.sha256(token.encode()).hexdigest())
            if not token or not login or login.expires_at <= int(time.time()):
                raise HTTPException(401, 'login_required')
            user = session.get(User, login.user_id)
            if not user or user.role == 'disabled':
                raise HTTPException(401, 'login_required')
            return {'id': user.id, 'username': user.username, 'role': user.role}

    def reviewer(user=Depends(current_user)):
        if user['role'] != 'reviewer':
            raise HTTPException(403, 'reviewer_required')
        return user

    @app.get('/api/health')
    def health():
        with database.session() as session:
            session.execute(select(1))
        return {'status': 'ok', 'version': __version__, 'llm_required': False}

    @app.get('/api/config')
    def config():
        revision = os.getenv('BDT_REVISION', 'development')
        code = 'https://github.com/rafaelob/brasildetodos'
        if re.fullmatch(r'[0-9a-f]{40}', revision):
            code += '/tree/' + revision
        return {'registration_enabled': os.getenv('BDT_ALLOW_REGISTRATION') == '1',
                'source_code': code, 'revision': revision, 'photo_uploads': False,
                'evidence_workbench': True, 'viewport_api': True}

    @app.post('/api/auth/register', status_code=201)
    def register(body: Credentials, request: Request):
        if os.getenv('BDT_ALLOW_REGISTRATION') != '1':
            raise HTTPException(403, 'registration_disabled')
        rate_limit(request, 'register', 5)
        try:
            with database.session() as session:
                session.add(User(username=body.username.lower(), password_hash=password_hash(body.password)))
        except IntegrityError:
            raise HTTPException(409, 'username_unavailable') from None
        return {'status': 'created'}

    @app.post('/api/auth/login')
    def login(body: Credentials, request: Request, response: Response):
        rate_limit(request, 'login', 20)
        with database.session() as session:
            user = session.scalar(select(User).where(User.username == body.username.lower()))
            valid = check_password(body.password, user.password_hash if user else dummy_hash)
            if not user or not valid or user.role == 'disabled':
                raise HTTPException(401, 'invalid_credentials')
            token = secrets.token_urlsafe(32)
            session.execute(delete(LoginSession).where(LoginSession.expires_at <= int(time.time())))
            session.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user.id, expires_at=int(time.time()) + 28800))
            result = {'username': user.username, 'role': user.role}
        response.set_cookie('bdt_session', token, httponly=True, secure=secure, samesite='strict', max_age=28800, path='/')
        return result

    @app.get('/api/auth/me')
    def me(user=Depends(current_user)):
        return {'username': user['username'], 'role': user['role']}

    @app.post('/api/auth/logout', status_code=204)
    def logout(request: Request, response: Response):
        with database.session() as session:
            token = request.cookies.get('bdt_session', '')
            session.execute(delete(LoginSession).where(LoginSession.token_hash == hashlib.sha256(token.encode()).hexdigest()))
        response.delete_cookie('bdt_session', path='/', secure=secure, httponly=True, samesite='strict')

    @app.get('/api/municipalities')
    def municipalities(state: str | None = Query(None, pattern=r'^[A-Z]{2}$')):
        with database.session() as session:
            statement = select(Municipality).order_by(Municipality.name)
            if state:
                statement = statement.where(Municipality.state == state)
            return [{'id': row.id, 'name': row.name, 'state': row.state} for row in session.scalars(statement)]

    @app.get('/api/places')
    def places(q: str = Query('', max_length=200), kind: Literal['school', 'health', 'work'] | None = None,
               state: str | None = Query(None, pattern=r'^[A-Z]{2}$'),
               municipality_id: str | None = Query(None, pattern=r'^[0-9]{7}$'),
               bbox: str | None = Query(None, max_length=150), page: int = Query(1, ge=1, le=100000),
               limit: int = Query(30, ge=1, le=100)):
        statement = select(Place).where(Place.catalogue_eligible.is_(True))
        if q:
            statement = statement.where(Place.search_name.contains(fold(q), autoescape=True))
        for column, value in ((Place.kind, kind), (Place.state, state), (Place.municipality_id, municipality_id)):
            if value:
                statement = statement.where(column == value)
        if bbox:
            from .geo import parse_bbox
            try:
                west, south, east, north = parse_bbox(bbox)
            except ValueError:
                raise HTTPException(422, 'invalid_bbox') from None
            statement = statement.where(Place.longitude.between(west, east), Place.latitude.between(south, north))
        with database.session() as session:
            total = session.scalar(select(func.count()).select_from(statement.subquery()))
            items = session.scalars(statement.order_by(Place.name, Place.id).offset((page-1)*limit).limit(limit))
            return {'total': total, 'page': page, 'limit': limit, 'items': [row.payload for row in items]}

    @app.get('/api/places/{place_id:path}/history')
    def history(place_id: str):
        with database.session() as session:
            if not session.get(Place, place_id):
                raise HTTPException(404, 'place_not_found')
            rows = session.scalars(select(Change).where(Change.place_id == place_id).order_by(Change.at.desc()).limit(100))
            return [{'at': row.at, 'type': 'started' if row.before is None else 'updated', 'fields': row.fields,
                     'before': row.before, 'after': row.after} for row in rows]

    @app.get('/api/places/{place_id:path}')
    def place(place_id: str):
        with database.session() as session:
            row = session.get(Place, place_id)
            if not row:
                raise HTTPException(404, 'place_not_found')
            money = list(session.scalars(select(Finance).where(Finance.facility_id == place_id)))
            observations = session.scalars(select(Observation).where(Observation.place_id == place_id,
                Observation.status == 'approved').order_by(Observation.created_at.desc()).limit(100))
            return {'place': row.payload, 'finance': [item.payload for item in money],
                    'observations': [public_observation(item) for item in observations]}

    @app.get('/api/regions/{municipality_id}')
    def region(municipality_id: str):
        with database.session() as session:
            row = session.get(Municipality, municipality_id)
            if not row:
                raise HTTPException(404, 'municipality_not_found')
            total = session.scalar(select(func.count()).select_from(Finance).where(Finance.municipality_id == municipality_id))
            events = [item.payload for item in session.scalars(select(Finance).where(Finance.municipality_id == municipality_id).order_by(Finance.key).limit(1000))]
            return {'total': total, 'truncated': total > 1000, 'municipality': {'id': row.id, 'name': row.name, 'state': row.state},
                    'events': events, 'cells': financial_cells(events), 'limit': 1000, 'scope': 'loaded_records_only'}

    @app.post('/api/observations', status_code=201)
    def observe(body: ObservationInput, request: Request, user=Depends(current_user)):
        rate_limit(request, 'observation', 20)
        with database.session() as session:
            if not session.get(Place, body.place_id):
                raise HTTPException(404, 'place_not_found')
            row = Observation(place_id=body.place_id, author_id=user['id'], payload=body.model_dump(mode='json'))
            session.add(row); session.flush()
            return public_observation(row)

    @app.get('/api/observations/mine')
    def mine(user=Depends(current_user)):
        with database.session() as session:
            rows = session.scalars(select(Observation).where(Observation.author_id == user['id'])
                .order_by(Observation.created_at.desc()).limit(100))
            return [public_observation(row) | {'review_note': row.review_note} for row in rows]

    @app.get('/api/review')
    def queue(_=Depends(reviewer)):
        with database.session() as session:
            return [public_observation(row) for row in session.scalars(select(Observation).where(Observation.status == 'pending').limit(100))]

    @app.post('/api/review/{observation_id}')
    def review(observation_id: str, body: Review, user=Depends(reviewer)):
        with database.session() as session:
            row = session.scalar(select(Observation).where(Observation.id == observation_id).with_for_update())
            if not row:
                raise HTTPException(404, 'observation_not_found')
            if row.author_id == user['id']:
                raise HTTPException(403, 'self_review_forbidden')
            if row.status != 'pending':
                raise HTTPException(409, 'already_reviewed')
            changed = session.execute(update(Observation).where(Observation.id == observation_id, Observation.status == 'pending')
                .values(status=body.decision, reviewer_id=user['id'], reviewed_at=now(), review_note=body.note))
            if changed.rowcount != 1:
                raise HTTPException(409, 'already_reviewed')
            from .evidence import audit
            audit(session, user['id'], 'observation', observation_id, body.decision)
            session.refresh(row)
            return public_observation(row)

    from .features import install
    install(app, database, current_user, reviewer, rate_limit, check_password)
    from .coverage_dashboard import install as install_coverage
    from .place_tracking import install as install_tracking
    install_coverage(app, database)
    install_tracking(app, database)
    from .regions import install as install_regions
    install_regions(app, database)
    static = Path(os.getenv('BDT_STATIC_DIR', 'web/dist'))
    if static.is_dir() and not testing:
        app.mount('/', StaticFiles(directory=static, html=True), name='web')
    return app
