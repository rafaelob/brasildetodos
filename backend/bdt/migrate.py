# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reviewed Alembic entry point for structural schema changes.

The baseline revision represents the schema bootstrapped by
``Database.initialize``. Existing databases must be stamped once before future
upgrades; new empty databases can be upgraded directly.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def _root() -> Path:
    configured = os.getenv("BDT_PROJECT_ROOT")
    if configured:
        return Path(configured)
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "alembic.ini").is_file():
            return candidate
    return Path.cwd()


ROOT = _root()


def config(database_url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str) -> None:
    command.upgrade(config(database_url), "head")


def stamp(database_url: str, revision: str = "head") -> None:
    command.stamp(config(database_url), revision)


def current(database_url: str) -> None:
    command.current(config(database_url))


def check(database_url: str) -> None:
    command.check(config(database_url))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("upgrade", "stamp", "current", "check"):
        item = sub.add_parser(name)
        item.add_argument("--database", default=os.getenv(
            "BDT_DATABASE_URL", "sqlite:///data/bdt.db"))
        if name == "stamp":
            item.add_argument("--revision", default="head")
    args = parser.parse_args(argv)
    if args.command == "upgrade":
        upgrade(args.database)
    elif args.command == "stamp":
        stamp(args.database, args.revision)
    elif args.command == "current":
        current(args.database)
    else:
        check(args.database)
    print(json.dumps({"status": "ok", "command": args.command}, ensure_ascii=False))


if __name__ == "__main__":
    main()
