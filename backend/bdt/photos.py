# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bounded, private photo evidence. Only re-encoded derivatives are retained.

A photo is not an official fact, and its approval never approves its observation.
Storage is relational so removing bytes and metadata can share a transaction.
"""
from __future__ import annotations

import base64
import binascii
from datetime import date
import hashlib
from io import BytesIO
import logging
import math
import time
from typing import Literal
from uuid import uuid4
import warnings

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pydantic import Field, field_validator, model_validator
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, LargeBinary, String, Text, delete, func, or_, select, update

from .domain import StrictModel, now
from .storage import Base, Observation, User

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_ENCODED_CHARS = 4 * ((MAX_INPUT_BYTES + 2) // 3)
MAX_REQUEST_BYTES = MAX_ENCODED_CHARS + 32768
MAX_PIXELS = 12_000_000
MAX_SIDE = 2048
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_PER_OBSERVATION = 3
MAX_PER_USER = 20
MAX_USER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
UNPUBLISHED_TTL = 30 * 24 * 3600
ACTIVE_STATES = ('pending', 'approved', 'rejected')
log = logging.getLogger('bdt.photos')


class PhotoVersion(Base):
    __tablename__ = 'photo_schema_version'
    id = Column(Integer, primary_key=True)
    version = Column(Integer, nullable=False)


class Photo(Base):
    __tablename__ = 'evidence_photos'
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    observation_id = Column(String(36), ForeignKey('observations.id'), nullable=False, index=True)
    author_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    state = Column(String(20), nullable=False, default='pending', index=True)
    revision = Column(Integer, nullable=False, default=1)
    caption = Column(String(280), nullable=False)
    credit = Column(String(80), nullable=False)
    captured_on = Column(String(10))
    license = Column(String(20), nullable=False, default='CC-BY-4.0')
    sha256 = Column(String(64), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    bytes = Column(Integer, nullable=False)
    masks_applied = Column(Boolean, nullable=False, default=False)
    created_at = Column(String(40), nullable=False, default=now)
    expires_at = Column(BigInteger, nullable=False)
    reviewer_id = Column(String(36), ForeignKey('users.id'))
    reviewed_at = Column(String(40))
    review_note = Column(Text)


class PhotoContent(Base):
    __tablename__ = 'photo_content'
    photo_id = Column(String(36), ForeignKey('evidence_photos.id'), primary_key=True)
    content = Column(LargeBinary, nullable=False)


def initialize(database):
    """Additive, version-checked schema. No changes to existing source records."""
    with database.engine.begin() as connection:
        PhotoVersion.__table__.create(connection, checkfirst=True)
        version = connection.execute(select(PhotoVersion.version).where(PhotoVersion.id == 1)).scalar_one_or_none()
        if version not in (None, 1):
            raise RuntimeError('unsupported_photo_schema')
        for model in (Photo, PhotoContent):
            model.__table__.create(connection, checkfirst=True)
        if version is None:
            connection.execute(PhotoVersion.__table__.insert().values(id=1, version=1))


def lock_budget(session):
    # All photo mutations use this row; quotas cannot race across different users.
    changed = session.execute(update(PhotoVersion).where(PhotoVersion.id == 1, PhotoVersion.version == 1)
                              .values(version=PhotoVersion.version))
    if changed.rowcount != 1:
        raise RuntimeError('unsupported_photo_schema')


def readable(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('invalid_photo_text')
    return value.strip()


class Mask(StrictModel):
    x: float = Field(ge=0, lt=1, allow_inf_nan=False)
    y: float = Field(ge=0, lt=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)

    @field_validator('x', 'y', 'width', 'height', mode='before')
    @classmethod
    def numbers_only(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('invalid_photo_mask')
        return value

    @model_validator(mode='after')
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError('photo_mask_outside_image')
        return self


class PhotoInput(StrictModel):
    observation_id: str = Field(pattern=r'^[a-f0-9-]{36}$')
    caption: str = Field(min_length=5, max_length=280)
    credit: str = Field(min_length=2, max_length=80)
    captured_on: date
    license: Literal['CC-BY-4.0']
    privacy_confirmed: Literal[True]
    image_base64: str = Field(min_length=16, max_length=MAX_ENCODED_CHARS)
    masks: list[Mask] = Field(default_factory=list, max_length=20)

    @field_validator('privacy_confirmed', mode='before')
    @classmethod
    def actual_consent(cls, value):
        if value is not True:
            raise ValueError('photo_consent_required')
        return value

    @field_validator('caption', 'credit', mode='before')
    @classmethod
    def text(cls, value):
        return readable(value)

    @field_validator('captured_on')
    @classmethod
    def past_or_present(cls, value):
        if value > date.today() or value.year < 1900:
            raise ValueError('invalid_photo_date')
        return value


class PhotoReview(StrictModel):
    decision: Literal['approved', 'rejected', 'retracted']
    expected_revision: int = Field(ge=1, strict=True)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    note: str = Field(min_length=20, max_length=1000)
    privacy_checked: bool = Field(default=False, strict=True)

    @field_validator('note', mode='before')
    @classmethod
    def text(cls, value):
        return readable(value)


class PhotoRemoval(StrictModel):
    confirmed: Literal[True]


def sanitize(encoded: str, masks: list[Mask]) -> dict:
    """JPEG/PNG only, bounded decode, opaque masks, fresh RGB JPEG without metadata.

    This is not face detection, malware scanning or certification of anonymity.
    Mandatory independent human review remains a separate publication gate.
    """
    if not isinstance(encoded, str) or len(encoded) > MAX_ENCODED_CHARS:
        raise ValueError('photo_size_limit')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('invalid_photo_image') from None
    if not 16 <= len(raw) <= MAX_INPUT_BYTES:
        raise ValueError('photo_size_limit')
    if len(masks) > 20:
        raise ValueError('photo_mask_limit')
    # Revalidate even when called outside the API.
    masks = [Mask.model_validate(mask) for mask in masks]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=['JPEG', 'PNG']) as probe:
                if (probe.width < 16 or probe.height < 16 or probe.width * probe.height > MAX_PIXELS
                        or getattr(probe, 'n_frames', 1) != 1):
                    raise ValueError('photo_dimensions_limit')
                probe.verify()
            with Image.open(BytesIO(raw), formats=['JPEG', 'PNG']) as original:
                original.load()
                oriented = ImageOps.exif_transpose(original)
                try:
                    # Copy pixels into a new image: EXIF, comments, ICC, XMP and text are not forwarded.
                    image = Image.new('RGB', oriented.size, 'white')
                    if 'A' in oriented.getbands() or 'transparency' in oriented.info:
                        rgba = oriented.convert('RGBA')
                        image.paste(rgba, mask=rgba.getchannel('A'))
                        rgba.close()
                    else:
                        image.paste(oriented.convert('RGB'))
                finally:
                    oriented.close()
            try:
                draw = ImageDraw.Draw(image)
                for mask in masks:
                    left, top = math.floor(mask.x * image.width), math.floor(mask.y * image.height)
                    right = min(image.width, math.ceil((mask.x + mask.width) * image.width))
                    bottom = min(image.height, math.ceil((mask.y + mask.height) * image.height))
                    draw.rectangle((left, top, right - 1, bottom - 1), fill='black')
                image.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
                result = BytesIO()
                image.save(result, format='JPEG', quality=85, optimize=False, subsampling=2)
                content = result.getvalue()
                if len(content) > MAX_OUTPUT_BYTES:
                    raise ValueError('photo_size_limit')
                return {'content': content, 'sha256': hashlib.sha256(content).hexdigest(),
                        'width': image.width, 'height': image.height, 'bytes': len(content),
                        'masks_applied': bool(masks)}
            finally:
                image.close()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        raise ValueError('invalid_photo_image') from None


def visible(photo, observation, author) -> bool:
    return bool(photo.state == 'approved' and observation.status == 'approved'
                and author.role != 'disabled' and photo.author_id == observation.author_id
                and not observation.payload.get('erased') and photo.bytes > 0)


def metadata(photo, observation, author, *, private=False) -> dict:
    result = {'id': photo.id, 'observation_id': photo.observation_id,
              'place_id': observation.place_id, 'caption': photo.caption,
              'credit': photo.credit, 'captured_on': photo.captured_on,
              'capture_date_user_reported': True, 'mode': 'field', 'license': photo.license,
              'sha256': photo.sha256, 'width': photo.width, 'height': photo.height,
              'bytes': photo.bytes, 'masks_applied': photo.masks_applied,
              'created_at': photo.created_at, 'reviewed_at': photo.reviewed_at,
              'official_record': False, 'public': visible(photo, observation, author)}
    if private:
        result.update(state=photo.state, revision=photo.revision,
                      expires_at=photo.expires_at, review_note=photo.review_note,
                      url=f'/api/photos/{photo.id}/image' if photo.bytes else None)
    else:
        result['url'] = f'/api/public/photos/{photo.id}/image'
    return result


def erase(session, rows, *, state='withdrawn') -> int:
    """Caller holds budget lock. No content or captions are copied into audit logs."""
    ids = [row.id for row in rows]
    if not ids:
        return 0
    session.execute(delete(PhotoContent).where(PhotoContent.photo_id.in_(ids)))
    session.execute(update(Photo).where(Photo.id.in_(ids)).values(
        state=state, caption='', credit='', captured_on=None, sha256='', bytes=0,
        width=0, height=0, masks_applied=False, review_note=None,
        revision=Photo.revision + 1))
    return len(ids)


def erase_observation(session, observation_id):
    lock_budget(session)
    return erase(session, session.scalars(select(Photo).where(Photo.observation_id == observation_id,
                                                            Photo.bytes > 0)).all())


def erase_account(session, user_id):
    lock_budget(session)
    return erase(session, session.scalars(select(Photo).where(Photo.author_id == user_id,
                                                            Photo.bytes > 0)).all())


def export_account(session, user_id):
    rows = session.execute(select(Photo, Observation, User).join(Observation, Photo.observation_id == Observation.id)
                           .join(User, Photo.author_id == User.id).where(Photo.author_id == user_id)
                           .order_by(Photo.created_at, Photo.id)).all()
    return [metadata(photo, observation, author, private=True) for photo, observation, author in rows]


def purge_expired(database, *, at: int | None = None, limit: int = 1000) -> int:
    """Operator job; remove expired unpublished photos in bounded transactions."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('invalid_photo_purge_limit')
    moment = int(time.time()) if at is None else at
    if type(moment) is not int or moment < 0:
        raise ValueError('invalid_photo_purge_time')
    with database.session() as session:
        lock_budget(session)
        rows = session.execute(select(Photo, Observation, User).join(Observation, Photo.observation_id == Observation.id)
            .join(User, Photo.author_id == User.id).where(Photo.bytes > 0, Photo.expires_at <= moment,
                or_(Photo.state != 'approved', Observation.status != 'approved', User.role == 'disabled',
                    Photo.author_id != Observation.author_id, Observation.payload['erased'].as_boolean() == True))
            .order_by(Photo.expires_at, Photo.id).limit(limit)).all()
        return erase(session, [p for p, o, u in rows if not visible(p, o, u)], state='expired')


def load(session, photo_id: str) -> tuple[Photo, Observation, User]:
    row = session.execute(select(Photo, Observation, User).join(Observation, Photo.observation_id == Observation.id)
                          .join(User, Photo.author_id == User.id).where(Photo.id == photo_id)).one_or_none()
    if row is None:
        raise ValueError('photo_not_found')
    return row[0], row[1], row[2]


def stored_bytes(session, photo: Photo) -> bytes:
    row = session.get(PhotoContent, photo.id)
    if row is None or photo.bytes <= 0 or not row.content:
        raise ValueError('photo_not_found')
    return row.content


def submit(session, body: PhotoInput, author_id: str) -> Photo:
    lock_budget(session)
    locked = session.execute(update(Observation).where(
        Observation.id == body.observation_id, Observation.author_id == author_id,
        Observation.status != 'withdrawn').values(place_id=Observation.place_id))
    if locked.rowcount != 1:
        raise ValueError('observation_not_found')
    observation = session.get(Observation, body.observation_id)
    if observation is None or observation.payload.get('erased'):
        raise ValueError('observation_not_found')
    per_observation = session.scalar(select(func.count()).select_from(Photo).where(
        Photo.observation_id == observation.id, Photo.bytes > 0)) or 0
    if per_observation >= MAX_PER_OBSERVATION:
        raise ValueError('photo_quota_observation')
    per_user = session.scalar(select(func.count()).select_from(Photo).where(
        Photo.author_id == author_id, Photo.bytes > 0)) or 0
    if per_user >= MAX_PER_USER:
        raise ValueError('photo_quota_user')
    derived = sanitize(body.image_base64, body.masks)
    user_bytes = int(session.scalar(select(func.coalesce(func.sum(Photo.bytes), 0)).where(
        Photo.author_id == author_id)) or 0)
    if user_bytes + derived['bytes'] > MAX_USER_BYTES:
        raise ValueError('photo_quota_user_bytes')
    total_bytes = int(session.scalar(select(func.coalesce(func.sum(Photo.bytes), 0))) or 0)
    if total_bytes + derived['bytes'] > MAX_TOTAL_BYTES:
        raise ValueError('photo_quota_total')
    photo = Photo(observation_id=observation.id, author_id=author_id, state='pending',
                  caption=body.caption, credit=body.credit, captured_on=body.captured_on.isoformat(),
                  license=body.license, sha256=derived['sha256'], width=derived['width'],
                  height=derived['height'], bytes=derived['bytes'], masks_applied=derived['masks_applied'],
                  expires_at=int(time.time()) + UNPUBLISHED_TTL)
    session.add(photo)
    session.flush()
    session.add(PhotoContent(photo_id=photo.id, content=derived['content']))
    session.flush()
    log.info('photo.submit photo_id=%s observation_id=%s size=%s', photo.id, observation.id, photo.bytes)
    return photo


def review_photo(session, photo_id: str, body: PhotoReview, reviewer_id: str) -> Photo:
    lock_budget(session)
    photo, _observation, _author = load(session, photo_id)
    if photo.author_id == reviewer_id:
        raise ValueError('self_review_forbidden')
    if body.decision == 'approved' and body.privacy_checked is not True:
        raise ValueError('photo_privacy_review_required')
    allowed = ((photo.state == 'pending' and body.decision in {'approved', 'rejected'})
               or (photo.state == 'approved' and body.decision == 'retracted'))
    if (not allowed or photo.revision != body.expected_revision or photo.sha256 != body.sha256
            or photo.bytes <= 0):
        raise ValueError('photo_revision_conflict')
    changed = session.execute(update(Photo).where(
        Photo.id == photo.id, Photo.revision == body.expected_revision, Photo.sha256 == body.sha256,
        Photo.state == photo.state, Photo.bytes > 0).values(
        state=body.decision, reviewer_id=reviewer_id, reviewed_at=now(), review_note=body.note,
        revision=body.expected_revision + 1))
    if changed.rowcount != 1:
        raise ValueError('photo_revision_conflict')
    session.refresh(photo)
    log.info('photo.review photo_id=%s decision=%s', photo.id, body.decision)
    return photo


def remove_photo(session, photo_id: str, body: PhotoRemoval, author_id: str) -> Photo:
    lock_budget(session)
    photo, _observation, _author = load(session, photo_id)
    if photo.author_id != author_id:
        raise ValueError('photo_not_found')
    if body.confirmed is not True:
        raise ValueError('photo_removal_unconfirmed')
    if photo.bytes > 0:
        erase(session, [photo])
        session.refresh(photo)
    log.info('photo.remove photo_id=%s', photo_id)
    return photo
