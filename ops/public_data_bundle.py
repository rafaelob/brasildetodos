# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build/verify an installable public-data bundle from pinned, reviewed artifacts.

Never exports arbitrary files, active databases, community data or raw microdata.
The original public records keep their provenance. This is not fresh collection.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from bdt.catalog_release import FILES, load_manifest, verify_catalog
from bdt.resource_artifact import verify_resource_artifact
from bdt.resource_release import _copy_pinned
from resource_release_acceptance import exercise

FORMAT='bdt.public-data-bundle.v1'
MEMBERS=tuple('catalog/'+name for name in (*FILES,'manifest.json'))+('resources/report.json','resources/resources.jsonl','acceptance.json')
MAX_BYTES=512*1024*1024
MAX_MEMBER=256*1024*1024


def encode(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def pins(catalog_sha256,report_sha256,resources_sha256):
    values={'catalog_manifest_sha256':catalog_sha256,'report_sha256':report_sha256,'resources_sha256':resources_sha256}
    if any(not re.fullmatch(r'[a-f0-9]{64}',v) for v in values.values()):raise ValueError('bundle_external_hashes_required')
    return values


def freeze(catalog,resources,folder,selected):
    cat=folder/'catalog';res=folder/'resources';cat.mkdir();res.mkdir()
    _copy_pinned(Path(catalog)/'manifest.json',cat/'manifest.json',selected['catalog_manifest_sha256'],4*1024*1024)
    declared=json.loads((cat/'manifest.json').read_text())
    if not isinstance(declared,dict) or set(declared.get('files',{}))!=set(FILES):raise ValueError('bundle_catalog_manifest_invalid')
    total=0
    for name in FILES:
        expected=declared['files'][name]
        if not isinstance(expected,dict) or type(expected.get('bytes')) is not int or expected['bytes']<0:raise ValueError('bundle_catalog_metadata_invalid')
        total+=expected['bytes']
        if total>MAX_BYTES or expected['bytes']>MAX_MEMBER:raise ValueError('bundle_size_budget')
        _copy_pinned(Path(catalog)/name,cat/name,expected['sha256'],MAX_MEMBER)
    verify_catalog(cat)
    _copy_pinned(Path(resources)/'report.json',res/'report.json',selected['report_sha256'],4*1024*1024)
    _copy_pinned(Path(resources)/'resources.jsonl',res/'resources.jsonl',selected['resources_sha256'],MAX_MEMBER)
    verify_resource_artifact(res)


def validate_folder(folder,manifest):
    if (not isinstance(manifest,dict) or manifest.get('schema')!=FORMAT or
        manifest.get('fresh_collection') is not False or manifest.get('public_deployment') is not False or
        manifest.get('includes_private_data') is not False or set(manifest.get('files',{}))!=set(MEMBERS)):
        raise ValueError('bundle_manifest_invalid')
    selected=manifest['selected_inputs']
    pins(selected['catalog_manifest_sha256'],selected['report_sha256'],selected['resources_sha256'])
    if not re.fullmatch(r'[a-f0-9]{40}',manifest.get('code_revision','')):raise ValueError('bundle_revision_invalid')
    for name in MEMBERS:
        file=folder/name;expected=manifest['files'][name]
        if file.is_symlink() or not file.is_file() or file.stat().st_size!=expected['bytes'] or sha(file)!=expected['sha256']:
            raise ValueError('bundle_member_hash_mismatch')
    if (sha(folder/'catalog/manifest.json')!=selected['catalog_manifest_sha256'] or
        sha(folder/'resources/report.json')!=selected['report_sha256'] or
        sha(folder/'resources/resources.jsonl')!=selected['resources_sha256']):
        raise ValueError('bundle_selected_input_mismatch')
    verify_catalog(folder/'catalog');resource=verify_resource_artifact(folder/'resources')
    result=json.loads((folder/'acceptance.json').read_text())
    if (result.get('status')!='passed' or result.get('fresh_collection') is not False or
        result.get('synthetic_records_added') is not False or result.get('public_deployment') is not False or
        result.get('api_checked') is not True or result.get('catalog_manifest_sha256')!=selected['catalog_manifest_sha256'] or
        result.get('counts')!=manifest['counts']):raise ValueError('bundle_acceptance_invalid')
    catalog_manifest=load_manifest(folder/'catalog')
    if (manifest['counts']['places']!=catalog_manifest['files']['places.jsonl']['records'] or
        manifest['counts']['resources']!=resource['records'] or manifest['counts']['users'] or manifest['counts']['observations']):
        raise ValueError('bundle_count_mismatch')
    return {'status':'passed','schema':FORMAT,'counts':manifest['counts'],'selected_inputs':selected,
            'fresh_collection':False,'public_deployment':False,'includes_private_data':False}


def verify(path,expected_sha256):
    path=Path(path)
    with tempfile.TemporaryDirectory(prefix='bdt-bundle-verify-') as tmp:
        root=Path(tmp);pinned=root/'selected.zip'
        _copy_pinned(path,pinned,expected_sha256,MAX_BYTES)
        with zipfile.ZipFile(pinned) as archive:
            entries=archive.infolist();names=[entry.filename for entry in entries]
            if len(names)!=len(set(names)) or set(names)!=set(MEMBERS)|{'bundle.json'}:raise ValueError('bundle_unexpected_members')
            total=0
            for entry in entries:
                total+=entry.file_size
                if entry.is_dir() or entry.file_size>MAX_MEMBER or total>MAX_BYTES or entry.flag_bits&1:
                    raise ValueError('bundle_size_or_encryption_budget')
                if (entry.external_attr>>16)&0o170000 not in (0,0o100000):raise ValueError('bundle_unsupported_member_type')
                target=root/entry.filename;target.parent.mkdir(parents=True,exist_ok=True)
                written=0
                with archive.open(entry) as reader,target.open('xb') as writer:
                    for block in iter(lambda:reader.read(1024*1024),b''):
                        written+=len(block)
                        if written>entry.file_size or written>MAX_MEMBER:raise ValueError('bundle_member_budget')
                        writer.write(block)
                if written!=entry.file_size:raise ValueError('bundle_member_truncated')
        result=validate_folder(root,json.loads((root/'bundle.json').read_text()))
        return result|{'archive_sha256':expected_sha256,'archive_bytes':pinned.stat().st_size}


def build(catalog,resources,output,*,catalog_sha256,report_sha256,resources_sha256,revision):
    output=Path(output)
    if output.exists() or output.is_symlink():raise FileExistsError('bundle_destination_exists')
    if not re.fullmatch(r'[a-f0-9]{40}',revision):raise ValueError('bundle_revision_invalid')
    selected=pins(catalog_sha256,report_sha256,resources_sha256)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.bdt-data-bundle-',dir=output.parent) as tmp:
        root=Path(tmp);freeze(catalog,resources,root,selected)
        accepted=exercise(root/'catalog',root/'resources',catalog_sha256=catalog_sha256,report_sha256=report_sha256,resources_sha256=resources_sha256)
        (root/'acceptance.json').write_bytes(encode(accepted))
        manifest={'schema':FORMAT,'code_revision':revision,'selected_inputs':selected,'counts':accepted['counts'],
                  'fresh_collection':False,'public_deployment':False,'includes_private_data':False,
                  'files':{name:{'bytes':(root/name).stat().st_size,'sha256':sha(root/name)} for name in MEMBERS}}
        (root/'bundle.json').write_bytes(encode(manifest));validate_folder(root,manifest)
        pending=root/'bundle.zip'
        with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name in (*MEMBERS,'bundle.json'):
                info=zipfile.ZipInfo(name,date_time=(2026,9,6,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                with archive.open(info,'w',force_zip64=True) as writer,(root/name).open('rb') as reader:
                    for block in iter(lambda:reader.read(1024*1024),b''):writer.write(block)
        result=verify(pending,sha(pending))
        os.link(pending,output)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
    create=sub.add_parser('build');create.add_argument('--catalog',required=True,type=Path);create.add_argument('--resources',required=True,type=Path)
    create.add_argument('--output',required=True,type=Path);create.add_argument('--revision',required=True)
    for arg in ('catalog-sha256','report-sha256','resources-sha256'):create.add_argument('--'+arg,required=True)
    check=sub.add_parser('verify');check.add_argument('archive',type=Path);check.add_argument('--sha256',required=True)
    args=parser.parse_args(argv)
    if args.operation=='build':result=build(args.catalog,args.resources,args.output,catalog_sha256=args.catalog_sha256,report_sha256=args.report_sha256,resources_sha256=args.resources_sha256,revision=args.revision)
    else:result=verify(args.archive,args.sha256)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
