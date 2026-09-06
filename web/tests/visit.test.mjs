import test from 'node:test';
import assert from 'node:assert/strict';
import {visitText} from '../src/visit-text.mjs';
import {composeVisit,visitGuide,publicObservationReport} from '../src/visit-guide.mjs';
const place={id:'test:school',kind:'school',source:{dataset:'synthetic',reference_date:'2025'}};
for(const locale of ['pt-BR','en','es']) {
 test(`guide copy is complete in ${locale}`,()=>{
  assert.deepEqual(Object.keys(visitText[locale]).sort(),Object.keys(visitText['pt-BR']).sort());
  for(const value of Object.values(visitText[locale]))assert.ok(typeof value==='string'&&value.trim().length>0);
 });
 for(const kind of ['school','health','work'])test(`real observation text for ${kind} in ${locale}`,()=>{
  const guide=visitGuide(kind,locale),answers=Object.fromEntries(guide.items.map(i=>[i.id,'unknown']));
  const body=composeVisit({...place,kind},locale,answers,'Synthetic context written only for the unit test.');
  assert.ok(body.includes(guide.id)&&body.includes('test:school')&&body.includes('2025'));
  assert.ok(Array.from(body).length<=1200);
  for(const item of guide.items)assert.ok(body.includes(item.label));
 });
}
test('guide instances do not share mutable answers or labels',()=>{
 const g=visitGuide('school','en');g.items[0].allowed_answers.push('invented');
 assert.deepEqual(visitGuide('school','en').items[0].allowed_answers,['yes','no','unknown']);
});
test('incomplete, extra and invalid responses cannot compose a guide',()=>{
 const guide=visitGuide('school','en'),answers=Object.fromEntries(guide.items.map(i=>[i.id,'yes']));
 for(const bad of [{},{...answers,identification:'maybe'},{...answers,extra:'yes'}])assert.throws(()=>composeVisit(place,'en',bad,'A complete synthetic observation context.'),/answers_incomplete/);
 assert.throws(()=>composeVisit(place,'en',answers,'short'),/context_required/);
 assert.throws(()=>composeVisit(place,'en',answers,'long '.repeat(500)),/observation_budget/);
 assert.throws(()=>visitGuide('other','en'),/unsupported/);
 assert.throws(()=>visitGuide('school','fr'),/unsupported/);
});
test('public export excludes extra private attributes and cannot copy unpublished records',()=>{
 const row={id:'obs',place_id:'test:school',status:'approved',created_at:'2025-01-01',reviewed_at:'2025-01-02',review_note:'PRIVATE',author_id:'PRIVATE',observation:{mode:'field',observed_on:'2025-01-01',body:'Synthetic narrative to export.',reference_url:null,consent:true,private:'PRIVATE'}};
 const report=publicObservationReport(row,'pt-BR');assert.ok(!JSON.stringify(report).includes('PRIVATE'));
 assert.equal(report.observation.body,row.observation.body);assert.equal(report.schema,'bdt.citizen-observation-copy.v1');
 for(const status of ['pending','rejected','withdrawn','retracted'])assert.throws(()=>publicObservationReport({...row,status},'en'),/not_public/);
 assert.throws(()=>publicObservationReport(row,'fr'),/not_public/);
 assert.throws(()=>publicObservationReport({...row,observation:{body:'x'.repeat(1201)}},'en'),/invalid_public/);
});
