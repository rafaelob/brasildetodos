"""Whole public bundle with actual catalog, transaction and API, synthetic records."""
import hashlib
import importlib
from pathlib import Path
import zipfile
import pytest
from bdt.catalog_release import export_catalog
from bdt.storage import User
from test_resource_release import records,package

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def bundler(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'ops'))
    return importlib.import_module('public_data_bundle')

@pytest.fixture
def bundle_input(database,stored,tmp_path):
    with database.session() as session:
        session.add(User(username='private_not_in_bundle',password_hash='never-a-password',role='citizen'))
    catalog=tmp_path/'catalog';export_catalog(database,catalog,revision='a'*40)
    source=tmp_path/'resources';selected=package(source,records())
    selected['catalog_sha256']=hashlib.sha256((catalog/'manifest.json').read_bytes()).hexdigest()
    return catalog,source,selected


def test_installable_inputs_reconciled_and_only_public_files(bundler,bundle_input,tmp_path):
    catalog,source,selected=bundle_input;out=tmp_path/'download.zip'
    result=bundler.build(catalog,source,out,**selected,revision='a'*40)
    assert result['counts']['places']==1 and result['counts']['resources']==2
    assert result['counts']['users']==result['counts']['observations']==0
    assert not result['fresh_collection'] and not result['public_deployment']
    assert bundler.verify(out,result['archive_sha256'])==result
    with zipfile.ZipFile(out) as z:
        assert set(z.namelist())==set(bundler.MEMBERS)|{'bundle.json'}
        assert all(b'private_not_in_bundle' not in z.read(n) for n in z.namelist())
        assert b'100.0001' in z.read('resources/resources.jsonl')
        assert b'not_payment' in z.read('resources/resources.jsonl')
    before=out.read_bytes()
    with pytest.raises(FileExistsError):bundler.build(catalog,source,out,**selected,revision='a'*40)
    assert out.read_bytes()==before

@pytest.mark.parametrize('pin',['catalog_sha256','report_sha256','resources_sha256'])
def test_wrong_input_pin_cannot_publish_partial_bundle(bundler,bundle_input,tmp_path,pin):
    catalog,source,selected=bundle_input;selected[pin]='b'*64
    with pytest.raises(ValueError):bundler.build(catalog,source,tmp_path/'out.zip',**selected,revision='a'*40)
    assert not (tmp_path/'out.zip').exists()


def test_extra_unreviewed_source_files_are_not_included(bundler,bundle_input,tmp_path):
    catalog,source,selected=bundle_input
    (catalog/'database.db').write_text('private');(source/'raw-private.json').write_text('private')
    result=bundler.build(catalog,source,tmp_path/'out.zip',**selected,revision='a'*40)
    assert result['status']=='passed'
    with zipfile.ZipFile(tmp_path/'out.zip') as z:
        assert 'database.db' not in str(z.namelist()) and 'raw-private' not in str(z.namelist())

@pytest.mark.parametrize('mutation',['extra','duplicate','traversal','wrong-bytes','symlink'])
def test_mutated_bundle_refused_even_with_recomputed_outer_hash(bundler,bundle_input,tmp_path,mutation):
    catalog,source,selected=bundle_input;out=tmp_path/'out.zip';bundler.build(catalog,source,out,**selected,revision='a'*40)
    changed=tmp_path/'changed.zip'
    with zipfile.ZipFile(out) as original,zipfile.ZipFile(changed,'w') as target:
        for n in original.namelist():
            body=original.read(n)
            if mutation=='wrong-bytes' and n=='resources/resources.jsonl':body+=b'\n'
            if mutation=='symlink' and n=='catalog/places.jsonl':
                info=zipfile.ZipInfo(n);info.create_system=3;info.external_attr=0o120777<<16;target.writestr(info,'/etc/passwd')
            else:target.writestr(n,body)
        if mutation=='extra':target.writestr('private.db',b'not-public')
        if mutation=='duplicate':
            with pytest.warns(UserWarning):target.writestr('acceptance.json',b'{}')
        if mutation=='traversal':target.writestr('../outside',b'not-allowed')
    with pytest.raises(ValueError):bundler.verify(changed,bundler.sha(changed))
    assert not (tmp_path/'outside').exists()


def test_external_bundle_hash_and_file_budget_are_enforced(bundler,tmp_path,monkeypatch):
    path=tmp_path/'not.zip';path.write_bytes(b'test')
    with pytest.raises(ValueError,match='hash'):bundler.verify(path,'a'*64)
    monkeypatch.setattr(bundler,'MAX_BYTES',2)
    with pytest.raises(ValueError,match='budget'):bundler.verify(path,bundler.sha(path))


def test_archive_revision_and_hash_formats_are_explicit(bundler,bundle_input,tmp_path):
    catalog,source,selected=bundle_input
    with pytest.raises(ValueError,match='revision'):bundler.build(catalog,source,tmp_path/'out.zip',**selected,revision='main')
    with pytest.raises(ValueError,match='hashes'):bundler.pins('https://example.org','a'*64,'b'*64)
