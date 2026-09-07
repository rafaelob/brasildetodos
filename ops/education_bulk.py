"""Build a national school catalog from the exact-year INEP distribution.

Run on operator infrastructure, never in an HTTP request. The artifact includes
only the minimized public catalog and a coverage/provenance report, not original
microdata archives or any student/teacher tables. Failed stages exit nonzero.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from bdt.catalog_release import export_catalog, verify_catalog
from bdt.catalog_acceptance import exercise_catalog
from bdt.domain import Source, now
from bdt.education_bulk import Limits, discover_distribution, import_school_archive
from bdt.education_transport import official_anchor
from bdt.ingest import IBGE_URL, file_source, import_ibge
from bdt.storage import Database
from bdt.sync import atomic_json, download_retry, file_hash
from bdt.territory import import_territory_snapshot


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year',type=int,default=2025)
    parser.add_argument('--output',type=Path,default=Path('test-results/national-education'))
    parser.add_argument('--territory-snapshot',type=Path)
    args=parser.parse_args(argv)
    if not 2000 <= args.year <= 2100:
        parser.error('year out of supported range')
    root=args.output
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):
        parser.error('output must be empty; existing artifacts are never overwritten')
    report={'started_at':now(), 'year':args.year, 'revision':os.getenv('GITHUB_SHA','development'),
            'stages':[], 'national_catalog_certified':False, 'application_deployed':False,
            'scope':'public schools declared active in reviewed INEP school tables',
            'status':'running'}
    database=Database('sqlite:///'+str(root/'catalog.db'))
    database.initialize()
    archive=root/'inep-distribution.zip'
    status=1

    def stage(name,**data):
        report['stages'].append({'stage':name,**data})
        atomic_json(root/'report.json',report)
        print(json.dumps(report['stages'][-1],ensure_ascii=False),flush=True)

    try:
        if args.territory_snapshot:
            territorial=import_territory_snapshot(database,args.territory_snapshot)
        else:
            path=root/'municipalities.json'
            meta=download_retry(IBGE_URL,path,16*1024**2)
            provenance=file_source(path,'ibge',IBGE_URL,None).model_copy(update={'collected_at':meta['collected_at']})
            territorial={'records':import_ibge(database,path,provenance), 'mode':'fresh_upstream', 'sha256':meta['sha256']}
        stage('territory',status='imported',**territorial)
        html,anchor=official_anchor()
        distribution=discover_distribution(html,args.year)
        report['anchor']=anchor
        report['distribution_url']=distribution
        stage('discovery',status='one_verified_year_link',url=distribution,anchor=anchor)
        meta=download_retry(distribution,archive,Limits().archive_bytes)
        report['distribution']=meta
        stage('download',status='complete',bytes=meta['bytes'],sha256=meta['sha256'])
        source=Source(dataset=f'inep-schools-{args.year}',url=distribution,record_id=archive.name,
                      reference_date=str(args.year),collected_at=meta['collected_at'],snapshot_sha256=meta['sha256'])
        result=import_school_archive(database,archive,source,year=args.year)
        report['validation']=result
        stage('school_tables',status=result['status'],counts=result['counts'],
              missing_eligible_states=result['missing_eligible_states'],tables=result['tables'])
        if result['status'] != 'imported':
            raise ValueError('national_partitions_require_review_no_school_publish')
        manifest=export_catalog(database,root/'public-catalog',revision=report['revision'])
        verified=verify_catalog(root/'public-catalog')
        report['public_catalog']={'manifest_sha256':file_hash(root/'public-catalog'/'manifest.json'),
                                  'verification':verified}
        stage('public_catalog',status='verified',tables=manifest.get('tables',{}))
        accepted = exercise_catalog(root/'public-catalog')
        report['api_acceptance'] = accepted
        stage('api_acceptance', status=accepted['status'],
              records=accepted['records'], saved_places=accepted['saved_places'])
        report['status']='imported'
        status=0
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).startswith((
            'school_', 'reviewed_school_', 'official_', 'national_', 'invalid_school_', 'empty_school_')) else 'transport_or_profile_failure'
        report.update(status='failed',error_type=type(error).__name__,error_code=code[:200])
        stage('failure',status='failed',error_type=type(error).__name__,error_code=code[:200])
    finally:
        with database.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        database.engine.dispose()
        archive.unlink(missing_ok=True)
        report['finished_at']=now()
        atomic_json(root/'report.json',report)
    return status


if __name__=='__main__':
    sys.exit(main())
