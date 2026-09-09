import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';

const styleCssPath = new URL('../src/style.css', import.meta.url);
const workbenchCssPath = new URL('../src/workbench.css', import.meta.url);

function mediaBlocks(css, maxWidth) {
  const re = new RegExp(`@media\\s*\\(\\s*max-width:\\s*${maxWidth}\\s*\\)\\s*\\{`, 'g');
  const blocks = [];
  let match;
  while ((match = re.exec(css))) {
    const open = match.index + match[0].length - 1;
    let depth = 0;
    for (let i = open; i < css.length; i++) {
      if (css[i] === '{') depth += 1;
      else if (css[i] === '}') {
        depth -= 1;
        if (depth === 0) {
          blocks.push(css.slice(open + 1, i));
          break;
        }
      }
    }
  }
  return blocks;
}

function ruleBodies(block, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`(^|[\\s,}])${escaped}\\s*\\{([^}]*)\\}`, 'g');
  const bodies = [];
  let match;
  while ((match = re.exec(block))) bodies.push(match[2]);
  return bodies;
}

function declared(bodies, property) {
  const re = new RegExp(`(?:^|;)\\s*${property}\\s*:\\s*([^;}]+)`, 'gi');
  const values = [];
  for (const body of bodies) {
    re.lastIndex = 0;
    let match;
    while ((match = re.exec(body))) values.push(match[1].trim().replace(/;$/, ''));
  }
  return values;
}

test('style.css 1024px .header-right wraps; nowrap does not win', () => {
  assert.ok(existsSync(styleCssPath), 'style.css must exist');
  const styleCss = readFileSync(styleCssPath, 'utf8');
  const blocks = mediaBlocks(styleCss, '1024px');
  assert.ok(blocks.length > 0, 'Must have @media (max-width: 1024px)');

  const wrapValues = [];
  for (const block of blocks) {
    wrapValues.push(...declared(ruleBodies(block, '.header-right'), 'flex-wrap'));
  }
  assert.ok(wrapValues.length > 0, '1024px .header-right must declare flex-wrap');
  assert.equal(wrapValues.at(-1), 'wrap', '1024px .header-right flex-wrap must win as wrap');
  assert.ok(
    wrapValues.every((value) => value !== 'nowrap'),
    '1024px .header-right must not declare flex-wrap: nowrap',
  );

  assert.doesNotMatch(
    styleCss,
    /\.header-right\s*\{[^}]*flex-wrap:\s*nowrap/,
    'style.css must not set .header-right { flex-wrap: nowrap }',
  );
});

test('style.css 640px .header-right does not reintroduce nowrap', () => {
  const styleCss = readFileSync(styleCssPath, 'utf8');
  const blocks = mediaBlocks(styleCss, '640px');
  assert.ok(blocks.length > 0, 'Must have @media (max-width: 640px)');

  const wrapValues = [];
  for (const block of blocks) {
    wrapValues.push(...declared(ruleBodies(block, '.header-right'), 'flex-wrap'));
  }
  assert.ok(
    wrapValues.every((value) => value !== 'nowrap'),
    '640px .header-right must not declare flex-wrap: nowrap',
  );
  if (wrapValues.length > 0) {
    assert.equal(wrapValues.at(-1), 'wrap', '640px .header-right flex-wrap must win as wrap');
  }
});

test('workbench.css keeps .header-right flex-wrap: wrap', () => {
  assert.ok(existsSync(workbenchCssPath), 'workbench.css must exist');
  const workbenchCss = readFileSync(workbenchCssPath, 'utf8');
  const values = declared(ruleBodies(workbenchCss, '.header-right'), 'flex-wrap');
  assert.ok(values.includes('wrap'), 'workbench.css .header-right must keep flex-wrap: wrap');
  assert.ok(
    values.every((value) => value !== 'nowrap'),
    'workbench.css .header-right must not set nowrap',
  );
});

test('nav stays horizontally scrollable; 44px header-right targets remain', () => {
  const styleCss = readFileSync(styleCssPath, 'utf8');
  const mobile = mediaBlocks(styleCss, '1024px').join('\n');
  const compact = mediaBlocks(styleCss, '640px').join('\n');

  const navWrap = declared(ruleBodies(mobile, '.header nav'), 'flex-wrap');
  const navOverflow = declared(ruleBodies(mobile, '.header nav'), 'overflow-x');
  assert.ok(navWrap.includes('nowrap'), '.header nav must keep flex-wrap: nowrap');
  assert.ok(navOverflow.includes('auto'), '.header nav must keep overflow-x: auto');

  const selectMin = declared(ruleBodies(compact, '.header-right select'), 'min-height');
  const buttonMin = declared(ruleBodies(compact, '.header-right button'), 'min-height');
  assert.ok(selectMin.includes('44px'), '.header-right select must keep min-height: 44px');
  assert.ok(buttonMin.includes('44px'), '.header-right button must keep min-height: 44px');
});
