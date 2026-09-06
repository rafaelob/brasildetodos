"""Validate declared/actual runtimes without importing the application or secrets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tomllib

PYTHON = '3.14.7'
NODE = '24.20.0'
ROOT = Path(__file__).resolve().parents[1]


def configuration_errors(root: Path = ROOT) -> list[str]:
    """Return small diagnostics; never read .env, credentials or user data."""
    errors: list[str] = []
    for name, expected in (('.python-version', PYTHON), ('.nvmrc', NODE), ('.node-version', NODE)):
        if not (root / name).is_file() or (root / name).read_text().strip() != expected:
            errors.append(f'{name}: expected {expected}')
    try:
        config = tomllib.loads((root / 'pyproject.toml').read_text())
        if config['project']['requires-python'] != f'=={PYTHON}':
            errors.append('pyproject.toml: inconsistent requires-python')
        package = json.loads((root / 'web/package.json').read_text())
        if package['engines']['node'] != NODE:
            errors.append('web/package.json: inconsistent engines.node')
        if 'engine-strict=true' not in (root / 'web/.npmrc').read_text().splitlines():
            errors.append('web/.npmrc: engine-strict must be enabled')
        docker = (root / 'Dockerfile').read_text()
        images = re.findall(r'^FROM\s+(\S+)', docker, flags=re.M | re.I)
        if f'node:{NODE}-bookworm-slim' not in images or f'python:{PYTHON}-slim-bookworm' not in images:
            errors.append('Dockerfile: inconsistent build/application images')
        for image in images:
            if image.startswith(('python:', 'node:')) and image not in (
                f'node:{NODE}-bookworm-slim', f'python:{PYTHON}-slim-bookworm'):
                errors.append('Dockerfile: unpinned runtime image')
        for workflow in sorted((root / '.github/workflows').glob('*.yml')):
            text = workflow.read_text()
            # Check every setup block, not just one matching string per file.
            for block in re.split(r'(?m)^\s*- (?:name:|uses:)', text):
                if 'actions/setup-python@' in block:
                    if "python-version-file: '.python-version'" not in block or re.search(r'(?m)^\s*python-version:', block):
                        errors.append(f'{workflow.name}: Python setup must use .python-version')
                if 'actions/setup-node@' in block:
                    if "node-version-file: '.nvmrc'" not in block or re.search(r'(?m)^\s*node-version:', block):
                        errors.append(f'{workflow.name}: Node setup must use .nvmrc')
    except (OSError, ValueError, KeyError, TypeError):
        errors.append('toolchain configuration is missing or malformed')
    return errors


def runtime_errors(runtime: str, python_version: str | None = None, node_version: str | None = None) -> list[str]:
    errors: list[str] = []
    if runtime in ('python', 'all'):
        actual = python_version if python_version is not None else platform.python_version()
        if actual != PYTHON:
            errors.append(f'Python {PYTHON} required, found {actual}')
    if runtime in ('node', 'all'):
        if node_version is None:
            try:
                node_version = subprocess.run(['node', '--version'], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                errors.append('Node runtime unavailable')
        if node_version is not None and node_version.removeprefix('v') != NODE:
            errors.append(f'Node {NODE} required, found {node_version}')
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('config', 'python', 'node', 'all'), default='all')
    args = parser.parse_args(argv)
    errors = configuration_errors() + runtime_errors(args.runtime)
    print(json.dumps({'target': {'python': PYTHON, 'node': NODE},
                      'checked': args.runtime, 'status': 'failed' if errors else 'passed',
                      'errors': errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
