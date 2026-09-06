"""Build a minimized health catalog from the bulk file linked by the official portal."""
from __future__ import annotations
import codecs
import csv
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from sqlalchemy import func, select
from bdt.cnes_bulk import REQUIRED, converted
from bdt.domain import now
from bdt.ingest import IBGE_URL, csv_records, file_source, import_ibge, import_places
from bdt.storage import Database, Place
from bdt.sync import atomic_json, download_retry
from bdt.transport import download_registered

URL='https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip'
ROOT=Path('test-results/national-health')


def detect_encoding(archive,name):
    decoder=codecs.getincrementaldecoder('utf-8-sig')('strict')
    try:
        with archive.open(name) as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):
                decoder.decode(chunk)
            decoder.decode(b'',final=True)
        return 'utf-8-sig'
    except UnicodeDecodeError:
        return 'cp1252'


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    report={'started_at':now(),'source':URL,'national_catalog_certified':False,
        'scope':'CNES bulk: textual outpatient SUS declaration, excluding nonempty deactivation reasons; not live availability','stages':[]}
    database=Database('sqlite:///'+str(ROOT/'catalog.db'));database.initialize()
    success=False
    try:
        path=ROOT/'municipalities.json';meta=download_retry(IBGE_URL,path,16*1024*1024)
        total=import_ibge(database,path,file_source(path,'ibge',IBGE_URL,None))
        report['stages'].append({'stage':'municipalities','status':'imported','records':total,'sha256':meta['sha256']})
        print(json.dumps(report['stages'][-1]),flush=True)
        path=ROOT/'cnes.csv.zip';meta=download_registered(URL,path,768*1024*1024)
        report['distribution']=meta
        with zipfile.ZipFile(path) as archive:
            members=[item for item in archive.infolist() if item.filename.lower().endswith('.csv')]
            report['members']=[{'name':item.filename,'bytes':item.file_size} for item in members]
            if len(members)!=1:
                raise ValueError('bulk_member_profile_review_required')
            member=members[0]
            if member.file_size>4*1024**3 or member.file_size/max(member.compress_size,1)>500:
                raise ValueError('bulk_uncompressed_budget')
            encoding=detect_encoding(archive,member.filename)
            with archive.open(member) as raw:
                first=io.TextIOWrapper(raw,encoding=encoding,newline='').readline()
            delimiter=max([';',',','\t','|'],key=lambda value:len(next(csv.reader([first],delimiter=value))))
            fields=next(csv.reader([first],delimiter=delimiter))
            report['profile']={'member':member.filename,'encoding':encoding,'delimiter':delimiter,'fields':fields}
        print(json.dumps({'stage':'header','profile':report['profile'],'bytes':meta['bytes'],'sha256':meta['sha256']},ensure_ascii=False),flush=True)
        if not REQUIRED.issubset(fields):
            raise ValueError('bulk_columns_require_reviewed_adapter')
        flags=Counter();disabled=Counter();read=0
        for row in csv_records(path,member.filename,encoding,delimiter):
            flags[str(row['CO_AMBULATORIAL_SUS'])]+=1
            disabled[str(row['CO_MOTIVO_DESAB'])]+=1
            read+=1
        report['profile']['eligibility_values']={'outpatient_sus':dict(flags),'deactivation':dict(disabled),'rows':read}
        print(json.dumps({'stage':'eligibility_values','values':report['profile']['eligibility_values']},ensure_ascii=False),flush=True)
        source=file_source(path,'cnes-national-bulk',URL,None)
        report['import']=import_places(database,converted(csv_records(path,member.filename,encoding,delimiter)),source,'cnes')
        with database.session() as session:
            partitions=session.execute(select(Place.state,func.count(),func.count(Place.latitude))
                .where(Place.dataset=='cnes-national-bulk',Place.catalogue_eligible.is_(True)).group_by(Place.state)).all()
        report['partitions']=[{'state':state,'records':count,'geocoded':geo} for state,count,geo in partitions]
        report['status']='imported'
        print(json.dumps({'stage':'import','result':report['import'],'partitions':report['partitions']},ensure_ascii=False),flush=True)
        success=True
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,error=str(error)[:400])
        print(json.dumps({'stage':'failed','error_type':type(error).__name__,'error':str(error)[:400]},ensure_ascii=False),flush=True)
    finally:
        with database.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        database.engine.dispose();report['finished_at']=now();atomic_json(ROOT/'report.json',report)
        (ROOT/'cnes.csv.zip').unlink(missing_ok=True)
    if not success:
        raise SystemExit(1)


if __name__=='__main__':
    main()
