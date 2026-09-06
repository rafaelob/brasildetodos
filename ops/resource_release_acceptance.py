"""Combine pinned public catalog/resource artifacts and exercise the real API.

No HTTP collection, synthetic records, user accounts or public deployment. Only
aggregate evidence leaves the temporary installation; the database is discarded.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from bdt.api import create_app
from bdt.catalog_release import install_catalog,load_manifest
from bdt.resource_release import install_resource_release
from bdt.resource_sync import ResourceRevision
from bdt.storage import Database,Place,Finance,User,Observation
from bdt.evidence import Resource


def exercise(catalog,resources,*,catalog_sha256,report_sha256,resources_sha256):
    manifest_path=Path(catalog)/'manifest.json'
    if manifest_path.is_symlink() or hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=catalog_sha256:
        raise ValueError('selected_catalog_manifest_mismatch')
    manifest=load_manifest(Path(catalog))
    expected_places=manifest['files']['places.jsonl']['records']
    if manifest['files']['resources.jsonl']['records']!=0:
        raise ValueError('acceptance_requires_unenriched_public_catalog')
    with tempfile.TemporaryDirectory(prefix='bdt-combined-acceptance-') as temporary:
        destination=Path(temporary)/'application.db'
        install_catalog(Path(catalog),destination)
        if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=catalog_sha256:
            raise ValueError('selected_catalog_manifest_changed')
        database=Database('sqlite:///'+str(destination))
        try:
            database.initialize()
            with database.session() as session:
                baseline_finance=session.scalar(select(func.count()).select_from(Finance))
            pins=dict(report_sha256=report_sha256,resources_sha256=resources_sha256)
            first=install_resource_release(database,Path(resources),**pins)
            second=install_resource_release(database,Path(resources),**pins)
            if any(c['created'] or c['updated'] or c['unchanged']!=c['read'] for c in second['by_profile'].values()):
                raise ValueError('combined_release_not_idempotent')
            with database.session() as session:
                counts={t.__tablename__:session.scalar(select(func.count()).select_from(t)) for t in (Place,Resource,ResourceRevision,Finance,User,Observation)}
                if counts['places']!=expected_places or counts['resources']!=first['records'] or counts['resource_revisions']!=first['records']:
                    raise ValueError('combined_release_count_mismatch')
                if counts['finance']!=baseline_finance or counts['users'] or counts['observations']:
                    raise ValueError('unexpected_private_or_financial_changes')
                precise=next((row.payload for row in session.scalars(select(Resource).order_by(Resource.id)) if row.payload['attributes'].get('precise_amounts')),None)
            with TestClient(create_app(str(database.engine.url),testing=True)) as client:
                places=client.get('/api/places',params={'limit':1})
                listed=client.get('/api/resources',params={'limit':1})
                if places.status_code!=200 or places.json()['total']!=expected_places or listed.status_code!=200 or listed.json()['total']!=first['records']:
                    raise ValueError('combined_release_api_count_mismatch')
                for profile,values in first['by_profile'].items():
                    response=client.get('/api/resources',params={'profile':profile,'limit':1})
                    if response.status_code!=200 or response.json()['total']!=values['read']:
                        raise ValueError('combined_release_profile_mismatch')
                if precise:
                    response=client.get('/api/resource-export/'+precise['id'])
                    if response.status_code!=200 or response.json()['revision']!=1:
                        raise ValueError('combined_release_export_failed')
                    amounts={x['field']:x['decimal'] for x in response.json()['resource']['amounts']}
                    if any(amounts.get(k)!=v for k,v in precise['attributes']['precise_amounts'].items()):
                        raise ValueError('combined_release_export_precision_mismatch')
                if client.get('/api/workbench/documents').status_code!=401 or client.get('/api/resource-coverage').status_code!=200:
                    raise ValueError('combined_release_route_regression')
            return {'schema':'bdt.combined-release-acceptance.v1','status':'passed',
                'counts':counts,'catalog_manifest_sha256':catalog_sha256,
                'first_install':first,'replay':second,'api_checked':True,
                'subcent_export_checked':precise is not None,'fresh_collection':False,
                'synthetic_records_added':False,'public_deployment':False}
        finally:database.engine.dispose()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',required=True,type=Path)
    parser.add_argument('--resources',required=True,type=Path)
    parser.add_argument('--catalog-sha256',required=True)
    parser.add_argument('--report-sha256',required=True)
    parser.add_argument('--resources-sha256',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as output:
        try:result=exercise(args.catalog,args.resources,catalog_sha256=args.catalog_sha256,
            report_sha256=args.report_sha256,resources_sha256=args.resources_sha256)
        except Exception as error:result={'status':'failed','error_type':type(error).__name__,'public_deployment':False}
        json.dump(result,output,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
