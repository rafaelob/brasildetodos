"""Alembic environment for the Brasil de Todos schema.

The baseline revision is the schema currently created by ``Database.initialize``.
New structural changes must be added as reviewed revisions here; the local
bootstrap remains the fastest path for an empty development database.
"""
from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing every model module is intentional: Alembic must see the full
# metadata, including ingestion and collaboration tables not loaded by the API.
import bdt.cgu_emendas  # noqa: F401
import bdt.cgu_transferencias  # noqa: F401
import bdt.compras  # noqa: F401
import bdt.document_originals  # noqa: F401
import bdt.evidence  # noqa: F401
import bdt.fns  # noqa: F401
import bdt.groups  # noqa: F401
import bdt.obrasgov_catalog  # noqa: F401
import bdt.obrasgov_execution  # noqa: F401
import bdt.ocr_queue  # noqa: F401
import bdt.pdde  # noqa: F401
import bdt.photos  # noqa: F401
import bdt.pncp_atas  # noqa: F401
import bdt.pncp_documents  # noqa: F401
import bdt.resource_sync  # noqa: F401
import bdt.siconfi  # noqa: F401
import bdt.storage  # noqa: F401
import bdt.transferegov_especiais  # noqa: F401
from bdt.storage import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.getenv("BDT_DATABASE_URL") or config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("BDT_DATABASE_URL or sqlalchemy.url is required")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
