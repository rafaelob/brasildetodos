// SPDX-License-Identifier: AGPL-3.0-or-later
import test from 'node:test';
import assert from 'node:assert/strict';
import {MAP_TEXT, mapText} from '../src/map-text.mjs';

test('MAP_TEXT contains complete 3D camera controls across pt-BR, en, and es', () => {
  const requiredKeys = [
    'bearing', 'pitch', 'zoom', 'camera3D', 'mode2D', 'mode3D',
    'resetCompass', 'rotateLeft', 'rotateRight', 'tiltDown', 'tiltUp', 'zoomIn3D',
    'landmarks3D', 'clickToInspect',
    'brasilia3D', 'saopaulo3D', 'rio3D', 'curitiba3D',
    'belohorizonte3D', 'salvador3D', 'recife3D', 'portoalegre3D'
  ];

  for (const locale of ['pt-BR', 'en', 'es']) {
    for (const key of requiredKeys) {
      const text = mapText(locale, key);
      assert.ok(text, `Missing text for key ${key} in locale ${locale}`);
      assert.notEqual(text, key, `Untranslated key fallback for ${key} in locale ${locale}`);
      assert.equal(typeof text, 'string');
      assert.ok(text.trim().length > 0);
    }
  }
});

test('3D city presets have distinct, localized labels in all languages', () => {
  const cities = [
    'brasilia3D', 'saopaulo3D', 'rio3D', 'curitiba3D',
    'belohorizonte3D', 'salvador3D', 'recife3D', 'portoalegre3D'
  ];

  for (const city of cities) {
    const pt = mapText('pt-BR', city);
    const en = mapText('en', city);
    const es = mapText('es', city);
    assert.ok(pt.includes('·'), `pt-BR label for ${city} should format city and landmark: ${pt}`);
    assert.ok(en.includes('·'), `en label for ${city} should format city and landmark: ${en}`);
    assert.ok(es.includes('·'), `es label for ${city} should format city and landmark: ${es}`);
  }
});

test('mapText returns fallback key gracefully on unknown keys', () => {
  assert.equal(mapText('pt-BR', 'nonexistent_key_123'), 'nonexistent_key_123');
  assert.equal(mapText('unknown_locale', 'bearing'), 'Orientação');
});
