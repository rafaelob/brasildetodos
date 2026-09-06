import test from 'node:test';
import assert from 'node:assert/strict';
import {messages,translate,money,safeReference} from '../src/i18n.mjs';
for (const locale of ['pt-BR','en','es']) {
  test(`complete locale ${locale}`,()=>{assert.deepEqual(Object.keys(messages[locale]).sort(),Object.keys(messages['pt-BR']).sort());for(const value of Object.values(messages[locale]))assert.ok(value.trim().length);});
  test(`money formatting ${locale}`,()=>assert.equal(typeof money(123456,locale),'string'));
}
test('unsafe references are not hyperlinks',()=>{for(const s of ['javascript:alert(1)','data:text/html,x','https://u:p@example.org'])assert.equal(safeReference(s),null);});
test('public references accepted',()=>assert.equal(safeReference('https://example.org/x'),'https://example.org/x'));
test('fallback language',()=>assert.equal(translate('fr','explore'),messages['pt-BR'].explore));
test('unsafe integer is not formatted as accurate money',()=>assert.equal(money(Number.MAX_SAFE_INTEGER+1,'pt-BR'),'—'));
