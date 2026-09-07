# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recover one reviewed resource artifact by its external archive hash.

GitHub's per-run latest-attempt listing can omit an earlier still-downloadable
artifact. The caller obtains the exact artifact ID through the normal API;
this verifier never chooses a replacement and never makes a network request.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile
from bdt.resource_release import _copy_pinned

NAMES={'report.json','resources.jsonl','artifact-check.json'}
MAX_ARCHIVE=32*1024*1024
MAX_EXPANDED=256*1024*1024


def unpack(archive:Path,destination:Path,expected_sha256:str)->dict:
    destination=Path(destination)
    if destination.exists() or destination.is_symlink():raise FileExistsError('reviewed_artifact_destination_exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.reviewed-resource-',dir=destination.parent) as tmp:
        root=Path(tmp);pinned=root/'selected.zip';stage=root/'extracted';stage.mkdir()
        _copy_pinned(archive,pinned,expected_sha256,MAX_ARCHIVE)
        manifest={}
        with zipfile.ZipFile(pinned) as source:
            entries=source.infolist();names=[entry.filename for entry in entries]
            if len(names)!=len(set(names)) or set(names)!=NAMES:raise ValueError('reviewed_artifact_members')
            if sum(entry.file_size for entry in entries)>MAX_EXPANDED:raise ValueError('reviewed_artifact_budget')
            for entry in entries:
                if entry.flag_bits&1 or (entry.external_attr>>16)&0o170000 not in (0,0o100000):raise ValueError('reviewed_artifact_member_type')
                limit=MAX_EXPANDED if entry.filename=='resources.jsonl' else 4*1024*1024
                if entry.file_size>limit:raise ValueError('reviewed_artifact_budget')
                size=0;digest=hashlib.sha256()
                with source.open(entry) as reader,(stage/entry.filename).open('xb') as writer:
                    for block in iter(lambda:reader.read(1024*1024),b''):
                        size+=len(block)
                        if size>limit or size>entry.file_size:raise ValueError('reviewed_artifact_budget')
                        digest.update(block);writer.write(block)
                if size!=entry.file_size:raise ValueError('reviewed_artifact_truncated')
                manifest[entry.filename]={'bytes':size,'sha256':digest.hexdigest()}
        if destination.exists() or destination.is_symlink():raise FileExistsError('reviewed_artifact_destination_exists')
        stage.rename(destination)
    return {'status':'passed','archive_sha256':expected_sha256,'files':manifest,
            'fresh_collection':False,'semantic_validation_required':True,'production_database_changed':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path);parser.add_argument('--destination',required=True,type=Path);parser.add_argument('--sha256',required=True)
    args=parser.parse_args(argv)
    print(json.dumps(unpack(args.archive,args.destination,args.sha256),indent=2))

if __name__=='__main__':main()
