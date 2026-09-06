// SPDX-License-Identifier: AGPL-3.0-or-later
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {historyFields,historyText} from '../src/resource-history.mjs';
for(const [locale,label] of [['pt-BR','Valor global informado'],['en','Declared global amount'],['es','Importe global declarado']]){
 test(`history field labels are readable in ${locale} without changing technical keys`,()=>{
   assert.deepEqual(historyFields(['attributes.global_cents'],locale),[{key:'attributes.global_cents',label}]);
   assert.notEqual(historyText(locale,'technical'),'technical');
 });
}
test('precise metadata is not mislabeled as a payment',()=>{
 const result=historyFields(['attributes.precise_amounts','source.reference_date'],'pt-BR');
 assert.match(result[0].label,/precisão/);assert.match(result[1].label,/referência/);assert(!JSON.stringify(result).includes('pago'));
});
test('unknown fields remain inspectable rather than being silently dropped',()=>{
 const result=historyFields(['attributes.new_publisher_field'],'en');
 assert.deepEqual(result,[{key:'attributes.new_publisher_field',label:'Other source field'}]);
});
test('invalid collections and non-string keys are rejected',()=>{
 assert.throws(()=>historyFields('title','pt-BR'));
 assert.throws(()=>historyFields([null],'pt-BR'));
});
test('does not interpret source identifiers as HTML',()=>{
 const key='attributes.<script>alert(1)</script>';
 assert.equal(historyFields([key],'pt-BR')[0].key,key);
});
test('duplicate changes retain one key and source order',()=>{
 assert.deepEqual(historyFields(['title','attributes.global_cents','title'],'en').map(x=>x.key),['title','attributes.global_cents']);
});
