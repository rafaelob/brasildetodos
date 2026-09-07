import hashlib
import importlib
from pathlib import Path
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'ops'));return importlib.import_module('unpack_reviewed_resources')

@pytest.fixture
def archive(tmp_path):
    p=tmp_path/'artifact.zip'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('report.json',b'{"synthetic":true}');z.writestr('resources.jsonl',b'{}\n');z.writestr('artifact-check.json',b'{}')
    return p,hashlib.sha256(p.read_bytes()).hexdigest()


def test_exact_files_preserved_before_separate_semantic_validation(module,archive,tmp_path):
    p,digest=archive;target=tmp_path/'out';result=module.unpack(p,target,digest)
    assert result['status']=='passed' and result['semantic_validation_required']
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():assert (target/name).read_bytes()==z.read(name)
    with pytest.raises(FileExistsError):module.unpack(p,target,digest)


def test_wrong_archive_pin_does_not_write(module,archive,tmp_path):
    with pytest.raises(ValueError):module.unpack(archive[0],tmp_path/'out','a'*64)
    assert not (tmp_path/'out').exists()

@pytest.mark.parametrize('variant',['extra','duplicate','traversal','symlink'])
def test_invalid_members_refused_even_with_matching_hash(module,archive,tmp_path,variant):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(archive[0]) as src,zipfile.ZipFile(p,'w') as z:
        for n in src.namelist():
            if variant=='symlink' and n=='resources.jsonl':
                i=zipfile.ZipInfo(n);i.external_attr=0o120777<<16;z.writestr(i,b'/etc/passwd')
            else:z.writestr(n,src.read(n))
        if variant=='extra':z.writestr('private.db',b'private')
        if variant=='traversal':z.writestr('../outside',b'bad')
        if variant=='duplicate':
            with pytest.warns(UserWarning):z.writestr('report.json',b'{}')
    with pytest.raises(ValueError):module.unpack(p,tmp_path/'out',hashlib.sha256(p.read_bytes()).hexdigest())
    assert not (tmp_path/'out').exists() and not (tmp_path/'outside').exists()


def test_expansion_budget(module,archive,tmp_path,monkeypatch):
    monkeypatch.setattr(module,'MAX_EXPANDED',1)
    with pytest.raises(ValueError,match='budget'):module.unpack(archive[0],tmp_path/'out',archive[1])


def test_cli_emits_no_raw_content(module,archive,tmp_path,capsys):
    module.main([str(archive[0]),'--sha256',archive[1],'--destination',str(tmp_path/'out')])
    output=capsys.readouterr().out;assert 'synthetic' not in output and 'semantic_validation_required' in output
