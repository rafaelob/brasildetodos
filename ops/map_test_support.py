"""Tiny synthetic MVT/style fixtures: browser tests only, never production data."""
from __future__ import annotations
import struct


def varint(value: int) -> bytes:
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(number: int, value: bytes | int) -> bytes:
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def tile() -> bytes:
    # Clockwise polygon in tile coordinates (positive Y down). Units: meters.
    def zigzag(value: int) -> int:
        return (value << 1) ^ (value >> 31)
    commands = [9, zigzag(1024), zigzag(1024), 26, zigzag(2048), 0,
                0, zigzag(2048), zigzag(-2048), 0, 15]
    tags = b''.join(varint(x) for x in (0, 0, 1, 1))
    feature = field(1, 1) + field(2, tags) + field(3, 3) + field(4, b''.join(varint(x) for x in commands))
    layer = field(15, 2) + field(1, b'building') + field(2, feature)
    layer += field(3, b'render_height') + field(3, b'render_min_height')
    # Value.double_value = field 3, wire type 1.
    layer += field(4, varint(3 << 3 | 1) + struct.pack('<d', 24.0))
    layer += field(4, varint(3 << 3 | 1) + struct.pack('<d', 0.0))
    return field(3, layer + field(5, 4096))


def style(*, buildings: bool = True) -> dict:
    sources = {'unused-first-vector': {'type': 'vector', 'tiles': ['https://tiles.openfreemap.org/test/unused/{z}/{x}/{y}.pbf']}}
    layers = [{'id': 'background', 'type': 'background', 'paint': {'background-color': '#e7eee8'}}]
    if buildings:
        sources['actual-buildings'] = {'type': 'vector', 'minzoom': 15, 'maxzoom': 16,
            'tiles': ['https://tiles.openfreemap.org/test/building/{z}/{x}/{y}.pbf'],
            'attribution': 'SYNTHETIC TEST ONLY — not official buildings'}
        layers.append({'id': 'building-footprints', 'type': 'fill', 'source': 'actual-buildings',
            'source-layer': 'building', 'minzoom': 15, 'paint': {'fill-color': '#b7cfc2'}})
    return {'version': 8, 'sources': sources, 'layers': layers,
            'glyphs': 'https://tiles.openfreemap.org/test/font/{fontstack}/{range}.pbf'}
