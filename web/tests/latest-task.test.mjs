// SPDX-License-Identifier: AGPL-3.0-or-later
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createLatestTask} from '../src/latest-task.mjs';

function deferred(){let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function callbacks(){const values=[],errors=[],settled=[];return {values,errors,settled,handlers:{success:value=>values.push(value),failure:error=>errors.push(error),settled:()=>settled.push(true)}};}

test('current operation commits and settles exactly once',async()=>{
 const gate=createLatestTask(),c=callbacks();
 assert.equal(await gate.run(async()=>({value:1}),c.handlers),'completed');
 assert.deepEqual(c.values,[{value:1}]);assert.deepEqual(c.errors,[]);assert.equal(c.settled.length,1);
});
test('current failure is visible and settles',async()=>{
 const gate=createLatestTask(),c=callbacks(),error=new Error('unavailable');
 assert.equal(await gate.run(async()=>{throw error;},c.handlers),'failed');
 assert.deepEqual(c.errors,[error]);assert.equal(c.settled.length,1);assert.deepEqual(c.values,[]);
});
test('late success cannot replace a newer selection even when operation ignores abort',async()=>{
 const gate=createLatestTask(),first=deferred(),a=callbacks(),b=callbacks();let signal;
 const old=gate.run(s=>{signal=s;return first.promise;},a.handlers);
 assert.equal(await gate.run(async()=>'new selection',b.handlers),'completed');
 assert.equal(signal.aborted,true);first.resolve('old selection');
 assert.equal(await old,'superseded');assert.deepEqual(a.values,[]);assert.deepEqual(a.settled,[]);assert.deepEqual(b.values,['new selection']);
});
test('late failure cannot display an error for a newer successful selection',async()=>{
 const gate=createLatestTask(),first=deferred(),a=callbacks(),b=callbacks();
 const old=gate.run(()=>first.promise,a.handlers);await gate.run(async()=>'new',b.handlers);
 first.reject(new Error('old failure'));assert.equal(await old,'superseded');assert.deepEqual(a.errors,[]);assert.deepEqual(a.settled,[]);
});
test('cancel aborts pending request and suppresses eventual browser-side publication',async()=>{
 const gate=createLatestTask(),next=deferred(),c=callbacks();let signal;
 const result=gate.run(s=>{signal=s;return next.promise;},c.handlers);
 gate.cancel();gate.cancel();assert.equal(signal.aborted,true);
 next.resolve(new Blob(['partial result']));assert.equal(await result,'superseded');assert.deepEqual(c.values,[]);assert.deepEqual(c.settled,[]);
});
test('AbortError caused by cancellation is not reported as a failed export',async()=>{
 const gate=createLatestTask(),c=callbacks();
 const result=gate.run(signal=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Cancelled','AbortError')))),c.handlers);
 gate.cancel();assert.equal(await result,'superseded');assert.deepEqual(c.errors,[]);
});
test('independent instances do not cancel each other',async()=>{
 const one=createLatestTask(),two=createLatestTask(),next=deferred(),a=callbacks(),b=callbacks();
 const first=one.run(()=>next.promise,a.handlers);await two.run(async()=>2,b.handlers);next.resolve(1);await first;
 assert.deepEqual(a.values,[1]);assert.deepEqual(b.values,[2]);
});
test('publication errors are handled instead of reporting success',async()=>{
 const gate=createLatestTask(),c=callbacks();
 const result=await gate.run(async()=>'bytes',{...c.handlers,success:()=>{throw new Error('browser download failed');}});
 assert.equal(result,'failed');assert.equal(c.errors.length,1);assert.equal(c.settled.length,1);
});
test('cancelled task does not invalidate the next operation',async()=>{
 const gate=createLatestTask(),next=deferred(),a=callbacks(),b=callbacks();
 const old=gate.run(()=>next.promise,a.handlers);gate.cancel();
 await gate.run(async()=>'new',b.handlers);next.reject(new Error('late'));await old;
 assert.deepEqual(b.values,['new']);assert.deepEqual(a.errors,[]);
});
test('completed tasks no longer abort signals on a later unrelated cancellation',async()=>{
 const gate=createLatestTask();let signal;
 await gate.run(async value=>{signal=value;return 1;},{success:()=>{}});gate.cancel();assert.equal(signal.aborted,false);
});
