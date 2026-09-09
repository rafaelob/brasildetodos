import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {additionalMessages,uiText} from '../src/ui-text.mjs';

const main=readFileSync(new URL('../src/main.tsx',import.meta.url),'utf8');
const LOCALES=['pt-BR','en','es'];

test('account recovery routes are wired in main.tsx',()=>{
  assert.match(main,/\/auth\/recovery\/prepare/);
  assert.match(main,/\/auth\/recovery\/revoke/);
  assert.match(main,/\/auth\/recovery\/consume/);
});

test('consume form confirms password client-side and does not POST the confirm field',()=>{
  assert.match(main,/name="new_password_confirm"/);
  assert.match(main,/if\(data\.get\('new_password'\)!==data\.get\('new_password_confirm'\)\)\{setNotice\('recoveryMismatch'\);return;\}/);
  assert.match(
    main,
    /<input name="new_password_confirm" type="password" autoComplete="new-password" minLength=\{12\} maxLength=\{128\} required\/>/,
  );
  assert.match(
    main,
    /api\('\/auth\/recovery\/consume',\{method:'POST',body:JSON\.stringify\(\{username:data\.get\('username'\),code:data\.get\('code'\),new_password:data\.get\('new_password'\)\}\)\}\)/,
  );
  assert.doesNotMatch(main,/new_password_confirm:data\.get/);
});

test('leaving account clears the recovery secret from React state',()=>{
  assert.match(main,/if\(next!=='account'\)setRecoveryCode\(''\)/);
  assert.match(main,/setUser\(null\);setMine\(\[\]\);setRecoveryCode\(''\)/);
});

test('recoveryConfirmPassword and recoveryMismatch exist in pt-BR, en and es',()=>{
  for(const locale of LOCALES){
    for(const key of ['recoveryConfirmPassword','recoveryMismatch']){
      const copy=additionalMessages[locale][key];
      assert.equal(typeof copy,'string',`${locale}.${key} must be a string`);
      assert.ok(copy.trim().length>1,`${locale}.${key} must be non-empty`);
      assert.equal(uiText(locale,key),copy);
      assert.notEqual(uiText(locale,key),key);
    }
  }
  assert.match(additionalMessages['pt-BR'].recoveryConfirmPassword,/senha/i);
  assert.match(additionalMessages.en.recoveryConfirmPassword,/password/i);
  assert.match(additionalMessages.es.recoveryConfirmPassword,/contraseña/i);
  assert.match(additionalMessages['pt-BR'].recoveryMismatch,/coincidem/i);
  assert.match(additionalMessages.en.recoveryMismatch,/match/i);
  assert.match(additionalMessages.es.recoveryMismatch,/coinciden/i);
});

test('moderation contest is wired in account copy and mine list',()=>{
  for(const locale of LOCALES){
    for(const key of ['contested','contestNote','contestReason','contestSubmit','contestSent']){
      const copy=additionalMessages[locale][key];
      assert.equal(typeof copy,'string',`${locale}.${key} must be a string`);
      assert.ok(copy.trim().length>1,`${locale}.${key} must be non-empty`);
      assert.equal(uiText(locale,key),copy);
    }
  }
  assert.match(main,/\/observations\/'\+row\.id\+'\/contest'/);
  assert.match(main,/allowContest&&row\.status==='rejected'/);
  assert.match(main,/<ObservationCards rows=\{mine\} allowContest\/>/);
});

test('recovery code is not written to localStorage, URLs or logs',()=>{
  const storageWrites=[...main.matchAll(/localStorage\.setItem\(([^)]*)\)/g)].map(match=>match[1]);
  assert.ok(storageWrites.length>0,'locale/favorites storage must remain');
  for(const args of storageWrites){
    assert.equal(args.includes('recoveryCode'),false,`localStorage.setItem must not receive recoveryCode (${args})`);
    assert.doesNotMatch(args,/recovery/i);
  }
  assert.doesNotMatch(main,/sessionStorage\.setItem/);
  assert.doesNotMatch(main,/console\.(?:log|info|debug|warn|error)\([^)]*recoveryCode/);
  assert.doesNotMatch(main,/(?:searchParams|location\.(?:hash|search|href)|history\.(?:push|replace)State)[^;]*recoveryCode/);
  assert.doesNotMatch(main,/setRecoveryCode\([^)]*(?:location|search|hash|localStorage)/);
});
