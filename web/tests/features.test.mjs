import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {featureMessages,additionalMessages,uiText} from '../src/ui-text.mjs';
import {translate} from '../src/i18n.mjs';

// Match the translation function, not the suffix of FormData.get('field').
const literalTranslationKeys=source=>[...source.matchAll(/\bt\('([^']+)'\)/g)].map(match=>match[1]);

test('translation scan does not mistake form field identifiers for UI keys',()=>{
  const code="form.get('dataset'); t('sourceDataset'); values.get('record_id'); t('sourceRecord');";
  assert.deepEqual(literalTranslationKeys(code),['sourceDataset','sourceRecord']);
});

for(const locale of ['pt-BR','en','es']){
  test(`${locale}: complete document and privacy vocabulary`,()=>{
    assert.deepEqual(Object.keys(featureMessages[locale]).sort(),Object.keys(featureMessages['pt-BR']).sort());
    assert.deepEqual(Object.keys(additionalMessages[locale]).sort(),Object.keys(additionalMessages['pt-BR']).sort());
    for(const key of [...Object.keys(featureMessages[locale]),...Object.keys(additionalMessages[locale])]){
      assert.equal(typeof uiText(locale,key),'string');assert.ok(uiText(locale,key).length>1);
    }
  });
  test(`${locale}: literal workbench strings resolve`,()=>{
    const source=readFileSync(new URL('../src/Workbench.tsx',import.meta.url),'utf8');
    const keys=literalTranslationKeys(source);
    assert.ok(keys.length>30,'workbench translation coverage unexpectedly empty');
    for(const key of keys)assert.notEqual(uiText(locale,key),key,`missing ${locale}.${key}`);
  });
  test(`${locale}: unknown source labels remain renderable text`,()=>{
    for(const key of ['constructor','__proto__','toString','unknown_source_service'])assert.equal(typeof uiText(locale,key),'string');
    assert.equal(uiText(locale,'withdrawn'),translate(locale,'withdrawn'));
    assert.notEqual(uiText(locale,'withdrawn'),uiText(locale,'observationWithdrawn'));
  });
}
test('unsupported locale falls back only at the locale boundary',()=>{
  assert.equal(uiText('unsupported','workbench'),uiText('pt-BR','workbench'));
});
