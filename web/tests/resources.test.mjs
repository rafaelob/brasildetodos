import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resourceMessages,resourceAmounts,amountFields} from '../src/resource-i18n.mjs';
import {uiText} from '../src/ui-text.mjs';
import {money} from '../src/i18n.mjs';
for(const locale of ['pt-BR','en','es']) {
  test(`${locale}: resource vocabulary is complete`,()=>{
    assert.deepEqual(Object.keys(resourceMessages[locale]).sort(),Object.keys(resourceMessages['pt-BR']).sort());
    for(const key of Object.keys(resourceMessages['pt-BR']))assert.equal(uiText(locale,key),resourceMessages[locale][key]);
    const source=readFileSync(new URL('../src/Resources.tsx',import.meta.url),'utf8');
    for(const [,key]of source.matchAll(/\bt\('([^']+)'\)/g))assert.notEqual(uiText(locale,key),key);
  });
  test(`${locale}: very large and sub-unit negative amounts keep cents`,()=>{
    assert.match(money(9007199254740991,locale),/[.,]91/);
    assert.match(money(-1,locale),/-/);
    assert.match(money(-1,locale),/[.,]01/);
    assert.match(money(0,locale),/[.,]00/);
  });
}
test('amount cards are separate and never include an implied sum or unknown financial field',()=>{
  const rows=resourceAmounts({initial_cents:10001,global_cents:20002,accumulated_cents:null,
    paid_cents:30003,planned_operating_cents:0,planned_investment_cents:1.5});
  assert.deepEqual(rows.map(row=>row.cents),[10001,20002,0]);
  assert.ok(rows.every(row=>Object.hasOwn(amountFields,row.key)));
  assert.deepEqual(resourceAmounts({initial_cents:true,global_cents:Number.MAX_SAFE_INTEGER+1}),[]);
});

test('PNCP subcent amounts keep exact decimal metadata, never become payment cents',async()=>{
  const {resourceAmountText}=await import('../src/resource-i18n.mjs');
  const rows=resourceAmounts({profile:'pncp_contracts',initial_cents:null,global_cents:10,
    precise_amounts:{initial:'100.0001'}});
  assert.equal(rows.length,2);assert.equal(rows[0].cents,null);
  assert.equal(rows[0].decimal,'100.0001');assert.equal(rows[1].cents,10);
  for(const locale of ['pt-BR','en','es']){
    assert.match(resourceAmountText(rows[0],locale),/[.,]0001/);
    const big={decimal:'90071992547409.9099',cents:null};
    assert.match(resourceAmountText(big,locale),/[.,]9099/);
  }
});

test('unsupported precision is not silently rounded or replaced with a conflicting cent value',()=>{
  for(const value of ['0.00001','bad','1e-4',1.2345,'-1.2345','90071992547409.9199']){
    const result=resourceAmounts({profile:'pncp_contracts',initial_cents:123,
      precise_amounts:{initial:value}});
    assert.deepEqual(result,[]);
  }
  assert.deepEqual(resourceAmounts({initial_cents:123,precise_amounts:{initial:'0.0001'}}).map(a=>a.cents),[123]);
});
