"""Small isolated fixtures; the operational command also runs on official releases."""
import json
import pytest
from bdt.catalog_acceptance import exercise_catalog, main
from bdt.catalog_release import export_catalog
from bdt.storage import upsert_place


def test_runtime_acceptance_counts_unlocated_and_located_records(database,place,tmp_path):
    with database.session() as session:
        upsert_place(session,place)
        upsert_place(session,place.model_copy(update={'id':'test:second','latitude':-12.9,
                     'longitude':-38.5,'geo_source':'synthetic'}))
    folder=tmp_path/'public';export_catalog(database,folder)
    result=exercise_catalog(folder)
    assert result['status']=='passed'
    assert result['records']==2 and result['geocoded']==1 and result['without_geometry']==1
    assert result['national_catalog_certified'] is False
    assert result['public_deployment'] is False
    assert len(result['checks'])==6
    assert result['saved_places']['sampled_records'] >= 1
    assert result['saved_places']['without_geometry_included'] == 1
    assert result['saved_places']['favorites_persisted'] is False
    assert result['saved_places']['new_remote_collection'] is False


def test_empty_release_is_tested_as_empty_not_national(database,tmp_path):
    folder=tmp_path/'public';export_catalog(database,folder)
    result=exercise_catalog(folder)
    assert result['records']==0 and result['map']['features']==0
    assert result['national_catalog_certified'] is False


def test_cli_preserves_previous_evidence(database,tmp_path,capsys):
    folder=tmp_path/'public';export_catalog(database,folder)
    output=tmp_path/'result.json'
    main([str(folder),'--output',str(output)])
    assert json.loads(output.read_text())['status']=='passed'
    old=output.read_bytes()
    with pytest.raises(SystemExit):main([str(folder),'--output',str(output)])
    assert output.read_bytes()==old


def test_tampered_package_fails_before_api(database,place,tmp_path):
    with database.session() as session:upsert_place(session,place)
    folder=tmp_path/'public';export_catalog(database,folder)
    with (folder/'places.jsonl').open('ab') as stream:stream.write(b'{}\n')
    with pytest.raises(ValueError):exercise_catalog(folder)
