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


def record(root: Path = ROOT, check_environment: bool = True, *, lock: Path = LOCK,
           manifest: Path = MANIFEST, system: str = 'Linux',
           architecture: str | None = None) -> dict:
    if check_environment and (platform.python_version() != '3.14.8' or platform.system() != system):
        raise ValueError(f'lock_requires_{system.lower()}_python_3_14_8')
    packages = locked_versions((root / lock).read_text(encoding='utf-8'))
    for name, expected in packages.items():
        if version(name) != expected:
            raise ValueError(f'installed_version_mismatch:{name}')
    result = {'schema': 'bdt.python-lock.v1', 'python': '3.14.8', 'system': system,
              'architecture': architecture or platform.machine(),
              'pyproject_sha256': fingerprint(root / 'pyproject.toml'),
              'lock_sha256': fingerprint(root / lock), 'packages': len(packages),
              'scope': 'runtime_test_postgres_and_build_dependencies',
              'installed_versions_verified': True, 'hash_checked_installation_required': True,
              'not_a_vulnerability_audit': True}
    (root / manifest).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def verify(root: Path = ROOT, *, lock: Path = LOCK, manifest: Path = MANIFEST,
           system: str = 'Linux') -> dict:
    data = json.loads((root / manifest).read_text(encoding='utf-8'))
    if (data.get('schema') != 'bdt.python-lock.v1' or data.get('python') != '3.14.8'
            or data.get('system') != system
            or data.get('pyproject_sha256') != fingerprint(root / 'pyproject.toml')
            or data.get('lock_sha256') != fingerprint(root / lock)):
        raise ValueError('python_lock_manifest_mismatch')
    if data.get('packages') != len(locked_versions((root / lock).read_text(encoding='utf-8'))):
        raise ValueError('python_lock_count_mismatch')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('record', 'verify'))
    parser.add_argument('--lock', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--system', default='Linux')
    parser.add_argument('--architecture')
    args = parser.parse_args()
    lock = args.lock or LOCK
    manifest = args.manifest or MANIFEST
    if args.command == 'record':
        result = record(lock=lock, manifest=manifest, system=args.system,
                        architecture=args.architecture)
    else:
        result = verify(lock=lock, manifest=manifest, system=args.system)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
