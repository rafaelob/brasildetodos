import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from bdt.api import create_app, password_hash, check_password
from bdt.storage import LoginSession, Place, User

HEAD={'X-BDT-Client':'web'}
PASSWORD='synthetic-password-only'

@pytest.fixture
def client(database,stored,monkeypatch):
    monkeypatch.setenv('BDT_ALLOW_REGISTRATION','1')
    app=create_app(str(database.engine.url),testing=True)
    with TestClient(app) as c:yield c

def register(client,name='reader'):
    assert client.post('/api/auth/register',headers=HEAD,json={'username':name,'password':PASSWORD}).status_code==201

def login(client,name='reader'):
    return client.post('/api/auth/login',headers=HEAD,json={'username':name,'password':PASSWORD})

def reviewer(database):
    with database.session() as s:s.add(User(username='reviewer',password_hash=password_hash(PASSWORD),role='reviewer'))

def observation():return {'place_id':'test:school','mode':'field','observed_on':'2025-01-01','body':'Synthetic description of the sign at the public entrance.','consent':True}

def test_health_no_llm(client):assert client.get('/api/health').json()['llm_required'] is False

def test_empty_geometry_is_in_list(client):
    response=client.get('/api/places').json()
    assert response['total']==1 and response['items'][0]['latitude'] is None

def test_search_accent_and_literal_wildcard(client):
    assert client.get('/api/places',params={'q':'arvore'}).json()['total']==1
    assert client.get('/api/places',params={'q':'%'}).json()['total']==0
    assert client.get('/api/places',params={'q':"' OR 1=1 --"}).json()['total']==0

def test_unknown_place_404(client):assert client.get('/api/places/test:missing').status_code==404

def test_bbox_does_not_show_missing_geometry(client):assert client.get('/api/places',params={'bbox':'-75,-35,-32,6'}).json()['total']==0

@pytest.mark.parametrize('bbox',['nan,0,2,3','0,0,1','1,0,0,3','-181,0,10,50'])
def test_invalid_bbox(client,bbox):assert client.get('/api/places',params={'bbox':bbox}).status_code==422

def test_history_started_not_fake_past(client):
    rows=client.get('/api/places/test:school/history').json()
    assert len(rows)==1 and rows[0]['type']=='started' and rows[0]['before'] is None

def test_coverage_not_national_claim(client):assert client.get('/api/coverage').json()['national_catalog_certified'] is False

def test_mutation_requires_csrf_header(client):assert client.post('/api/auth/register',json={'username':'x','password':PASSWORD}).status_code==403

def test_foreign_origin_denied(client):assert client.post('/api/auth/login',headers=HEAD|{'Origin':'https://other.example'},json={'username':'reader','password':PASSWORD}).status_code==403

def test_body_limit(client):assert client.post('/api/auth/login',headers=HEAD,content='x'*32769).status_code==413

def test_validation_does_not_echo_password(client):
    response=client.post('/api/auth/login',headers=HEAD,json={'username':'x','password':'secretshort'})
    assert response.status_code==422 and 'secretshort' not in response.text

def test_closed_registration(client,monkeypatch):
    monkeypatch.setenv('BDT_ALLOW_REGISTRATION','0')
    assert client.post('/api/auth/register',headers=HEAD,json={'username':'reader','password':PASSWORD}).status_code==403

def test_auth_cookie_hashed_and_logout(client,database):
    register(client);r=login(client);assert r.status_code==200
    assert 'httponly' in r.headers['set-cookie'].lower() and 'samesite=strict' in r.headers['set-cookie'].lower()
    cookie=client.cookies['bdt_session']
    with database.session() as s:assert s.scalar(select(LoginSession)).token_hash!=cookie
    assert client.get('/api/auth/me').json()['username']=='reader'
    assert client.post('/api/auth/logout',headers=HEAD).status_code==204
    assert client.get('/api/auth/me').status_code==401

def test_duplicate_username(client):
    register(client)
    assert client.post('/api/auth/register',headers=HEAD,json={'username':'READER','password':PASSWORD}).status_code==409

def test_plain_reader_cannot_review(client):
    register(client);login(client)
    assert client.get('/api/review').status_code==403
    assert client.post('/api/review/x',headers=HEAD,json={'decision':'approved','note':'Approved synthetic test.'}).status_code==403

def test_unauthenticated_observation_denied(client):assert client.post('/api/observations',headers=HEAD,json=observation()).status_code==401

def test_moderation_complete_cycle(client,database):
    register(client);login(client)
    submitted=client.post('/api/observations',headers=HEAD,json=observation())
    assert submitted.status_code==201 and submitted.json()['status']=='pending'
    id=submitted.json()['id']
    assert client.get('/api/places/test:school').json()['observations']==[]
    assert len(client.get('/api/observations/mine').json())==1
    client.post('/api/auth/logout',headers=HEAD);reviewer(database);login(client,'reviewer')
    assert len(client.get('/api/review').json())==1
    approved=client.post('/api/review/'+id,headers=HEAD,json={'decision':'approved','note':'Checked synthetic statement for this test.'})
    assert approved.status_code==200 and approved.json()['status']=='approved'
    assert 'author_id' not in approved.json()
    assert len(client.get('/api/places/test:school').json()['observations'])==1
    assert client.post('/api/review/'+id,headers=HEAD,json={'decision':'rejected','note':'Second review should fail.'}).status_code==409

def test_rejected_not_public(client,database):
    register(client);login(client);id=client.post('/api/observations',headers=HEAD,json=observation()).json()['id']
    client.post('/api/auth/logout',headers=HEAD);reviewer(database);login(client,'reviewer')
    assert client.post('/api/review/'+id,headers=HEAD,json={'decision':'rejected','note':'Not suitable for this synthetic test.'}).status_code==200
    assert client.get('/api/places/test:school').json()['observations']==[]

def test_reviewer_cannot_approve_own_submission(client,database):
    reviewer(database);login(client,'reviewer')
    id=client.post('/api/observations',headers=HEAD,json=observation()).json()['id']
    assert client.post('/api/review/'+id,headers=HEAD,json={'decision':'approved','note':'Not an independent review.'}).status_code==403

def test_private_observations_isolated(client):
    register(client);login(client);client.post('/api/observations',headers=HEAD,json=observation());client.post('/api/auth/logout',headers=HEAD)
    register(client,'other');login(client,'other')
    assert client.get('/api/observations/mine').json()==[]

def test_headers(client):
    r=client.get('/api/health');assert r.headers['x-content-type-options']=='nosniff'
    assert "frame-ancestors 'none'" in r.headers['content-security-policy'] and r.headers['cache-control']=='no-store'

def test_password_hash_salt_and_verification():
    a=password_hash(PASSWORD);b=password_hash(PASSWORD)
    assert a!=b and check_password(PASSWORD,a) and not check_password('wrong',a)
    assert not check_password(PASSWORD,'broken')

def test_no_synthetic_bootstrap(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path/'empty.db'}",testing=True)) as c:
        assert c.get('/api/places').json()['total']==0
        assert c.get('/api/coverage').json()['municipalities']==0

def test_production_fails_without_https(tmp_path,monkeypatch):
    monkeypatch.setenv('BDT_ENV','production');monkeypatch.setenv('BDT_PUBLIC_ORIGIN','http://localhost')
    with pytest.raises(RuntimeError):create_app(f"sqlite:///{tmp_path/'prod.db'}",testing=True)

def test_withdrawn_place_hidden_from_discovery(client,database):
    with database.session() as s:s.get(Place,'test:school').catalogue_eligible=False
    assert client.get('/api/places').json()['total']==0
    assert client.get('/api/places/test:school').status_code==200

def test_exact_code_revision(client,monkeypatch):
    monkeypatch.setenv('BDT_REVISION','a'*40)
    assert client.get('/api/config').json()['source_code'].endswith('/tree/'+'a'*40)

def test_municipality_filter_and_region(client):
    assert len(client.get('/api/municipalities?state=BA').json())==1
    assert client.get('/api/municipalities?state=SP').json()==[]
    assert client.get('/api/regions/1234567').json()['total']==0
    assert client.get('/api/regions/9999999').status_code==404

def test_unknown_history(client):assert client.get('/api/places/test:unknown/history').status_code==404

def test_unknown_observation_place(client):
    register(client);login(client)
    assert client.post('/api/observations',headers=HEAD,json=observation()|{'place_id':'test:missing'}).status_code==404

def test_invalid_credentials_and_rate_limit(client):
    for _ in range(20):assert login(client).status_code==401
    response=login(client);assert response.status_code==429 and response.headers['retry-after']

def test_review_missing(client,database):
    reviewer(database);login(client,'reviewer')
    assert client.post('/api/review/unknown',headers=HEAD,json={'decision':'approved','note':'Synthetic missing record.'}).status_code==404
