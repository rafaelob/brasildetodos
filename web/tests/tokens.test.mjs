import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {additionalMessages, uiText} from '../src/ui-text.mjs';

const tokensPath = new URL('../src/tokens.css', import.meta.url);
const stylePath = new URL('../src/style.css', import.meta.url);
const indexPath = new URL('../index.html', import.meta.url);
const mainPath = new URL('../src/main.tsx', import.meta.url);

const CATALOG = {
  forest: '#12644e',
  ink: '#1a211c',
  sphere: '#0b3b75',
  honor: '#f2b705',
  fog: '#eef1ec',
  hairline: '#d5dbd4',
};
const LIME = '#9fe870';

function read(url) {
  assert.ok(existsSync(url), `${url.pathname} must exist`);
  return readFileSync(url, 'utf8');
}

function ruleBody(css, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(^|[\\s,}])${escaped}\\s*\\{([^}]*)\\}`, 'm');
  const match = css.match(re);
  return match ? match[2] : '';
}

function declarations(body, property) {
  const re = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;}]+)`, 'gi');
  const values = [];
  let match;
  while ((match = re.exec(body))) values.push(match[1].trim());
  return values;
}

function textColorDeclarations(css) {
  const values = [];
  const re = /(?:^|[{;])\s*(?<![-a-z])color\s*:\s*([^;}{]+)/gi;
  let match;
  while ((match = re.exec(css))) values.push(match[1].trim());
  return values;
}

test('tokens.css declares the fintech-trust forest catalog', () => {
  const tokens = read(tokensPath);
  assert.match(tokens, /--color-forest:\s*#12644e/);
  assert.match(tokens, /--color-ink:\s*#1a211c/);
  assert.match(tokens, /--color-sphere:\s*#0b3b75/);
  assert.match(tokens, /--color-honor:\s*#f2b705/);
  assert.match(tokens, /--color-fog:\s*#eef1ec/);
  assert.match(tokens, /--color-hairline:\s*#d5dbd4/);
  for (const hex of Object.values(CATALOG)) {
    assert.ok(tokens.includes(hex), `tokens.css must contain ${hex}`);
  }
  assert.equal(tokens.toLowerCase().includes(LIME), false, 'catalog must not include lime #9fe870');
  assert.match(tokens, /--radius-cta:\s*4px/);
  assert.match(tokens, /--focus-width:\s*2px/);
  assert.match(tokens, /--font-sans:[\s\S]*Inter/);
  assert.match(tokens, /--font-serif:[\s\S]*Source Serif 4/);
  assert.match(tokens, /--font-mono:[\s\S]*IBM Plex Mono/);
});

test('style.css imports tokens, maps forest, and keeps reduced-motion', () => {
  const style = read(stylePath);
  assert.match(style, /@import\s+['"]\.\/tokens\.css['"]/);
  assert.match(style, /--green:\s*var\(--color-forest\)/);
  assert.match(style, /font-family:\s*var\(--font-sans\)/);
  assert.match(style, /@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)[\s\S]*animation:\s*none\s*!important/);
  assert.equal(style.toLowerCase().includes(LIME), false, 'style.css must not introduce lime #9fe870');
});

test('primary CTA uses forest at 4px radius; buttons keep 44px min-height', () => {
  const style = read(stylePath);
  const primary = ruleBody(style, 'button.primary');
  assert.ok(primary, 'button.primary rule must exist');
  const background = declarations(primary, 'background');
  const radius = declarations(primary, 'border-radius');
  const color = declarations(primary, 'color');
  assert.ok(background.some((value) => value.includes('var(--color-forest)')), 'CTA background is forest');
  assert.ok(radius.some((value) => value === 'var(--radius-cta)' || value === '4px'), 'CTA radius is 4px');
  assert.ok(color.every((value) => value === '#fff' || value === '#ffffff' || value === 'white'), 'CTA text is not honor');
  const parsedRadius = radius[0] === 'var(--radius-cta)' ? 4 : Number.parseFloat(radius[0]);
  assert.ok(parsedRadius <= 6, `CTA radius ${parsedRadius}px must be ≤6px`);

  const button = ruleBody(style, 'button');
  const minHeight = declarations(button, 'min-height');
  assert.ok(minHeight.includes('44px'), 'buttons keep min-height 44px');
});

test('focus ring is 2px forest', () => {
  const style = read(stylePath);
  assert.match(
    style,
    /outline:\s*(?:2px|var\(--focus-width\))\s+solid\s+var\(--color-forest\)/,
    'focus-visible outline must be 2px forest'
  );
});

test('honor is never a text color on body or buttons', () => {
  const style = read(stylePath);
  const tokens = read(tokensPath);
  const forbidden = new Set(['var(--color-honor)', CATALOG.honor, CATALOG.honor.toUpperCase()]);
  for (const css of [style, tokens]) {
    for (const value of textColorDeclarations(css)) {
      assert.equal(forbidden.has(value), false, `text color must not be honor (${value})`);
    }
  }
  const body = ruleBody(style, 'body');
  const button = ruleBody(style, 'button');
  const primary = ruleBody(style, 'button.primary');
  for (const [name, bodyText] of [['body', body], ['button', button], ['button.primary', primary]]) {
    for (const value of declarations(bodyText, 'color')) {
      assert.equal(forbidden.has(value), false, `${name} color must not be honor (${value})`);
      assert.doesNotMatch(value, /--color-honor|#f2b705/i);
    }
  }
});

test('index.html loads Inter, Source Serif 4 and IBM Plex Mono', () => {
  const html = read(indexPath);
  assert.match(html, /fonts\.googleapis\.com/);
  assert.match(html, /family=Inter/);
  assert.match(html, /family=Source\+Serif\+4/);
  assert.match(html, /family=IBM\+Plex\+Mono/);
  assert.match(
    html,
    /<link\s+rel="icon"\s+type="image\/svg\+xml"\s+href="\/favicon\.svg"\s*\/>/
  );
});

test('skipToContent exists in additionalMessages for pt-BR, en and es', () => {
  for (const locale of ['pt-BR', 'en', 'es']) {
    const copy = additionalMessages[locale].skipToContent;
    assert.equal(typeof copy, 'string');
    assert.ok(copy.trim().length > 1, `${locale}.skipToContent must be non-empty`);
    assert.equal(uiText(locale, 'skipToContent'), copy);
    assert.notEqual(uiText(locale, 'skipToContent'), uiText(locale, 'explore'));
  }
  assert.match(additionalMessages['pt-BR'].skipToContent, /conteúdo/i);
  assert.match(additionalMessages.en.skipToContent, /content/i);
  assert.match(additionalMessages.es.skipToContent, /contenido/i);
});

test('main.tsx skip link uses skipToContent', () => {
  const main = read(mainPath);
  assert.match(main, /<a className="skip" href="#main">\{t\('skipToContent'\)\}<\/a>/);
  assert.equal(/<a className="skip" href="#main">\{t\('explore'\)\}<\/a>/.test(main), false);
  assert.match(main, /<main id="main">/);
});
