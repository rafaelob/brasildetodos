"""Strict JSON decoding shared by collection boundaries."""
from __future__ import annotations

import json
from typing import Callable


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('non_finite_json_number')


def decode(raw: bytes, *, parse_float: Callable[[str], object] | None = None):
    options = {'object_pairs_hook': _pairs, 'parse_constant': _constant}
    if parse_float is not None:
        options['parse_float'] = parse_float
    return json.loads(raw.decode('utf-8-sig'), **options)
