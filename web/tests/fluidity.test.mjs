import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { messages, formatReferenceDate } from '../src/i18n.mjs';
import { regionMessages } from '../src/region-text.mjs';

const styleCssPath = new URL('../src/style.css', import.meta.url);
const mapCssPath = new URL('../src/map.css', import.meta.url);
const workbenchCssPath = new URL('../src/workbench.css', import.meta.url);
const groupsCssPath = new URL('../src/groups.css', import.meta.url);

function hexToRgb(hex) {
  const cleaned = hex.replace('#', '');
  const r = parseInt(cleaned.slice(0, 2), 16);
  const g = parseInt(cleaned.slice(2, 4), 16);
  const b = parseInt(cleaned.slice(4, 6), 16);
  return [r, g, b];
}

function relativeLuminance(r, g, b) {
  const [rs, gs, bs] = [r, g, b].map(c => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
}

function contrastRatio(hex1, hex2) {
  const l1 = relativeLuminance(...hexToRgb(hex1));
  const l2 = relativeLuminance(...hexToRgb(hex2));
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

test('Feature F13 & F14: Mobile & desktop header fluidity', () => {
  assert.ok(existsSync(workbenchCssPath), 'workbench.css must exist');
  const wbCss = readFileSync(workbenchCssPath, 'utf8');

  // Verify workbench.css does not enforce width: 100% on .header-right at max-width: 480px
  assert.ok(
    !wbCss.includes('.header-right{width:100%'),
    'workbench.css must not contain rogue .header-right { width: 100% }'
  );

  const styleCss = readFileSync(styleCssPath, 'utf8');

  // Desktop alignment with page content max-width (1440px)
  assert.ok(
    styleCss.includes('1440px'),
    'style.css header should align desktop padding with 1440px max-width boundary'
  );

  // Language/account controls wrap; 44px targets must not overflow the row
  assert.match(
    styleCss,
    /\.header-right\s*\{[^}]*flex-wrap:\s*wrap/,
    '.header-right must wrap on narrow viewports so 44px controls stay usable'
  );
  assert.doesNotMatch(
    styleCss,
    /\.header-right\s*\{[^}]*flex-wrap:\s*nowrap/,
    '.header-right must not force nowrap (overflows language/account buttons)'
  );
});

test('Feature F15: Map panel sticky vs relative harmonization', () => {
  const mapCss = readFileSync(mapCssPath, 'utf8');
  const styleCss = readFileSync(styleCssPath, 'utf8');

  // map.css must NOT override position: relative on .map-panel globally
  assert.doesNotMatch(
    mapCss,
    /\.map-panel\s*\{[^}]*position:\s*relative/,
    '.map-panel in map.css must not enforce position: relative'
  );

  // style.css desktop maintains position: sticky; top: 4.8rem;
  assert.match(
    styleCss,
    /\.map-panel\s*\{[^}]*position:\s*sticky;\s*top:\s*4\.8rem;/,
    '.map-panel in style.css must preserve desktop sticky positioning'
  );

  // style.css mobile maintains position: relative
  const mobileMediaMatch = styleCss.match(/@media\s*\(max-width:\s*1024px\)\s*\{([\s\S]*?)\n\}/);
  assert.ok(mobileMediaMatch, 'Must have @media (max-width: 1024px) block');
  assert.match(
    mobileMediaMatch[1],
    /\.map-panel\s*\{[^}]*position:\s*relative/,
    '.map-panel must be in normal document flow on mobile viewports'
  );
});

test('Feature F16: Target anchor scroll margins prevent sticky header clipping', () => {
  const styleCss = readFileSync(styleCssPath, 'utf8');

  // scroll-margin-top must be declared on #main, .card / .place-card, .map-panel
  assert.match(
    styleCss,
    /(?:main|#main|\.card|\.place-card|\.map-panel)[^{]*\{[^}]*scroll-margin-top:\s*5\.5rem;/,
    'Targets must declare scroll-margin-top: 5.5rem;'
  );
  assert.ok(styleCss.includes('#main'), 'Must include #main in scroll-margin-top rule');
  assert.ok(styleCss.includes('.map-panel'), 'Must include .map-panel in scroll-margin-top rule');
  assert.ok(styleCss.includes('.place-card'), 'Must include .place-card in scroll-margin-top rule');
});

test('Feature F14: Single-scrollbar document flow in groups and body', () => {
  const groupsCss = readFileSync(groupsCssPath, 'utf8');
  const styleCss = readFileSync(styleCssPath, 'utf8');

  // .group-place-results must not generate a nested scroll container
  assert.doesNotMatch(
    groupsCss,
    /\.group-place-results\s*\{[^}]*overflow:\s*auto/,
    '.group-place-results must not have overflow: auto'
  );
  assert.doesNotMatch(
    groupsCss,
    /\.group-place-results\s*\{[^}]*max-height:\s*300px/,
    '.group-place-results must not restrict max-height to 300px'
  );

  // html and body must not have conflicting overflow styles
  assert.doesNotMatch(
    styleCss,
    /body\s*\{[^}]*overflow:\s*hidden/,
    'body must not have overflow: hidden'
  );
});

test('Feature F17: WCAG AA contrast compliance and :root custom properties', () => {
  const styleCss = readFileSync(styleCssPath, 'utf8');

  // :root defines --bg and --text
  assert.match(styleCss, /--bg:\s*#f5f4ef;/, ':root must declare --bg: #f5f4ef');
  assert.match(styleCss, /--text:\s*#19241e;/, ':root must declare --text: #19241e');

  // Quiet text color
  assert.match(styleCss, /\.quiet-text\s*\{[^}]*color:\s*#486357;/, '.quiet-text must use #486357');
  const quietVsWhite = contrastRatio('#486357', '#ffffff');
  assert.ok(quietVsWhite >= 5.0, `.quiet-text vs white must have >= 5:1 contrast (got ${quietVsWhite.toFixed(2)})`);
  const quietVsBg = contrastRatio('#486357', '#f5f4ef');
  assert.ok(quietVsBg >= 5.0, `.quiet-text vs #f5f4ef must have >= 5:1 contrast (got ${quietVsBg.toFixed(2)})`);

  // Quiet pill text color
  assert.match(styleCss, /\.quiet-pill\s*\{[^}]*color:\s*#5a452d;/, '.quiet-pill must use #5a452d');
  const pillVsBg = contrastRatio('#5a452d', '#f7f2ea');
  assert.ok(pillVsBg >= 4.5, `.quiet-pill vs background must have >= 4.5:1 contrast (got ${pillVsBg.toFixed(2)})`);

  // Save icon inactive & active/hover
  assert.match(styleCss, /\.save-icon\s*\{[^}]*color:\s*#5a7366;/, '.save-icon inactive must use #5a7366');
  assert.match(styleCss, /\.save-icon:hover\s*\{[^}]*color:\s*#9c6000;/, '.save-icon:hover must use #9c6000');
  assert.match(styleCss, /\.save-icon\[aria-pressed=true\]\s*\{[^}]*color:\s*#9c6000;/, '.save-icon[aria-pressed=true] must use #9c6000');
  const saveInactiveRatio = contrastRatio('#5a7366', '#ffffff');
  assert.ok(saveInactiveRatio >= 4.0, `.save-icon inactive vs white must have >= 4:1 (got ${saveInactiveRatio.toFixed(2)})`);
  const saveActiveRatio = contrastRatio('#9c6000', '#ffffff');
  assert.ok(saveActiveRatio >= 3.5, `.save-icon active vs white must have >= 3.5:1 for graphical UI (got ${saveActiveRatio.toFixed(2)})`);
});

test('Feature F18: Mobile touch target sizing (minimum 44x44px)', () => {
  const mapCss = readFileSync(mapCssPath, 'utf8');
  const styleCss = readFileSync(styleCssPath, 'utf8');

  // .map-tilt-pill button
  assert.match(
    mapCss,
    /\.map-tilt-pill button\s*\{[^}]*min-height:\s*44px;[^}]*min-width:\s*44px;/,
    '.map-tilt-pill button must be at least 44x44px'
  );

  // .city-pill-btn
  assert.match(
    mapCss,
    /\.city-pill-btn\s*\{[^}]*min-height:\s*44px;[^}]*min-width:\s*44px;/,
    '.city-pill-btn must be at least 44x44px'
  );

  // .copy-pill
  assert.match(
    styleCss,
    /\.copy-pill\s*\{[^}]*min-height:\s*44px;/,
    '.copy-pill must be at least 44px min-height'
  );

  // .btn-map-3d
  assert.match(
    styleCss,
    /\.btn-map-3d\s*\{[^}]*min-height:\s*44px;/,
    '.btn-map-3d must be at least 44px min-height'
  );

  // .save-icon
  assert.match(
    styleCss,
    /\.save-icon\s*\{[^}]*min-width:\s*44px;[^}]*min-height:\s*44px;/,
    '.save-icon must be at least 44x44px'
  );

  // .notice button
  assert.match(
    styleCss,
    /\.notice button\s*\{[^}]*min-height:\s*44px;/,
    '.notice button must be at least 44px min-height'
  );

  // .header-right select on mobile
  assert.match(
    styleCss,
    /\.header-right select\s*\{[^}]*min-height:\s*44px;/,
    '.header-right select on mobile must be at least 44px min-height'
  );
});

test('Feature F19: Missing i18n translation keys in i18n.mjs and region-text.mjs', () => {
  // Check 'map' key across locales
  assert.equal(messages['pt-BR'].map, 'Mapa', "messages['pt-BR'].map must be 'Mapa'");
  assert.equal(messages['en'].map, 'Map', "messages['en'].map must be 'Map'");
  assert.equal(messages['es'].map, 'Mapa', "messages['es'].map must be 'Mapa'");

  // Check 'retry' key in regionMessages
  assert.equal(regionMessages['pt-BR'].retry, 'Tentar novamente', "regionMessages['pt-BR'].retry must be 'Tentar novamente'");
  assert.equal(regionMessages['en'].retry, 'Try again', "regionMessages['en'].retry must be 'Try again'");
  assert.equal(regionMessages['es'].retry, 'Reintentar', "regionMessages['es'].retry must be 'Reintentar'");
});

test('Feature F20: Reference date sanitization for official data', () => {
  // Valid dates preserve refPrefix
  assert.equal(formatReferenceDate('2026-01-15', 'pt-BR'), 'Ref. 2026-01-15');
  assert.equal(formatReferenceDate('2026-01-15', 'en'), 'Ref. 2026-01-15');
  assert.equal(formatReferenceDate('2026-01-15', 'es'), 'Ref. 2026-01-15');

  // "Não informado" and empty values must map to officialRecord
  assert.equal(formatReferenceDate('Não informado', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('Não informado', 'en'), 'Official record');
  assert.equal(formatReferenceDate('Não informado', 'es'), 'Registro oficial');
  assert.equal(formatReferenceDate(null, 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate('', 'pt-BR'), 'Cadastro oficial');
  assert.equal(formatReferenceDate(undefined, 'pt-BR'), 'Cadastro oficial');
});
