import test from 'node:test';
import assert from 'node:assert/strict';
import {compareResourceVersions,comparisonMessages,comparisonText} from '../src/resource-comparison.mjs';
const record=(revision,attributes={},extra={})=>({revision,resource:{id:'pncp_contracts:synthetic',kind:'contract',title:'Synthetic public object',municipality_id:null,source:{dataset:'pncp_contracts',reference_date:'2026'},attributes:{profile:'pncp_contracts',global_cents:15002,...attributes},...extra}});

test('consecutive retained versions show separate exact values, never a combined total',()=>{
 const value=compareResourceVersions(record(1),record(2,{global_cents:20000}));
 assert.equal(value.status,'comparable');assert.equal(value.changes.length,1);
 assert.equal(value.changes[0].key,'attributes.global_cents');
 assert.equal(value.changes[0].before.cents,15002);assert.equal(value.changes[0].after.cents,20000);
 assert.equal('total' in value,false);assert.equal('delta' in value,false);
});
test('same number represented as cents or a decimal is not a change',()=>{
 const before=record(1,{global_cents:100});
 const after=record(2,{global_cents:null,precise_amounts:{global:'1.0000'}});
 assert.deepEqual(compareResourceVersions(before,after),{status:'comparable',changes:[]});
});
test('subcent values remain exact strings, including beyond safe integer magnitudes',()=>{
 const value=compareResourceVersions(record(1,{global_cents:null,precise_amounts:{global:'90071992547409.9100'}}),record(2,{global_cents:null,precise_amounts:{global:'90071992547409.9001'}}));
 assert.equal(value.changes[0].before.decimal,'90071992547409.9100');
 assert.equal(value.changes[0].after.decimal,'90071992547409.9001');
});
test('missing amount and zero are distinct',()=>{
 const value=compareResourceVersions(record(1,{global_cents:null}),record(2,{global_cents:0}));
 assert.equal(value.changes[0].before,null);assert.equal(value.changes[0].after.cents,0);
});
for(const value of ['10',-1,NaN,{},[],true])test(`malformed monetary data requires review (${JSON.stringify(value)})`,()=>{
 assert.equal(compareResourceVersions(record(1),record(2,{global_cents:value})).status,'unavailable');
});
test('conflicting decimal and cents do not silently choose one representation',()=>{
 assert.equal(compareResourceVersions(record(1),record(2,{precise_amounts:{global:'150.0201'}})).status,'unavailable');
});
for(const pair of [[record(1),record(3)],[record(2),record(1)],[record(0),record(1)],[null,record(1)],[record('1'),record(2)]])test('do not invent adjacency or accept malformed revisions '+JSON.stringify(pair),()=>{
 assert.equal(compareResourceVersions(...pair).status,'unavailable');
});
test('different identities and sources cannot be compared as versions',()=>{
 assert.equal(compareResourceVersions(record(1),record(2,{}, {id:'other'})).status,'unavailable');
 assert.equal(compareResourceVersions(record(1),record(2,{profile:'obrasgov_projects'})).status,'unavailable');
 assert.equal(compareResourceVersions(record(1),record(2,{}, {source:{dataset:'other'}})).status,'unavailable');
});
test('unknown attributes and private extras never enter the projection',()=>{
 const result=compareResourceVersions(record(1,{private_note:'DO_NOT_PUBLISH',new_numeric:22}),record(2,{private_note:'CHANGED_PRIVATE',new_numeric:32}));
 assert.deepEqual(result.changes,[]);
});
test('title and dates preserve literal source text, not an inferred event',()=>{
 const title='Synthetic long public description '.repeat(250);
 const value=compareResourceVersions(record(1),record(2,{ends_on:'2027-03-01'},{title}));
 assert.equal(value.changes.find(c=>c.key==='title').after,title);
 assert.equal(value.changes.find(c=>c.key==='attributes.ends_on').before,null);
});
test('unsupported structures are not stringified into claims',()=>{
 assert.equal(compareResourceVersions(record(1),record(2,{}, {title:{internal:'no'}})).status,'unavailable');
 assert.equal(compareResourceVersions(record(1),record(2,{}, {attributes:[]})).status,'unavailable');
});
for(const locale of ['pt-BR','en','es'])test(locale+' comparison copy is complete and independent of a model',()=>{
 assert.deepEqual(Object.keys(comparisonMessages[locale]),Object.keys(comparisonMessages['pt-BR']));
 for(const key of Object.keys(comparisonMessages['pt-BR']))assert.notEqual(comparisonText(locale,key),key);
});
