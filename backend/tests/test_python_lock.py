from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import json
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = spec_from_file_location('python_lock_manifest', ROOT / 'ops/python_lock_manifest.py')
module = module_from_spec(spec)
spec.loader.exec_module(module)
GOOD = 'example==1.2.3 \\\n    --hash=sha256:' + 'a' * 64 + '\n'


def test_hashed_pin_is_preserved():
    assert module.locked_versions('# generated\n' + GOOD) == {'example': '1.2.3'}


@pytest.mark.parametrize('text', ['', 'example>=1.2.3', 'example==1.2.3', '-r other.txt',
    'example @ https://example.org/x.whl', '--index-url https://example.org', GOOD+GOOD,
    'example==1.2.3 \\', GOOD.replace('sha256:', 'md5:'), GOOD.replace('a'*64, 'x'*64)])
def test_unverifiable_lock_rejected(text):
    with pytest.raises(ValueError):
        module.locked_versions(text)


def test_pin_normalization_and_multiple_hashes():
    text = 'Example_Pkg==1.2.3 \\\n    --hash=sha256:'+'a'*64+' \\\n    --hash=sha256:'+'b'*64+'\n'
    assert module.locked_versions(text) == {'example-pkg': '1.2.3'}


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / 'requirements').mkdir()
    (tmp_path / 'pyproject.toml').write_text('synthetic manifest')
    (tmp_path / module.LOCK).write_text(GOOD)
    monkeypatch.setattr(module, 'version', lambda _: '1.2.3')
    module.record(tmp_path, check_environment=False)
    return tmp_path


def test_manifest_roundtrip(root):
    assert module.verify(root)['packages'] == 1


@pytest.mark.parametrize('path', ['pyproject.toml', str(module.LOCK)])
def test_changed_input_or_lock_rejected(root, path):
    p = root / path
    p.write_text(p.read_text() + '\n# changed\n')
    with pytest.raises(ValueError, match='manifest_mismatch'):
        module.verify(root)


def test_manifest_count_mismatch(root):
    p = root / module.MANIFEST
    data = json.loads(p.read_text()); data['packages'] = 9
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='count_mismatch'):
        module.verify(root)


def test_wrong_runtime_cannot_record(root, monkeypatch):
    monkeypatch.setattr(module.platform, 'python_version', lambda: '3.13.5')
    with pytest.raises(ValueError, match='3_14_7'):
        module.record(root)


def test_installed_version_mismatch(root, monkeypatch):
    monkeypatch.setattr(module, 'version', lambda _: '1.2.4')
    with pytest.raises(ValueError, match='installed_version_mismatch'):
        module.record(root, check_environment=False)
