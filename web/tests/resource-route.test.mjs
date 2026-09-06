import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeResourceRoute,parseResourceRoute,resourceHash,resourceShareURL} from '../src/resource-route.mjs';
import {actionMessages} from '../src/resource-actions.mjs';
import {uiText} from '../src/ui-text.mjs';
for(const locale of ['pt-BR','en','es'])test(`${locale}: exact public criteria roundtrip and complete actions`,()=>{
  const criteria={q:'Creche 100% & saúde',profile:'pncp_contracts',state:'BA',municipality:'1234567',id:'pncp_contracts:12345678000199-2-000001/2026',locale};
  assert.deepEqual(parseResourceRoute(resourceHash(criteria)),criteria);
  assert.deepEqual(Object.keys(actionMessages[locale]),Object.keys(actionMessages['pt-BR']));
  for(const key of Object.keys(actionMessages[locale]))assert.equal(uiText(locale,key),actionMessages[locale][key]);
});
test('sharing discards query credentials, old hashes and private fields',()=>{
  const link=resourceShareURL('https://example.org/app?token=PRIVATE#private',{q:'education',state:'BA',token:'PRIVATE',favorites:['PRIVATE'],latitude:1});
  assert.equal(link,'https://example.org/app#resources?q=education&state=BA&locale=pt-BR');
  assert.ok(!link.includes('PRIVATE')&&!link.includes('latitude'));
});
test('unknown route and duplicate public keys are not silently reinterpreted',()=>{
  for(const hash of ['#resources-fake','#resources?q=x&q=y','#main','x'.repeat(4000)])assert.equal(parseResourceRoute(hash),null);
});
test('criteria are bounded and invalid identifiers are not used in URLs',()=>{
  const cleaned=normalizeResourceRoute({q:'x'.repeat(201),profile:'constructor',state:'ZZ',municipality:'abc',id:'../../bad',locale:'constructor'});
  assert.deepEqual(cleaned,{q:'',profile:'',state:'',municipality:'',id:'',locale:'pt-BR'});
  assert.equal(normalizeResourceRoute({q:'a\nPRIVATE'}).q,'');
  assert.throws(()=>resourceShareURL('javascript:alert(1)',{}));
  assert.throws(()=>resourceShareURL('https://user:secret@example.org',{}));
});
