# SPDX-License-Identifier: AGPL-3.0-or-later
"""Photo HTTP: disabled by default; dual-control publication; no EXIF retention."""
import base64
from io import BytesIO
import logging

from PIL import Image
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select

from bdt.api import create_app, password_hash
from bdt.storage import Observation, User
from test_photos import picture

HEAD = {'X-BDT-Client': 'web'}
PASSWORD = 'synthetic-password-only'
NOTE = 'Independent privacy review of this synthetic photograph.'
OBSERVATION = {'place_id': 'test:school', 'mode': 'field', 'observed_on': '2025-01-01',
               'body': 'Synthetic description of the sign at the public entrance.', 'consent': True}


@pytest.fixture
def client(database, stored, monkeypatch):
    monkeypatch.setenv('BDT_ALLOW_REGISTRATION', '1')
    app = create_app(str(database.engine.url), testing=True)
    with TestClient(app) as client:
        yield client


def enable(monkeypatch):
    monkeypatch.setenv('BDT_PHOTO_UPLOADS', '1')


def register(client, name='reader'):
    assert client.post('/api/auth/register', headers=HEAD, json={'username': name, 'password': PASSWORD}).status_code == 201


def login(client, name='reader'):
    assert client.post('/api/auth/login', headers=HEAD, json={'username': name, 'password': PASSWORD}).status_code == 200


def add_reviewer(database, name='reviewer'):
    with database.session() as session:
        session.add(User(username=name, password_hash=password_hash(PASSWORD), role='reviewer'))


def observe(client):
    response = client.post('/api/observations', headers=HEAD, json=OBSERVATION)
    assert response.status_code == 201
    return response.json()['id']


def payload(observation_id, image=None):
    return {'observation_id': observation_id, 'caption': 'Synthetic facade of the public entrance.',
            'credit': 'Test author', 'captured_on': '2025-01-01', 'license': 'CC-BY-4.0',
            'privacy_confirmed': True, 'image_base64': image or picture()}


def review_body(photo, decision='approved'):
    return {'decision': decision, 'expected_revision': photo['revision'], 'sha256': photo['sha256'],
            'note': NOTE, 'privacy_checked': decision == 'approved'}


def noisy_jpeg(minimum=40000):
    side = 240
    while side <= 900:
        out = BytesIO()
        image = Image.new('RGB', (side, side))
        pixels = image.load()
        for x in range(side):
            for y in range(side):
                pixels[x, y] = ((x * 37 + y * 19) % 256, (x * 11) % 256, (y * 23) % 256)
        image.save(out, format='JPEG', quality=92)
        encoded = base64.b64encode(out.getvalue()).decode()
        image.close()
        if len(encoded) >= minimum:
            return encoded
        side += 80
    raise RuntimeError('synthetic JPEG stayed under the 32KiB request cap')


def test_photo_uploads_disabled_by_default(client):
    assert client.get('/api/config').json()['photo_uploads'] is False
    register(client)
    login(client)
    observation_id = observe(client)
    response = client.post('/api/photos', headers=HEAD, json=payload(observation_id))
    assert response.status_code == 404
    assert response.json() == {'detail': 'photo_uploads_disabled'}


@pytest.mark.parametrize('value,expected', [(None, False), ('', False), ('0', False),
                                            ('true', False), ('yes', False), ('2', False), ('1', True)])
def test_config_photo_uploads_true_only_when_env_is_1(client, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('BDT_PHOTO_UPLOADS', raising=False)
    else:
        monkeypatch.setenv('BDT_PHOTO_UPLOADS', value)
    assert client.get('/api/config').json()['photo_uploads'] is expected


def test_upload_stays_private_until_photo_and_observation_are_approved(client, database, monkeypatch, caplog):
    enable(monkeypatch)
    caplog.set_level(logging.INFO)
    register(client)
    login(client)
    observation_id = observe(client)
    created = client.post('/api/photos', headers=HEAD, json=payload(observation_id))
    assert created.status_code == 201
    photo = created.json()
    assert photo['state'] == 'pending' and photo['public'] is False
    assert photo['official_record'] is False
    assert 'Synthetic facade' not in caplog.text
    photo_id = photo['id']
    assert client.get(f'/api/public/photos/{photo_id}/image').status_code == 404
    private = client.get(f'/api/photos/{photo_id}/image')
    assert private.status_code == 200
    assert private.headers['content-type'].startswith('image/jpeg')
    assert private.content[:2] == b'\xff\xd8'
    assert private.headers.get('cache-control') == 'no-store'
    add_reviewer(database)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    approved_photo = client.post(f'/api/photos/{photo_id}/review', headers=HEAD, json=review_body(photo))
    assert approved_photo.status_code == 200
    assert approved_photo.json()['state'] == 'approved'
    assert client.get(f'/api/public/photos/{photo_id}/image').status_code == 404
    with database.session() as session:
        assert session.get(Observation, observation_id).status == 'pending'
    observation_review = client.post(
        f'/api/review/{observation_id}', headers=HEAD,
        json={'decision': 'approved', 'note': 'Checked synthetic statement for this test.'})
    assert observation_review.status_code == 200
    assert observation_review.json()['status'] == 'approved'
    public = client.get(f'/api/public/photos/{photo_id}/image')
    assert public.status_code == 200
    assert public.headers['content-type'].startswith('image/jpeg')
    assert public.content[:2] == b'\xff\xd8'


def test_exif_is_not_present_in_stored_jpeg(client, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    exif = Image.Exif()
    exif[274] = 1
    exif[315] = 'private author'
    created = client.post('/api/photos', headers=HEAD, json=payload(observation_id, picture('JPEG', exif=exif)))
    assert created.status_code == 201
    stored = client.get(f'/api/photos/{created.json()["id"]}/image')
    assert stored.status_code == 200
    assert b'private author' not in stored.content
    with Image.open(BytesIO(stored.content)) as decoded:
        decoded.load()
        assert decoded.format == 'JPEG' and not decoded.getexif()


def test_author_cannot_approve_own_photo(client, database, monkeypatch):
    enable(monkeypatch)
    add_reviewer(database)
    login(client, 'reviewer')
    observation_id = observe(client)
    photo = client.post('/api/photos', headers=HEAD, json=payload(observation_id)).json()
    response = client.post(f'/api/photos/{photo["id"]}/review', headers=HEAD, json=review_body(photo))
    assert response.status_code == 403
    assert response.json() == {'detail': 'self_review_forbidden'}
    assert client.get(f'/api/public/photos/{photo["id"]}/image').status_code == 404


def test_retracted_observation_cannot_receive_new_photo(client, database, monkeypatch):
    enable(monkeypatch)
    register(client)
    add_reviewer(database)
    login(client)
    observation_id = observe(client)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    assert client.post(
        f'/api/review/{observation_id}',
        headers=HEAD,
        json={'decision': 'approved', 'note': 'Independent review of synthetic evidence.'},
    ).status_code == 200
    assert client.post(
        f'/api/moderation/observations/{observation_id}/retract',
        headers=HEAD,
        json={'note': 'Publication retracted after additional contextual review.'},
    ).status_code == 200
    client.post('/api/auth/logout', headers=HEAD)
    login(client)

    response = client.post('/api/photos', headers=HEAD, json=payload(observation_id))
    assert response.status_code == 404
    assert response.json() == {'detail': 'observation_not_found'}
    with database.session() as session:
        from bdt.photos import Photo
        assert session.scalar(select(func.count()).select_from(Photo)) == 0


def test_csrf_required_to_upload(client, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    assert client.post('/api/photos', json=payload(observation_id)).status_code == 403


def test_public_image_404_when_flag_turned_off(client, database, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    photo = client.post('/api/photos', headers=HEAD, json=payload(observation_id)).json()
    add_reviewer(database)
    client.post('/api/auth/logout', headers=HEAD)
    login(client, 'reviewer')
    assert client.post(f'/api/photos/{photo["id"]}/review', headers=HEAD, json=review_body(photo)).status_code == 200
    assert client.post(f'/api/review/{observation_id}', headers=HEAD,
                       json={'decision': 'approved', 'note': 'Checked synthetic statement for this test.'}
                       ).status_code == 200
    assert client.get(f'/api/public/photos/{photo["id"]}/image').status_code == 200
    monkeypatch.delenv('BDT_PHOTO_UPLOADS', raising=False)
    hidden = client.get(f'/api/public/photos/{photo["id"]}/image')
    assert hidden.status_code == 404
    assert hidden.json() == {'detail': 'photo_uploads_disabled'}
    assert client.get('/api/config').json()['photo_uploads'] is False


def test_fourth_photo_on_same_observation_is_conflict(client, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    for _ in range(3):
        assert client.post('/api/photos', headers=HEAD, json=payload(observation_id)).status_code == 201
    fourth = client.post('/api/photos', headers=HEAD, json=payload(observation_id))
    assert fourth.status_code == 409
    assert 'quota' in fourth.json()['detail']


def test_enabled_upload_may_exceed_global_32kib_cap(client, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    image = noisy_jpeg()
    body = payload(observation_id, image)
    assert len(base64.b64decode(image)) > 16
    large = client.post('/api/photos', headers=HEAD, json=body)
    assert large.status_code == 201
    monkeypatch.delenv('BDT_PHOTO_UPLOADS', raising=False)
    blocked = client.post('/api/photos', headers=HEAD, json=body)
    assert blocked.status_code == 413
    assert blocked.json() == {'detail': 'request_too_large'}


def test_withdraw_and_account_delete_erase_photo_bytes(client, database, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    first = observe(client)
    photo = client.post('/api/photos', headers=HEAD, json=payload(first)).json()
    exported = client.get('/api/account/export').json()
    assert exported['photos'][0]['id'] == photo['id']
    assert 'content' not in exported['photos'][0]
    assert client.post(f'/api/observations/{first}/withdraw', headers=HEAD).status_code == 200
    with database.session() as session:
        from bdt.photos import Photo, PhotoContent
        stored = session.get(Photo, photo['id'])
        assert stored.bytes == 0 and session.get(PhotoContent, photo['id']) is None
    second = observe(client)
    later = client.post('/api/photos', headers=HEAD, json=payload(second)).json()
    assert client.post('/api/account/delete', headers=HEAD,
                       json={'password': PASSWORD, 'confirmed': True}).status_code == 200
    with database.session() as session:
        from bdt.photos import Photo, PhotoContent
        stored = session.get(Photo, later['id'])
        assert stored.bytes == 0 and session.get(PhotoContent, later['id']) is None


def test_private_routes_are_not_available_to_other_accounts(client, monkeypatch):
    enable(monkeypatch)
    register(client)
    login(client)
    observation_id = observe(client)
    photo = client.post('/api/photos', headers=HEAD, json=payload(observation_id)).json()
    client.post('/api/auth/logout', headers=HEAD)
    assert client.get(f'/api/photos/{photo["id"]}').status_code == 401
    assert client.get(f'/api/photos/{photo["id"]}/image').status_code == 401
    register(client, 'other')
    login(client, 'other')
    assert client.get(f'/api/photos/{photo["id"]}').status_code == 404
    assert client.get(f'/api/photos/{photo["id"]}/image').status_code == 404
    assert client.get(f'/api/public/photos/{photo["id"]}/image').status_code == 404
