"""Record and verify a Linux CPython lock; never read environment credentials."""
from __future__ import annotations
import argparse
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re

ROOT = Path(__file__).resolve().parents[1]
LOCK = Path('requirements/linux-py314.lock')
MANIFEST = Path('requirements/linux-py314.json')


def fingerprint(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def locked_versions(text: str) -> dict[str, str]:
    """Accept pip-compile's pinned, hashed package blocks; reject URLs/includes."""
    if len(text) > 4 * 1024 * 1024:
        raise ValueError('lock_too_large')
    versions = {}
    block = ''
    for line in text.splitlines():
        part = line.strip()
        if not part or part.startswith('#'):
            continue
        continued = part.endswith('\\')
        block += ' ' + (part[:-1] if continued else part)
        if continued:
            continue
        match = re.fullmatch(r'\s*([a-zA-Z0-9][a-zA-Z0-9_.-]*)==([a-zA-Z0-9][a-zA-Z0-9_.+!-]*)\s+((?:--hash=sha256:[0-9a-f]{64}\s*)+)', block)
        if not match:
            raise ValueError('lock_requires_exact_pins_and_hashes')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in versions:
            raise ValueError('duplicate_lock_package')
        versions[name] = match[2]
        block = ''
    if block or not versions:
        raise ValueError('incomplete_or_empty_lock')
    return versions


def record(root: Path = ROOT, check_environment: bool = True) -> dict:
    if check_environment and (platform.python_version() != '3.14.7' or platform.system() != 'Linux'):
        raise ValueError('lock_requires_linux_python_3_14_7')
    packages = locked_versions((root / LOCK).read_text(encoding='utf-8'))
    for name, expected in packages.items():
        if version(name) != expected:
            raise ValueError(f'installed_version_mismatch:{name}')
    result = {'schema': 'bdt.python-lock.v1', 'python': '3.14.7', 'system': 'Linux',
              'architecture': platform.machine(), 'pyproject_sha256': fingerprint(root / 'pyproject.toml'),
              'lock_sha256': fingerprint(root / LOCK), 'packages': len(packages),
              'scope': 'runtime_test_postgres_and_build_dependencies',
              'installed_versions_verified': True, 'hash_checked_installation_required': True,
              'not_a_vulnerability_audit': True}
    (root / MANIFEST).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def verify(root: Path = ROOT) -> dict:
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    if (manifest.get('schema') != 'bdt.python-lock.v1' or manifest.get('python') != '3.14.7'
            or manifest.get('system') != 'Linux'
            or manifest.get('pyproject_sha256') != fingerprint(root / 'pyproject.toml')
            or manifest.get('lock_sha256') != fingerprint(root / LOCK)):
        raise ValueError('python_lock_manifest_mismatch')
    if manifest.get('packages') != len(locked_versions((root / LOCK).read_text(encoding='utf-8'))):
        raise ValueError('python_lock_count_mismatch')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('record', 'verify'))
    args = parser.parse_args()
    print(json.dumps(record() if args.command == 'record' else verify(), indent=2))


if __name__ == '__main__':
    main()
