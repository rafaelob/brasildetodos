// SPDX-License-Identifier: AGPL-3.0-or-later
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createLatestTask} from '../src/latest-task.mjs';
import {uiText} from '../src/ui-text.mjs';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}};

test('detail and history share one cancellation; neither can publish on its own',async()=>{
 const gate=createLatestTask(),detail=deferred(),history=deferred(),published=[],errors=[];let signal;
 const pending=gate.run(s=>{signal=s;return Promise.all([detail.promise,history.promise])},{success:value=>published.push(value),failure:error=>errors.push(error)});
 detail.resolve({place:{id:'a'}});await Promise.resolve();assert.deepEqual(published,[]);
 gate.cancel();assert.equal(signal.aborted,true);history.resolve([]);
 assert.equal(await pending,'superseded');assert.deepEqual(published,[]);assert.deepEqual(errors,[]);
});
test('a previous detail finalizer cannot clear a newer loading state',async()=>{
 const gate=createLatestTask(),old=deferred(),current=deferred();let loading=true;
 const first=gate.run(()=>old.promise,{settled:()=>{loading=false}});
 const second=gate.run(()=>current.promise,{settled:()=>{loading=false}});
 old.reject(new Error('late'));await first;assert.equal(loading,true);
 current.resolve('current');await second;assert.equal(loading,false);
});
test('place opening and cancellation have citizen labels in every supported locale',()=>{
 for(const locale of ['pt-BR','en','es'])for(const key of ['loadingPlace','cancelPlace']){
  const value=uiText(locale,key);assert.notEqual(value,key);assert.ok(value.length>10);
 }
});
