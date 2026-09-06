# SPDX-License-Identifier: AGPL-3.0-or-later
"""Public import diagnostics must not reveal queries, errors, identities or files."""
import json
from fastapi.testclient import TestClient
from sqlalchemy import select
from bdt.api import create_app
from bdt.storage import Ingestion
from test_resource_sync import contract, current, save_collection
from bdt.resource_sync import import_resources


def coverage(database):
    with TestClient(create_app(str(database.engine.url), testing=True)) as client:
        response = client.get('/api/resource-coverage')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        return response.json()


def test_empty_installation_does_not_claim_national_coverage(database):
    result = coverage(database)
    assert result['national_resources_certified'] is False
    assert result['scope'] == 'installation_import_history_not_upstream_service_monitor'
    assert len(result['profiles']) == 3
    assert all(row['loaded_records'] == 0 and row['last_attempt'] is None for row in result['profiles'])
    assert all(row['availability'] == 'not_loaded' for row in result['profiles'])


def test_failed_import_keeps_old_loaded_counts_and_last_success(database, tmp_path):
    save_collection(tmp_path/'good', [contract()]); import_resources(database, tmp_path/'good')
    save_collection(tmp_path/'bad', [contract(valorInicial='1.00001')])
    try: import_resources(database, tmp_path/'bad')
    except ValueError: pass
    else: raise AssertionError('invalid precision unexpectedly imported')
    with database.session() as session:
        failed = session.scalar(select(Ingestion).where(Ingestion.status=='failed'))
        failed.source = {'url':'https://example.invalid/?token=PRIVATE', 'query':{'owner':'PRIVATE'}}
        failed.error = 'PRIVATE account, original path, person and query'
        failed.counts = {'read': 'PRIVATE', 'path':'PRIVATE','published':0,'rolled_back':True}
    result = coverage(database)
    row = next(row for row in result['profiles'] if row['profile']=='pncp_contracts')
    assert row['loaded_records'] == 1 and row['availability'] == 'available'
    assert row['last_attempt']['status'] == 'failed'
    assert row['last_successful_import_at'] is not None
    assert row['last_attempt']['counts'] == {'published':0}
    assert row['last_attempt']['rolled_back'] is True
    assert 'PRIVATE' not in json.dumps(result) and 'error' not in row['last_attempt']
    assert len(current(database)) == 1


def test_only_known_import_profiles_are_public(database):
    with database.session() as session:
        session.add(Ingestion(dataset='operator_private', source={'secret':'PRIVATE'}, error='PRIVATE'))
        session.add(Ingestion(dataset='pncp_contracts', source={}, status='running',
                              counts={'read':1,'created':True,'updated':-1,'unchanged':1.5}))
    result = coverage(database)
    row = result['profiles'][0]
    assert row['last_attempt']['status'] == 'running'
    assert row['last_attempt']['counts'] == {'read':1}
    assert row['last_successful_import_at'] is None
    assert 'PRIVATE' not in json.dumps(result) and 'operator_private' not in json.dumps(result)


def test_import_timestamp_is_not_presented_as_source_reference_date(database, tmp_path):
    save_collection(tmp_path/'good', [contract()]); import_resources(database, tmp_path/'good')
    row = coverage(database)['profiles'][0]
    assert row['last_attempt']['status'] == 'success'
    assert row['last_attempt']['counts']['created'] == 1
    assert row['last_attempt']['finished_at'] == row['last_successful_import_at']
    assert 'reference_date' not in row and 'source_updated_at' not in row


def test_unknown_status_and_non_timestamp_text_are_not_echoed(database):
    with database.session() as session:
        session.add(Ingestion(dataset='pncp_contracts', source={}, status='PRIVATE',
                              started_at='PRIVATE', finished_at='PRIVATE'))
    row = coverage(database)['profiles'][0]
    assert row['last_attempt'] == {'status':'unknown','started_at':None,'finished_at':None,
                                   'counts':{},'rolled_back':False}
