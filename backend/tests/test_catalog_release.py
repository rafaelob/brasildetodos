"""Public release integrity, rollback and privacy tests with synthetic records only."""
import json
import hashlib
import os
import sys
import pytest
from sqlalchemy import func, select
from bdt.catalog_release import (EXCLUDED, FILES, TABLES, canonical, export_catalog, install_catalog,
    load_manifest, records, timestamp, validate_record, verify_catalog)
from bdt.domain import MoneyEvent, now, digest
from bdt.evidence import Resource, ResourceInput, initialize_extensions
from bdt.ingest import import_finance
from bdt.storage import (Change, Database, Finance, LoginSession, Municipality, Observation, Place,
                         RateBucket, User, upsert_place)


@pytest.fixture
def full(database, place, source):
    initialize_extensions(database)
    with database.session() as s:
        upsert_place(s, place)
        upsert_place(s, place.model_copy(update={'address': 'Rua Atualizada'}))
        s.add(User(id='private-user', username='DO_NOT_EXPORT_PRIVATE_USERNAME', password_hash='DO_NOT_EXPORT_PASSWORD'))
        s.flush()
        s.add(LoginSession(token_hash='DO_NOT_EXPORT_SESSION', user_id='private-user', expires_at=9000000000))
        s.add(RateBucket(id='DO_NOT_EXPORT_RATE', count=1, expires_at=9000000000))
        s.add(Observation(place_id=place.id, author_id='private-user', payload={'body':'DO_NOT_EXPORT_PERSONAL_REPORT'}))
        resource = ResourceInput(id='synthetic:contract', kind='contract', title='Synthetic public contract',
                                 municipality_id=place.municipality_id, source=source)
        payload = resource.model_dump(mode='json')
        s.add(Resource(id=resource.id, kind=resource.kind, municipality_id=resource.municipality_id,
                       title=resource.title, source=payload['source'], payload=payload))
    import_finance(database, [{'id':'test-payment','municipality_id':place.municipality_id,
        'instrument_id':'synthetic:contract', 'recipient':'Public test recipient', 'period':'2025',
        'cents':120000, 'phase':'paid', 'perspective':'federal', 'nature':'event'}], source)
    return database


def rewrite_release(folder, filename, change):
    path=folder/filename
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    change(rows)
    data=b''.join(canonical(row)+b'\n' for row in rows)
    path.write_bytes(data)
    manifest=json.loads((folder/'manifest.json').read_text())
    manifest['files'][filename]={'bytes':len(data),'records':len(rows),'sha256':hashlib.sha256(data).hexdigest()}
    (folder/'manifest.json').write_bytes(canonical(manifest))


def test_public_export_never_contains_private_tables(full,tmp_path):
    folder=tmp_path/'release'; manifest=export_catalog(full,folder,'a'*40)
    assert set(p.name for p in folder.iterdir())==set(FILES)|{'manifest.json'}
    combined=''.join(p.read_text() for p in folder.iterdir())
    assert 'DO_NOT_EXPORT' not in combined
    assert 'private-user' not in combined
    assert manifest['excluded']==EXCLUDED
    assert manifest['national_catalog_certified'] is False
    assert manifest['files']['places.jsonl']['records']==1
    assert manifest['files']['changes.jsonl']['records']==2
    assert verify_catalog(folder)==manifest
    assert manifest['partitions']==[{'dataset':'synthetic','state':'BA','eligible':True,'with_geometry':False,'records':1}]


def test_install_roundtrip_preserves_public_state_not_accounts(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    target=tmp_path/'installed.db'; result=install_catalog(folder,target)
    assert result['status']=='installed_new_database'
    if os.name != 'nt':
        assert os.stat(target).st_mode & 0o777 == 0o600
    installed=Database('sqlite:///'+str(target))
    with installed.session() as s:
        assert s.scalar(select(func.count()).select_from(Place))==1
        assert s.scalar(select(func.count()).select_from(Change))==2
        assert s.scalar(select(func.count()).select_from(Resource))==1
        assert s.scalar(select(func.count()).select_from(Finance))==1
        assert s.scalar(select(func.count()).select_from(User))==0
        assert s.scalar(select(func.count()).select_from(Observation))==0
        assert s.get(Place,'test:school').payload['address']=='Rua Atualizada'
    again=tmp_path/'roundtrip'; export_catalog(installed,again)
    for name in FILES:
        assert (again/name).read_bytes()==(folder/name).read_bytes()
    installed.engine.dispose()


def test_empty_release_is_explicit_not_national(database,tmp_path):
    folder=tmp_path/'release'; report=export_catalog(database,folder)
    assert report['files']['places.jsonl']['records']==0
    assert report['partitions']==[] and report['national_catalog_certified'] is False
    assert report['files']['resources.jsonl']['records']==0
    install_catalog(folder,tmp_path/'new.db')


@pytest.mark.parametrize('revision',['main','shortsha','a'*39,'x'*40])
def test_revision_is_content_address_not_moving_ref(database,tmp_path,revision):
    with pytest.raises(ValueError,match='invalid_revision'):
        export_catalog(database,tmp_path/'release',revision)


def test_existing_destination_never_overwritten(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    original=(folder/'manifest.json').read_bytes()
    with pytest.raises(FileExistsError):export_catalog(full,folder)
    assert (folder/'manifest.json').read_bytes()==original
    target=tmp_path/'active.db'; target.write_bytes(b'active-db-placeholder')
    with pytest.raises(FileExistsError):install_catalog(folder,target)
    assert target.read_bytes()==b'active-db-placeholder'


def test_detect_modified_bytes_before_atomic_install(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    path=folder/'places.jsonl'
    path.write_bytes(path.read_bytes().replace(b'Rua Atualizada',b'Rua adulterada'))
    with pytest.raises(ValueError):install_catalog(folder,tmp_path/'must-not-exist.db')
    assert not (tmp_path/'must-not-exist.db').exists()
    assert not list(tmp_path.glob('.bdt-install-*'))


@pytest.mark.parametrize('mutation',[
    lambda rows:rows[0].update(password_hash='must-be-refused'),
    lambda rows:rows[0].update(name='incorrect denormalized name'),
    lambda rows:rows[0].update(search_name='incorrect search index'),
    lambda rows:rows[0].update(fingerprint='b'*64),
    lambda rows:rows[0].update(updated_at='2025-01-01T00:00:00'),
])
def test_even_rehashed_payload_requires_schema_and_consistency(full,tmp_path,mutation):
    folder=tmp_path/'release'; export_catalog(full,folder)
    rewrite_release(folder,'places.jsonl',mutation)
    with pytest.raises(ValueError):verify_catalog(folder)


def test_foreign_key_failure_rolls_back_new_database(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    rewrite_release(folder,'municipalities.jsonl',lambda rows:rows.clear())
    with pytest.raises(Exception):install_catalog(folder,tmp_path/'invalid.db')
    assert not (tmp_path/'invalid.db').exists()


def test_municipal_state_consistency(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    rewrite_release(folder,'municipalities.jsonl',lambda rows:rows[0].update(state='SP'))
    with pytest.raises(ValueError,match='state_mismatch'):install_catalog(folder,tmp_path/'invalid.db')
    assert not (tmp_path/'invalid.db').exists()


@pytest.mark.parametrize('mutation',[
    lambda m:m.update(format='another-format'),
    lambda m:m.update(national_catalog_certified=True),
    lambda m:m['files'].update({'../../outside':m['files']['places.jsonl']}),
    lambda m:m['files']['places.jsonl'].update(bytes=True),
    lambda m:m['files']['places.jsonl'].update(records=-1),
    lambda m:m['files']['places.jsonl'].update(sha256='invalid'),
    lambda m:m['files']['places.jsonl'].update(arbitrary='field'),
    lambda m:m['files']['places.jsonl'].update(bytes=5*1024**3),
])
def test_manifest_is_untrusted(full,tmp_path,mutation):
    folder=tmp_path/'release'; export_catalog(full,folder)
    path=folder/'manifest.json'; manifest=json.loads(path.read_text()); mutation(manifest); path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError):verify_catalog(folder)


def test_record_counts_are_checked(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    path=folder/'manifest.json'; manifest=json.loads(path.read_text()); manifest['files']['places.jsonl']['records']=0; path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError,match='count_mismatch'):verify_catalog(folder)


def test_reject_symlinks(full,tmp_path):
    folder=tmp_path/'release'; export_catalog(full,folder)
    external=tmp_path/'external.jsonl'; path=folder/'places.jsonl'; path.rename(external); path.symlink_to(external)
    with pytest.raises(ValueError):verify_catalog(folder)
    linked=tmp_path/'linked'; linked.symlink_to(folder,target_is_directory=True)
    with pytest.raises(ValueError):verify_catalog(linked)


def test_financial_phase_is_not_merged(full,tmp_path,source):
    import_finance(full,[{'id':'different-stage','municipality_id':'1234567','instrument_id':'synthetic:contract',
        'recipient':'Public test recipient','period':'2025','cents':120000,'phase':'transferred',
        'perspective':'federal','nature':'event'}],source)
    folder=tmp_path/'release'; export_catalog(full,folder)
    entries=[json.loads(line) for line in (folder/'finance.jsonl').read_text().splitlines()]
    assert {r['payload']['phase'] for r in entries}=={'paid','transferred'}
    assert len(entries)==2


@pytest.mark.parametrize('name,mutation',[
    ('municipalities.jsonl',lambda r:r.update(id='123')),
    ('municipalities.jsonl',lambda r:r.update(name='')),
    ('municipalities.jsonl',lambda r:r.update(state='invalid')),
    ('resources.jsonl',lambda r:r.update(title='inconsistent')),
    ('resources.jsonl',lambda r:r.update(source={'invalid':True})),
    ('finance.jsonl',lambda r:r.update(cents=1)),
    ('changes.jsonl',lambda r:r.update(place_id='another:place')),
    ('changes.jsonl',lambda r:r.update(fields=[1])),
    ('changes.jsonl',lambda r:r.update(id='')),
])
def test_other_public_rows_require_consistent_schema(full,tmp_path,name,mutation):
    folder=tmp_path/'release'; export_catalog(full,folder)
    rewrite_release(folder,name,lambda rows:mutation(rows[0]))
    with pytest.raises(ValueError):verify_catalog(folder)


def test_invalid_source_data_cleans_staging(full,tmp_path):
    with full.session() as s:
        s.get(Place,'test:school').search_name='bad'
    with pytest.raises(ValueError):export_catalog(full,tmp_path/'release')
    assert not (tmp_path/'release').exists()
    assert not list(tmp_path.glob('.bdt-catalog-*'))


def test_cli_export_verify_install(full,tmp_path):
    from bdt.catalog_release import main
    import unittest.mock as mock
    folder=tmp_path/'release'
    for argv in (
        ['catalog','export','--database',str(full.engine.url),'--output',str(folder)],
        ['catalog','verify',str(folder)],
        ['catalog','install',str(folder),'--output',str(tmp_path/'cli.db')],
    ):
        with mock.patch.object(sys,'argv',argv):main()
    assert (tmp_path/'cli.db').is_file()


def test_refuses_uninitialized_database(tmp_path):
    db=Database('sqlite:///'+str(tmp_path/'empty.db'))
    with pytest.raises(ValueError,match='uninitialized'):
        export_catalog(db,tmp_path/'release')
    assert not (tmp_path/'release').exists()
    db.engine.dispose()


@pytest.mark.parametrize('value',[[], None, 1, 'bad'])
def test_manifest_shape_validation(full,tmp_path,value):
    folder=tmp_path/'release';export_catalog(full,folder)
    (folder/'manifest.json').write_text(json.dumps(value))
    with pytest.raises(ValueError):verify_catalog(folder)


def test_counts_cannot_be_inflated_in_manifest(full,tmp_path):
    folder=tmp_path/'release';export_catalog(full,folder)
    path=folder/'manifest.json';manifest=json.loads(path.read_text())
    manifest['partitions'][0]['records']=999999
    path.write_bytes(canonical(manifest))
    with pytest.raises(ValueError,match='partition_mismatch'):verify_catalog(folder)
    with pytest.raises(ValueError,match='partition_mismatch'):install_catalog(folder,tmp_path/'bad.db')
    assert not (tmp_path/'bad.db').exists()


def test_unsupported_database_version(full,tmp_path):
    from bdt.storage import SchemaVersion
    with full.session() as session:session.get(SchemaVersion,1).version=999
    with pytest.raises(ValueError,match='database_version'):export_catalog(full,tmp_path/'release')
