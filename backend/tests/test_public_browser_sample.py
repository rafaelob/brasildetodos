"""Behavioral tests for deterministic selections; production catalog is not seeded."""
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import pytest
from sqlalchemy import select,func
from bdt.domain import Source,PlaceInput,now
from bdt.storage import Database,Municipality,Place,Change,upsert_place

spec=spec_from_file_location('public_browser',Path(__file__).resolve().parents[2]/'ops/browser_public_catalog.py')
module=module_from_spec(spec);spec.loader.exec_module(module)

@pytest.fixture
def db(tmp_path):
    database=Database('sqlite:///'+str(tmp_path/'test.db'));database.initialize()
    source=Source(dataset='synthetic-only',url='https://example.org/test',record_id='unit',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
    with database.session() as s:
        s.add(Municipality(id='1234567',name='Synthetic city',state='BA',source=source.model_dump()));s.flush()
        for identity,geo,eligible in [('test:a',False,True),('test:b',False,True),('test:c',True,True),('test:d',True,False)]:
            upsert_place(s,PlaceInput(id=identity,name='Synthetic '+identity,kind='school',municipality_id='1234567',state='BA',catalogue_eligible=eligible,latitude=-12.0 if geo else None,longitude=-45.0 if geo else None,geo_source='test' if geo else None,source=source))
    try:yield database
    finally:database.engine.dispose()


def test_selection_is_bounded_deterministic_and_keeps_absent_geometry(db):
    selected=module.choose_samples(db,'synthetic-only')
    assert selected['records']==3
    assert [x['id'] for x in selected['samples']]==['test:a','test:c']
    assert selected['samples'][0]['latitude'] is None
    assert selected==module.choose_samples(db,'synthetic-only')
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(Place))==4
        assert session.scalar(select(func.count()).select_from(Change))==4


def test_empty_selection_is_not_replaced_by_another_dataset(db):
    with pytest.raises(ValueError,match='dataset_is_empty'):module.choose_samples(db,'not-loaded')


@pytest.mark.parametrize('dataset',['','x'*101,'some dataset','a/../b',None,17])
def test_invalid_dataset_is_rejected(db,dataset):
    with pytest.raises(ValueError,match='dataset_not_selected'):module.choose_samples(db,dataset)


def test_geometry_only_selection_does_not_invent_missing_example(db):
    with db.session() as session:
        for row in session.scalars(select(Place).where(Place.latitude.is_(None))):row.catalogue_eligible=False
    selected=module.choose_samples(db,'synthetic-only')
    assert selected['records']==1 and len(selected['samples'])==1
    assert selected['samples'][0]['latitude'] is not None


def test_snapshot_is_pinned_and_original_changes_do_not_change_copy(db,tmp_path):
    from bdt.catalog_release import export_catalog,verify_catalog
    folder=tmp_path/'export';export_catalog(db,folder)
    expected=module.file_sha(folder/'manifest.json')
    copy=module.freeze_catalog(folder,expected,tmp_path/'frozen')
    before=(copy/'places.jsonl').read_bytes()
    (folder/'places.jsonl').write_text('modified later')
    assert (copy/'places.jsonl').read_bytes()==before
    assert verify_catalog(copy)['files']['places.jsonl']['records']==4


def test_snapshot_does_not_copy_extra_private_files(db,tmp_path):
    from bdt.catalog_release import export_catalog
    folder=tmp_path/'export';export_catalog(db,folder)
    (folder/'private.txt').write_text('SYNTHETIC PRIVATE FILE MUST NOT BE COPIED')
    copy=module.freeze_catalog(folder,module.file_sha(folder/'manifest.json'),tmp_path/'frozen')
    assert not (copy/'private.txt').exists()


@pytest.mark.parametrize('mutate',['manifest','places','symlink'])
def test_snapshot_failure_discards_partial_copy(db,tmp_path,mutate):
    from bdt.catalog_release import export_catalog
    folder=tmp_path/'export';export_catalog(db,folder)
    expected=module.file_sha(folder/'manifest.json')
    if mutate=='manifest':(folder/'manifest.json').write_text('{}')
    elif mutate=='places':(folder/'places.jsonl').write_text('invalid')
    else:
        original=folder/'places.jsonl';raw=original.read_bytes();original.unlink()
        target=tmp_path/'outside';target.write_bytes(raw);original.symlink_to(target)
    with pytest.raises((ValueError,OSError)):module.freeze_catalog(folder,expected,tmp_path/'frozen')
    assert not (tmp_path/'frozen').exists()


def test_snapshot_refuses_existing_output(db,tmp_path):
    target=tmp_path/'frozen';target.mkdir();(target/'keep').write_text('preserve')
    with pytest.raises(FileExistsError):module.freeze_catalog(tmp_path,'0'*64,target)
    assert (target/'keep').read_text()=='preserve'
