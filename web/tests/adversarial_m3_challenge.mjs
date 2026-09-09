// Adversarial Empirical Challenge Suite for Milestone M3
// Interface Fluidity, Usability, WCAG AA Contrast, Touch Targets & Multilingual Parity
// Features: F13 (Desktop Header), F14 (Mobile Header & Single Scroll), F15 (Map Sticky Docking),
//           F16 (Scroll Margins), F17 (WCAG AA Contrast), F18 (44px Touch Targets),
//           F19 (Missing i18n Keys 'map' & 'retry'), F20 (Date Sanitization), F21 (Build Verification)

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import { messages, translate, formatReferenceDate } from '../src/i18n.mjs';
import { regionMessages } from '../src/region-text.mjs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, '..');
const srcDir = path.join(webDir, 'src');

const styleCssPath = path.join(srcDir, 'style.css');
const mapCssPath = path.join(srcDir, 'map.css');
const workbenchCssPath = path.join(srcDir, 'workbench.css');
const groupsCssPath = path.join(srcDir, 'groups.css');

const findings = [];
let passCount = 0;
let failCount = 0;

function runCheck(title, fn) {
  try {
    fn();
    passCount++;
    console.log(`  ✔ PASS: ${title}`);
  } catch (err) {
    failCount++;
    findings.push({ title, error: err.message, stack: err.stack });
    console.error(`  ✘ FAIL: ${title}\n    ${err.message}`);
  }
}

console.log('================================================================');
console.log('STARTING EMPIRICAL ADVERSARIAL CHALLENGE SUITE FOR MILESTONE M3');
console.log('================================================================\n');

// ----------------------------------------------------------------------
// Mathematical WCAG 2.1 Luminance & Contrast Algorithms
// ----------------------------------------------------------------------
function hexToRgb(hex) {
  const cleaned = hex.replace('#', '').trim();
  assert.match(cleaned, /^[0-9a-fA-F]{6}$/, `Invalid 6-digit hex color: "${hex}"`);
  const r = parseInt(cleaned.slice(0, 2), 16);
  const g = parseInt(cleaned.slice(2, 4), 16);
  const b = parseInt(cleaned.slice(4, 6), 16);
  return [r, g, b];
}

function sRgbToLinear(c) {
  const norm = c / 255;
  return norm <= 0.04045 ? norm / 12.92 : Math.pow((norm + 0.055) / 1.055, 2.4);
}

function calculateRelativeLuminance(r, g, b) {
  const rLin = sRgbToLinear(r);
  const gLin = sRgbToLinear(g);
  const bLin = sRgbToLinear(b);
  return 0.2126 * rLin + 0.7152 * gLin + 0.0722 * bLin;
}

function calculateContrastRatio(hex1, hex2) {
  const [r1, g1, b1] = hexToRgb(hex1);
  const [r2, g2, b2] = hexToRgb(hex2);
  const l1 = calculateRelativeLuminance(r1, g1, b1);
  const l2 = calculateRelativeLuminance(r2, g2, b2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// ----------------------------------------------------------------------
// 1. ADVERSARIAL TEST: Mathematical Contrast Ratio Verification
// ----------------------------------------------------------------------
console.log('--- 1. Mathematical WCAG Contrast Ratio Verification ---');

runCheck('WCAG Math: #486357 on #ffffff must be >= 4.5:1 (normal text AA)', () => {
  const ratio = calculateContrastRatio('#486357', '#ffffff');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, required >= 4.5:1]`);
  assert.ok(ratio >= 4.5, `Expected >= 4.5:1, got ${ratio.toFixed(4)}:1`);
  assert.ok(ratio >= 5.0, `Expected comfortable margin >= 5.0:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('WCAG Math: #486357 on #f5f4ef (page background) must be >= 4.5:1', () => {
  const ratio = calculateContrastRatio('#486357', '#f5f4ef');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, required >= 4.5:1]`);
  assert.ok(ratio >= 4.5, `Expected >= 4.5:1, got ${ratio.toFixed(4)}:1`);
  assert.ok(ratio >= 5.0, `Expected comfortable margin >= 5.0:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('WCAG Math: #5a452d on #f7f2ea (quiet pill bg) must be >= 4.5:1', () => {
  const ratio = calculateContrastRatio('#5a452d', '#f7f2ea');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, required >= 4.5:1]`);
  assert.ok(ratio >= 4.5, `Expected >= 4.5:1, got ${ratio.toFixed(4)}:1`);
  assert.ok(ratio >= 5.0, `Expected comfortable margin >= 5.0:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('WCAG Math: Save icon inactive #5a7366 on #ffffff must be >= 3.0:1', () => {
  const ratio = calculateContrastRatio('#5a7366', '#ffffff');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, required >= 3.0:1]`);
  assert.ok(ratio >= 3.0, `Expected >= 3.0:1, got ${ratio.toFixed(4)}:1`);
  assert.ok(ratio >= 4.0, `Expected comfortable margin >= 4.0:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('WCAG Math: Save icon active #9c6000 on #ffffff must be >= 3.0:1', () => {
  const ratio = calculateContrastRatio('#9c6000', '#ffffff');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, required >= 3.0:1]`);
  assert.ok(ratio >= 3.0, `Expected >= 3.0:1, got ${ratio.toFixed(4)}:1`);
  assert.ok(ratio >= 3.5, `Expected comfortable margin >= 3.5:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('WCAG Math: Save icon colors on page background #f5f4ef must be >= 3.0:1', () => {
  const inactiveOnBg = calculateContrastRatio('#5a7366', '#f5f4ef');
  const activeOnBg = calculateContrastRatio('#9c6000', '#f5f4ef');
  console.log(`    [Inactive on #f5f4ef: ${inactiveOnBg.toFixed(4)}:1, Active on #f5f4ef: ${activeOnBg.toFixed(4)}:1]`);
  assert.ok(inactiveOnBg >= 3.0, `Expected >= 3.0:1, got ${inactiveOnBg.toFixed(4)}:1`);
  assert.ok(activeOnBg >= 3.0, `Expected >= 3.0:1, got ${activeOnBg.toFixed(4)}:1`);
});

runCheck('WCAG Math: Body text --text (#19241e) on --bg (#f5f4ef) must be >= 7.0:1 (AAA level)', () => {
  const ratio = calculateContrastRatio('#19241e', '#f5f4ef');
  console.log(`    [Computed ratio: ${ratio.toFixed(4)}:1, AAA level >= 7.0:1]`);
  assert.ok(ratio >= 7.0, `Expected AAA >= 7.0:1, got ${ratio.toFixed(4)}:1`);
});

runCheck('Negative Oracle Test: Validate that genuinely failing colors are accurately rejected by the contrast algorithm', () => {
  // Old quiet-text #7b9487 on white: was failing WCAG AA (< 4.5:1)
  const oldQuietVsWhite = calculateContrastRatio('#7b9487', '#ffffff');
  assert.ok(oldQuietVsWhite < 4.5, `Old #7b9487 should fail (<4.5:1), got ${oldQuietVsWhite.toFixed(2)}`);

  // An insufficiently contrasted pill text #a68d72 on #f7f2ea fails WCAG AA (< 4.5:1)
  const weakPillVsBg = calculateContrastRatio('#a68d72', '#f7f2ea');
  assert.ok(weakPillVsBg < 4.5, `Weak color #a68d72 should fail (<4.5:1), got ${weakPillVsBg.toFixed(2)}`);

  // Old save-icon inactive #a4b8ad on white: was failing UI component minimum (< 3.0:1)
  const oldSaveInactive = calculateContrastRatio('#a4b8ad', '#ffffff');
  assert.ok(oldSaveInactive < 3.0, `Old #a4b8ad should fail (<3.0:1), got ${oldSaveInactive.toFixed(2)}`);

  // Old save-icon active #d18a14 on white: was failing UI component minimum (< 3.0:1)
  const oldSaveActive = calculateContrastRatio('#d18a14', '#ffffff');
  assert.ok(oldSaveActive < 3.0, `Old #d18a14 should fail (<3.0:1), got ${oldSaveActive.toFixed(2)}`);
  console.log('    [Confirmed: Test oracle correctly rejects insufficiently contrasted colors]');
});

// ----------------------------------------------------------------------
// 2. ADVERSARIAL TEST: CSS Layout & Fluidity (No Rogue Rules, Docking, Margins)
// ----------------------------------------------------------------------
console.log('\n--- 2. CSS Layout & Fluidity Verification ---');

runCheck('workbench.css: Absence of rogue .header-right { width: 100% }', () => {
  assert.ok(fs.existsSync(workbenchCssPath), 'workbench.css must exist');
  const wbCss = fs.readFileSync(workbenchCssPath, 'utf8');

  assert.ok(
    !wbCss.includes('.header-right{width:100%') &&
    !wbCss.includes('.header-right { width: 100%') &&
    !wbCss.includes('.header-right{width: 100%') &&
    !wbCss.includes('.header-right {width:100%'),
    'workbench.css must not contain rogue .header-right { width: 100% }'
  );

  // Negative assertion: no width: 100% on header-right in any form
  const rogueMatch = wbCss.match(/\.header-right\s*\{[^}]*width\s*:\s*100%/);
  assert.equal(rogueMatch, null, 'Must have zero matches for .header-right with width: 100%');
});

runCheck('style.css: Desktop header aligns padding with 1440px max-width', () => {
  assert.ok(fs.existsSync(styleCssPath), 'style.css must exist');
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');

  assert.match(
    styleCss,
    /\.header\s*\{[^}]*1440px/,
    'style.css .header must reference 1440px to align padding with main content max-width'
  );
});

runCheck('style.css: Mobile header wraps language/account controls (flex-wrap: wrap)', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');

  assert.match(
    styleCss,
    /\.header-right\s*\{[^}]*flex-wrap:\s*wrap/,
    '.header-right must wrap on mobile viewports so 44px controls stay usable'
  );

  assert.doesNotMatch(
    styleCss,
    /\.header-right\s*\{[^}]*flex-wrap:\s*nowrap/,
    '.header-right must not force nowrap on mobile viewports'
  );
});

runCheck('map.css: Absence of position: relative override on .map-panel', () => {
  assert.ok(fs.existsSync(mapCssPath), 'map.css must exist');
  const mapCss = fs.readFileSync(mapCssPath, 'utf8');

  // Must not have position: relative on .map-panel globally
  assert.doesNotMatch(
    mapCss,
    /^\s*\.map-panel\s*\{[^}]*position:\s*relative/m,
    'map.css must not override .map-panel position to relative'
  );
});

runCheck('style.css: Desktop .map-panel maintains position: sticky; top: 4.8rem;', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');

  assert.match(
    styleCss,
    /\.map-panel\s*\{[^}]*position:\s*sticky;\s*top:\s*4\.8rem;/,
    'Desktop .map-panel in style.css must preserve sticky docking'
  );
});

runCheck('style.css: Mobile .map-panel maintains position: relative; order: -1;', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  const mobileBlock = styleCss.match(/@media\s*\(max-width:\s*1024px\)\s*\{([\s\S]*?)\n\}/);
  assert.ok(mobileBlock, 'Must find @media (max-width: 1024px) block');

  assert.match(
    mobileBlock[1],
    /\.map-panel\s*\{[^}]*position:\s*relative;\s*order:\s*-1;/,
    'Mobile .map-panel must be relative with order: -1 for single-column stacked flow'
  );
});

runCheck('style.css: scroll-margin-top: 5.5rem declared on target anchors', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');

  assert.match(
    styleCss,
    /(?:main|#main|\.card|\.place-card|\.map-panel)[^{]*\{[^}]*scroll-margin-top:\s*5\.5rem;/,
    'Target elements must have scroll-margin-top: 5.5rem'
  );

  const scrollMarginRule = styleCss.match(/([^{}]+)\{\s*scroll-margin-top:\s*5\.5rem;\s*\}/);
  assert.ok(scrollMarginRule, 'Must find exact rule block for scroll-margin-top: 5.5rem');
  const selector = scrollMarginRule[1];
  assert.ok(selector.includes('main'), 'Selector must include main');
  assert.ok(selector.includes('#main'), 'Selector must include #main');
  assert.ok(selector.includes('.place-card'), 'Selector must include .place-card');
  assert.ok(selector.includes('.map-panel'), 'Selector must include .map-panel');
});

runCheck('DOM Wiring: main.tsx and Map.tsx contain matching scroll target elements', () => {
  const mainTsxPath = path.join(srcDir, 'main.tsx');
  const mapTsxPath = path.join(srcDir, 'Map.tsx');
  assert.ok(fs.existsSync(mainTsxPath), 'main.tsx must exist');
  assert.ok(fs.existsSync(mapTsxPath), 'Map.tsx must exist');

  const mainTsx = fs.readFileSync(mainTsxPath, 'utf8');
  const mapTsx = fs.readFileSync(mapTsxPath, 'utf8');

  // Verify skip link and target
  assert.match(mainTsx, /<a\s+className="skip"\s+href="#main"/, 'main.tsx must contain skip link to #main');
  assert.match(mainTsx, /<main\s+id="main"/, 'main.tsx must contain <main id="main">');

  // Verify place-card target
  assert.match(mainTsx, /className="place-card"/, 'main.tsx must contain .place-card elements');

  // Verify map-panel target
  assert.match(mapTsx, /className="map-panel"/, 'Map.tsx must render aside with .map-panel');
});

runCheck('groups.css: Elimination of nested scrollbars (.group-place-results)', () => {
  assert.ok(fs.existsSync(groupsCssPath), 'groups.css must exist');
  const groupsCss = fs.readFileSync(groupsCssPath, 'utf8');

  assert.match(
    groupsCss,
    /\.group-place-results\s*\{[^}]*max-height:\s*none;?[^}]*overflow:\s*visible;?/,
    '.group-place-results must have max-height: none and overflow: visible'
  );

  assert.doesNotMatch(
    groupsCss,
    /\.group-place-results\s*\{[^}]*overflow:\s*auto/,
    '.group-place-results must not have overflow: auto'
  );
});

// ----------------------------------------------------------------------
// 3. ADVERSARIAL TEST: 44px Touch Target Size Enforcement
// ----------------------------------------------------------------------
console.log('\n--- 3. Touch Target Dimensions (WCAG 2.5.5 >= 44px) ---');

runCheck('map.css: .map-tilt-pill button has min-height >= 44px and min-width >= 44px', () => {
  const mapCss = fs.readFileSync(mapCssPath, 'utf8');
  assert.match(
    mapCss,
    /\.map-tilt-pill button\s*\{[^}]*min-height:\s*44px;[^}]*min-width:\s*44px;/,
    '.map-tilt-pill button must be at least 44x44px'
  );
});

runCheck('map.css: .city-pill-btn has min-height >= 44px and min-width >= 44px', () => {
  const mapCss = fs.readFileSync(mapCssPath, 'utf8');
  assert.match(
    mapCss,
    /\.city-pill-btn\s*\{[^}]*min-height:\s*44px;[^}]*min-width:\s*44px;/,
    '.city-pill-btn must be at least 44x44px'
  );
});

runCheck('style.css: .copy-pill has min-height >= 44px', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  assert.match(
    styleCss,
    /\.copy-pill\s*\{[^}]*min-height:\s*44px;/,
    '.copy-pill must enforce min-height: 44px'
  );
});

runCheck('style.css: .btn-map-3d has min-height >= 44px', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  assert.match(
    styleCss,
    /\.btn-map-3d\s*\{[^}]*min-height:\s*44px;/,
    '.btn-map-3d must enforce min-height: 44px'
  );
});

runCheck('style.css: .save-icon has min-width >= 44px and min-height >= 44px', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  assert.match(
    styleCss,
    /\.save-icon\s*\{[^}]*min-width:\s*44px;[^}]*min-height:\s*44px;/,
    '.save-icon must enforce 44x44px min dimensions'
  );
});

runCheck('style.css: .notice button has min-height >= 44px', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  assert.match(
    styleCss,
    /\.notice button\s*\{[^}]*min-height:\s*44px;/,
    '.notice button must enforce min-height: 44px'
  );
});

runCheck('style.css: .header-right select and button on mobile have min-height >= 44px', () => {
  const styleCss = fs.readFileSync(styleCssPath, 'utf8');
  assert.match(
    styleCss,
    /\.header-right select\s*\{[^}]*min-height:\s*44px;/,
    '.header-right select on mobile must enforce min-height: 44px'
  );
  assert.match(
    styleCss,
    /\.header-right button\s*\{[^}]*min-height:\s*44px;/,
    '.header-right button on mobile must enforce min-height: 44px'
  );
});

runCheck('workbench.css & groups.css: panel summary has min-height >= 44px', () => {
  const wbCss = fs.readFileSync(workbenchCssPath, 'utf8');
  const groupsCss = fs.readFileSync(groupsCssPath, 'utf8');

  assert.match(wbCss, /summary\{[^}]*min-height:44px/, 'workbench summary must enforce min-height: 44px');
  assert.match(groupsCss, /summary\{[^}]*min-height:44px/, 'groups summary must enforce min-height: 44px');
});

// ----------------------------------------------------------------------
// 4. ADVERSARIAL TEST: Multilingual Translation Parity (pt-BR, en, es)
// ----------------------------------------------------------------------
console.log('\n--- 4. Multilingual Translation Parity (pt-BR, en, es) ---');

runCheck("i18n.mjs: Key 'map' is present and localized non-empty across pt-BR, en, es", () => {
  const locales = ['pt-BR', 'en', 'es'];
  const expected = {
    'pt-BR': 'Mapa',
    'en': 'Map',
    'es': 'Mapa',
  };

  for (const loc of locales) {
    assert.ok(messages[loc], `messages[${loc}] must exist`);
    assert.ok(messages[loc].map, `messages[${loc}].map must exist`);
    assert.equal(typeof messages[loc].map, 'string', `messages[${loc}].map must be string`);
    assert.ok(messages[loc].map.trim().length > 0, `messages[${loc}].map must not be empty`);
    assert.equal(messages[loc].map, expected[loc], `messages[${loc}].map must equal ${expected[loc]}`);
    assert.equal(translate(loc, 'map'), expected[loc], `translate(${loc}, 'map') must resolve correctly`);
  }
});

runCheck("region-text.mjs: Key 'retry' is present and localized non-empty across pt-BR, en, es", () => {
  const locales = ['pt-BR', 'en', 'es'];
  const expected = {
    'pt-BR': 'Tentar novamente',
    'en': 'Try again',
    'es': 'Reintentar',
  };

  for (const loc of locales) {
    assert.ok(regionMessages[loc], `regionMessages[${loc}] must exist`);
    assert.ok(regionMessages[loc].retry, `regionMessages[${loc}].retry must exist`);
    assert.equal(typeof regionMessages[loc].retry, 'string', `regionMessages[${loc}].retry must be string`);
    assert.ok(regionMessages[loc].retry.trim().length > 0, `regionMessages[${loc}].retry must not be empty`);
    assert.equal(regionMessages[loc].retry, expected[loc], `regionMessages[${loc}].retry must equal ${expected[loc]}`);
  }
});

runCheck("i18n.mjs: Complete key symmetry across pt-BR, en, es dictionaries", () => {
  const ptKeys = Object.keys(messages['pt-BR']).sort();
  const enKeys = Object.keys(messages['en']).sort();
  const esKeys = Object.keys(messages['es']).sort();

  const missingInEn = ptKeys.filter(k => !(k in messages['en']));
  const missingInEs = ptKeys.filter(k => !(k in messages['es']));

  assert.deepEqual(missingInEn, [], `Keys in pt-BR missing in en: ${missingInEn.join(', ')}`);
  assert.deepEqual(missingInEs, [], `Keys in pt-BR missing in es: ${missingInEs.join(', ')}`);
});

runCheck("region-text.mjs: Complete key symmetry across pt-BR, en, es dictionaries", () => {
  const ptKeys = Object.keys(regionMessages['pt-BR']).sort();
  const enKeys = Object.keys(regionMessages['en']).sort();
  const esKeys = Object.keys(regionMessages['es']).sort();

  const missingInEn = ptKeys.filter(k => !(k in regionMessages['en']));
  const missingInEs = ptKeys.filter(k => !(k in regionMessages['es']));

  assert.deepEqual(missingInEn, [], `Keys in pt-BR missing in en: ${missingInEn.join(', ')}`);
  assert.deepEqual(missingInEs, [], `Keys in pt-BR missing in es: ${missingInEs.join(', ')}`);
});

runCheck('formatReferenceDate: Adversarial inputs and locale handling', () => {
  const adversarialCases = [
    { input: 'Não informado', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: 'não informado', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: 'NÃO INFORMADO', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: '  Não informado  ', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: null, pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: undefined, pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: '', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: '   ', pt: 'Cadastro oficial', en: 'Official record', es: 'Registro oficial' },
    { input: '2026-09-08', pt: 'Ref. 2026-09-08', en: 'Ref. 2026-09-08', es: 'Ref. 2026-09-08' },
  ];

  for (const c of adversarialCases) {
    assert.equal(formatReferenceDate(c.input, 'pt-BR'), c.pt, `Failed pt-BR for input "${c.input}"`);
    assert.equal(formatReferenceDate(c.input, 'en'), c.en, `Failed en for input "${c.input}"`);
    assert.equal(formatReferenceDate(c.input, 'es'), c.es, `Failed es for input "${c.input}"`);
  }
});

// ----------------------------------------------------------------------
// 5. ADVERSARIAL TEST: Verify Build Output Assets
// ----------------------------------------------------------------------
console.log('\n--- 5. Production Build Output Verification ---');

runCheck('dist/: Build output contains expected HTML, CSS and JS assets', () => {
  const distDir = path.join(webDir, 'dist');
  assert.ok(fs.existsSync(distDir), 'dist/ directory must exist');

  const distIndex = path.join(distDir, 'index.html');
  assert.ok(fs.existsSync(distIndex), 'dist/index.html must exist');

  const assetsDir = path.join(distDir, 'assets');
  assert.ok(fs.existsSync(assetsDir), 'dist/assets directory must exist');
  const assetFiles = fs.readdirSync(assetsDir);

  const hasCss = assetFiles.some(f => f.endsWith('.css'));
  const hasJs = assetFiles.some(f => f.endsWith('.js'));
  const hasWorker = assetFiles.some(f => f.includes('worker') && f.endsWith('.js'));

  assert.ok(hasCss, 'dist/assets must contain bundled CSS');
  assert.ok(hasJs, 'dist/assets must contain bundled JS');
  assert.ok(hasWorker, 'dist/assets must contain maplibre worker bundle');
});

// ----------------------------------------------------------------------
// Summary
// ----------------------------------------------------------------------
console.log('\n================================================================');
console.log(`CHALLENGE RESULTS: ${passCount} Passed, ${failCount} Failed`);
console.log('================================================================');

if (failCount > 0) {
  console.error('\nVULNERABILITIES FOUND:');
  for (const f of findings) {
    console.error(`- ${f.title}: ${f.error}`);
  }
  process.exit(1);
} else {
  console.log('\nALL ADVERSARIAL CHALLENGES PASSED EMPIRICALLY WITH ZERO DEFECTS.');
  process.exit(0);
}
