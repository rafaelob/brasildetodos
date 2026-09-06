"""Bounded real CNES load with explicit quarantine and portable public release.

Starts from an empty operator-selected output directory. Public artifacts contain
no accounts, sessions, citizen observations or full source rows. No LLM.
"""
from __future__ import annotations
import json
import os
import codecs
import csv
import io
import zipfile
from pathlib import Path
from sqlalchemy import func, select
from bdt.catalog_release import export_catalog, install_catalog
from bdt.cnes_bulk import REQUIRED
from bdt.cnes_quality import prepare, publish
from bdt.domain import Source, now
from bdt.ingest import IBGE_URL, csv_records, file_source, import_ibge
from bdt.storage import Database, Place
from bdt.sync import atomic_json, download_retry
from bdt.territory import import_territory_snapshot
from bdt.transport import download_registered

URL='https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip'


def profile(path):
    with zipfile.ZipFile(path) as archive:
        members=[item for item in archive.infolist() if item.filename.lower().endswith('.csv')]
        if len(members)!=1:
            raise ValueError('bulk_member_profile_review_required')
        member=members[0]
        if member.file_size>4*1024**3 or member.file_size/max(member.compress_size,1)>500:
            raise ValueError('bulk_uncompressed_budget')
        decoder=codecs.getincrementaldecoder('utf-8-sig')('strict')
        encoding='utf-8-sig'
        try:
            with archive.open(member) as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):decoder.decode(chunk)
                decoder.decode(b'',final=True)
        except UnicodeDecodeError:encoding='cp1252'
        with archive.open(member) as stream:
            first=io.TextIOWrapper(stream,encoding=encoding,newline='').readline()
        delimiter=max([';',',','\t','|'],key=lambda d:len(next(csv.reader([first],delimiter=d))))
        fields=next(csv.reader([first],delimiter=delimiter))
        if not REQUIRED.issubset(fields):raise ValueError('bulk_columns_require_reviewed_adapter')
        return {'member':member.filename,'encoding':encoding,'delimiter':delimiter,'fields':fields}


def main():
    root=Path(os.getenv('BDT_CNES_OUTPUT','test-results/cnes-quality'))
    root.mkdir(parents=True,exist_ok=False)
    database=Database('sqlite:///'+str((root/'working.db').resolve()));database.initialize()
    public=root/'public';public.mkdir()
    report={'started_at':now(),'revision':os.getenv('GITHUB_SHA','development'),
        'national_catalog_certified':False,'public_deployment':False,'stages':[]}
    def stage(name,**values):
        item={'stage':name,**values};report['stages'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    success=False
    try:
        snapshot=os.getenv('BDT_TERRITORY_SNAPSHOT')
        if snapshot:
            territory=import_territory_snapshot(database,Path(snapshot))
        else:
            path=root/'municipalities.json';meta=download_retry(IBGE_URL,path,16*1024*1024)
            count=import_ibge(database,path,file_source(path,'ibge',IBGE_URL,None))
            territory={'records':count,'sha256':meta['sha256'],'mode':'upstream_import'}
        stage('territory',**territory)
        raw=root/'cnes.zip';meta=download_registered(URL,raw,768*1024*1024)
        stage('distribution',**meta)
        selected=profile(raw);stage('profile',**selected)
        source=Source(dataset='cnes-national-bulk',url=URL,record_id=selected['member'],
            reference_date=None,collected_at=meta['collected_at'],snapshot_sha256=meta['sha256'])
        folder=root/'quality'
        quality=prepare(database,csv_records(raw,selected['member'],selected['encoding'],selected['delimiter']),
            source,folder,max_rejected=int(os.getenv('BDT_MAX_QUARANTINED','0')),
            max_rejected_fraction=float(os.getenv('BDT_MAX_QUARANTINED_FRACTION','0')))
        stage('quality',status=quality['status'],counts=quality['counts'],reasons=quality['reasons'],policy=quality['policy'])
        result=publish(database,folder);stage('import',**result)
        with database.session() as session:
            partitions=session.execute(select(Place.state,func.count(),func.count(Place.latitude))
                .where(Place.catalogue_eligible.is_(True)).group_by(Place.state)).all()
        report['partitions']=[{'state':state,'records':count,'geocoded':geo} for state,count,geo in partitions]
        stage('partitions',partitions=report['partitions'])
        release=export_catalog(database,public/'catalog',report['revision'])
        stage('public_release',files=release['files'])
        installed=install_catalog(public/'catalog',root/'roundtrip.db')
        stage('roundtrip',status=installed['status'],accounts_imported=installed['accounts_imported'])
        report['status']='partial_quality' if quality['counts'].get('quarantined',0) else 'imported_provided_file'
        success=True
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error)[:300])
        stage('failed',error_type=type(error).__name__,error=str(error)[:300])
    finally:
        quality_path=root/'quality'/'quality.json'
        if quality_path.exists():
            quality=json.loads(quality_path.read_text())
            atomic_json(public/'quality.json',quality)
            rejection=root/'quality'/'quarantine.jsonl'
            if rejection.exists():
                (public/'quarantine.jsonl').write_bytes(rejection.read_bytes())
        database.engine.dispose()
        report['finished_at']=now();atomic_json(public/'report.json',report)
        (root/'cnes.zip').unlink(missing_ok=True)
    if not success:raise SystemExit(1)


if __name__=='__main__':main()
