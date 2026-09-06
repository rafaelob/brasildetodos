"""Exercise a verified public catalog through the real read API in an isolated DB.

No model, remote request, account, or production database is needed. These checks
prove the installed package is queryable, not that every real-world service is
present, currently operational, or accepting appointments/enrolments.
"""
from __future__ import annotations
import argparse
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from .api import create_app
from .catalog_release import install_catalog
from .domain import now
from .place_tracking import WatchRequest, watch_summary
from .storage import Database, LoginSession, Observation, Place, User
from .sync import file_hash


def exercise_catalog(folder: Path) -> dict:
    started=time.perf_counter()
    report={'started_at':now(),'public_deployment':False,'national_catalog_certified':False,
            'manifest_sha256':file_hash(folder/'manifest.json'),'checks':[],
            'scope':'installed public catalog; no remote collection or service availability verification'}
    with tempfile.TemporaryDirectory(prefix='bdt-catalog-acceptance-') as temp:
        target=Path(temp)/'catalog.db'
        installed=install_catalog(folder,target)
        report['installation']=installed
        url='sqlite:///'+str(target)
        database=Database(url)
        with database.session() as session:
            groups=session.execute(select(Place.state,Place.kind,func.count(),func.count(Place.latitude))
                .where(Place.catalogue_eligible.is_(True)).group_by(Place.state,Place.kind)).all()
            missing=list(session.scalars(select(Place.id).where(Place.catalogue_eligible.is_(True),
                Place.latitude.is_(None)).order_by(Place.id).limit(10)))
            for table in (User,LoginSession,Observation):
                if session.scalar(select(func.count()).select_from(table)):
                    raise ValueError('public_package_contains_private_records')
        database.engine.dispose()
        expected=sum(count for _,_,count,_ in groups)
        expected_geocoded=sum(count for *_,count in groups)
        report['records']=expected
        report['geocoded']=expected_geocoded
        report['without_geometry']=expected-expected_geocoded
        report['partitions']=[{'state':s,'kind':k,'records':n,'geocoded':g} for s,k,n,g in groups]
        report['checks'].append('public_install_excludes_accounts_sessions_and_observations')
        app=create_app(url,testing=True)
        with TestClient(app) as client:
            def get(path,**params):
                response=client.get(path,params=params)
                if response.status_code != 200 or response.headers.get('cache-control') != 'no-store':
                    raise ValueError('catalog_read_or_cache_policy_failure')
                return response.json()
            if get('/api/places',limit=1)['total'] != expected:
                raise ValueError('catalog_api_total_mismatch')
            watched = list(missing)
            for state,kind,count,_ in groups:
                listing=get('/api/places',state=state,kind=kind,limit=3)
                if listing['total']!=count or len(listing['items'])!=min(3,count):
                    raise ValueError('catalog_partition_mismatch')
                if listing['items']:
                    watched.append(listing['items'][0]['id'])
                for row in listing['items']:
                    if row['state']!=state or row['kind']!=kind:
                        raise ValueError('catalog_filter_mismatch')
                    detail=get('/api/places/'+quote(row['id'],safe=''))
                    if detail['place']!=row or detail['observations']:
                        raise ValueError('catalog_detail_or_privacy_mismatch')
            report['checks'].append('all_loaded_state_kind_partitions_match_database_and_detail')
            # Exercise the bounded read-query module proposed for saved-place cards. No
            # interest list is stored, and no external call is made here.
            watched = list(dict.fromkeys(watched))
            watched_count = 0
            for offset in range(0, len(watched), 30):
                batch = watched[offset:offset+30]
                result = watch_summary(app.state.database, WatchRequest(
                    place_ids=batch, versions_per_place=2))
                if result['favorites_persisted'] or [item['id'] for item in result['items']] != batch:
                    raise ValueError('catalog_watch_scope_failure')
                for item in result['items']:
                    if item['status'] != 'available' or item['history']['included'] > 2:
                        raise ValueError('catalog_watch_projection_failure')
                    if item['id'] in missing and item['place']['latitude'] is not None:
                        raise ValueError('catalog_watch_invented_geometry')
                watched_count += len(batch)
            report['saved_places'] = {'sampled_records': watched_count,
                'without_geometry_included': len(missing), 'batch_limit': 30,
                'new_remote_collection': False, 'favorites_persisted': False, 'integration': 'query_module_only_not_public_endpoint'}
            report['checks'].append('saved_places_query_sample_matches_catalog_without_persisting_interests')
            mapped=get('/api/map/viewport',bbox='-180,-90,180,90',zoom=3)
            if (mapped['matched_records']!=expected_geocoded or mapped['represented_records']!=expected_geocoded
                    or len(mapped['features'])>500
                    or sum(f['properties']['count'] for f in mapped['features'])!=expected_geocoded):
                raise ValueError('catalog_map_accounting_mismatch')
            for feature in mapped['features']:
                props=feature['properties']
                if props['cluster'] and props.get('location_kind')!='aggregate_not_facility':
                    raise ValueError('aggregate_location_must_not_be_facility')
            report['map']={'features':len(mapped['features']),'represented_records':mapped['represented_records'],
                           'aggregated':mapped['aggregated'],'live_tiles_rendered':False}
            report['checks'].append('viewport_represents_every_geocoded_record_without_list_page_truncation')
            for identity in missing:
                detail=get('/api/places/'+quote(identity,safe=''))
                if detail['place']['latitude'] is not None or detail['place']['longitude'] is not None:
                    raise ValueError('missing_geometry_was_invented')
            report['checks'].append('records_without_geometry_remain_readable_without_invented_coordinates')
            coverage=get('/api/coverage')
            if coverage['national_catalog_certified'] is not False or sum(p['records'] for p in coverage['partitions'])!=expected:
                raise ValueError('catalog_coverage_misrepresents_loaded_records')
            for path in ('/api/workbench/documents','/api/workbench/links','/api/observations/mine','/api/account/export'):
                if client.get(path).status_code!=401:
                    raise ValueError('private_endpoint_must_require_authentication')
            report['checks'].append('coverage_is_explicit_and_private_endpoints_require_authentication')
    report.update(status='passed',finished_at=now(),duration_seconds=round(time.perf_counter()-started,3))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.exists():parser.error('existing evidence is never overwritten')
    result=exercise_catalog(args.catalog)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
