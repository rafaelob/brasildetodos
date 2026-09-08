import test from 'node:test';
import assert from 'node:assert/strict';
import {messages,translate,money,safeReference,formatDataset,formatReferenceDate,formatSourceSummary} from '../src/i18n.mjs';
for (const locale of ['pt-BR','en','es']) {
  test(`complete locale ${locale}`,()=>{assert.deepEqual(Object.keys(messages[locale]).sort(),Object.keys(messages['pt-BR']).sort());for(const value of Object.values(messages[locale]))assert.ok(value.trim().length);});
  test(`money formatting ${locale}`,()=>assert.equal(typeof money(123456,locale),'string'));
}
test('unsafe references are not hyperlinks',()=>{for(const s of ['javascript:alert(1)','data:text/html,x','https://u:p@example.org'])assert.equal(safeReference(s),null);});
test('public references accepted',()=>assert.equal(safeReference('https://example.org/x'),'https://example.org/x'));
test('fallback language',()=>assert.equal(translate('fr','explore'),messages['pt-BR'].explore));
test('unsafe integer is not formatted as accurate money',()=>assert.equal(money(Number.MAX_SAFE_INTEGER+1,'pt-BR'),'—'));

test('formatDataset humanizes all technical official slugs', () => {
  assert.equal(formatDataset('cnes-national-bulk', 'pt-BR'), 'CNES · Estabelecimentos de Saúde');
  assert.equal(formatDataset('inep-schools-2025', 'pt-BR'), 'INEP · Censo Escolar');
  assert.equal(formatDataset('transferegov_special_plans', 'pt-BR'), 'Transferegov · Repasses Federais');
  assert.equal(formatDataset('obrasgov_projects', 'pt-BR'), 'Obrasgov.br · Investimentos & Infraestrutura');
  assert.equal(formatDataset('ibge-municipalities', 'pt-BR'), 'IBGE · Base Territorial Oficial');
  assert.equal(formatDataset('cnes-national-bulk', 'en'), 'CNES · Health Facilities');
  assert.equal(formatDataset('cnes-national-bulk', 'es'), 'CNES · Centros de Salud');
});

test('formatReferenceDate sanitizes null, empty and Não informado to officialRecord', () => {
  assert.equal(formatReferenceDate(null, 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate(undefined, 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('   ', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('Não informado', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('  Não informado  ', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('não informado', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('NAO INFORMADO', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('nao informado', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('No informado', 'es'), 'Registro oficial');
  assert.equal(formatReferenceDate('  no informado  ', 'es'), 'Registro oficial');
  assert.equal(formatReferenceDate('not provided', 'en'), 'Official record');
  assert.equal(formatReferenceDate('NOT PROVIDED', 'en'), 'Official record');
  assert.equal(formatReferenceDate('unknown', 'en'), 'Official record');
  assert.equal(formatReferenceDate('null', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('undefined', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('none', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('None', 'en'), 'Official record');
  assert.equal(formatReferenceDate(12345, 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('2025', 'pt-BR'), 'Ref. 2025');
  assert.equal(formatReferenceDate('  2025  ', 'pt-BR'), 'Ref. 2025');
  assert.equal(formatReferenceDate('2025', 'en'), 'Ref. 2025');
  assert.equal(formatReferenceDate('2025', 'es'), 'Ref. 2025');
});

test('formatSourceSummary pairs humanized dataset and sanitized reference date', () => {
  const source = { dataset: 'cnes-national-bulk', reference_date: 'Não informado' };
  assert.equal(formatSourceSummary(source, 'pt-BR'), 'CNES · Estabelecimentos de Saúde · Cadastro oficial');
  assert.equal(formatSourceSummary(source, 'en'), 'CNES · Health Facilities · Official record');
});
