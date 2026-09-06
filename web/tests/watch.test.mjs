import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {favoriteIds,readFavorites,saveFavorites,watchPage,watchValue,watchDate,WATCH_PAGE_SIZE} from '../src/watch-state.mjs';
import {watchMessages} from '../src/watch-i18n.mjs';
import {uiText} from '../src/ui-text.mjs';

test('legacy favorites are normalized without changing order or fabricating IDs',()=>{
 assert.deepEqual(favoriteIds(['inep:12345678',null,5,'missing:value','inep:12345678','unsafe?path','test:'+('x'.repeat(181))]),['inep:12345678','missing:value']);
 assert.deepEqual(favoriteIds({id:'test:x'}),[]);
});
test('read handles blocked storage and damaged JSON without writes',()=>{
 assert.deepEqual(readFavorites({getItem(){throw Error('blocked');}}),[]);
 assert.deepEqual(readFavorites({getItem(){return '{';}}),[]);
 assert.deepEqual(readFavorites({getItem(){return null;}}),[]);
 assert.deepEqual(readFavorites({getItem(){return '["cnes:0000001","cnes:0000001"]';}}),['cnes:0000001']);
});
test('write reports failure and preserves original storage key',()=>{
 const calls=[];
 assert.equal(saveFavorites({setItem(...args){calls.push(args);}},['test:a','test:a']),true);
 assert.deepEqual(calls,[['bdt:favorites','["test:a"]']]);
 assert.equal(saveFavorites({setItem(){throw Error('quota');}},['test:a']),false);
});
test('more favorites than the batch cap stay reachable through paging',()=>{
 const ids=Array.from({length:89},(_,i)=>`test:p${i}`),got=[];
 const first=watchPage(ids,1);
 for(let p=1;p<=first.pages;p++){
  const page=watchPage(ids,p);assert.ok(page.ids.length<=WATCH_PAGE_SIZE);got.push(...page.ids);
 }
 assert.deepEqual(got,ids);assert.equal(first.total,89);
});
test('deleting the final page clamps rather than displaying an empty page',()=>{
 assert.equal(watchPage(['test:a'],9).page,1);
 assert.equal(watchPage(['test:a'],-4).page,1);
 assert.equal(watchPage(['test:a'],NaN).page,1);
 assert.equal(watchPage([],1).pages,1);
});
for(const locale of ['pt-BR','en','es']){
 const t=key=>uiText(locale,key);
 test(`${locale}: watch and load-status vocabularies are complete`,()=>{
  assert.deepEqual(Object.keys(watchMessages[locale]).sort(),Object.keys(watchMessages['pt-BR']).sort());
  for(const key of Object.keys(watchMessages['pt-BR']))assert.notEqual(t(key),key);
  const files=['SavedPlaces.tsx'].map(file=>readFileSync(new URL('../src/'+file,import.meta.url),'utf8'));
  for(const body of files)for(const match of body.matchAll(/\bt\('([^']+)'\)/g))assert.notEqual(t(match[1]),match[1]);
 });
 test(`${locale}: unknown values do not acquire a made-up translation or numeric value`,()=>{
  assert.equal(watchValue(null,locale,t),t('unknown'));
  assert.equal(watchValue([],locale,t),t('unknown'));
  assert.equal(watchValue({},locale,t),t('unknown'));
  assert.equal(watchValue(NaN,locale,t),t('unknown'));
  assert.equal(watchValue(true,locale,t),t('watchYes'));
  assert.equal(watchValue(false,locale,t),t('watchNo'));
  assert.equal(watchValue('Unknown upstream category',locale,t),'Unknown upstream category');
  assert.equal(watchValue(['unknown'],locale,t),t('unknown'));
  assert.equal(watchValue([null],locale,t),t('unknown'));
  assert.equal(watchValue(1.234567,locale,t),new Intl.NumberFormat(locale,{maximumFractionDigits:7}).format(1.234567));
 });
 test(`${locale}: malformed and timezone-free dates are not displayed as known moments`,()=>{
  for(const value of [null,'','2026-09-06','2026-09-06T13:00:00','badTdateZ'])assert.equal(watchDate(value,locale,t),t('unknown'));
  assert.notEqual(watchDate('2026-09-06T13:00:00Z',locale,t),t('unknown'));
 });
}
