# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded transport for the fixed INEP discovery page, not arbitrary URLs.

A transport retry never changes the year, chooses a mirror, follows redirects,
disables TLS checks or certifies a partial body. Only a full successful page
receives a byte hash and collection timestamp.
"""
from __future__ import annotations
import hashlib
import time
import httpx
from .education_bulk import ANCHOR
from .domain import now

MAX_BYTES=8*1024*1024
RETRYABLE={429,500,502,503,504}


def retry_delay(header: str | None, attempt: int) -> float:
    if header and header.isascii() and header.isdigit():
        return float(min(int(header[:8]),10))
    return float(min(2**attempt,8))


def official_anchor(*,attempts: int=3,sleep=time.sleep) -> tuple[str,dict]:
    if type(attempts) is not int or not 1<=attempts<=3:
        raise ValueError('official_anchor_retry_budget')
    with httpx.Client(timeout=httpx.Timeout(60,connect=20),trust_env=False,follow_redirects=False) as client:
        for attempt in range(attempts):
            blocks=[];size=0;sha=hashlib.sha256()
            try:
                with client.stream('GET',ANCHOR,headers={'User-Agent':'BrasilDeTodos/0.3 (+https://github.com/rafaelob/brasildetodos)'}) as response:
                    response.raise_for_status()
                    if response.status_code!=200 or 'text/html' not in response.headers.get('content-type',''):
                        raise ValueError('official_anchor_response_requires_review')
                    for block in response.iter_bytes():
                        size+=len(block)
                        if size>MAX_BYTES:raise ValueError('official_anchor_byte_budget')
                        blocks.append(block);sha.update(block)
                if not size:raise ValueError('official_anchor_empty_page')
                text=b''.join(blocks).decode('utf-8')
                return text,{'url':ANCHOR,'bytes':size,'sha256':sha.hexdigest(),
                             'collected_at':now(),'attempts':attempt+1,'status_code':200}
            except (httpx.TimeoutException,httpx.NetworkError,httpx.RemoteProtocolError,httpx.HTTPStatusError) as error:
                if isinstance(error,httpx.HTTPStatusError):
                    if error.response.status_code not in RETRYABLE:raise
                    delay=retry_delay(error.response.headers.get('retry-after'),attempt)
                else:delay=retry_delay(None,attempt)
                if attempt+1==attempts:raise
                sleep(delay)
    raise RuntimeError('official_anchor_unreachable_state')
