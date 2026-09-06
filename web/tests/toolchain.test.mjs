import {test} from 'node:test';
import assert from 'node:assert/strict';
import {assertNodeVersion} from '../../ops/check-node.mjs';
test('exact requested Node version is accepted', () => assert.equal(assertNodeVersion('24.20.0'), '24.20.0'));
for (const version of ['22.16.0','24.19.0','24.20.1','24','24.20.0-rc1']) {
  test(`rejects runtime drift ${version}`, () => assert.throws(() => assertNodeVersion(version), /24\.20\.0 required/));
}
