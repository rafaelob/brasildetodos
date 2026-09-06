import test from 'node:test';
import assert from 'node:assert/strict';
import {comparisonSelection,toggleComparison,comparisonItems,comparisonText,COMPARISON_LIMIT} from '../src/place-comparison.mjs';
const ids=['test:one','test:two','test:three','test:four'];
const item=(id)=>({id,status:'available',place:{id,kind:'school',name:'Synthetic '+id,source:{dataset:'test'},declared_services:[]}});
test('comparison choices are valid, bounded, ordered and removable',()=>{
 assert.equal(COMPARISON_LIMIT,3);
 assert.deepEqual(comparisonSelection([...ids,ids[0]],ids),ids.slice(0,3));
 assert.deepEqual(comparisonSelection(['bad',ids[2],ids[0],ids[0]],ids),[ids[2],ids[0]]);
 assert.deepEqual(comparisonSelection(ids,[ids[3]]),[ids[3]]);
 assert.deepEqual(comparisonSelection(null,ids),[]);
 assert.deepEqual(toggleComparison([],ids[0],ids),[ids[0]]);
 assert.deepEqual(toggleComparison(ids.slice(0,3),ids[3],ids),ids.slice(0,3));
 assert.deepEqual(toggleComparison(ids.slice(0,3),ids[1],ids),[ids[0],ids[2]]);
 assert.deepEqual(toggleComparison([], 'private:absent',ids),[]);
 assert.deepEqual(toggleComparison([], 'invalid',ids),[]);
});
for(const locale of ['pt-BR','en','es'])test('comparison language complete: '+locale,()=>{
 assert.deepEqual(Object.keys(comparisonText[locale]).sort(),Object.keys(comparisonText['pt-BR']).sort());
 for(const value of Object.values(comparisonText[locale]))assert.ok(typeof value==='string'&&value.length>0);
});
test('public response preserves the requested order and missing states',()=>{
 const items=[item(ids[0]),{id:ids[1],status:'not_found',place:null}];
 assert.deepEqual(comparisonItems({items},ids.slice(0,2)),items);
 assert.deepEqual(comparisonItems({items:[item(ids[0]),{...item(ids[1]),status:'outside_current_profile'}]},ids.slice(0,2))[1].status,'outside_current_profile');
});
for(const change of ['reordered','extra','wrong_place','unknown_kind','bad_services','unknown_status','missing_place','unavailable_with_place'])test('refuses inconsistent comparison '+change,()=>{
 const items=[item(ids[0]),item(ids[1])];
 if(change==='reordered')items.reverse();
 if(change==='extra')items.push(item(ids[2]));
 if(change==='wrong_place')items[0].place.id=ids[1];
 if(change==='unknown_kind')items[0].place.kind='rank';
 if(change==='bad_services')items[0].place.declared_services=[{}];
 if(change==='unknown_status')items[0].status='secret';
 if(change==='missing_place')items[0].place=null;
 if(change==='unavailable_with_place')items[0].status='unavailable';
 assert.throws(()=>comparisonItems({items},ids.slice(0,2)),/comparison_/);
});
test('refuses invalid comparison response or requested selection',()=>{
 assert.throws(()=>comparisonItems(null,ids.slice(0,2)),/comparison_count/);
 assert.throws(()=>comparisonItems({items:[item(ids[0])]},[ids[0]]),/selection_invalid/);
 assert.throws(()=>comparisonItems({items:ids.map(item)},ids),/selection_invalid/);
 assert.throws(()=>comparisonItems({items:[item(ids[0]),item(ids[0])]},[ids[0],ids[0]]),/selection_invalid/);
});
