// SPDX-License-Identifier: AGPL-3.0-or-later
import test from 'node:test';
import assert from 'node:assert/strict';
import {regionMessages,regionParameters} from '../src/region-text.mjs';
import {uiText} from '../src/ui-text.mjs';
test('region messages are complete, registered and not shared accidental fallbacks',()=>{
 const keys=Object.keys(regionMessages['pt-BR']).sort();
 for(const locale of ['pt-BR','en','es']){assert.deepEqual(Object.keys(regionMessages[locale]).sort(),keys);for(const key of keys){assert.equal(uiText(locale,key),regionMessages[locale][key]);assert.notEqual(uiText(locale,key),key);}}
});
test('region queries preserve literals and omit private or invalid criteria',()=>{
 const p=new URLSearchParams(regionParameters('São José 100%','BA',2));assert.equal(p.get('q'),'São José 100%');assert.equal(p.get('page'),'2');assert.equal(p.get('limit'),'12');assert.equal(p.get('state'),'BA');assert.equal([...p.keys()].length,4);
 assert.equal(new URLSearchParams(regionParameters('x'.repeat(500),'evil',-1)).get('q').length,200);
 assert.equal(new URLSearchParams(regionParameters('',null,NaN)).get('page'),'1');
 assert.equal(new URLSearchParams(regionParameters('','SP',1e9)).get('page'),'100000');
});
