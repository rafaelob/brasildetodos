"""Reuse operator-selected municipality snapshots; never copy user tables.

A failed upstream request must not turn valid prior territorial identities into
invented data or silently refresh their reference/collection dates.
"""
from __future__ import annotations
from contextlib import closing
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote, urlsplit
from .domain import Source
from .storage import Municipality
from .sync import file_hash


def import_territory_snapshot(database, path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > 512*1024*1024:
        raise ValueError('territory_snapshot_missing_or_too_large')
    uri='file:'+quote(str(path.resolve()))+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True)) as source:
        source.execute('PRAGMA query_only=ON')
        rows=source.execute('SELECT id,name,state,source FROM municipalities ORDER BY id').fetchmany(10001)
    if not rows or len(rows)>10000:
        raise ValueError('invalid_territory_snapshot_size')
    seen=set();dates=set();hashes=set()
    with database.session() as session:
        for identity,name,state,provenance in rows:
            if not isinstance(identity,str) or not re.fullmatch(r'[0-9]{7}',identity) or identity in seen or not name:
                raise ValueError('invalid_territory_identity')
            if state not in 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO'.split():
                raise ValueError('invalid_territory_state')
            record=Source.model_validate(json.loads(provenance))
            if record.dataset!='ibge' or urlsplit(record.url).hostname!='servicodados.ibge.gov.br' or record.record_id!=identity:
                raise ValueError('snapshot_requires_original_ibge_provenance')
            seen.add(identity);dates.add(str(record.collected_at));hashes.add(record.snapshot_sha256)
            existing=session.get(Municipality,identity)
            payload=record.model_dump(mode='json')
            if existing:
                if (existing.name,existing.state,existing.source)!=(name,state,payload):
                    raise ValueError('snapshot_conflicts_with_existing_territory')
            else:
                session.add(Municipality(id=identity,name=name,state=state,source=payload))
    return {'records':len(rows),'mode':'reused_verified_snapshot','snapshot_sha256':file_hash(path),
            'original_collection_dates':sorted(dates),'original_source_hashes':sorted(hashes),
            'fresh_upstream_request':False,'tables_copied':['municipalities']}
