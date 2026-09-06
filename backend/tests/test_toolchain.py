"""Project/runtime consistency; unit tests may inspect the target from any host."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('toolchain', ROOT / 'ops/check_toolchain.py')
module = module_from_spec(spec)
spec.loader.exec_module(module)


def test_repository_configuration_is_consistent():
    assert module.configuration_errors(ROOT) == []


@pytest.mark.parametrize('runtime,python,node', [
    ('python', '3.14.7', None), ('node', None, 'v24.20.0'),
    ('all', '3.14.7', '24.20.0'), ('config', '3.13.5', '22.16.0')])
def test_expected_runtime(runtime, python, node):
    assert module.runtime_errors(runtime, python, node) == []


@pytest.mark.parametrize('python,node', [
    ('3.14.6', '24.20.0'), ('3.15.0', '24.20.0'),
    ('3.14.7', '24.20.1'), ('3.13.5', '22.16.0'),
    ('3.14.7rc1', '24.20.0')])
def test_wrong_runtime_fails_instead_of_falling_back(python, node):
    assert module.runtime_errors('all', python, node)


@pytest.fixture
def config_root(tmp_path):
    for name in ('.python-version', '.nvmrc', '.node-version', 'pyproject.toml',
                 'web/package.json', 'web/.npmrc', 'Dockerfile'):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, p)
    shutil.copytree(ROOT / '.github/workflows', tmp_path / '.github/workflows')
    return tmp_path


@pytest.mark.parametrize('filename,old,new', [
    ('.python-version', '3.14.7', '3.13'),
    ('.nvmrc', '24.20.0', '24'),
    ('.node-version', '24.20.0', '22'),
    ('pyproject.toml', '==3.14.7', '>=3.13'),
    ('web/package.json', '24.20.0', '>=22.12'),
    ('web/.npmrc', 'engine-strict=true', 'engine-strict=false'),
    ('Dockerfile', 'python:3.14.7', 'python:3.13'),
    ('.github/workflows/ci.yml', "python-version-file: '.python-version'", "python-version: '3.13'"),
    ('.github/workflows/ci.yml', "node-version-file: '.nvmrc'", "node-version: '24'"),
])
def test_configuration_drift_is_detected(config_root, filename, old, new):
    p = config_root / filename
    p.write_text(p.read_text().replace(old, new))
    assert module.configuration_errors(config_root)


def test_missing_file_reports_error(config_root):
    (config_root / 'web/package.json').unlink()
    assert module.configuration_errors(config_root)


def test_unavailable_node_reports_error(monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(module.subprocess, 'run', unavailable)
    assert module.runtime_errors('node') == ['Node runtime unavailable']


def test_cli_config_only_is_explicit(capsys):
    assert module.main(['--runtime', 'config']) == 0
    assert json.loads(capsys.readouterr().out)['checked'] == 'config'
