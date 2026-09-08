import test from 'node:test';
import assert from 'node:assert/strict';
import {coverageMessages,coverageCount,sourceLabel,statusLabel,partitionSelection,SOURCE_IDS,STATUS_IDS} from '../src/coverage-text.mjs';
import {uiText} from '../src/ui-text.mjs';

test('coverage translations have the same nonempty keys in all locales',()=>{
 for(const locale of ['pt-BR','en','es']){
  assert.deepEqual(Object.keys(coverageMessages[locale]).sort(),Object.keys(coverageMessages['pt-BR']).sort());
  for(const [key,value] of Object.entries(coverageMessages[locale])){assert.equal(typeof value,'string');assert.ok(value.length>0);assert.equal(uiText(locale,key),value);}
 }
});
test('counts preserve zero and do not invent an unknown count',()=>{
 const t=()=>'?';assert.equal(coverageCount(0,'pt-BR',t),'0');assert.equal(coverageCount(1000,'en',t),'1,000');
 for(const value of [null,undefined,'20',NaN,-1,Infinity,1.2,Number.MAX_SAFE_INTEGER+1]) assert.equal(coverageCount(value,'en',t),'?');
});
test('arbitrary labels cannot become a source or status name',()=>{
 const t=key=>key;assert.equal(sourceLabel('PRIVATE_LABEL',t),'coverageOther');assert.equal(sourceLabel('__proto__',t),'coverageOther');
 assert.equal(statusLabel('PRIVATE_LABEL',t),'coverageUnknown');assert.equal(statusLabel('constructor',t),'coverageUnknown');
 for(const id of SOURCE_IDS)assert.ok(sourceLabel(id,t));for(const id of STATUS_IDS)assert.ok(statusLabel(id,t));
});
test('territorial filters do not change global data or remove unknown geometry',()=>{
 const rows=[{source_id:'inep',state:'BA',records:3,geocoded:0},{source_id:'cnes',state:'BA',records:4,geocoded:4},{source_id:'cnes',state:'SP',records:2,geocoded:1}];
 assert.equal(partitionSelection(rows).length,3);assert.equal(partitionSelection(rows,'cnes').length,2);
 assert.deepEqual(partitionSelection(rows,'inep','BA'),[rows[0]]);assert.deepEqual(partitionSelection(rows,'inep','SP'),[]);assert.equal(rows.length,3);
});

test('statusLabel and coverageCount never emit Não informado for missing official data', () => {
  for (const locale of ['pt-BR', 'en', 'es']) {
    const t = (k) => uiText(locale, k);
    const unknownStatus = statusLabel('unknown', t);
    const unassignedStatus = statusLabel('unassigned', t);
    assert.notEqual(unknownStatus, 'Não informado');
    assert.notEqual(unassignedStatus, 'Não informado');

    const nullCount = coverageCount(null, locale, t);
    const undefinedCount = coverageCount(undefined, locale, t);
    assert.notEqual(nullCount, 'Não informado');
    assert.notEqual(undefinedCount, 'Não informado');

    if (locale === 'pt-BR') {
      assert.equal(unknownStatus, 'Cadastro oficial');
      assert.equal(nullCount, 'Cadastro oficial');
    } else if (locale === 'en') {
      assert.equal(unknownStatus, 'Official record');
      assert.equal(nullCount, 'Official record');
    } else if (locale === 'es') {
      assert.equal(unknownStatus, 'Registro oficial');
      assert.equal(nullCount, 'Registro oficial');
    }
  }
});
