// SPDX-License-Identifier: AGPL-3.0-or-later
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {heroFromCoverage} from '../src/coverage-text.mjs';

const emptyInstall={
  schema_version:1,
  national_catalog_certified:false,
  municipalities:0,
  summary:{places:0,geocoded:0,without_geometry:0,resources:0},
  sources:[]
};

test('heroFromCoverage empty payload is emptyInstall, not certified, places 0',()=>{
  const result=heroFromCoverage(emptyInstall);
  assert.equal(result.emptyInstall,true);
  assert.equal(result.certified,false);
  assert.equal(result.places,0);
  assert.equal(result.municipalities,0);
  assert.equal(result.withoutGeometry,0);
  assert.equal(result.failedImports,0);
});

test('missing or invalid payload does not invent national totals and is not certified',()=>{
  for(const payload of [undefined,null,'',0,[],{summary:null},{summary:{places:'20'}},{summary:{places:-1}},{summary:{places:1.2}},{}]){
    const result=heroFromCoverage(payload);
    assert.equal(result.certified,false);
    assert.equal(result.emptyInstall,false);
    assert.equal(result.places,null);
    assert.equal(result.municipalities,null);
    assert.equal(result.withoutGeometry,null);
    assert.notEqual(result.places,234209);
    assert.notEqual(result.municipalities,5570);
    assert.notEqual(result.withoutGeometry,63930);
    assert.notEqual(result.places,0);
  }
});

test('loaded payload maps places, municipalities, without_geometry and counts failed last attempts',()=>{
  const result=heroFromCoverage({
    schema_version:1,
    national_catalog_certified:false,
    municipalities:12,
    summary:{places:40,geocoded:30,without_geometry:10,resources:5},
    sources:[
      {id:'inep',last_attempt:{status:'failed'}},
      {id:'cnes',last_attempt:{status:'completed'}},
      {id:'pncp',last_attempt:{status:'failed'}},
      {id:'ibge',last_attempt:null},
      {id:'transferegov'},
      {id:'obrasgov',last_attempt:{status:'partial'}},
      {id:'other',last_attempt:{status:'running'}}
    ]
  });
  assert.equal(result.places,40);
  assert.equal(result.municipalities,12);
  assert.equal(result.withoutGeometry,10);
  assert.equal(result.failedImports,2);
  assert.equal(result.emptyInstall,false);
  assert.equal(result.certified,false);
});

test('national_catalog_certified true still yields certified false',()=>{
  const result=heroFromCoverage({
    national_catalog_certified:true,
    municipalities:1,
    summary:{places:1,without_geometry:0},
    sources:[]
  });
  assert.equal(result.certified,false);
  assert.equal(result.emptyInstall,false);
  assert.equal(result.places,1);
});

test('explore hero fetches /coverage and does not hardcode certified-zip totals',()=>{
  const source=readFileSync(new URL('../src/main.tsx',import.meta.url),'utf8');
  assert.ok(source.includes("'/coverage'"));
  assert.ok(source.includes('heroFromCoverage'));
  assert.ok(source.includes('AbortController'));
  for(const banned of ['234209','5570','63930']){
    assert.equal(source.includes(banned),false,`main.tsx must not contain ${banned}`);
  }
});
