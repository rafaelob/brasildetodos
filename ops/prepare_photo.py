# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare a bounded JPEG/PNG derivative without storing or publishing the original.

This operator command does not upload, approve, associate or publish a photograph.
It writes a new file only, with explicit opaque masks and a receipt without paths.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from bdt.photos import Mask, MAX_INPUT_BYTES, sanitize


def prepare(source: Path, destination: Path, *, masks=None):
    source, destination = Path(source), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('photo_destination_exists')
    if source.is_symlink() or not source.is_file():
        raise ValueError('regular_photo_source_required')
    with source.open('rb') as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError('photo_size_limit')
    selected = [Mask.model_validate(mask) for mask in (masks or [])]
    result = sanitize(base64.b64encode(raw).decode('ascii'), selected)
    content = result.pop('content')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.bdt-photo-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'derivative.jpg'
        with staged.open('xb') as stream:
            stream.write(content); stream.flush(); os.fsync(stream.fileno())
        staged.chmod(0o600)
        os.link(staged, destination)
    return {'schema': 'bdt.photo-derivative.v1', **result,
            'original_stored': False, 'uploaded': False, 'approved': False,
            'identity_or_anonymity_certified': False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--masks', type=Path)
    args=parser.parse_args(argv)
    masks=[]
    if args.masks:
        if args.masks.is_symlink() or not args.masks.is_file():
            raise ValueError('regular_mask_file_required')
        with args.masks.open('rb') as stream: raw=stream.read(32769)
        if len(raw)>32768: raise ValueError('mask_file_too_large')
        masks=json.loads(raw)
        if not isinstance(masks,list) or len(masks)>20: raise ValueError('invalid_mask_collection')
    result=prepare(args.source,args.output,masks=masks)
    print(json.dumps(result,sort_keys=True));return result


if __name__=='__main__': main()
