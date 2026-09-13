"""Integration proof against a fresh, explicitly ephemeral localhost PostgreSQL.

No real citizens or source data are used. Never point this at production.
"""
from __future__ import annotations
import json
import os
import secrets
import tempfile
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from bdt.api import create_app, password_hash
from bdt.catalog_release import export_catalog, install_catalog, verify_catalog
from bdt.domain import PlaceInput, Source, now
from bdt.evidence import initialize_extensions
from bdt.ingest import import_finance
from bdt.storage import Database, Municipality, User, Place, upsert_place


def main():
    url = make_url(os.environ['BDT_RUNTIME_TEST_DATABASE_URL'])
    local_host = url.host in {'127.0.0.1', 'localhost'}
    compose_host = url.host == 'postgres-test' and os.getenv('BDT_COMPOSE_TEST') == '1'
    if (url.get_backend_name() != 'postgresql' or not (local_host or compose_host)
            or url.port != 5432 or url.database != 'bdt_ci'
            or url.username != 'bdt_ci' or os.getenv('BDT_EPHEMERAL_TEST') != '1'):
        raise ValueError('only_explicit_ephemeral_test_database_allowed')
    database = Database(url.render_as_string(hide_password=False))
    if inspect(database.engine).get_table_names():
        raise ValueError('ephemeral_database_must_be_empty')
    checks=[]
    with database.engine.connect() as connection:
        assert connection.execute(text(
            'SELECT rolsuper FROM pg_roles WHERE rolname = current_user'
        )).scalar_one() is False
    checks.append('non_superuser_database_role')
    database.initialize(); initialize_extensions(database)
    database.initialize(); initialize_extensions(database)
    checks.append('schema_initialized_twice')
    schema = inspect(database.engine)
    observation_fks = {tuple(item['constrained_columns']) for item in schema.get_foreign_keys('observations')}
    user_uniques = {tuple(item['column_names']) for item in schema.get_unique_constraints('users')}
    observation_indexes = {tuple(item['column_names']) for item in schema.get_indexes('observations')}
    assert {('place_id',), ('author_id',), ('reviewer_id',), ('previous_reviewer_id',)} <= observation_fks
    assert ('username',) in user_uniques and ('status',) in observation_indexes
    checks.append('foreign_keys_unique_constraints_and_indexes')
    source=Source(dataset='synthetic-runtime',url='https://example.org/synthetic-runtime',
        record_id='synthetic',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
    place=PlaceInput(id='synthetic:runtime',kind='school',name='Escola Sintética Runtime',
        municipality_id='1234567',state='BA',source=source,latitude=-15.8,longitude=-47.9,geo_source='synthetic-runtime')
    password=secrets.token_urlsafe(24)
    with database.session() as session:
        session.add(Municipality(id='1234567',state='BA',name='Município Sintético',source=source.model_dump()))
        session.flush();upsert_place(session,place)
        session.add_all([User(username='runtime_citizen',password_hash=password_hash(password)),
            User(username='runtime_reviewer',password_hash=password_hash(password),role='reviewer')])
    try:
        with database.session() as session:
            session.add(Municipality(id='7654321', state='SP', name='Município de rollback',
                source=source.model_dump()))
            session.add(User(username='runtime_citizen', password_hash=password_hash(password)))
    except IntegrityError:
        pass
    else:
        raise AssertionError('postgres_unique_constraint_not_enforced')
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 2
        assert session.get(Municipality, '7654321') is None
    checks.append('constraint_failure_rolled_back')
    for phase in ['transferred','paid']:
        import_finance(database,[{'id':phase,'municipality_id':place.municipality_id,
            'instrument_id':'synthetic-runtime','recipient':'Synthetic entity','period':'2025',
            'cents':100000,'phase':phase,'perspective':'federal','nature':'event'}],source)
    app=create_app(url.render_as_string(hide_password=False))
    headers={'x-bdt-client':'web','origin':'http://localhost:8000'}
    with TestClient(app,base_url='http://localhost:8000') as client:
        assert client.get('/api/health').json()['llm_required'] is False;checks.append('health_no_llm')
        assert client.get('/api/places').json()['total']==1;checks.append('query_json_booleans')
        view=client.get('/api/map/viewport',params={'bbox':'-49,-17,-46,-14','zoom':12})
        assert view.status_code==200;checks.append('geospatial_viewport')
        login=client.post('/api/auth/login',json={'username':'runtime_citizen','password':password},headers=headers)
        assert login.status_code==200;checks.append('postgres_rate_limit_upsert_and_login')
        result=client.post('/api/observations',json={'place_id':place.id,'mode':'field',
            'observed_on':date.today().isoformat(),'body':'Synthetic observation for database integration only.',
            'consent':True},headers=headers)
        assert result.status_code==201, result.text
        identity=result.json()['id'];assert result.json()['status']=='pending'
        assert client.get('/api/account/export').json()['credentials_included'] is False
        client.post('/api/auth/logout',headers=headers)
        client.post('/api/auth/login',json={'username':'runtime_reviewer','password':password},headers=headers)
        decision=client.post('/api/review/'+identity,json={'decision':'approved',
            'note':'Synthetic independent moderation test.'},headers=headers)
        assert decision.status_code==200 and decision.json()['status']=='approved';checks.append('row_lock_and_independent_moderation')
        public = client.get('/api/places/'+place.id)
        assert public.status_code == 200 and public.json()['observations'][0]['id'] == identity
        checks.append('contribution_moderation_public_read')
        duplicate=client.post('/api/review/'+identity,json={'decision':'approved',
            'note':'Synthetic duplicate moderation test.'},headers=headers)
        assert duplicate.status_code==409;checks.append('duplicate_review_rejected')
    with tempfile.TemporaryDirectory(prefix='bdt-pg-test-') as temporary:
        root=Path(temporary);release=root/'release';target=root/'installed.db'
        manifest=export_catalog(database,release,os.getenv('GITHUB_SHA','development'))
        assert manifest['files']['places.jsonl']['records']==1
        verify_catalog(release);install_catalog(release,target)
        sqlite=Database('sqlite:///'+str(target))
        with sqlite.session() as session:
            assert session.scalar(select(func.count()).select_from(Place))==1
            assert session.scalar(select(func.count()).select_from(User))==0
        sqlite.engine.dispose();checks.append('postgres_repeatable_snapshot_to_sqlite_public_install')
    database.engine.dispose()
    result={'synthetic_test_only':True,'backend':'postgresql','checks':checks,
        'revision':os.getenv('GITHUB_SHA','development'),'production_deployed':False}
    output=Path(os.getenv('BDT_RUNTIME_TEST_OUTPUT', 'test-results/runtime'))
    output.mkdir(parents=True,exist_ok=True)
    (output/'postgres.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':main()
