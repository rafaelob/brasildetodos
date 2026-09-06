"""No network calls: prove verified installation fails closed and uses hashes."""
import importlib
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installer(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'ops'))
    return importlib.import_module('install_locked')


@pytest.fixture
def target(installer, tmp_path, monkeypatch):
    manifest = {'python': '3.14.7', 'system': 'Linux', 'architecture': 'x86_64',
                'lock_sha256': 'a' * 64}
    monkeypatch.setattr(installer, 'verify', lambda _: manifest)
    monkeypatch.setattr(installer.platform, 'python_version', lambda: '3.14.7')
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(installer.platform, 'machine', lambda: 'x86_64')
    p = tmp_path / installer.LOCK
    p.parent.mkdir(parents=True)
    p.write_text('synthetic==1.0 \\\n --hash=sha256:' + 'a' * 64 + '\n')
    monkeypatch.setattr(installer, 'version', lambda _: '1.0')
    return tmp_path


@pytest.mark.parametrize('editable', [True, False])
def test_uses_hashed_distributions_and_no_secondary_resolution(installer, target, monkeypatch, editable):
    called = []
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: called.append((a, k)))
    report = installer.install(target, editable=editable)
    assert len(called) == 3
    assert called[0][0][0][4:6] == ['--require-hashes', '--only-binary=:all:']
    assert '--no-deps' in called[1][0][0] and '--no-build-isolation' in called[1][0][0]
    assert ('-e' in called[1][0][0]) == editable
    assert called[2][0][0][-1] == 'check'
    assert all(k['check'] is True and k['cwd'] == target for _, k in called)
    assert report['hash_checked'] and not report['resolver_fallback']


@pytest.mark.parametrize('property,value', [('python_version','3.13.5'),('system','Windows'),('machine','aarch64')])
def test_wrong_platform_does_not_run_pip(installer, target, monkeypatch, property, value):
    monkeypatch.setattr(installer.platform, property, lambda: value)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: pytest.fail('pip should not execute'))
    with pytest.raises(ValueError, match='runtime_or_platform'):
        installer.install(target)


def test_invalid_manifest_does_not_run_pip(installer, target, monkeypatch):
    def reject(_):
        raise ValueError('python_lock_manifest_mismatch')
    monkeypatch.setattr(installer, 'verify', reject)
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: pytest.fail('pip should not execute'))
    with pytest.raises(ValueError, match='manifest_mismatch'):
        installer.install(target)


@pytest.mark.parametrize('failed_command', [1, 2, 3])
def test_pip_failure_is_not_retried_without_hashes(installer, target, monkeypatch, failed_command):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if len(calls) == failed_command:
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(installer.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(target)
    assert len(calls) == failed_command


def test_installed_drift_is_rejected(installer, target, monkeypatch):
    monkeypatch.setattr(installer.subprocess, 'run', lambda *a, **k: None)
    monkeypatch.setattr(installer, 'version', lambda _: '2.0')
    with pytest.raises(ValueError, match='installed_version_mismatch'):
        installer.install(target)


def test_ci_and_docker_no_longer_resolve_web_or_core_python(installer):
    ci = (ROOT / '.github/workflows/ci.yml').read_text()
    docker = (ROOT / 'Dockerfile').read_text()
    assert "if [ -f package-lock.json ]" not in ci + docker
    assert 'run: npm ci' in ci and 'RUN npm ci' in docker
    assert 'python ops/install_locked.py --editable' in ci
    assert 'python ops/install_locked.py' in docker
    assert "pip install -e '.[test]'" not in ci
