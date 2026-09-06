# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded selection exports, reusing the existing individual public projection."""
from __future__ import annotations
import csv
import hashlib
import io
import json
from typing import Literal
from fastapi import HTTPException, Query, Response
from sqlalchemy import func, select
from .domain import digest, now
from .evidence import Resource
from .resource_export import COPY, csv_cell, public_resource
from .resource_sync import ResourceRevision, semantic


def collection(database, *, q='', profile=None, state=None, municipality_id=None,
               kind=None, limit=100, locale='pt-BR'):
    from .resource_routes import resource_query
    if locale not in COPY or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('invalid_collection_export_options')
    statement = resource_query(q=q, profile=profile, state=state,
                              municipality_id=municipality_id, kind=kind)
    records = []
    with database.session() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = list(session.scalars(statement.order_by(Resource.id).limit(limit).with_for_update(read=True)))
        for row in rows:
            version = session.scalar(select(ResourceRevision).where(ResourceRevision.resource_id == row.id)
                .order_by(ResourceRevision.revision.desc()).limit(1))
            if version is not None and (digest(semantic(version.payload)) != version.fingerprint or
                                       digest(semantic(row.payload)) != version.fingerprint):
                raise HTTPException(409, 'resource_revision_integrity_failure')
            projected = public_resource(version.payload if version is not None else row.payload)
            records.append({'resource': projected, 'revision': version.revision if version else None,
                'observed_at': version.observed_at if version else None, 'content_sha256': digest(projected)})
    return {'schema': 'bdt.public-resource-collection.v1', 'locale': locale,
        'generated_at': now(), 'notice': COPY[locale][1],
        'scope': 'first_loaded_records_in_stable_id_order_not_all_public_spending',
        'filters': {key:value for key,value in {'q':q.strip(), 'profile':profile, 'state':state,
                    'municipality_id':municipality_id, 'kind':kind}.items() if value},
        'total': total, 'included': len(records), 'limit': limit,
        'truncated': total > len(records), 'records': records}


def render(report, format):
    if format == 'json':
        return json.dumps(report, ensure_ascii=False, indent=2)+'\n', 'application/json'
    if format == 'text':
        lines = [COPY[report['locale']][0], report['notice'],
            f"{report['included']} / {report['total']}", 'scope: '+report['scope'],
            'filters: '+json.dumps(report['filters'], ensure_ascii=False),
            'generated_at: '+report['generated_at'], 'truncated: '+str(report['truncated'])]
        for entry in report['records']:
            row = entry['resource']
            lines.extend(['', row['title'], row['id'], 'revision: '+str(entry['revision']),
                json.dumps(row,ensure_ascii=False), 'content_sha256: '+entry['content_sha256']])
        return '\n'.join(lines)+'\n','text/plain'
    if format != 'csv':
        raise ValueError('unsupported_export_format')
    stream = io.StringIO(newline=''); writer = csv.writer(stream)
    writer.writerow(['id','title','kind','municipality_id','revision','observed_at','amounts_json',
        'attributes_json','source_json','content_sha256','generated_at','filters_json','included','total','truncated','notice'])
    records = report['records'] or [{'resource':{},'revision':None,'observed_at':None,'content_sha256':None}]
    for entry in records:
        row = entry['resource']
        values=[row.get(key) for key in ('id','title','kind','municipality_id')]
        values += [entry['revision'],entry['observed_at'],json.dumps(row.get('amounts',[]),ensure_ascii=False),
            json.dumps(row.get('attributes',{}),ensure_ascii=False),json.dumps(row.get('source',{}),ensure_ascii=False),
            entry['content_sha256'],report['generated_at'],json.dumps(report['filters'],ensure_ascii=False),
            report['included'],report['total'],report['truncated'],report['notice']]
        writer.writerow([csv_cell(value) for value in values])
    return '\ufeff'+stream.getvalue(),'text/csv'


def install(app, database):
    @app.get('/api/resource-collection-export')
    def export(format: Literal['json','text','csv']='json', locale: Literal['pt-BR','en','es']='pt-BR',
        q: str=Query('',max_length=200), profile: str|None=Query(None,max_length=80),
        state: str|None=Query(None,pattern=r'^[A-Z]{2}$'),
        municipality_id: str|None=Query(None,pattern=r'^[0-9]{7}$'),
        kind: Literal['contract','instrument','proposal','work']|None=None,
        limit: int=Query(100,ge=1,le=100)):
        try:
            report=collection(database,q=q,profile=profile,state=state,municipality_id=municipality_id,
                              kind=kind,limit=limit,locale=locale)
            body,media=render(report,format)
        except ValueError as error:
            if str(error) in {'unknown_resource_profile','invalid_resource_state'}:
                raise HTTPException(422,str(error)) from None
            raise HTTPException(409,'resource_export_requires_review') from None
        suffix='txt' if format=='text' else format
        return Response(body,media_type=media,headers={
            'Content-Disposition':f'attachment; filename="brasildetodos-resource-selection.{suffix}"',
            'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'X-Content-SHA256':hashlib.sha256(body.encode()).hexdigest()})
