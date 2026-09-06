"""Bounded real-source intake and public API acceptance; no public deployment."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from bdt.api import create_app
from bdt.domain import now
from bdt.evidence import Resource
from bdt.resource_profiles import PROFILES, collection_plan
from bdt.resource_diagnostics import ResourceTextError
from bdt.resource_sync import ResourceRevision, decode, import_resources
from bdt.storage import Database, Finance
from bdt.sync import atomic_json, collect, file_hash
from bdt.territory import import_territory_snapshot


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--territory-snapshot',required=True,type=Path)
    parser.add_argument('--output',type=Path,default=Path('test-results/resource-intake'))
    parser.add_argument('--date',default='20260904')
    args=parser.parse_args()
    root=args.output;root.mkdir(parents=True,exist_ok=False)
    public=root/'public';public.mkdir()
    url='sqlite:///'+str((root/'working.db').resolve())
    database=Database(url);database.initialize()
    report={'started_at':now(),'code_revision':os.environ.get('GITHUB_SHA','local'),
        'public_deployment':False,'national_resources_certified':False,'collections':[]}
    try:
        report['territory']=import_territory_snapshot(database,args.territory_snapshot)
        plans=[collection_plan('pncp_contracts',start=args.date,end=args.date,page_size=500,max_pages=20)]
        # Discovery is explicitly partial and is NEVER imported. It only identifies
        # one real record to run a separate, complete identity-filtered query.
        for profile in ('transferegov_special_plans','obrasgov_projects'):
            folder=root/(profile+'-discovery')
            try:
                discovery=collect(collection_plan(profile,page_size=1,max_pages=1),folder)
                rows=decode((folder/'page-000000.json').read_bytes())['data']
                if not rows:raise ValueError('no_discovery_record')
                identity=rows[0][PROFILES[profile][1]]
                plans.append(collection_plan(profile,identity=str(identity),page_size=10,max_pages=2))
                report['collections'].append({'profile':profile,'stage':'identity_discovery_only',
                    'status':discovery['status'],'published':False,'identity':str(identity)})
            except Exception as error:
                report['collections'].append({'profile':profile,'stage':'discovery','status':'failed',
                    'error_type':type(error).__name__,'published':False})
        for plan in plans:
            folder=root/plan.dataset
            entry={'profile':plan.dataset,'stage':'complete_scoped_query','query':plan.parameters}
            try:
                collection=collect(plan,folder)
                entry['collection']={key:collection.get(key) for key in ('status','records','expected_records','terminal')}
                entry['pages']=collection['pages']
                entry['import']=import_resources(database,folder)
                # A second import must not create another version or any payment.
                again=import_resources(database,folder)
                if again['updated'] or again['created'] or again['unchanged']!=again['read']:
                    raise ValueError('resource_import_not_idempotent')
                entry['idempotent']=True;entry['status']='passed'
            except Exception as error:
                entry.update(status='failed',error_type=type(error).__name__,
                    reason=str(error)[:160] if type(error) is ValueError else 'transport_or_validation_failure')
                if isinstance(error,ResourceTextError):
                    entry['reason']='invalid_resource_text'
                    entry['validation']=error.public_diagnostic()
                checkpoint=folder/'collection.json'
                if checkpoint.exists():
                    c=json.loads(checkpoint.read_text());entry['collection']={key:c.get(key) for key in ('status','records','terminal','error_code')}
            report['collections'].append(entry)
            atomic_json(public/'report.json',report)
        with database.session() as session:
            rows=list(session.scalars(select(Resource).order_by(Resource.id)))
            if session.scalar(select(func.count()).select_from(Finance)):
                raise ValueError('unexpected_financial_events')
            report['resources']=len(rows)
            report['versions']=session.scalar(select(func.count()).select_from(ResourceRevision))
            partition={}
            for row in rows:partition[row.source['dataset']]=partition.get(row.source['dataset'],0)+1
            report['by_profile']=partition
            with (public/'resources.jsonl').open('w',encoding='utf-8') as out:
                for row in rows:out.write(json.dumps(row.payload,ensure_ascii=False)+'\n')
            # No full database, accounts, raw supplier fields or raw collections
            # are uploaded. This export is normalized metadata, not source bytes.
            report['resources_sha256']=file_hash(public/'resources.jsonl')
        app=create_app(url,testing=True)
        with TestClient(app) as client:
            listed=client.get('/api/resources?limit=1')
            if listed.status_code!=200 or listed.json()['total']!=report['resources']:
                raise ValueError('public_resource_list_mismatch')
            for profile,count in report['by_profile'].items():
                response=client.get('/api/resources',params={'profile':profile,'limit':2})
                if response.status_code!=200 or response.json()['total']!=count:
                    raise ValueError('public_resource_filter_mismatch')
                for row in response.json()['items']:
                    history=client.get('/api/resource-history/'+quote(row['id'],safe=''))
                    if history.status_code!=200 or history.json()['total']!=1 or history.json()['resource']!=row:
                        raise ValueError('resource_history_mismatch')
            if client.get('/api/workbench/documents').status_code!=401:
                raise ValueError('private_document_endpoint_not_protected')
        report['api_acceptance']='passed'
        report['status']='passed' if all(c['status']!='failed' for c in report['collections']) else 'partial_with_explicit_failures'
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,
                      reason=str(error)[:160] if type(error) is ValueError else 'intake_failed')
    finally:
        report['finished_at']=now();atomic_json(public/'report.json',report)
        database.engine.dispose()
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
