"""Versioned relational storage, portable between SQLite and PostgreSQL."""
from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4
from sqlalchemy import JSON, BigInteger, Boolean, Column, Float, ForeignKey, Integer, String, Text, create_engine, event, inspect as inspect_state, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import CreateColumn
from .domain import PlaceInput, digest, fold, now

Base = declarative_base()

class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)

class Municipality(Base):
    __tablename__ = "municipalities"
    id = Column(String(7), primary_key=True)
    name = Column(String(200), nullable=False)
    state = Column(String(2), nullable=False, index=True)
    source = Column(JSON, nullable=False)

class Place(Base):
    __tablename__ = "places"
    id = Column(String(180), primary_key=True)
    kind = Column(String(20), nullable=False, index=True)
    catalogue_eligible = Column(Boolean, nullable=False, default=True, index=True)
    name = Column(String(300), nullable=False)
    search_name = Column(Text, nullable=False)
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), nullable=False, index=True)
    state = Column(String(2), nullable=False, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    dataset = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    updated_at = Column(String(40), nullable=False)

class Change(Base):
    __tablename__ = "changes"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    place_id = Column(String(180), ForeignKey("places.id"), nullable=False, index=True)
    at = Column(String(40), nullable=False, default=now)
    before = Column(JSON)
    after = Column(JSON, nullable=False)
    fields = Column(JSON, nullable=False)

class Ingestion(Base):
    __tablename__ = "ingestions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset = Column(String(100), nullable=False, index=True)
    started_at = Column(String(40), nullable=False, default=now)
    finished_at = Column(String(40))
    status = Column(String(20), nullable=False, default="running")
    counts = Column(JSON, nullable=False, default=dict)
    source = Column(JSON, nullable=False)
    error = Column(Text)

class Finance(Base):
    __tablename__ = "finance"
    key = Column(String(64), primary_key=True)
    municipality_id = Column(String(7), ForeignKey("municipalities.id"), nullable=False, index=True)
    facility_id = Column(String(180), ForeignKey("places.id"), index=True)
    cents = Column(BigInteger, nullable=False)
    payload = Column(JSON, nullable=False)

class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username = Column(String(40), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), nullable=False, default="contributor")

class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    expires_at = Column(BigInteger, nullable=False)

class RateBucket(Base):
    __tablename__ = "rate_buckets"
    id = Column(String(100), primary_key=True)
    count = Column(Integer, nullable=False)
    expires_at = Column(BigInteger, nullable=False)

class RecoveryCode(Base):
    """One live code per user. Only the SHA-256 digest is stored."""
    __tablename__ = "recovery_codes"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    digest = Column(String(64), nullable=False, unique=True)
    expires_at = Column(BigInteger, nullable=False)
    version = Column(Integer, nullable=False)
    created_at = Column(BigInteger, nullable=False)


@event.listens_for(User, "before_update")
def _purge_recovery_codes_when_disabled(mapper, connection, target):
    # Same transaction as the role change, so a rolled-back disable cannot leave a usable code.
    if target.role != "disabled":
        return
    history = inspect_state(target).attrs.role.history
    if not history.has_changes():
        return
    connection.execute(
        RecoveryCode.__table__.delete().where(RecoveryCode.__table__.c.user_id == target.id)
    )


class Observation(Base):
    __tablename__ = "observations"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    place_id = Column(String(180), ForeignKey("places.id"), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    payload = Column(JSON, nullable=False)
    created_at = Column(String(40), nullable=False, default=now)
    reviewer_id = Column(String(36), ForeignKey("users.id"))
    reviewed_at = Column(String(40))
    review_note = Column(Text)
    contest_count = Column(Integer, nullable=False, default=0, server_default="0")
    previous_reviewer_id = Column(String(36), ForeignKey("users.id"))

class Database:
    def __init__(self, url: str):
        args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=args, pool_pre_ping=True)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def sqlite_settings(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self):
        """Preflight and apply additive schema changes in one serialized transaction.

        This is not a general migration engine: destructive/incompatible changes
        still require a reviewed migration and a restore-tested backup.
        """
        with self.engine.begin() as connection:
            if connection.dialect.name == 'sqlite':
                # sqlite3 legacy transaction mode does not begin on DDL. Without
                # an explicit BEGIN, a later failure leaves earlier ALTERs committed.
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            elif connection.dialect.name == 'postgresql':
                # Database-local, transaction-scoped lock: BDT / schema initialization.
                connection.execute(text('SELECT pg_advisory_xact_lock(4342868, 1)'))
            inspector = inspect_state(connection)
            existing_tables = set(inspector.get_table_names())
            version_names = ('schema_version', 'extension_version',
                             'photo_schema_version', 'group_schema_version')
            unversioned = []
            # Validate every loaded module BEFORE create_all can mutate any table.
            for name in version_names:
                table = Base.metadata.tables.get(name)
                rows = []
                if name in existing_tables:
                    if not {'id', 'version'} <= {column['name'] for column in inspector.get_columns(name)}:
                        raise RuntimeError('Unsupported schema version; run a reviewed migration')
                    # Validate known persisted versions even before their module is loaded.
                    quoted_name = connection.dialect.identifier_preparer.quote(name)
                    rows = connection.execute(text(f'SELECT id, version FROM {quoted_name}')).fetchmany(2)
                if rows and (len(rows) != 1 or rows[0].id != 1
                             or type(rows[0].version) is not int or rows[0].version != 1):
                    raise RuntimeError('Unsupported schema version; run a reviewed migration')
                if not rows and table is not None:
                    unversioned.append(table)
            statements = self._plan_additive_columns(connection)
            Base.metadata.create_all(connection)
            for statement in statements:
                connection.exec_driver_sql(statement)
            for table in unversioned:
                connection.execute(table.insert().values(id=1, version=1))

    def _plan_additive_columns(self, connection) -> list[str]:
        """Plan against the locked connection, before any table or column is added."""
        inspector = inspect_state(connection)
        existing_tables = set(inspector.get_table_names())
        dialect = connection.dialect
        quote = dialect.identifier_preparer.quote
        statements = []
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column['name'] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                if (not column.nullable and column.server_default is None
                        or column.primary_key or column.unique or column.computed is not None
                        or column.identity is not None or column.index):
                    raise RuntimeError(
                        f'{table.name}.{column.name} cannot be added safely; run a reviewed migration'
                    )
                # SQLAlchemy quotes string defaults and identifiers for the backend.
                definition = str(CreateColumn(column).compile(dialect=dialect))
                references = list(column.foreign_keys)
                if len(references) > 1:
                    raise RuntimeError('Multiple column references require a reviewed migration')
                if references:
                    reference = references[0]
                    if reference.ondelete or reference.onupdate or reference.deferrable or reference.initially or reference.match:
                        raise RuntimeError('Foreign key options require a reviewed migration')
                    target = reference.column
                    definition += f' REFERENCES {quote(target.table.name)} ({quote(target.name)})'
                statements.append(f'ALTER TABLE {quote(table.name)} ADD COLUMN {definition}')
        return statements

    @contextmanager
    def session(self):
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

def upsert_place(session, incoming: PlaceInput) -> str:
    municipality = session.get(Municipality, incoming.municipality_id)
    if municipality is None or municipality.state != incoming.state:
        raise ValueError("Unknown or inconsistent municipality: import IBGE first")
    payload = incoming.model_dump(mode="json")
    semantic = payload | {"source": {k: v for k, v in payload["source"].items() if k not in {"collected_at", "snapshot_sha256"}}}
    fingerprint = digest(semantic)
    row = session.get(Place, incoming.id)
    if row is None:
        row = Place(id=incoming.id)
        session.add(row)
        previous = None
        changed = list(payload)
        outcome = "inserted"
    else:
        previous = row.payload
        if row.fingerprint == fingerprint:
            row.payload = payload
            return "unchanged"
        changed = [k for k in payload if k != "source" and payload[k] != previous.get(k)]
        if payload["source"]["reference_date"] != previous["source"].get("reference_date"):
            changed.append("source.reference_date")
        outcome = "updated"
    row.catalogue_eligible = incoming.catalogue_eligible
    row.kind, row.name = incoming.kind, incoming.name
    row.search_name = fold(incoming.name + " " + incoming.address)
    row.municipality_id, row.state = incoming.municipality_id, incoming.state
    row.latitude, row.longitude = incoming.latitude, incoming.longitude
    row.dataset = incoming.source.dataset
    row.payload, row.fingerprint, row.updated_at = payload, fingerprint, now()
    session.flush()
    session.add(Change(place_id=row.id, before=previous, after=payload, fields=changed))
    return outcome
