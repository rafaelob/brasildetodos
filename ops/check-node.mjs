/** Exact frontend runtime. This checks the runtime, not just package metadata. */
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';
export const EXPECTED_NODE = '24.20.0';
export function assertNodeVersion(actual = process.versions.node) {
  if (actual !== EXPECTED_NODE) throw new Error(`Node.js ${EXPECTED_NODE} required; found ${actual}`);
  return actual;
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    assertNodeVersion();
    const packageFile = new URL('../web/package.json', import.meta.url);
    if (JSON.parse(readFileSync(packageFile, 'utf8')).engines.node !== EXPECTED_NODE) {
      throw new Error('package.json Node runtime differs from the project target');
    }
    console.log(JSON.stringify({node: process.versions.node, status: 'passed'}));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
