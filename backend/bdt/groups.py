# SPDX-License-Identifier: AGPL-3.0-or-later
"""Private, persistent civic teams. Task review NEVER publishes an observation.

All mutations compare the group revision after authenticating an active member.
Invites are random bearer secrets, hashed at rest and returned only at creation.
Shared observations are read live: withdrawal, retraction or erasure hides them.
"""
from __future__ import annotations
import hashlib
import secrets
import time
from typing import Literal
from uuid import uuid4
from fastapi import Depends, HTTPException, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import Column, ForeignKey, Integer, String, Text, delete, func, select, update
from sqlalchemy.orm import Session
from .catalog_release import consistent_read
from .domain import StrictModel, now
from .evidence import audit
from .storage import Base, Observation, Place, User

MAX_GROUPS, MAX_MEMBERS, MAX_TASKS, MAX_INVITES = 20, 50, 200, 20
TOKEN_TTL = 48 * 3600


def identity():
    return str(uuid4())


class GroupVersion(Base):
    __tablename__ = 'group_schema_version'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)


class Group(Base):
    __tablename__ = 'community_groups'
    id = Column(String(36), primary_key=True, default=identity)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=False, default='')
    owner_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default='active')
    created_at = Column(String(40), nullable=False, default=now)


class Member(Base):
    __tablename__ = 'group_members'
    group_id = Column(String(36), ForeignKey('community_groups.id'), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), primary_key=True, index=True)
    joined_at = Column(String(40), nullable=False, default=now)


class Invite(Base):
    __tablename__ = 'group_invites'
    id = Column(String(36), primary_key=True, default=identity)
    group_id = Column(String(36), ForeignKey('community_groups.id'), nullable=False, index=True)
    creator_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(64), unique=True)
    expires_at = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    created_at = Column(String(40), nullable=False, default=now)


class Task(Base):
    __tablename__ = 'group_tasks'
    id = Column(String(36), primary_key=True, default=identity)
    group_id = Column(String(36), ForeignKey('community_groups.id'), nullable=False, index=True)
    place_id = Column(String(180), ForeignKey('places.id'), nullable=False)
    author_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    title = Column(String(160), nullable=False)
    instructions = Column(Text, nullable=False, default='')
    state = Column(String(30), nullable=False, default='open')
    revision = Column(Integer, nullable=False, default=1)
    assignee_id = Column(String(36), ForeignKey('users.id'))
    observation_id = Column(String(36), ForeignKey('observations.id'))
    reviewer_id = Column(String(36), ForeignKey('users.id'))
    review_note = Column(Text)
    created_at = Column(String(40), nullable=False, default=now)
    updated_at = Column(String(40), nullable=False, default=now)


def initialize(database):
    with database.engine.begin() as connection:
        GroupVersion.__table__.create(connection, checkfirst=True)
        version = connection.execute(select(GroupVersion.version).where(GroupVersion.id == 1)).scalar_one_or_none()
        if version not in (None, 1):
            raise RuntimeError('unsupported_group_schema')
        for model in (Group, Member, Invite, Task):
            model.__table__.create(connection, checkfirst=True)
        if version is None:
            connection.execute(GroupVersion.__table__.insert().values(id=1, version=1))


class GroupBody(StrictModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(default='', max_length=1000)

    @field_validator('name', 'description', mode='before')
    @classmethod
    def readable(cls, value):
        if not isinstance(value, str):
            raise ValueError('text_required')
        if any((ord(c) < 32 and c not in '\n\t') or ord(c) == 127 for c in value):
            raise ValueError('control_character')
        if value and not value.strip():
            raise ValueError('blank_text')
        return value.strip()


class Revision(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)


class GroupEdit(GroupBody, Revision):
    pass


class Join(StrictModel):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    consent: Literal[True]


class MemberAction(Revision):
    user_id: str = Field(pattern=r'^[a-f0-9-]{36}$')


class NewTask(Revision):
    place_id: str = Field(min_length=1, max_length=180)
    title: str = Field(min_length=5, max_length=160)
    instructions: str = Field(default='', max_length=2000)

    @field_validator('title', 'instructions', mode='before')
    @classmethod
    def readable(cls, value):
        return GroupBody.readable(value)


class TaskAction(Revision):
    action: Literal['claim', 'release', 'submit', 'accept', 'request_changes', 'reopen', 'cancel']
    observation_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')
    share_with_group: bool = False
    note: str = Field(default='', max_length=1000)

    @field_validator('note', mode='before')
    @classmethod
    def readable(cls, value):
        return GroupBody.readable(value)


def active_actor(session, user_id, *, lock=False):
    if lock:
        # Recheck and lock the actor; serialize cross-group membership quotas.
        changed = session.execute(update(User).where(User.id == user_id, User.role != 'disabled')
                                  .values(role=User.role))
        if changed.rowcount != 1:
            raise HTTPException(401, 'login_required')
    user = session.get(User, user_id)
    if not user or user.role == 'disabled':
        raise HTTPException(401, 'login_required')
    return user


def group_for(session, group_id, user_id, *, revision=None, owner=False, allow_archived=False):
    group = session.get(Group, group_id)
    member = session.get(Member, (group_id, user_id))
    if not group or not member:
        raise HTTPException(404, 'group_not_found')
    if owner and group.owner_id != user_id:
        raise HTTPException(403, 'group_owner_required')
    if revision is not None:
        if group.status != 'active' and not allow_archived:
            raise HTTPException(409, 'group_archived')
        changed = session.execute(update(Group).where(Group.id == group_id, Group.revision == revision)
                                  .values(revision=revision + 1))
        if changed.rowcount != 1:
            raise HTTPException(409, 'group_revision_conflict')
        session.refresh(group)
    return group


def visible_observation(session, task):
    row = session.get(Observation, task.observation_id) if task.observation_id else None
    if not row or row.author_id != task.assignee_id or row.place_id != task.place_id:
        return None
    author = session.get(User, row.author_id)
    if (row.status not in ('pending', 'approved') or not isinstance(row.payload, dict) or row.payload.get('erased') or
            not author or author.role == 'disabled' or not session.get(Member, (task.group_id, row.author_id))):
        return None
    from .domain import ObservationInput
    try:
        body = ObservationInput.model_validate(row.payload).model_dump(mode='json')
    except ValueError:
        return None
    return {'id': row.id, 'status': row.status, 'observation': body,
            'shared_privately': True, 'created_at': row.created_at}


def task_payload(session, task, user_id):
    observation = visible_observation(session, task)
    unavailable = task.state in ('submitted', 'accepted') and observation is None
    place = session.get(Place, task.place_id)
    return {'id': task.id, 'place_id': task.place_id, 'place_name': place.name if place else None,
        'title': task.title, 'instructions': task.instructions, 'state': task.state,
        'effective_state': 'evidence_unavailable' if unavailable else task.state,
        'revision': task.revision, 'created_at': task.created_at, 'updated_at': task.updated_at,
        'assigned_to_me': task.assignee_id == user_id, 'created_by_me': task.author_id == user_id,
        'can_review': task.state == 'submitted' and task.assignee_id != user_id and observation is not None,
        'observation': observation, 'review_note': task.review_note if observation else None}


def group_payload(group, user_id):
    return {'id': group.id, 'name': group.name, 'description': group.description,
        'status': group.status, 'revision': group.revision, 'owner': group.owner_id == user_id,
        'created_at': group.created_at, 'visibility': 'private'}


def remove_member_content(session, group_id, user_id):
    # Leaving revokes future access and retracts the member's private submissions.
    for task in session.scalars(select(Task).where(Task.group_id == group_id, Task.assignee_id == user_id)):
        task.assignee_id = task.observation_id = task.reviewer_id = task.review_note = None
        if task.state != 'cancelled':
            task.state = 'open'
        task.revision += 1
        task.updated_at = now()
    for task in session.scalars(select(Task).where(Task.group_id == group_id, Task.reviewer_id == user_id)):
        task.reviewer_id = task.review_note = None
        if task.state in ('accepted', 'changes_requested'):
            task.state = 'submitted'
        task.revision += 1
        task.updated_at = now()
    session.execute(delete(Member).where(Member.group_id == group_id, Member.user_id == user_id))


def account_export(session, user_id):
    """Own authored content only; no other member identities or invitation secrets."""
    memberships = list(session.scalars(select(Member).where(Member.user_id == user_id)))
    authored = list(session.scalars(select(Task).where(Task.author_id == user_id)))
    reviews = list(session.scalars(select(Task).where(Task.reviewer_id == user_id)))
    return {'memberships': [{'group_id': m.group_id, 'joined_at': m.joined_at} for m in memberships],
        'owned_groups': [group_payload(g, user_id) for g in session.scalars(select(Group).where(Group.owner_id == user_id))],
        'authored_tasks': [{'id': t.id, 'group_id': t.group_id, 'place_id': t.place_id,
                           'title': t.title, 'instructions': t.instructions} for t in authored],
        'authored_reviews': [{'task_id': t.id, 'note': t.review_note} for t in reviews],
        'invitation_secrets_included': False}


def deactivate_user(session, user_id):
    """Called inside the existing account-erasure transaction; never commits alone."""
    group_ids = set(session.scalars(select(Member.group_id).where(Member.user_id == user_id)))
    group_ids.update(session.scalars(select(Task.group_id).where((Task.author_id == user_id) | (Task.reviewer_id == user_id))))
    for group_id in sorted(group_ids):
        group = session.get(Group, group_id)
        session.execute(update(Group).where(Group.id == group_id).values(revision=Group.revision + 1))
        if group.owner_id == user_id:
            group.name, group.description, group.status = 'Archived group', '', 'archived'
            session.execute(update(Invite).where(Invite.group_id == group_id).values(status='revoked', token_hash=None))
        remove_member_content(session, group_id, user_id)
        for task in session.scalars(select(Task).where(Task.group_id == group_id)):
            if task.author_id == user_id:
                task.title, task.instructions, task.state = 'Removed task', '', 'cancelled'
                task.observation_id = task.review_note = task.reviewer_id = task.assignee_id = None
                task.revision += 1
            elif task.reviewer_id == user_id:
                task.review_note = task.reviewer_id = None
                if task.state == 'accepted':
                    task.state = 'submitted'
                task.revision += 1
    session.execute(update(Invite).where(Invite.creator_id == user_id).values(status='revoked', token_hash=None))


def install(app, database, current_user, rate_limit):
    initialize(database)

    @app.get('/api/groups')
    def groups(user=Depends(current_user)):
        with consistent_read(database) as connection, Session(bind=connection) as session:
            active_actor(session, user['id'])
            rows = session.scalars(select(Group).join(Member).where(Member.user_id == user['id'])
                                   .order_by(Group.created_at.desc(), Group.id).limit(MAX_GROUPS))
            return {'items': [group_payload(g, user['id']) for g in rows], 'limit': MAX_GROUPS, 'public': False}

    @app.post('/api/groups', status_code=201)
    def create_group(body: GroupBody, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_write', 60)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            if session.scalar(select(func.count()).select_from(Member).where(Member.user_id == user['id'])) >= MAX_GROUPS:
                raise HTTPException(409, 'group_limit')
            group = Group(**body.model_dump(), owner_id=user['id'])
            session.add(group); session.flush()
            session.add(Member(group_id=group.id, user_id=user['id']))
            audit(session, user['id'], 'group', group.id, 'created')
            return group_payload(group, user['id'])

    @app.post('/api/groups/join')
    def join_group(body: Join, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_join', 15)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            invite = session.scalar(select(Invite).where(Invite.token_hash == hashlib.sha256(body.token.encode()).hexdigest(),
                Invite.status == 'pending', Invite.expires_at > int(time.time())))
            if not invite:
                raise HTTPException(404, 'invite_unavailable')
            group = session.get(Group, invite.group_id)
            if group.status != 'active':
                raise HTTPException(404, 'invite_unavailable')
            if session.get(Member, (group.id, user['id'])):
                raise HTTPException(409, 'already_group_member')
            if session.scalar(select(func.count()).select_from(Member).where(Member.user_id == user['id'])) >= MAX_GROUPS:
                raise HTTPException(409, 'group_limit')
            changed = session.execute(update(Group).where(Group.id == group.id, Group.revision == group.revision)
                                      .values(revision=Group.revision + 1))
            if changed.rowcount != 1:
                raise HTTPException(409, 'group_revision_conflict')
            if session.scalar(select(func.count()).select_from(Member).where(Member.group_id == group.id)) >= MAX_MEMBERS:
                raise HTTPException(409, 'member_limit')
            used = session.execute(update(Invite).where(Invite.id == invite.id, Invite.status == 'pending',
                Invite.expires_at > int(time.time())).values(status='used', token_hash=None))
            if used.rowcount != 1:
                raise HTTPException(404, 'invite_unavailable')
            session.add(Member(group_id=group.id, user_id=user['id']))
            audit(session, user['id'], 'group', group.id, 'joined')
            session.refresh(group)
            return group_payload(group, user['id'])

    @app.get('/api/groups/{group_id}')
    def detail(group_id: str, page: int = Query(1, ge=1, le=1000), user=Depends(current_user)):
        with consistent_read(database) as connection, Session(bind=connection) as session:
            active_actor(session, user['id'])
            group = group_for(session, group_id, user['id'])
            members = session.execute(select(Member, User).join(User).where(Member.group_id == group.id)
                                      .order_by(Member.joined_at, Member.user_id)).all()
            tasks = session.scalars(select(Task).where(Task.group_id == group.id)
                .order_by(Task.created_at.desc(), Task.id).offset((page-1)*20).limit(20))
            total = session.scalar(select(func.count()).select_from(Task).where(Task.group_id == group.id))
            invites = []
            if group.owner_id == user['id']:
                invites = [{'id': i.id, 'expires_at': i.expires_at} for i in session.scalars(select(Invite).where(
                    Invite.group_id == group.id, Invite.status == 'pending', Invite.expires_at > int(time.time())).order_by(Invite.created_at))]
            return {'group': group_payload(group, user['id']), 'members': [
                {'id': m.user_id, 'username': u.username, 'owner': m.user_id == group.owner_id, 'me': m.user_id == user['id']}
                for m,u in members if u.role != 'disabled'], 'invites': invites,
                'tasks': {'items': [task_payload(session, t, user['id']) for t in tasks], 'total': total, 'page': page, 'limit': 20},
                'public': False}

    @app.post('/api/groups/{group_id}/edit')
    def edit(group_id: str, body: GroupEdit, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            group.name, group.description = body.name, body.description
            audit(session, user['id'], 'group', group.id, 'edited')
            return group_payload(group, user['id'])

    @app.post('/api/groups/{group_id}/invites', status_code=201)
    def invite(group_id: str, body: Revision, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_invite', 30)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            current = int(time.time())
            session.execute(delete(Invite).where(Invite.group_id == group_id,
                (Invite.expires_at <= current) | (Invite.status != 'pending')))
            if session.scalar(select(func.count()).select_from(Invite).where(Invite.group_id == group_id)) >= MAX_INVITES:
                raise HTTPException(409, 'invite_limit')
            token = secrets.token_urlsafe(32)
            row = Invite(group_id=group_id, creator_id=user['id'], token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=current+TOKEN_TTL)
            session.add(row); session.flush()
            audit(session, user['id'], 'group', group_id, 'invite_created')
            return {'id': row.id, 'token': token, 'expires_at': row.expires_at, 'revision': group.revision}

    @app.post('/api/groups/{group_id}/invites/{invite_id}/revoke')
    def revoke(group_id: str, invite_id: str, body: Revision, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            result = session.execute(update(Invite).where(Invite.id == invite_id, Invite.group_id == group_id)
                .values(status='revoked', token_hash=None))
            if result.rowcount != 1:
                raise HTTPException(404, 'invite_unavailable')
            audit(session, user['id'], 'group', group_id, 'invite_revoked')
            return {'revision': group.revision}

    @app.post('/api/groups/{group_id}/leave')
    def leave(group_id: str, body: Revision, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, allow_archived=True)
            if group.owner_id == user['id'] and group.status == 'active':
                raise HTTPException(409, 'transfer_or_archive_first')
            remove_member_content(session, group_id, user['id'])
            audit(session, user['id'], 'group', group_id, 'left')
            return {'status': 'left'}

    @app.post('/api/groups/{group_id}/members/remove')
    def remove(group_id: str, body: MemberAction, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            if body.user_id == user['id'] or not session.get(Member, (group_id, body.user_id)):
                raise HTTPException(409, 'invalid_member_action')
            remove_member_content(session, group_id, body.user_id)
            audit(session, user['id'], 'group', group_id, 'member_removed')
            return {'revision': group.revision}

    @app.post('/api/groups/{group_id}/transfer')
    def transfer(group_id: str, body: MemberAction, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            if body.user_id == user['id'] or not session.get(Member, (group_id, body.user_id)):
                raise HTTPException(409, 'invalid_member_action')
            active_actor(session, body.user_id)
            group.owner_id = body.user_id
            session.execute(update(Invite).where(Invite.group_id == group_id).values(status='revoked', token_hash=None))
            audit(session, user['id'], 'group', group_id, 'ownership_transferred')
            return group_payload(group, user['id'])

    @app.post('/api/groups/{group_id}/archive')
    def archive(group_id: str, body: Revision, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision, owner=True)
            group.status = 'archived'
            session.execute(update(Invite).where(Invite.group_id == group_id).values(status='revoked', token_hash=None))
            audit(session, user['id'], 'group', group_id, 'archived')
            return group_payload(group, user['id'])

    @app.post('/api/groups/{group_id}/tasks', status_code=201)
    def create_task(group_id: str, body: NewTask, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_task', 60)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision)
            if not session.get(Place, body.place_id):
                raise HTTPException(404, 'place_not_found')
            if session.scalar(select(func.count()).select_from(Task).where(Task.group_id == group_id)) >= MAX_TASKS:
                raise HTTPException(409, 'task_limit')
            task = Task(group_id=group_id, author_id=user['id'], **body.model_dump(exclude={'expected_revision'}))
            session.add(task); session.flush()
            audit(session, user['id'], 'group_task', task.id, 'created')
            return {'task': task_payload(session, task, user['id']), 'revision': group.revision}

    @app.post('/api/groups/{group_id}/tasks/{task_id}')
    def change_task(group_id: str, task_id: str, body: TaskAction, request: Request, user=Depends(current_user)):
        rate_limit(request, 'group_mutation', 120)
        with database.session() as session:
            active_actor(session, user['id'], lock=True)
            group = group_for(session, group_id, user['id'], revision=body.expected_revision)
            task = session.get(Task, task_id)
            if not task or task.group_id != group_id:
                raise HTTPException(404, 'task_not_found')
            mine, action = task.assignee_id == user['id'], body.action
            if action == 'claim' and task.state == 'open' and task.assignee_id is None:
                task.assignee_id, task.state = user['id'], 'in_progress'
            elif action == 'release' and mine and task.state in ('in_progress', 'changes_requested'):
                task.assignee_id = task.observation_id = task.review_note = task.reviewer_id = None
                task.state = 'open'
            elif action == 'submit' and mine and task.state in ('in_progress', 'changes_requested'):
                if not body.share_with_group or not body.observation_id:
                    raise HTTPException(422, 'private_share_confirmation_required')
                with session.no_autoflush:
                    task.observation_id = body.observation_id
                    if not visible_observation(session, task):
                        raise HTTPException(422, 'observation_not_shareable')
                task.state, task.review_note, task.reviewer_id = 'submitted', None, None
            elif action in ('accept', 'request_changes') and task.state == 'submitted':
                if mine:
                    raise HTTPException(403, 'independent_review_required')
                if not visible_observation(session, task):
                    raise HTTPException(409, 'evidence_unavailable')
                if len(body.note.strip()) < 10:
                    raise HTTPException(422, 'review_note_required')
                task.state = 'accepted' if action == 'accept' else 'changes_requested'
                task.review_note, task.reviewer_id = body.note.strip(), user['id']
            elif action == 'reopen' and (mine or group.owner_id == user['id']) and task.state in ('accepted', 'submitted', 'changes_requested'):
                task.state = 'in_progress' if task.assignee_id else 'open'
                task.observation_id = task.review_note = task.reviewer_id = None
            elif action == 'cancel' and (task.author_id == user['id'] or group.owner_id == user['id']) and task.state != 'cancelled':
                task.state = 'cancelled'
                task.observation_id = task.review_note = task.reviewer_id = None
            else:
                raise HTTPException(409, 'task_transition_conflict')
            task.revision += 1
            task.updated_at = now()
            audit(session, user['id'], 'group_task', task.id, action, revision=task.revision)
            session.flush()
            return {'task': task_payload(session, task, user['id']), 'revision': group.revision}
