"""Strict JSON decoding shared by collection boundaries."""
from __future__ import annotations

import json
import math
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


def _finite_float(raw: str) -> float:
    # parse_constant only sees literal NaN/Infinity, not overflow such as 1e999.
    value = float(raw)
    if not math.isfinite(value):
        raise ValueError('non_finite_json_number')
    return value


def decode(raw: bytes, *, parse_float: Callable[[str], object] | None = None):
    options = {'object_pairs_hook': _pairs, 'parse_constant': _constant,
               'parse_float': _finite_float if parse_float is None else parse_float}
    return json.loads(raw.decode('utf-8-sig'), **options)
