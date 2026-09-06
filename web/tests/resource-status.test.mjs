import test from 'node:test';
import assert from 'node:assert/strict';
import {statusMessages,statusText,selectionExportURL} from '../src/resource-status.mjs';
for(const locale of ['pt-BR','en','es'])test(`coverage/export messages ${locale}`,()=>{
  assert.deepEqual(Object.keys(statusMessages[locale]).sort(),Object.keys(statusMessages['pt-BR']).sort());
  for(const key of Object.keys(statusMessages[locale]))assert.ok(statusText(locale,key).length>2);
  const url=selectionExportURL({q:'A & B%',profile:'pncp_contracts',state:'BA',municipality:'1234567',password:'PRIVATE'},'json',locale);
  const params=new URL(url,'https://example.org').searchParams;
  assert.equal(params.get('q'),'A & B%');assert.equal(params.get('municipality_id'),'1234567');
  assert.equal(params.get('locale'),locale);assert.equal(params.get('limit'),'100');assert.ok(!url.includes('PRIVATE'));
});
test('only valid format is accepted',()=>assert.throws(()=>selectionExportURL({},'html','pt-BR')));
test('individual versions use the existing separate exporter',()=>assert.throws(()=>selectionExportURL({id:'pncp:one'},'json','en')));
test('unknown locale and text key do not crash the interface',()=>{
  assert.equal(statusText('unknown','title'),statusText('pt-BR','title'));
  assert.equal(statusText('unknown','missing'),'missing');
});
