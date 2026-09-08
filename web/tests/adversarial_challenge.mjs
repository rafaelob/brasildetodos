// Adversarial Empirical Challenge Suite for Milestone M1
// Tests: formatReferenceDate, formatDataset, composeVisit (visit guide), coverageCount, statusLabel

import assert from 'node:assert/strict';
import { formatReferenceDate, formatDataset, formatSourceSummary, translate } from '../src/i18n.mjs';
import { composeVisit, visitGuide } from '../src/visit-guide.mjs';
import { coverageCount, statusLabel, sourceLabel } from '../src/coverage-text.mjs';
import { uiText } from '../src/ui-text.mjs';

const findings = [];

function recordFinding(category, severity, title, details) {
  findings.push({ category, severity, title, details });
  console.log(`[${severity}] [${category}] ${title}\n  Details: ${details}`);
}

console.log('================================================================');
console.log('STARTING EMPIRICAL ADVERSARIAL CHALLENGE FOR MILESTONE M1');
console.log('================================================================\n');

// ----------------------------------------------------------------------
// 1. ADVERSARIAL STRESS TEST: formatReferenceDate
// ----------------------------------------------------------------------
console.log('--- 1. Testing formatReferenceDate ---');

const dateCases = [
  // Canonical and variants of "Não informado"
  { input: 'Não informado', expectedSanitized: true },
  { input: '  Não informado  ', expectedSanitized: true },
  { input: 'não informado', expectedSanitized: true },
  { input: '  não informado  ', expectedSanitized: true },
  { input: 'NAO INFORMADO', expectedSanitized: true },
  { input: 'NÃO INFORMADO', expectedSanitized: true },
  { input: 'nao informado', expectedSanitized: true },
  { input: 'No informado', expectedSanitized: true },
  { input: '  No informado  ', expectedSanitized: true },
  { input: 'no informado', expectedSanitized: true },
  { input: 'NO INFORMADO', expectedSanitized: true },
  { input: 'Not provided', expectedSanitized: true },
  { input: 'not provided', expectedSanitized: true },
  { input: 'NOT PROVIDED', expectedSanitized: true },
  { input: 'unknown', expectedSanitized: true },
  { input: 'UNKNOWN', expectedSanitized: true },
  { input: '  unknown  ', expectedSanitized: true },
  { input: 'Unknown', expectedSanitized: true },
  // Empty, blanks, nullish
  { input: '', expectedSanitized: true },
  { input: '   ', expectedSanitized: true },
  { input: '\t\n', expectedSanitized: true },
  { input: null, expectedSanitized: true },
  { input: undefined, expectedSanitized: true },
  // Stringified nullish
  { input: 'null', expectedSanitized: true },
  { input: 'undefined', expectedSanitized: true },
  { input: 'none', expectedSanitized: true },
  { input: 'None', expectedSanitized: true },
  // Types other than string
  { input: 2025, expectedSanitized: true }, // number
  { input: 0, expectedSanitized: true },
  { input: {}, expectedSanitized: true }, // object
  { input: [], expectedSanitized: true }, // array
  { input: true, expectedSanitized: true }, // boolean
  { input: false, expectedSanitized: true },
  // Script / HTML injection
  { input: '<script>alert(1)</script>', expectedSanitized: false },
  { input: '<img src=x onerror=alert(1)>', expectedSanitized: false },
  // Valid dates
  { input: '2024', expectedSanitized: false },
  { input: '2024-05', expectedSanitized: false },
  { input: '2024-05-12', expectedSanitized: false },
  { input: 'Ref. 2024', expectedSanitized: false },
];

for (const tc of dateCases) {
  for (const locale of ['pt-BR', 'en', 'es']) {
    const res = formatReferenceDate(tc.input, locale);
    const officialRecordText = translate(locale, 'officialRecord');

    // Check if result leaked "Não informado" or variant
    const lowerRes = String(res).toLowerCase();
    if (lowerRes.includes('não informado') || lowerRes.includes('nao informado') ||
        lowerRes.includes('no informado') || lowerRes.includes('not provided') ||
        lowerRes.includes('unknown') || lowerRes.includes('null') || lowerRes.includes('undefined')) {
      recordFinding(
        'formatReferenceDate',
        'HIGH',
        `Leak in formatReferenceDate: "${tc.input}" yielded "${res}" in locale "${locale}"`,
        `Input was treated as a valid date instead of being sanitized to officialRecord (${officialRecordText}).`
      );
    }

    if (tc.expectedSanitized) {
      if (res !== officialRecordText) {
        recordFinding(
          'formatReferenceDate',
          'MEDIUM',
          `Unsanitized sentinel date: "${tc.input}" yielded "${res}" instead of "${officialRecordText}" [${locale}]`,
          `Expected exact match with officialRecord.`
        );
      }
    }
  }
}

// ----------------------------------------------------------------------
// 2. ADVERSARIAL STRESS TEST: formatDataset
// ----------------------------------------------------------------------
console.log('\n--- 2. Testing formatDataset ---');

const datasetCases = [
  // Empty and falsy
  { input: null, expected: '' },
  { input: undefined, expected: '' },
  { input: '', expected: '' },
  // Official slugs with normal casing
  { input: 'cnes-national-bulk', prefix: 'CNES' },
  { input: 'inep-schools-2025', prefix: 'INEP' },
  { input: 'transferegov_special_plans', prefix: 'Transferegov' },
  { input: 'transferegov', prefix: 'Transferegov' },
  { input: 'transferegov-national-financial', prefix: 'Transferegov' },
  { input: 'obrasgov_projects', prefix: 'Obrasgov' },
  { input: 'obrasgov', prefix: 'Obrasgov' },
  { input: 'ibge-municipalities', prefix: 'IBGE' },
  { input: 'pncp-contracts', prefix: 'PNCP' },
  // Mixed casing and unusual casings
  { input: 'CNES-national-bulk', prefix: 'CNES' },
  { input: 'TransfereGov', prefix: 'Transferegov' },
  { input: 'TRANSFEREGOV-NATIONAL-FINANCIAL', prefix: 'Transferegov' },
  { input: 'OBRASGOV_PROJECTS', prefix: 'Obrasgov' },
  { input: 'iNeP-sChOoLs', prefix: 'INEP' },
  // Unknown and custom datasets
  { input: 'custom_source', isUnknown: true },
  { input: 'secret_database_dump', isUnknown: true },
  { input: 'random-slug-123', isUnknown: true },
  { input: 'other', isUnknown: true },
  // Non-string inputs
  { input: 12345, isUnknown: true },
  { input: {}, isUnknown: true },
  { input: '<script>alert(1)</script>', isUnknown: true },
];

for (const tc of datasetCases) {
  for (const locale of ['pt-BR', 'en', 'es']) {
    let res;
    try {
      res = formatDataset(tc.input, locale);
    } catch (err) {
      recordFinding('formatDataset', 'HIGH', `formatDataset threw on input: ${tc.input}`, err.message);
      continue;
    }

    if (!tc.input) {
      if (res !== '') {
        recordFinding('formatDataset', 'LOW', `Falsy input "${tc.input}" gave non-empty "${res}"`, '');
      }
      continue;
    }

    if (tc.prefix) {
      if (!res.startsWith(tc.prefix)) {
        recordFinding(
          'formatDataset',
          'HIGH',
          `Known dataset "${tc.input}" did not format with prefix "${tc.prefix}" in [${locale}]: got "${res}"`,
          'Raw slug or incorrect mapping returned.'
        );
      }
    }

    // Check if raw slug leaked with hyphens/underscores intact
    if (typeof tc.input === 'string' && (tc.input.includes('-') || tc.input.includes('_'))) {
      if (res === tc.input) {
        recordFinding(
          'formatDataset',
          'HIGH',
          `Raw slug leaked unchanged: "${tc.input}" => "${res}"`,
          'Dataset was not humanized.'
        );
      }
    }
  }
}

// ----------------------------------------------------------------------
// 3. ADVERSARIAL STRESS TEST: composeVisit (makeVisitGuide)
// ----------------------------------------------------------------------
console.log('\n--- 3. Testing composeVisit (makeVisitGuide) ---');

const baseAnswersHealth = { identification: 'yes', posted_hours: 'yes', entrance_barrier: 'no', health_sign: 'yes' };
const validNote = 'Contexto detalhado para observação cidadã no local especificado.';

const placeScenarios = [
  {
    name: 'Missing source object entirely',
    place: { id: 'health:001', kind: 'health' },
    expectNoThrow: true,
  },
  {
    name: 'Source is null',
    place: { id: 'health:002', kind: 'health', source: null },
    expectNoThrow: true,
  },
  {
    name: 'Source dataset is null',
    place: { id: 'health:003', kind: 'health', source: { dataset: null, reference_date: '2025' } },
    expectNoThrow: true,
  },
  {
    name: 'Source dataset is undefined',
    place: { id: 'health:004', kind: 'health', source: { dataset: undefined, reference_date: '2025' } },
    expectNoThrow: true,
  },
  {
    name: 'Source reference_date is "Não informado"',
    place: { id: 'health:005', kind: 'health', source: { dataset: 'cnes-national-bulk', reference_date: 'Não informado' } },
    expectNoThrow: true,
  },
  {
    name: 'Source reference_date is "  Não informado  " (with padding)',
    place: { id: 'health:006', kind: 'health', source: { dataset: 'cnes-national-bulk', reference_date: '  Não informado  ' } },
    expectNoThrow: true,
  },
  {
    name: 'Source reference_date is "não informado" (lowercase)',
    place: { id: 'health:007', kind: 'health', source: { dataset: 'cnes-national-bulk', reference_date: 'não informado' } },
    expectNoThrow: true,
  },
  {
    name: 'Source reference_date is "NAO INFORMADO" (all caps)',
    place: { id: 'health:008', kind: 'health', source: { dataset: 'cnes-national-bulk', reference_date: 'NAO INFORMADO' } },
    expectNoThrow: true,
  },
  {
    name: 'Source reference_date is "null" (string)',
    place: { id: 'health:009', kind: 'health', source: { dataset: 'cnes-national-bulk', reference_date: 'null' } },
    expectNoThrow: true,
  },
  {
    name: 'Dataset has special characters',
    place: { id: 'health:010', kind: 'health', source: { dataset: 'cnes_estabelecimentos_2025!@#$', reference_date: '2025' } },
    expectNoThrow: true,
  },
  {
    name: 'Unknown raw slug with hyphens',
    place: { id: 'health:011', kind: 'health', source: { dataset: 'custom-unregistered-slug', reference_date: '2025' } },
    expectNoThrow: true,
  },
];

for (const sc of placeScenarios) {
  for (const locale of ['pt-BR', 'en', 'es']) {
    let body;
    try {
      body = composeVisit(sc.place, locale, baseAnswersHealth, validNote);
    } catch (err) {
      recordFinding(
        'composeVisit',
        'HIGH',
        `composeVisit threw on scenario "${sc.name}" [${locale}]: ${err.message}`,
        err.stack
      );
      continue;
    }

    // Check for raw slug leaks
    if (body.includes('cnes-national-bulk')) {
      recordFinding(
        'composeVisit',
        'CRITICAL',
        `Raw slug "cnes-national-bulk" leaked into composeVisit body [${locale}]!`,
        `Scenario: ${sc.name}`
      );
    }

    // Check for "Não informado" leaks
    if (body.includes('Não informado') || body.includes('não informado') || body.includes('NAO INFORMADO')) {
      recordFinding(
        'composeVisit',
        'HIGH',
        `"Não informado" leaked into composeVisit body [${locale}]!`,
        `Scenario: "${sc.name}". Body snippet: ${body.split('\n')[2]}`
      );
    }
  }
}

// ----------------------------------------------------------------------
// 4. ADVERSARIAL STRESS TEST: coverageCount & statusLabel
// ----------------------------------------------------------------------
console.log('\n--- 4. Testing coverageCount & statusLabel ---');

const statusInputs = [
  'completed', 'partial', 'failed', 'running',
  'unknown', 'unassigned', '', 'COMPLETED', 'RUNNING',
  null, undefined, 123, {}, [], '__proto__', 'constructor'
];

for (const s of statusInputs) {
  for (const locale of ['pt-BR', 'en', 'es']) {
    const t = (k) => uiText(locale, k);
    let lbl;
    try {
      lbl = statusLabel(s, t);
    } catch (err) {
      recordFinding('statusLabel', 'HIGH', `statusLabel threw on input "${s}" [${locale}]`, err.message);
      continue;
    }
    if (lbl === 'Não informado' || lbl === 'No informado' || lbl === 'Not provided') {
      recordFinding('statusLabel', 'HIGH', `statusLabel returned "${lbl}" for input "${s}" [${locale}]`, '');
    }
  }
}

const countInputs = [
  0, 1, 100, 1000, 1000000,
  null, undefined, -1, -100, NaN, Infinity, -Infinity,
  '100', '0', 1.5, 3.14159,
  Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER + 1,
  {}, [], 'abc'
];

for (const c of countInputs) {
  for (const locale of ['pt-BR', 'en', 'es']) {
    const t = (k) => uiText(locale, k);
    let cnt;
    try {
      cnt = coverageCount(c, locale, t);
    } catch (err) {
      recordFinding('coverageCount', 'HIGH', `coverageCount threw on input "${c}" [${locale}]`, err.message);
      continue;
    }
    if (cnt === 'Não informado' || cnt === 'No informado' || cnt === 'Not provided') {
      recordFinding('coverageCount', 'HIGH', `coverageCount returned "${cnt}" for input "${c}" [${locale}]`, '');
    }
  }
}

// ----------------------------------------------------------------------
// SUMMARY OF FINDINGS
// ----------------------------------------------------------------------
console.log('\n================================================================');
console.log(`TOTAL FINDINGS: ${findings.length}`);
console.log('================================================================');
const criticals = findings.filter(f => f.severity === 'CRITICAL');
const highs = findings.filter(f => f.severity === 'HIGH');
const mediums = findings.filter(f => f.severity === 'MEDIUM');
const lows = findings.filter(f => f.severity === 'LOW');
console.log(`CRITICAL: ${criticals.length}`);
console.log(`HIGH:     ${highs.length}`);
console.log(`MEDIUM:   ${mediums.length}`);
console.log(`LOW:      ${lows.length}`);

if (findings.length > 0) {
  console.log('\n--- DETAILED SUMMARY OF ALL ISSUES FOUND ---');
  findings.forEach((f, i) => {
    console.log(`${i + 1}. [${f.severity}] [${f.category}] ${f.title}`);
  });
}

assert.equal(findings.length, 0, 'Adversarial challenge failed: findings detected');
console.log('\nALL ADVERSARIAL CHECKS PASSED.');

