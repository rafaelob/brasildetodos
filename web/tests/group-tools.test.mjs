import test from 'node:test';
import assert from 'node:assert/strict';
import {TASK_STATES,taskActions,ownObservations,validToken,groupFailure,taskPage} from '../src/group-tools.mjs';
import {groupText,groupMessages} from '../src/group-text.mjs';
import {uiText} from '../src/ui-text.mjs';
for(const locale of ['pt-BR','en','es']) test('group vocabulary and navigation '+locale,()=>{
 assert.deepEqual(Object.keys(groupMessages[locale]).sort(),Object.keys(groupMessages.en).sort());
 for(const key of Object.keys(groupMessages.en)){assert.equal(typeof groupText(locale,key),'string');assert.ok(groupText(locale,key).trim());}
 assert.equal(uiText(locale,'groups'),groupText(locale,'groups'));
 for(const state of TASK_STATES)assert.ok(Object.hasOwn(groupMessages[locale],state));
});
test('unknown keys remain text and cannot resolve object prototypes',()=>{assert.equal(groupText('xx','groups'),'Grupos');assert.equal(groupText('en','__proto__'),'__proto__');});
test('only valid invitation tokens accepted without interpreting a URL',()=>{
 assert.equal(validToken('a'.repeat(43)),true);
 for(const token of [null,{},'a'.repeat(42),'a'.repeat(44),'https://example.org/?token='+ 'a'.repeat(43),' '+ 'a'.repeat(43),'á'.repeat(43)])assert.equal(validToken(token),false);
});
test('draft observations remain limited to this account response and matching place',()=>{
 const rows=['pending','approved','withdrawn','rejected','retracted'].map((status,id)=>({id,status,place_id:'x:1',observation:{body:'private test'}}));
 rows.push({id:10,status:'pending',place_id:'x:2',observation:{body:'other'}});
 rows.push({id:11,status:'pending',place_id:'x:1',observation:{body:'removed',erased:true}});
 assert.deepEqual(ownObservations(rows,'x:1').map(x=>x.id),[0,1]);assert.deepEqual(ownObservations(null,'x:1'),[]);
});
test('self review unavailable and archive forbids mutation affordances',()=>{
 const own={state:'submitted',assigned_to_me:true,created_by_me:false,can_review:true,observation:{}};
 assert.deepEqual(taskActions(own),['reopen']);assert.deepEqual(taskActions(own,true,false),[]);
 assert.deepEqual(taskActions({...own,assigned_to_me:false}),['accept','request_changes']);
 assert.deepEqual(taskActions({...own,assigned_to_me:false,observation:null}),[]);
});
test('task transitions expose actual backend actions only',()=>{
 assert.deepEqual(taskActions({state:'open'}),['claim']);
 assert.deepEqual(taskActions({state:'in_progress',assigned_to_me:true}),['release','submit']);
 assert.deepEqual(taskActions({state:'accepted'},true),['reopen','cancel']);
 assert.deepEqual(taskActions({state:'cancelled'},true),[]);
 assert.deepEqual(taskActions({state:'invented'},true),[]);assert.deepEqual(taskActions(null),[]);
});
test('HTTP errors map to public translated messages, not raw response data',()=>{
 for(const [status,key] of [[401,'loginRequired'],[403,'forbidden'],[404,'unavailable'],[409,'conflict'],[422,'invalid'],[429,'rateLimited'],[500,'failure']])assert.equal(groupFailure(new Error('HTTP '+status)),key);
 assert.equal(groupFailure(new Error('private backend secret')),'failure');
});
test('task pagination clamps only the public task page',()=>{assert.equal(taskPage(3,21),2);assert.equal(taskPage(0,0),1);assert.equal(taskPage(2,40),2);for(const x of [-1,1.1,Infinity,'20'])assert.throws(()=>taskPage(1,x));});
