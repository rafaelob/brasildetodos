"""Exact third-party distribution URLs published by the official health catalog.

Only these registered objects are allowed on the shared S3 host. Other hosts
continue through the existing reviewed downloader. This is an operator tool;
production workers must also restrict egress independently of DNS checks.
"""
from __future__ import annotations
import hashlib
import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from .domain import now
from .ingest import safe_download
from .sync import atomic_json

CNES_FILES = frozenset({
    'https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_csv.zip',
    'https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_json.zip',
    'https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/CNES/cnes_estabelecimentos_xml.zip',
})


def download_registered(url: str, target: Path, max_bytes: int = 768*1024*1024) -> dict:
    parsed = urlsplit(url)
    if parsed.hostname != 's3.sa-east-1.amazonaws.com':
        return safe_download(url, target, max_bytes)
    if url not in CNES_FILES:
        raise ValueError('unregistered_cloud_object')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ValueError('non_public_distribution_address')
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.part-' + str(uuid4()))
    size, sha = 0, hashlib.sha256()
    try:
        with httpx.Client(timeout=httpx.Timeout(120, connect=20), follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', url, headers={'User-Agent':'BrasilDeTodos/0.2 (+https://github.com/rafaelob/brasildetodos)'}) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('full_distribution_response_required')
                with part.open('wb') as stream:
                    for block in response.iter_bytes():
                        size += len(block)
                        if size > max_bytes:
                            raise ValueError('distribution_byte_budget')
                        stream.write(block); sha.update(block)
                if size == 0:
                    raise ValueError('empty_distribution')
                manifest = {'url':url,'sha256':sha.hexdigest(),'bytes':size,'collected_at':now(),
                    'etag':response.headers.get('etag'),'last_modified':response.headers.get('last-modified'),
                    'catalog_url':'https://dadosabertos.saude.gov.br/dataset/cnes-cadastro-nacional-de-estabelecimentos-de-saude'}
        os.replace(part,target)
        atomic_json(target.with_suffix(target.suffix+'.manifest.json'),manifest)
        return manifest
    finally:
        part.unlink(missing_ok=True)
