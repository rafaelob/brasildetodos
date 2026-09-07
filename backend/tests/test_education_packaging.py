"""Keep the actual checked-in dependency receipt and certificate package aligned."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_repository_lock_matches_current_project_metadata():
    spec = spec_from_file_location('education_lock_check', ROOT / 'ops/python_lock_manifest.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    manifest = module.verify(ROOT)
    assert manifest['python'] == '3.14.7'
    assert manifest['hash_checked_installation_required'] is True


def test_reviewed_certificate_is_declared_as_package_data():
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert 'certificates/*.pem' in project['tool']['setuptools']['package-data']['bdt']
    assert project['project']['requires-python'] == '==3.14.7'
    assert (ROOT / 'backend/bdt/certificates/rnp-icpedu-gr46-2025.pem').is_file()
