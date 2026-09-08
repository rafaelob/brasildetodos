// Adversarial Empirical Challenge Suite for Milestone M2 (Visual Identity, Civic Logo & Favicon)
// Features: F10 (Responsive SVG Civic Logo), F11 (Vector Favicon), F12 (Header Branding)

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync, execFileSync } from 'node:child_process';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const webDir = path.resolve(__dirname, '..');
const projectDir = path.resolve(webDir, '..');

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
console.log('STARTING EMPIRICAL ADVERSARIAL CHALLENGE SUITE FOR MILESTONE M2');
console.log('================================================================\n');

// ----------------------------------------------------------------------
// Load & Transpile CivicLogo.tsx
// ----------------------------------------------------------------------
const logoTsxPath = path.join(webDir, 'src', 'CivicLogo.tsx');
assert.ok(fs.existsSync(logoTsxPath), 'CivicLogo.tsx must exist');
const logoSource = fs.readFileSync(logoTsxPath, 'utf8');

const transpileResult = ts.transpileModule(logoSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.React,
  },
});

const fn = new Function('React', 'exports', transpileResult.outputText);
const logoExports = {};
fn(React, logoExports);

const CivicLogo = logoExports.CivicLogo;
const CIVIC_COLORS = logoExports.CIVIC_COLORS;

// ----------------------------------------------------------------------
// 1. ADVERSARIAL TEST: CivicLogo Component & Prop Stress Testing
// ----------------------------------------------------------------------
console.log('--- 1. CivicLogo Component & Props Stress Testing ---');

runCheck('CivicLogo: Named and default exports exist and match', () => {
  assert.equal(typeof CivicLogo, 'function', 'Named export CivicLogo must be a function');
  assert.equal(typeof logoExports.default, 'function', 'Default export must be a function');
  assert.equal(logoExports.default, CivicLogo, 'Default export must match named export');
});

runCheck('CIVIC_COLORS: Exported color tokens match specification', () => {
  assert.ok(CIVIC_COLORS, 'CIVIC_COLORS must be exported');
  assert.equal(CIVIC_COLORS.green, '#12644e', 'green must be #12644e');
  assert.equal(CIVIC_COLORS.yellow, '#f2b705', 'yellow must be #f2b705');
  assert.equal(CIVIC_COLORS.blue, '#0b3b75', 'blue must be #0b3b75');
  assert.equal(CIVIC_COLORS.white, '#ffffff', 'white must be #ffffff');
});

runCheck('CivicLogo: Invocation with empty props {} applies defaults (size=36, className="")', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, {}));
  assert.match(rendered, /width="36"/, 'Should default width to 36');
  assert.match(rendered, /height="36"/, 'Should default height to 36');
  assert.match(rendered, /class="civic-logo"/, 'Should default class to civic-logo without trailing space');
  assert.ok(!rendered.includes('class="civic-logo "'), 'Should not have trailing space in class');
});

runCheck('CivicLogo: Invocation with undefined props applies defaults cleanly', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: undefined, className: undefined }));
  assert.match(rendered, /width="36"/);
  assert.match(rendered, /height="36"/);
  assert.match(rendered, /class="civic-logo"/);
});

runCheck('CivicLogo: Small size prop (size=16) renders width="16" and height="16"', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 16 }));
  assert.match(rendered, /width="16"/);
  assert.match(rendered, /height="16"/);
});

runCheck('CivicLogo: Medium size prop (size=72) and custom className renders properly', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 72, className: 'brand-hero' }));
  assert.match(rendered, /width="72"/);
  assert.match(rendered, /height="72"/);
  assert.match(rendered, /class="civic-logo brand-hero"/);
});

runCheck('CivicLogo: Large size prop (size=128) renders width="128" and height="128"', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 128 }));
  assert.match(rendered, /width="128"/);
  assert.match(rendered, /height="128"/);
});

runCheck('CivicLogo: Production header usage (size=36, className="civic-brand-logo")', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 36, className: 'civic-brand-logo' }));
  assert.match(rendered, /width="36"/);
  assert.match(rendered, /height="36"/);
  assert.match(rendered, /class="civic-logo civic-brand-logo"/);
});

runCheck('CivicLogo: Boundary size prop (size=0) renders width="0" height="0"', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 0 }));
  assert.match(rendered, /width="0"/);
  assert.match(rendered, /height="0"/);
});

runCheck('CivicLogo: Multiple custom classes are preserved', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { className: 'nav-icon extra-class' }));
  assert.match(rendered, /class="civic-logo nav-icon extra-class"/);
});

runCheck('CivicLogo: Floating-point size (size=42.5) renders correctly without truncation', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 42.5 }));
  assert.match(rendered, /width="42.5"/);
  assert.match(rendered, /height="42.5"/);
});

runCheck('CivicLogo: Malicious XSS payload in className is safely HTML-escaped by React', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { className: '"><script>alert(1)</script>' }));
  assert.ok(!rendered.includes('<script>'), 'Must not allow unescaped <script> tag in markup');
  assert.match(rendered, /class="civic-logo &quot;&gt;&lt;script&gt;alert\(1\)&lt;\/script&gt;"/);
});

// ----------------------------------------------------------------------
// 2. ADVERSARIAL TEST: SVG Element Attributes & Accessibility
// ----------------------------------------------------------------------
console.log('\n--- 2. SVG Element Attributes & Accessibility ---');

runCheck('CivicLogo: Root SVG element contains all required accessibility and vector attributes', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, {}));
  assert.match(rendered, /^<svg[^>]+role="img"[^>]*>/, 'Must declare role="img"');
  assert.match(rendered, /aria-label="Brasil de Todos"/, 'Must declare aria-label="Brasil de Todos"');
  assert.match(rendered, /viewBox="0 0 100 100"/, 'Must declare viewBox="0 0 100 100"');
  assert.match(rendered, /xmlns="http:\/\/www\.w3\.org\/2000\/svg"/, 'Must declare SVG xmlns');
  assert.match(rendered, /fill="none"/, 'Must declare fill="none" on svg root');
});

runCheck('CivicLogo: Geometric representation of Brazilian civic symbols', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, {}));

  // 1. Green field: rect with rx="20"
  assert.match(rendered, /<rect[^>]+width="100"[^>]+height="100"[^>]+rx="20"[^>]+fill="#12644e"/);

  // 2. Gold rhombus/lozenge: polygon with 50,14 86,50 50,86 14,50
  assert.match(rendered, /<polygon[^>]+points="50,14 86,50 50,86 14,50"[^>]+fill="#f2b705"/);

  // 3. Navy celestial sphere: circle centered at (50, 50) with radius 21
  assert.match(rendered, /<circle[^>]+cx="50"[^>]+cy="50"[^>]+r="21"[^>]+fill="#0b3b75"/);

  // 4. White citizen arc: path representing popular participation
  assert.match(rendered, /<path[^>]+d="M 32 55 C 42 46 58 46 68 55"[^>]+stroke="#ffffff"[^>]+stroke-width="3.5"[^>]+stroke-linecap="round"[^>]+fill="none"/);

  // 5. Citizen beacon: star / democracy light centered at (50, 42) with radius 2.5
  assert.match(rendered, /<circle[^>]+cx="50"[^>]+cy="42"[^>]+r="2.5"[^>]+fill="#ffffff"/);
});

// ----------------------------------------------------------------------
// 3. ADVERSARIAL TEST: Exact Hex Colors Presence
// ----------------------------------------------------------------------
console.log('\n--- 3. Exact Hex Colors Presence ---');

runCheck('CivicLogo: All Brazilian color hex codes (#12644e, #f2b705, #0b3b75, #ffffff) are present in rendered markup', () => {
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, {}));
  const requiredColors = ['#12644e', '#f2b705', '#0b3b75', '#ffffff'];
  for (const color of requiredColors) {
    assert.ok(rendered.includes(color), `Rendered SVG must include color ${color}`);
  }
});

// ----------------------------------------------------------------------
// 4. ADVERSARIAL TEST: Well-formed XML / SVG Parsing of favicon.svg
// ----------------------------------------------------------------------
console.log('\n--- 4. Well-formed XML/SVG Parsing of favicon.svg ---');

const faviconPath = path.join(webDir, 'public', 'favicon.svg');

runCheck('favicon.svg: File exists and is non-empty', () => {
  assert.ok(fs.existsSync(faviconPath), 'web/public/favicon.svg must exist');
  const stat = fs.statSync(faviconPath);
  assert.ok(stat.size > 100 && stat.size < 5000, `Favicon size must be reasonable (got ${stat.size} bytes)`);
});

runCheck('favicon.svg: Strictly parses as valid XML/SVG using Python xml.etree', () => {
  const pythonCmd = path.join(projectDir, '.venv', 'Scripts', 'python.exe');
  const pyScript = `
import xml.etree.ElementTree as ET
import sys

tree = ET.parse(sys.argv[1])
root = tree.getroot()

assert root.tag.endswith('svg'), f"Expected svg root, got {root.tag}"
assert root.attrib.get('viewBox') == '0 0 100 100', f"Bad viewBox: {root.attrib.get('viewBox')}"
assert root.attrib.get('role') == 'img', f"Bad role: {root.attrib.get('role')}"
assert root.attrib.get('aria-label') == 'Brasil de Todos', f"Bad aria-label: {root.attrib.get('aria-label')}"

# Check children
tags = [child.tag.split('}')[-1] for child in root]
assert tags == ['rect', 'polygon', 'circle', 'path', 'circle'], f"Unexpected children: {tags}"

colors = [child.attrib.get('fill') or child.attrib.get('stroke') for child in root]
assert '#12644e' in colors, "Missing #12644e"
assert '#f2b705' in colors, "Missing #f2b705"
assert '#0b3b75' in colors, "Missing #0b3b75"
assert '#ffffff' in colors, "Missing #ffffff"

print("OK_FAVICON_PARSED")
`;
  const result = execFileSync(pythonCmd, ['-c', pyScript, faviconPath], {
    encoding: 'utf8',
    cwd: projectDir,
  });
  assert.ok(result.includes('OK_FAVICON_PARSED'), 'Favicon XML validation must succeed');
});

runCheck('favicon.svg: SVG security audit (no script, no foreignObject, no external href, no event handlers)', () => {
  const content = fs.readFileSync(faviconPath, 'utf8');
  assert.ok(!/<script/i.test(content), 'favicon.svg must not contain script tags');
  assert.ok(!/<foreignObject/i.test(content), 'favicon.svg must not contain foreignObject tags');
  assert.ok(!/href\s*=/i.test(content), 'favicon.svg must not contain href attributes');
  assert.ok(!/on\w+\s*=/i.test(content), 'favicon.svg must not contain inline event handlers');
  assert.ok(!/javascript:/i.test(content), 'favicon.svg must not contain javascript: protocol');
});

runCheck('main.tsx and index.html: Broader unicode dingbat asterisk range (U+2720 - U+274B) complete absence from brand', () => {
  const mainTsxContent = fs.readFileSync(path.join(webDir, 'src', 'main.tsx'), 'utf8');
  const indexHtmlContent = fs.readFileSync(path.join(webDir, 'index.html'), 'utf8');
  
  // Unicode dingbats range commonly used for stars/asterisks: U+2720 - U+274B
  const dingbatStarRegex = /[\u2720-\u274B]/g;
  const mainMatches = mainTsxContent.match(dingbatStarRegex) || [];
  const indexMatches = indexHtmlContent.match(dingbatStarRegex) || [];
  
  assert.equal(mainMatches.length, 0, `main.tsx must contain 0 dingbat star characters, found: ${mainMatches.join(', ')}`);
  assert.equal(indexMatches.length, 0, `index.html must contain 0 dingbat star characters, found: ${indexMatches.join(', ')}`);
});

runCheck('CivicLogo: Rendered SVG string strictly parses as valid XML using Python xml.etree', () => {
  const pythonCmd = path.join(projectDir, '.venv', 'Scripts', 'python.exe');
  const rendered = renderToStaticMarkup(React.createElement(CivicLogo, { size: 48, className: 'test-xml' }));
  
  const pyScript = `
import xml.etree.ElementTree as ET
import sys

root = ET.fromstring(sys.stdin.read())
assert root.tag.endswith('svg')
assert root.attrib.get('viewBox') == '0 0 100 100'
assert root.attrib.get('role') == 'img'
assert root.attrib.get('aria-label') == 'Brasil de Todos'
assert root.attrib.get('class') == 'civic-logo test-xml'

tags = [child.tag.split('}')[-1] for child in root]
assert tags == ['rect', 'polygon', 'circle', 'path', 'circle'], f"Unexpected children: {tags}"
print("OK_RENDERED_XML_PARSED")
`;
  const result = execFileSync(pythonCmd, ['-c', pyScript], {
    input: rendered,
    encoding: 'utf8',
    cwd: projectDir,
  });
  assert.ok(result.includes('OK_RENDERED_XML_PARSED'), 'Rendered SVG XML validation must succeed');
});

// ----------------------------------------------------------------------
// 5. ADVERSARIAL TEST: Complete Removal of Unicode Asterisk ✳
// ----------------------------------------------------------------------
console.log('\n--- 5. Unicode Asterisk ✳ Complete Removal ---');

const asteriskChar = '✳'; // U+2733

runCheck('main.tsx: Unicode asterisk ✳ is completely absent from file', () => {
  const mainTsxPath = path.join(webDir, 'src', 'main.tsx');
  const mainTsxContent = fs.readFileSync(mainTsxPath, 'utf8');
  assert.ok(
    !mainTsxContent.includes(asteriskChar),
    `Unicode asterisk ${asteriskChar} (U+2733) MUST NOT exist anywhere in web/src/main.tsx`
  );
});

runCheck('index.html: Unicode asterisk ✳ is completely absent from file', () => {
  const indexHtmlPath = path.join(webDir, 'index.html');
  const indexHtmlContent = fs.readFileSync(indexHtmlPath, 'utf8');
  assert.ok(
    !indexHtmlContent.includes(asteriskChar),
    `Unicode asterisk ${asteriskChar} (U+2733) MUST NOT exist anywhere in web/index.html`
  );
});

runCheck('CivicLogo.tsx: Unicode asterisk ✳ is completely absent from file', () => {
  assert.ok(
    !logoSource.includes(asteriskChar),
    `Unicode asterisk ${asteriskChar} (U+2733) MUST NOT exist anywhere in web/src/CivicLogo.tsx`
  );
});

runCheck('favicon.svg: Unicode asterisk ✳ is completely absent from file', () => {
  const faviconContent = fs.readFileSync(faviconPath, 'utf8');
  assert.ok(
    !faviconContent.includes(asteriskChar),
    `Unicode asterisk ${asteriskChar} (U+2733) MUST NOT exist anywhere in web/public/favicon.svg`
  );
});

runCheck('Whole web/src/ directory: Zero occurrences of unicode asterisk ✳', () => {
  const srcFiles = fs.readdirSync(path.join(webDir, 'src'));
  for (const file of srcFiles) {
    const fullPath = path.join(webDir, 'src', file);
    if (fs.statSync(fullPath).isFile()) {
      const content = fs.readFileSync(fullPath, 'utf8');
      assert.ok(
        !content.includes(asteriskChar),
        `Unicode asterisk ${asteriskChar} found in web/src/${file}`
      );
    }
  }
});

// ----------------------------------------------------------------------
// 6. ADVERSARIAL TEST: Integration & Link Verification
// ----------------------------------------------------------------------
console.log('\n--- 6. Integration & HTML Link Verification ---');

runCheck('index.html: Links to /favicon.svg with rel="icon" and type="image/svg+xml"', () => {
  const indexHtmlPath = path.join(webDir, 'index.html');
  const content = fs.readFileSync(indexHtmlPath, 'utf8');
  assert.match(
    content,
    /<link\s+rel="icon"\s+type="image\/svg\+xml"\s+href="\/favicon\.svg"\s*\/>/,
    'index.html must have valid favicon link'
  );
});

runCheck('main.tsx: Header button.brand correctly embeds CivicLogo and retains navigation', () => {
  const mainTsxPath = path.join(webDir, 'src', 'main.tsx');
  const content = fs.readFileSync(mainTsxPath, 'utf8');
  
  // Must import CivicLogo
  assert.match(content, /import\s*\{[^}]*CivicLogo[^}]*\}\s*from\s*'\.\/CivicLogo';/);
  
  // Brand button structure
  assert.match(
    content,
    /<button className="brand" onClick=\{[^}]*navigate\('explore'\)[^}]*\} aria-label="Brasil de Todos"><CivicLogo size=\{36\} className="civic-brand-logo" \/><span>Brasil<span className="brand-sub">de Todos<\/span><\/span><\/button>/,
    'Brand button must embed CivicLogo and preserve brand text and navigation'
  );
});

// ----------------------------------------------------------------------
// 7. ADVERSARIAL TEST: Production Build Output Verification
// ----------------------------------------------------------------------
console.log('\n--- 7. Production Build Output Verification ---');

const distDir = path.join(webDir, 'dist');
runCheck('dist/: Build output contains dist/favicon.svg and dist/index.html', () => {
  const distFavicon = path.join(distDir, 'favicon.svg');
  const distIndex = path.join(distDir, 'index.html');
  assert.ok(fs.existsSync(distFavicon), 'dist/favicon.svg must exist');
  assert.ok(fs.existsSync(distIndex), 'dist/index.html must exist');

  // Verify dist/favicon.svg matches public/favicon.svg
  const publicContent = fs.readFileSync(faviconPath, 'utf8');
  const distContent = fs.readFileSync(distFavicon, 'utf8');
  assert.equal(distContent, publicContent, 'dist/favicon.svg must match web/public/favicon.svg');

  // Verify dist/index.html contains favicon link
  const distHtml = fs.readFileSync(distIndex, 'utf8');
  assert.match(distHtml, /href="\/favicon\.svg"/, 'dist/index.html must link to /favicon.svg');
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
