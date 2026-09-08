import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';

const logoSourcePath = new URL('../src/CivicLogo.tsx', import.meta.url);
const faviconPath = new URL('../public/favicon.svg', import.meta.url);
const indexPath = new URL('../index.html', import.meta.url);
const mainPath = new URL('../src/main.tsx', import.meta.url);

test('CivicLogo.tsx: component exists and exports CivicLogo', () => {
  assert.ok(existsSync(logoSourcePath), 'web/src/CivicLogo.tsx must exist');
  const source = readFileSync(logoSourcePath, 'utf8');

  // Must export CivicLogo function component with default parameters
  assert.match(source, /export\s+function\s+CivicLogo\s*\(/);
  assert.match(source, /size\s*=\s*36/);
  assert.match(source, /className\s*=\s*''/);
  assert.match(source, /export\s+default\s+CivicLogo/);
});

test('CivicLogo.tsx: SVG element structure and accessibility attributes', () => {
  const source = readFileSync(logoSourcePath, 'utf8');

  // SVG accessibility attributes
  assert.match(source, /role="img"/, 'Must specify role="img"');
  assert.match(source, /aria-label="Brasil de Todos"/, 'Must specify aria-label="Brasil de Todos"');

  // Vector geometry & scaling
  assert.match(source, /viewBox="0 0 100 100"/, 'Must declare viewBox="0 0 100 100"');
  assert.match(source, /width=\{size\}/, 'Must bind width to size prop');
  assert.match(source, /height=\{size\}/, 'Must bind height to size prop');
  assert.match(source, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/, 'Must declare SVG namespace');
});

test('CivicLogo.tsx: authentic Brazilian civic color tokens', () => {
  const source = readFileSync(logoSourcePath, 'utf8');

  // Green field: #12644e
  assert.ok(source.includes('#12644e'), 'Must contain Brazilian civic green (#12644e)');
  // Warm gold / yellow lozenge: #f2b705
  assert.ok(source.includes('#f2b705'), 'Must contain warm gold rhombus/lozenge (#f2b705)');
  // Navy celestial sphere: #0b3b75
  assert.ok(source.includes('#0b3b75'), 'Must contain navy celestial sphere (#0b3b75)');
  // White citizen arc: #ffffff
  assert.ok(source.includes('#ffffff'), 'Must contain white citizen arc (#ffffff)');
});

test('CivicLogo.tsx: geometric representation of Brazilian civic symbols', () => {
  const source = readFileSync(logoSourcePath, 'utf8');

  // Green field container
  assert.match(source, /<rect[^>]+fill="#12644e"/);
  // Gold lozenge / rhombus polygon
  assert.match(source, /<polygon[^>]+fill="#f2b705"/);
  // Navy celestial sphere circle
  assert.match(source, /<circle[^>]+fill="#0b3b75"/);
  // White citizen arc path
  assert.match(source, /<path[^>]+stroke="#ffffff"/);
  // Citizen beacon/star
  assert.match(source, /<circle[^>]+fill="#ffffff"/);
});

test('favicon.svg: file exists and contains valid vector SVG', () => {
  assert.ok(existsSync(faviconPath), 'web/public/favicon.svg must exist');
  const content = readFileSync(faviconPath, 'utf8').trim();

  assert.ok(content.startsWith('<svg'), 'Favicon must be valid XML/SVG starting with <svg');
  assert.ok(content.endsWith('</svg>'), 'Favicon must end with </svg>');
  assert.match(content, /viewBox="0 0 100 100"/);
  assert.match(content, /role="img"/);
  assert.match(content, /aria-label="Brasil de Todos"/);
});

test('favicon.svg: patriotic Brazilian color palette and geometry', () => {
  const content = readFileSync(faviconPath, 'utf8');

  assert.ok(content.includes('#12644e'), 'Favicon must contain #12644e');
  assert.ok(content.includes('#f2b705'), 'Favicon must contain #f2b705');
  assert.ok(content.includes('#0b3b75'), 'Favicon must contain #0b3b75');
  assert.ok(content.includes('#ffffff'), 'Favicon must contain #ffffff');

  // Must have rect, polygon, circle, and path
  assert.match(content, /<rect[^>]+fill="#12644e"/);
  assert.match(content, /<polygon[^>]+fill="#f2b705"/);
  assert.match(content, /<circle[^>]+fill="#0b3b75"/);
  assert.match(content, /<path[^>]+stroke="#ffffff"/);
});

test('index.html: favicon link references /favicon.svg', () => {
  const indexHtml = readFileSync(indexPath, 'utf8');
  assert.match(
    indexHtml,
    /<link\s+rel="icon"\s+type="image\/svg\+xml"\s+href="\/favicon\.svg"\s*\/>/,
    'index.html must include <link rel="icon" type="image/svg+xml" href="/favicon.svg" />'
  );
});

test('main.tsx: CivicLogo integrated into header brand container', () => {
  const mainTsx = readFileSync(mainPath, 'utf8');

  // CivicLogo import
  assert.match(mainTsx, /import\s*\{[^}]*CivicLogo[^}]*\}\s*from\s*'\.\/CivicLogo'/);

  // Replaced unicode asterisk '✳' in header brand
  assert.match(
    mainTsx,
    /<CivicLogo\s+size=\{36\}\s+className="civic-brand-logo"\s*\/>/,
    'Header brand container must render <CivicLogo size={36} className="civic-brand-logo" />'
  );

  // The improvised unicode asterisk must no longer be present in the brand button
  const brandButtonMatch = mainTsx.match(/<button className="brand"[^>]*>([\s\S]*?)<\/button>/);
  assert.ok(brandButtonMatch, 'Brand button must exist in main.tsx');
  assert.ok(!brandButtonMatch[1].includes('✳'), 'Improvised unicode asterisk ✳ must be removed from brand');
});
