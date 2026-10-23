"""Reconciliation evidence between the installed national DB and fresh sources.

Reads what was actually installed into ``data/national.db`` and what our own
bounded sources declared (CNES/INEP receipts). It compares **installed vs
declared** only. It never invents denominators, never claims national certifi-
cation, and marks a dimension with no declared total as ``missing_denominator``
instead of estimating it.

Pode afirmar: quantidades instaladas de cada tipo de lugar, por UF, o gap
inteiro entre o instalado e o total declarado de cada fonte que nós mesmos
coletamos, e a ausência declarada de reconciliação municipal.

Nunca pode afirmar: cobertura nacional certificada, denominador por município,
viés de subnotificação ou dado do lado da fonte que não foi coletado. Um gap
de zero prova igualdade aritmética com o total declarado, não que a mesma
seleção foi reproduzida -- réplica não significa fusão. ``national_catalog_certified``
continua ``false`` até reconciliar denominadores oficiais.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func, select

from bdt.domain import now
from bdt.json_codec import decode
from bdt.storage import Database, Place

SCHEMA = "bdt.national-reconciliation.v1"
DEFAULT_DATABASE = Path("data/national.db")
DEFAULT_RECEIPT = Path("reports/20261021-national-data.json")
DEFAULT_REPORT = Path("reports/20261023-national-reconciliation.json")


def compute(database: Database, receipt: dict, *, database_path: str,
            receipt_path: str) -> dict:
    """Computa installed-vs-declared. Não inventa nada: falta de denominador é marcada."""
    kinds = ("health", "school")
    by_state: dict[str, dict[str, int]] = defaultdict(dict)
    with database.session() as session:
        rows = session.execute(
            select(Place.state, Place.kind, func.count())
            .where(Place.catalogue_eligible.is_(True))
            .group_by(Place.state, Place.kind)).all()
        without_geometry = session.scalar(
            select(func.count()).select_from(Place)
            .where(Place.latitude.is_(None) | Place.longitude.is_(None)))
        for state, kind, total in rows:
            by_state[state][kind] = int(total)
    installed_by_kind = {
        kind: sum(counts.get(kind, 0) for counts in by_state.values())
        for kind in kinds
    }
    total_installed = sum(installed_by_kind.values())

    install = receipt.get("release_installation")
    fresh = receipt.get("fresh_sources")
    if not isinstance(install, dict) or not isinstance(fresh, dict):
        raise ValueError("national_reconciliation_receipt_schema_changed")

    declared_by_kind = {
        "health": fresh.get("cnes"),
        "school": fresh.get("inep"),
    }
    sources = {}
    for kind, source in declared_by_kind.items():
        if not isinstance(source, dict):
            sources[kind] = {"status": "missing_denominator"}
            continue
        eligible = source.get("eligible")
        if isinstance(eligible, bool) or not isinstance(eligible, int) or eligible < 0:
            sources[kind] = {"status": "missing_denominator"}
            continue
        declared_total = int(eligible)
        installed = installed_by_kind[kind]
        gap = installed - declared_total
        sources[kind] = {
            "status": "reconciled" if declared_total else "reconciled_zero_declared",
            "dataset": source.get("url"),
            "sha256": source.get("sha256"),
            "collected_at": source.get("collected_at"),
            "declared_total": declared_total,
            "installed": installed,
            "gap": gap,
            "datasource_scope": source.get("scope"),
            "status_note": source.get("status"),
        }
    return {
        "schema": SCHEMA,
        "generated_on": now(),
        "national_catalog_certified": False,
        "not_national_coverage": True,
        "receipt": {"path": receipt_path},
        "installed": {
            "database": database_path,
            "total_places": total_installed,
            "by_kind": installed_by_kind,
            "without_geometry": int(without_geometry or 0),
            "by_state": [
                {"state": state, "health": counts.get("health", 0),
                 "school": counts.get("school", 0)}
                for state, counts in sorted(by_state.items())
            ],
        },
        "sources": sources,
        "notes": [
            "Installed database and fresh sources were collected separately; they were not merged.",
            "Only national totals were published by these sources; no per-state denominator was compared.",
            "A zero gap proves arithmetic equality with the declared total, not a merge or reproduction.",
            "Certification requires official per-state/municipal denominators and a reconciled edition.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    database = Database(f"sqlite:///{args.database}")
    try:
        receipt = decode(args.receipt.read_bytes())
        if not isinstance(receipt, dict):
            raise ValueError("national_reconciliation_receipt_not_object")
        report = compute(database, receipt, database_path=args.database.as_posix(),
                         receipt_path=args.receipt.as_posix())
    finally:
        database.engine.dispose()
    temporary = args.report.with_name(args.report.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(args.report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
