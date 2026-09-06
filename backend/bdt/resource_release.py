# SPDX-License-Identifier: AGPL-3.0-or-later
"""Install selected public resource bytes into an existing application database.

This operator command does not collect data, infer facility links, import private
content or reconstruct historical versions. External hashes are mandatory; a
self-consistent manifest is not proof of origin. All records share one transaction.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .domain import digest, now
from .evidence import Resource, ResourceInput
from .resource_artifact import MAX_BYTES, MAX_LINE_BYTES, verify_resource_artifact
from .resource_export import AMOUNTS, FIELDS, public_resource
from .resource_profiles import PROFILES, STATES, date_value
from .resource_sync import ResourceRevision, _newer, changed_fields, decode, initialize_resource_versions, semantic
from .storage import Database, Ingestion, Municipality

KINDS={'pncp_contracts':'contract','transferegov_special_plans':'proposal','obrasgov_projects':'work'}
TERRITORY={'pncp_contracts':'buyer_registered_municipality_not_execution',
           'transferegov_special_plans':'beneficiary_municipality_not_resolved',
           'obrasgov_projects':'state_only_municipality_unresolved'}
ATTRIBUTES=set(FIELDS)|{key+'_cents' for key in AMOUNTS}|{'financial_interpretation','facility_id',
    'precise_amounts','planned_investments','beneficiary_id','collection_page_url','record_reference_url'}


def _copy_pinned(source: Path, target: Path, expected: str, budget: int):
    if not re.fullmatch(r'[a-f0-9]{64}',expected):
        raise ValueError('release_external_sha256_required')
    if source.is_symlink() or not source.is_file():
        raise ValueError('release_regular_file_required')
    size=0; sha=hashlib.sha256()
    with source.open('rb') as reader, target.open('xb') as writer:
        target.chmod(0o600)
        while block:=reader.read(1024*1024):
            size+=len(block)
            if size>budget:raise ValueError('release_byte_budget')
            sha.update(block);writer.write(block)
    if sha.hexdigest()!=expected:raise ValueError('release_external_hash_mismatch')


def _validate(raw: dict, territories: dict):
    body=ResourceInput.model_validate(raw)
    attrs=body.attributes;profile=attrs.get('profile')
    if (profile not in PROFILES or body.source.dataset!=profile or body.kind!=KINDS[profile]
            or body.id!=profile+':'+body.source.record_id):
        raise ValueError('release_resource_identity_mismatch')
    if set(attrs)-ATTRIBUTES:raise ValueError('release_unreviewed_metadata')
    for key in FIELDS:
        value=attrs.get(key)
        if value is not None and ((key=='year' and (type(value) is not int or not 2000<=value<=2100))
                or (key!='year' and not isinstance(value,str))):
            raise ValueError('release_invalid_metadata_type')
    if set(attrs.get('precise_amounts',{}))-{'initial','global','accumulated'}:
        raise ValueError('release_unknown_amount_field')
    for entry in attrs.get('planned_investments',[]):
        if not isinstance(entry,dict) or set(entry)-{'planned_cents','source_name'}:
            raise ValueError('release_unreviewed_investment_metadata')
    if attrs.get('financial_interpretation')!='not_payment' or attrs.get('facility_id') is not None:
        raise ValueError('release_financial_or_facility_claim')
    if attrs.get('territorial_basis')!=TERRITORY[profile]:
        raise ValueError('release_territorial_basis_mismatch')
    state=attrs.get('state')
    if state is not None and state not in STATES:raise ValueError('release_unknown_state')
    basis='publisher_update' if profile=='pncp_contracts' else 'collection_snapshot'
    if attrs.get('version_basis')!=basis:raise ValueError('release_version_basis_mismatch')
    if profile=='pncp_contracts':
        if (body.municipality_id not in territories or territories[body.municipality_id]!=state):
            raise ValueError('release_buyer_territory_not_loaded')
        if attrs.get('source_control_number')!=body.source.record_id:
            raise ValueError('release_control_number_mismatch')
        if not attrs.get('upstream_updated_at'):
            raise ValueError('release_missing_version_time')
        date_value(attrs['upstream_updated_at'],timestamp=True)
    elif body.municipality_id is not None:
        raise ValueError('release_unresolved_territory_cannot_be_assigned')
    payload=body.model_dump(mode='json')
    public_resource(payload)  # Includes exact cents/subcent conflict validation.
    return body,payload


def install_resource_release(database, folder: Path, *, report_sha256: str, resources_sha256: str) -> dict:
    """Freeze selected bytes first; publish all profiles or no resource changes."""
    with tempfile.TemporaryDirectory(prefix='bdt-resource-release-') as temporary:
        snapshot=Path(temporary)
        _copy_pinned(Path(folder)/'report.json',snapshot/'report.json',report_sha256,4*1024*1024)
        _copy_pinned(Path(folder)/'resources.jsonl',snapshot/'resources.jsonl',resources_sha256,MAX_BYTES)
        checked=verify_resource_artifact(snapshot)
        if checked['report_sha256']!=report_sha256 or checked['resources_sha256']!=resources_sha256:
            raise ValueError('release_snapshot_mismatch')
        initialize_resource_versions(database)
        profiles=sorted(checked['by_profile'])
        loads={}
        with database.session() as session:
            for profile in profiles:
                row=Ingestion(dataset=profile,source={'mode':'verified_artifact_install',
                    'report_sha256':report_sha256,'resources_sha256':resources_sha256})
                session.add(row);session.flush();loads[profile]=row.id
        counters={profile:Counter(read=0,created=0,updated=0,unchanged=0) for profile in profiles}
        try:
            with database.session() as session:
                territories={row.id:row.state for row in session.scalars(select(Municipality))}
                with (snapshot/'resources.jsonl').open('rb') as stream:
                    for line in stream:
                        if len(line)>MAX_LINE_BYTES:raise ValueError('release_row_budget')
                        body,payload=_validate(decode(line),territories)
                        profile=body.source.dataset;counts=counters[profile];counts['read']+=1
                        fingerprint=digest(semantic(payload))
                        current=session.scalar(select(Resource).where(Resource.id==body.id).with_for_update())
                        last=session.scalar(select(ResourceRevision).where(ResourceRevision.resource_id==body.id)
                            .order_by(ResourceRevision.revision.desc()).limit(1))
                        if current is None:
                            if last is not None:raise ValueError('release_orphan_version')
                            session.add(Resource(id=body.id,kind=body.kind,title=body.title,
                                municipality_id=body.municipality_id,source=payload['source'],payload=payload))
                            session.flush();version=1;fields=['initial_import'];counts['created']+=1
                        else:
                            if (last is None or current.source!=current.payload['source']
                                    or current.title!=current.payload['title'] or current.kind!=current.payload['kind']
                                    or current.municipality_id!=current.payload.get('municipality_id')
                                    or current.source['dataset']!=profile
                                    or last.fingerprint!=digest(semantic(current.payload))
                                    or last.fingerprint!=digest(semantic(last.payload))):
                                raise ValueError('release_current_ledger_conflict')
                            if last.fingerprint==fingerprint:
                                counts['unchanged']+=1;continue
                            _newer(current.payload,payload)
                            version=last.revision+1;fields=changed_fields(current.payload,payload)
                            current.title,current.kind,current.municipality_id=body.title,body.kind,body.municipality_id
                            current.payload,current.source=payload,payload['source'];counts['updated']+=1
                        session.add(ResourceRevision(resource_id=body.id,revision=version,fingerprint=fingerprint,
                            payload=payload,observed_at=now(),changed_fields=fields));session.flush()
                again=verify_resource_artifact(snapshot)
                if again['resources_sha256']!=resources_sha256 or again['report_sha256']!=report_sha256:
                    raise ValueError('release_bytes_changed_before_commit')
                if {p:c['read'] for p,c in counters.items()}!=checked['by_profile']:
                    raise ValueError('release_published_count_mismatch')
                for profile,load_id in loads.items():
                    load=session.get(Ingestion,load_id)
                    load.status,load.finished_at,load.counts='success',now(),dict(counters[profile])
        except Exception as error:
            with database.session() as session:
                for profile,load_id in loads.items():
                    load=session.get(Ingestion,load_id);load.status,load.finished_at='failed',now()
                    load.error='resource_release_install_failed'
                    load.counts={'records_attempted':counters[profile]['read'],'published':0,'rolled_back':True}
            if isinstance(error,IntegrityError):
                raise ValueError('release_concurrent_install_retry_required') from None
            raise
        return {'schema':'bdt.resource-release.v1','status':'installed','installed_at':now(),
            'records':checked['records'],'by_profile':{p:dict(c) for p,c in counters.items()},
            'ingestion_ids':loads,'report_sha256':report_sha256,'resources_sha256':resources_sha256,
            'subcent_records':checked['subcent_records'],'subcent_fields':checked['subcent_fields'],
            'removed':0,'financial_events_created':0,'automatic_place_links':0,
            'private_tables_imported':False,'historical_ledger_imported':False,
            'fresh_collection':False,'national_coverage_certified':False,'public_deployment':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path)
    parser.add_argument('--report-sha256',required=True)
    parser.add_argument('--resources-sha256',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    url=os.getenv('BDT_DATABASE_URL')
    if not url:parser.error('BDT_DATABASE_URL is required')
    # Exclusive reservation avoids a successful install followed by clobbering
    # evidence from a different operation. Never overwrite an existing report.
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as out:
        args.output.chmod(0o600)
        database=Database(url)
        try:
            database.initialize()
            result=install_resource_release(database,args.folder,
                report_sha256=args.report_sha256,resources_sha256=args.resources_sha256)
        except Exception as error:
            # Controlled structural status only; no database URL, SQL or raw rows.
            result={'status':'failed','error_type':type(error).__name__,
                    'reason':'resource_release_requires_review','public_deployment':False}
        finally:database.engine.dispose()
        json.dump(result,out,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status']=='installed' else 1


if __name__=='__main__':raise SystemExit(main())
