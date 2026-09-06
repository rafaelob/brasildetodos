"""Install the verified Linux Python dependencies without a resolver fallback.

Run in the chosen build/CI environment or a developer-created virtualenv.
The script checks the target runtime and manifest before invoking pip.
"""
from __future__ import annotations

import argparse
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

from python_lock_manifest import LOCK, ROOT, locked_versions, verify


def commands(root: Path, executable: str, editable: bool = False) -> list[list[str]]:
    return [
        [executable, '-m', 'pip', 'install', '--require-hashes', '--only-binary=:all:',
         '-r', str(root / LOCK)],
        [executable, '-m', 'pip', 'install', '--no-deps', '--no-build-isolation',
         *(['-e'] if editable else []), str(root)],
        [executable, '-m', 'pip', 'check'],
    ]


def install(root: Path = ROOT, *, editable: bool = False) -> dict:
    manifest = verify(root)
    if (platform.python_version() != manifest['python'] or platform.system() != 'Linux'
            or platform.machine() != manifest['architecture']):
        raise ValueError('lock_does_not_match_current_runtime_or_platform')
    for command in commands(root, sys.executable, editable):
        subprocess.run(command, check=True, cwd=root)
    packages = locked_versions((root / LOCK).read_text(encoding='utf-8'))
    for name, expected in packages.items():
        if version(name) != expected:
            raise ValueError(f'installed_version_mismatch:{name}')
    return {'status': 'passed', 'python': platform.python_version(), 'system': 'Linux',
            'architecture': platform.machine(), 'packages': len(packages),
            'lock_sha256': manifest['lock_sha256'], 'editable': editable,
            'hash_checked': True, 'resolver_fallback': False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editable', action='store_true')
    args = parser.parse_args(argv)
    print(json.dumps(install(editable=args.editable), indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
