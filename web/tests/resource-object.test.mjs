import test from 'node:test';
import assert from 'node:assert/strict';
import {objectPresentation,objectText} from '../src/resource-object.mjs';
test('short object stays a complete heading',()=>{
 assert.deepEqual(objectPresentation('Reforma da escola'),{text:'Reforma da escola',characters:17,long:false,heading:'Reforma da escola'});
});
test('observed-length object keeps every character with an explicit preview',()=>{
 const value='A'.repeat(5120),item=objectPresentation(value);
 assert.equal(item.text,value);assert.equal(item.characters,5120);assert(item.long);
 assert.equal(item.heading,'A'.repeat(180)+'…');
});
test('preview never splits a supplementary unicode character',()=>{
 const item=objectPresentation('🌍'.repeat(300));
 assert.equal(item.heading,'🌍'.repeat(180)+'…');assert.equal(item.characters,300);
});
test('text is not interpreted as HTML and whitespace is preserved',()=>{
 const text='<script>not executed</script>\n'+(' X '.repeat(300));
 assert.equal(objectPresentation(text).text,text);
});
test('the exact threshold is consistent',()=>{
 assert.equal(objectPresentation('X'.repeat(240)).long,false);
 assert.equal(objectPresentation('X'.repeat(241)).long,true);
});
for(const locale of ['pt-BR','en','es'])test('complete-object copy '+locale,()=>{
 assert.notEqual(objectText(locale,'full'),'full');assert.notEqual(objectText(locale,'characters'),'characters');
});
test('invalid input fails explicitly',()=>assert.throws(()=>objectPresentation(null)));
for(const locale of ['pt-BR','en','es'])test('short descriptions are flagged without expansion '+locale,()=>{
 const item=objectPresentation('TEST');
 assert.equal(item.heading,'TEST');assert.equal(item.text,'TEST');
 assert.notEqual(objectText(locale,'short'),'short');
});
