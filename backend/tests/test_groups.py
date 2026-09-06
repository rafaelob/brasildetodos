"""Synthetic groups use actual API/SQLite; no production bootstrap or mock backend."""
import hashlib
import json
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from bdt.api import create_app, password_hash
from bdt.domain import PlaceInput, Source, now
from bdt.storage import User, Observation, Municipality, upsert_place
from bdt.groups import Group, Member, Invite, Task

HEAD={'x-bdt-client':'web'}
PASSWORD='test-only-password-2026'

@pytest.fixture
def team(tmp_path, monkeypatch):
    monkeypatch.setenv('BDT_DATA_DIR',str(tmp_path/'data'))
    app=create_app(f"sqlite:///{tmp_path/'app.db'}", testing=True)
    db=app.state.database
    with db.session() as s:
        src=Source(dataset='synthetic',url='https://example.org/test',record_id='test',reference_date='2025',collected_at=now(),snapshot_sha256='a'*64)
        s.add(Municipality(id='1234567',name='Synthetic town',state='BA',source=src.model_dump(mode='json')));s.flush()
        for p in ('test:school','test:other'):
            upsert_place(s,PlaceInput(id=p,kind='school',name='Synthetic school',municipality_id='1234567',state='BA',source=src))
        for name in ('owner','member','outsider','reviewer'):
            s.add(User(username=name,password_hash=password_hash(PASSWORD),role='reviewer' if name=='reviewer' else 'contributor'))
    clients={}
    for name in ('owner','member','outsider','reviewer'):
        client=TestClient(app);client.__enter__()
        assert client.post('/api/auth/login',headers=HEAD,json={'username':name,'password':PASSWORD}).status_code==200
        clients[name]=client
    yield app,db,clients
    for client in clients.values():client.__exit__(None,None,None)


def new_group(c):
    r=c.post('/api/groups',headers=HEAD,json={'name':'Synthetic community','description':'A private test group'})
    assert r.status_code==201,r.text
    return r.json()['id']


def detail(c,g):
    r=c.get('/api/groups/'+g);assert r.status_code==200,r.text
    return r.json()


def action(c,g,path,**body):
    body={'expected_revision':detail(c,g)['group']['revision'],**body}
    return c.post('/api/groups/'+g+path,headers=HEAD,json=body)


def add_member(owner,member,g):
    r=action(owner,g,'/invites');assert r.status_code==201,r.text
    token=r.json()['token']
    r=member.post('/api/groups/join',headers=HEAD,json={'token':token,'consent':True})
    assert r.status_code==200,r.text
    return token


def task(owner,g):
    r=action(owner,g,'/tasks',place_id='test:school',title='Check the visible notice',instructions='Observe only from a public area.')
    assert r.status_code==201,r.text
    return r.json()['task']['id']


def observation(c,place='test:school'):
    r=c.post('/api/observations',headers=HEAD,json={'place_id':place,'mode':'field','observed_on':'2026-09-06','body':'Synthetic field observation without personal details.','consent':True})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_private_group_persists_and_restricts_access(team):
    app,db,c=team;g=new_group(c['owner'])
    assert c['owner'].get('/api/groups').json()['items'][0]['id']==g
    for name in ('member','reviewer','outsider'):
        assert c[name].get('/api/groups/'+g).status_code==404
        assert c[name].get('/api/groups').json()['items']==[]
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/groups').status_code==401
        assert anonymous.post('/api/groups',json={'name':'Blocked'}).status_code==403
    with db.session() as s:assert s.get(Group,g).name=='Synthetic community'


def test_invite_single_use_hashed_and_never_exported(team):
    _,db,c=team;g=new_group(c['owner'])
    invite=action(c['owner'],g,'/invites').json();token=invite['token']
    with db.session() as s:
        row=s.get(Invite,invite['id']);assert row.token_hash==hashlib.sha256(token.encode()).hexdigest()
    for path in ('/api/groups/'+g,'/api/account/export'):
        content=c['owner'].get(path).text
        assert token not in content and hashlib.sha256(token.encode()).hexdigest() not in content
    joined=c['member'].post('/api/groups/join',headers=HEAD,json={'token':token,'consent':True});assert joined.status_code==200
    assert c['outsider'].post('/api/groups/join',headers=HEAD,json={'token':token,'consent':True}).status_code==404
    assert c['member'].get('/api/auth/me').json()['role']=='contributor'


@pytest.mark.parametrize('mode',['expired','revoked','archived'])
def test_invalid_invites_do_not_grant_access(team,mode):
    _,db,c=team;g=new_group(c['owner']);i=action(c['owner'],g,'/invites').json()
    if mode=='expired':
        with db.session() as s:s.get(Invite,i['id']).expires_at=int(time.time())-1
    elif mode=='revoked':assert action(c['owner'],g,'/invites/'+i['id']+'/revoke').status_code==200
    else:assert action(c['owner'],g,'/archive').status_code==200
    assert c['member'].post('/api/groups/join',headers=HEAD,json={'token':i['token'],'consent':True}).status_code==404
    assert c['member'].get('/api/groups/'+g).status_code==404


def test_revision_conflict_preserves_state_and_invite_count(team):
    _,db,c=team;g=new_group(c['owner']);v=detail(c['owner'],g)['group']['revision']
    assert action(c['owner'],g,'/invites').status_code==201
    r=c['owner'].post('/api/groups/'+g+'/edit',headers=HEAD,json={'expected_revision':v,'name':'Stale change'})
    assert r.status_code==409
    assert detail(c['owner'],g)['group']['name']=='Synthetic community'
    with db.session() as s:assert s.scalar(select(func.count()).select_from(Invite))==1


def test_full_task_workflow_does_not_publish_observation(team):
    _,db,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    assert action(c['member'],g,'/tasks/'+t,action='claim').status_code==200
    obs=observation(c['member'])
    assert action(c['member'],g,'/tasks/'+t,action='submit',observation_id=obs,share_with_group=True).status_code==200
    r=action(c['member'],g,'/tasks/'+t,action='accept',note='My own delivery is good.')
    assert r.status_code==403
    assert action(c['owner'],g,'/tasks/'+t,action='request_changes',note='Please clarify the date shown.').status_code==200
    assert action(c['member'],g,'/tasks/'+t,action='submit',observation_id=obs,share_with_group=True).status_code==200
    r=action(c['owner'],g,'/tasks/'+t,action='accept',note='Independent group review complete.');assert r.status_code==200
    assert r.json()['task']['effective_state']=='accepted'
    assert c['owner'].get('/api/places/test:school').json()['observations']==[]
    with db.session() as s:assert s.get(Observation,obs).status=='pending'


@pytest.mark.parametrize('invalid',['wrong_place','other_author','no_confirmation','withdrawn','missing'])
def test_submission_requires_own_same_place_explicitly_shared_observation(team,invalid):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    action(c['member'],g,'/tasks/'+t,action='claim')
    obs=observation(c['owner'] if invalid=='other_author' else c['member'], 'test:other' if invalid=='wrong_place' else 'test:school')
    if invalid=='withdrawn':c['member'].post('/api/observations/'+obs+'/withdraw',headers=HEAD)
    if invalid=='missing':obs='00000000-0000-0000-0000-000000000000'
    v=detail(c['member'],g)['group']['revision']
    r=action(c['member'],g,'/tasks/'+t,action='submit',observation_id=obs,share_with_group=invalid!='no_confirmation')
    assert r.status_code==422,r.text
    d=detail(c['member'],g);assert d['group']['revision']==v and d['tasks']['items'][0]['state']=='in_progress'


def test_withdrawal_invalidates_accepted_task_immediately(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    action(c['member'],g,'/tasks/'+t,action='claim');obs=observation(c['member'])
    action(c['member'],g,'/tasks/'+t,action='submit',observation_id=obs,share_with_group=True)
    action(c['owner'],g,'/tasks/'+t,action='accept',note='Reviewed private evidence.')
    assert c['member'].post('/api/observations/'+obs+'/withdraw',headers=HEAD).status_code==200
    row=detail(c['owner'],g)['tasks']['items'][0]
    assert row['effective_state']=='evidence_unavailable' and row['observation'] is None and row['review_note'] is None
    assert action(c['owner'],g,'/tasks/'+t,action='reopen').status_code==200


@pytest.mark.parametrize('mode',['leave','remove','delete'])
def test_access_revocation_withdraws_private_sharing(team,mode):
    _,db,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    action(c['member'],g,'/tasks/'+t,action='claim');obs=observation(c['member'])
    action(c['member'],g,'/tasks/'+t,action='submit',observation_id=obs,share_with_group=True)
    if mode=='leave':r=action(c['member'],g,'/leave')
    elif mode=='remove':
        user_id=next(m['id'] for m in detail(c['owner'],g)['members'] if m['username']=='member')
        r=action(c['owner'],g,'/members/remove',user_id=user_id)
    else:r=c['member'].post('/api/account/delete',headers=HEAD,json={'password':PASSWORD,'confirmed':True})
    assert r.status_code==200,r.text
    assert c['member'].get('/api/groups/'+g).status_code in (401,404)
    row=detail(c['owner'],g)['tasks']['items'][0]
    assert row['observation'] is None and row['state']=='open'


def test_owner_transfer_and_archive_are_real_transitions(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g)
    assert action(c['owner'],g,'/leave').status_code==409
    uid=next(m['id'] for m in detail(c['owner'],g)['members'] if not m['me'])
    assert action(c['owner'],g,'/transfer',user_id=uid).status_code==200
    assert detail(c['member'],g)['group']['owner'] is True
    assert action(c['owner'],g,'/invites').status_code==403
    assert action(c['owner'],g,'/leave').status_code==200
    assert action(c['member'],g,'/archive').status_code==200
    assert action(c['member'],g,'/tasks',place_id='test:school',title='Cannot add task').status_code==409
    assert action(c['member'],g,'/leave').status_code==200


def test_account_export_own_content_and_deactivation_redacts(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);task(c['owner'],g)
    report=c['owner'].get('/api/account/export').json()['collaboration']
    assert report['authored_tasks'][0]['title']=='Check the visible notice'
    assert report['invitation_secrets_included'] is False
    assert 'member' not in json.dumps(report).replace('memberships','')
    r=c['owner'].post('/api/account/delete',headers=HEAD,json={'password':PASSWORD,'confirmed':True});assert r.status_code==200
    other=detail(c['member'],g)
    assert other['group']['status']=='archived' and other['group']['description']==''
    assert other['tasks']['items'][0]['instructions']=='' and other['tasks']['items'][0]['state']=='cancelled'


def test_group_limits_and_task_reference_validation(team,monkeypatch):
    import bdt.groups as module
    _,db,c=team;monkeypatch.setattr(module,'MAX_GROUPS',1)
    g=new_group(c['owner'])
    assert c['owner'].post('/api/groups',headers=HEAD,json={'name':'Too many'}).status_code==409
    assert action(c['owner'],g,'/tasks',place_id='test:missing',title='Check existing place').status_code==404
    monkeypatch.setattr(module,'MAX_TASKS',1);task(c['owner'],g)
    assert action(c['owner'],g,'/tasks',place_id='test:school',title='Too many tasks').status_code==409
    monkeypatch.setattr(module,'MAX_INVITES',1);assert action(c['owner'],g,'/invites').status_code==201
    assert action(c['owner'],g,'/invites').status_code==409


def test_schema_migration_idempotence_and_unknown_version(team):
    from bdt.groups import initialize,GroupVersion
    _,db,c=team;g=new_group(c['owner']);initialize(db)
    assert detail(c['owner'],g)['group']['name']=='Synthetic community'
    with db.session() as s:s.get(GroupVersion,1).version=99
    with pytest.raises(RuntimeError,match='unsupported_group_schema'):initialize(db)


@pytest.mark.parametrize('field,value',[('name',' ab '),('name',17),('name','A\x00BC'),('description','x\x7f')])
def test_text_validated_after_trimming(team,field,value):
    _,_,c=team
    r=c['owner'].post('/api/groups',headers=HEAD,json={'name':'Valid group',field:value})
    assert r.status_code==422


def test_invalid_title_and_join_consent_are_rejected(team):
    _,_,c=team;g=new_group(c['owner'])
    assert action(c['owner'],g,'/tasks',place_id='test:school',title=' a ').status_code==422
    i=action(c['owner'],g,'/invites').json()
    assert c['member'].post('/api/groups/join',headers=HEAD,json={'token':i['token'],'consent':False}).status_code==422
    assert c['member'].get('/api/groups/'+g).status_code==404


def test_cross_origin_and_nonowner_controls(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g)
    rev=detail(c['owner'],g)['group']['revision']
    assert c['owner'].post('/api/groups/'+g+'/archive',headers=HEAD|{'origin':'https://different.example.org'},json={'expected_revision':rev}).status_code==403
    for path,extra in [('/edit',{'name':'Blocked rename'}),('/archive',{}),('/invites',{}),('/transfer',{'user_id':'00000000-0000-0000-0000-000000000000'})]:
        assert action(c['member'],g,path,**extra).status_code==403
    assert detail(c['owner'],g)['group']['revision']==rev


def test_tasks_are_bound_to_group_and_owner_permissions(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    other=new_group(c['owner'])
    assert action(c['owner'],other,'/tasks/'+t,action='claim').status_code==404
    assert action(c['member'],g,'/tasks/'+t,action='cancel').status_code==409
    assert action(c['member'],g,'/tasks/'+t,action='claim').status_code==200
    assert action(c['owner'],g,'/tasks/'+t,action='release').status_code==409
    assert action(c['member'],g,'/tasks/'+t,action='release').status_code==200
    assert action(c['owner'],g,'/tasks/'+t,action='cancel').status_code==200
    assert action(c['member'],g,'/tasks/'+t,action='claim').status_code==409


def test_same_revision_competing_writes_have_one_winner(team):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);t=task(c['owner'],g)
    rev=detail(c['owner'],g)['group']['revision'];barrier=Barrier(2)
    def claim(name):
        barrier.wait()
        return c[name].post('/api/groups/'+g+'/tasks/'+t,headers=HEAD,json={'expected_revision':rev,'action':'claim'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,['owner','member']))
    assert sorted(results)==[200,409]
    assert detail(c['owner'],g)['group']['revision']==rev+1


def test_group_detail_pagination_and_read_only_snapshot(team):
    _,db,c=team;g=new_group(c['owner'])
    with db.session() as s:
        owner=s.scalar(select(User.id).where(User.username=='owner'))
        for i in range(23):s.add(Task(group_id=g,place_id='test:school',author_id=owner,title=f'Synthetic task {i:02d}'))
    first=detail(c['owner'],g)
    second=c['owner'].get('/api/groups/'+g+'?page=2').json()
    assert first['tasks']['total']==23 and len(first['tasks']['items'])==20 and len(second['tasks']['items'])==3
    assert not set(t['id'] for t in first['tasks']['items'])&set(t['id'] for t in second['tasks']['items'])
    assert second['group']['revision']==first['group']['revision']
    assert c['owner'].get('/api/groups/'+g+'?page=0').status_code==422


def test_member_quota_rolls_back_invitation_consumption(team,monkeypatch):
    import bdt.groups as module
    _,db,c=team;g=new_group(c['owner']);i=action(c['owner'],g,'/invites').json()
    monkeypatch.setattr(module,'MAX_MEMBERS',1)
    r=c['member'].post('/api/groups/join',headers=HEAD,json={'token':i['token'],'consent':True});assert r.status_code==409
    with db.session() as s:assert s.get(Invite,i['id']).status=='pending'
    monkeypatch.setattr(module,'MAX_MEMBERS',2)
    assert c['member'].post('/api/groups/join',headers=HEAD,json={'token':i['token'],'consent':True}).status_code==200


def test_account_disabled_reviewer_no_longer_confirms_task(team):
    _,_,c=team;g=new_group(c['owner']);add_member(c['owner'],c['member'],g);add_member(c['owner'],c['reviewer'],g);t=task(c['owner'],g)
    action(c['member'],g,'/tasks/'+t,action='claim');o=observation(c['member'])
    action(c['member'],g,'/tasks/'+t,action='submit',observation_id=o,share_with_group=True)
    action(c['reviewer'],g,'/tasks/'+t,action='accept',note='Independent reviewer comment to erase.')
    assert c['reviewer'].post('/api/account/delete',headers=HEAD,json={'password':PASSWORD,'confirmed':True}).status_code==200
    row=detail(c['owner'],g)['tasks']['items'][0]
    assert row['state']=='submitted' and row['review_note'] is None


def test_backup_revokes_invites_and_preserves_original(team,tmp_path):
    import sqlite3
    from contextlib import closing
    from pathlib import Path
    from bdt.backup import create_backup,restore_backup
    _,db,c=team;g=new_group(c['owner']);i=action(c['owner'],g,'/invites').json()
    source=Path(db.engine.url.database);folder=tmp_path/'private-backup';create_backup(source,folder)
    output=tmp_path/'restored.db';restore_backup(folder,output)
    with closing(sqlite3.connect(output)) as sql:
        assert sql.execute('SELECT token_hash,status FROM group_invites').fetchone()==(None,'revoked')
        assert sql.execute('SELECT count(*) FROM group_members').fetchone()==(1,)
    with db.session() as s:assert s.get(Invite,i['id']).status=='pending'
