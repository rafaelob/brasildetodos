# SPDX-License-Identifier: AGPL-3.0-or-later
"""Decode actual JPEG/PNG bytes; generated images are confined to this test suite."""
import base64
from datetime import date, timedelta
from io import BytesIO
import hashlib

from PIL import Image, PngImagePlugin
import pytest

from bdt import photos


def picture(format='PNG', size=(160, 120), mode='RGB', color='white', **save):
    out = BytesIO()
    with Image.new(mode, size, color) as image:
        image.save(out, format=format, **save)
    return base64.b64encode(out.getvalue()).decode()


def test_png_text_exif_and_input_trailer_are_not_retained():
    metadata = PngImagePlugin.PngInfo(); metadata.add_text('Private', 'private metadata never forwarded')
    encoded = picture(pnginfo=metadata)
    raw = base64.b64decode(encoded) + b'private trailing content'
    result = photos.sanitize(base64.b64encode(raw).decode(), [])
    assert result['content'][:2] == b'\xff\xd8'
    assert b'private' not in result['content']
    assert result['sha256'] == hashlib.sha256(result['content']).hexdigest()
    with Image.open(BytesIO(result['content'])) as decoded:
        decoded.load()
        assert decoded.format == 'JPEG' and decoded.size == (160, 120)
        assert not decoded.getexif() and 'Private' not in decoded.info
    assert result['masks_applied'] is False


def test_jpeg_orientation_corrected_then_metadata_removed():
    exif = Image.Exif(); exif[274] = 6; exif[315] = 'private author'
    result = photos.sanitize(picture('JPEG', exif=exif), [])
    assert (result['width'], result['height']) == (120, 160)
    with Image.open(BytesIO(result['content'])) as decoded:
        assert not decoded.getexif()
    assert b'private author' not in result['content']


def test_opaque_mask_covers_the_selected_region_not_whole_image():
    result = photos.sanitize(picture(), [photos.Mask(x=.25, y=.25, width=.5, height=.5)])
    assert result['masks_applied']
    with Image.open(BytesIO(result['content'])) as image:
        assert max(image.getpixel((80, 60))) < 10
        assert min(image.getpixel((5, 5))) > 240


def test_transparent_image_is_composited_and_large_image_is_bounded():
    result = photos.sanitize(picture(size=(3000, 1000), mode='RGBA', color=(255, 0, 0, 0)), [])
    assert result['width'] == 2048 and result['height'] <= 683
    with Image.open(BytesIO(result['content'])) as image:
        assert min(image.getpixel((20, 20))) > 240


@pytest.mark.parametrize('encoded', ['not_base64!', 'data:image/png;base64,aaaa', base64.b64encode(b'<svg>not an image</svg>').decode(), picture('GIF')])
def test_rejects_non_images_and_unsupported_formats(encoded):
    with pytest.raises(ValueError): photos.sanitize(encoded, [])


def test_truncated_jpeg_rejected():
    raw = base64.b64decode(picture('JPEG'))
    with pytest.raises(ValueError): photos.sanitize(base64.b64encode(raw[:len(raw)//2]).decode(), [])


def test_animated_png_rejected():
    one = Image.new('RGB', (20, 20), 'red'); two = Image.new('RGB', (20, 20), 'blue')
    out = BytesIO(); one.save(out, format='PNG', save_all=True, append_images=[two], duration=100)
    with pytest.raises(ValueError): photos.sanitize(base64.b64encode(out.getvalue()).decode(), [])
    one.close(); two.close()


@pytest.mark.parametrize('size', [(15, 100), (100, 15), (4000, 4000)])
def test_dimension_budget_before_decode(size):
    with pytest.raises(ValueError, match='dimensions'): photos.sanitize(picture(size=size), [])


def test_encoded_budget_and_output_budget(monkeypatch):
    with pytest.raises(ValueError, match='size'): photos.sanitize('a' * (photos.MAX_ENCODED_CHARS + 1), [])
    monkeypatch.setattr(photos, 'MAX_OUTPUT_BYTES', 1)
    with pytest.raises(ValueError, match='size'): photos.sanitize(picture(), [])


@pytest.mark.parametrize('key,value', [('x', -1), ('x', True), ('x', '0.1'), ('y', float('nan')), ('width', 0), ('height', float('inf')), ('width', 1.1)])
def test_invalid_masks_rejected(key, value):
    values = dict(x=0, y=0, width=.5, height=.5); values[key] = value
    with pytest.raises(ValueError): photos.Mask(**values)


def test_mask_bounds_and_count():
    with pytest.raises(ValueError): photos.Mask(x=.8, y=0, width=.4, height=1)
    mask = photos.Mask(x=0, y=0, width=1, height=1)
    with pytest.raises(ValueError): photos.sanitize(picture(), [mask] * 21)


def body(**overrides):
    return dict(observation_id='a'*36, caption='Synthetic facade', credit='Test author',
                captured_on='2025-01-01', license='CC-BY-4.0', privacy_confirmed=True,
                image_base64=picture()) | overrides


@pytest.mark.parametrize('change', [dict(caption='  '), dict(credit='x\x00y'), dict(license='unknown'), dict(privacy_confirmed=False),
    dict(captured_on=(date.today()+timedelta(days=1)).isoformat()), dict(captured_on='1899-12-31'), dict(extra='forbidden')])
def test_submission_contract(change):
    with pytest.raises(ValueError): photos.PhotoInput(**body(**change))


def test_purge_limit_and_schema_version(database):
    photos.initialize(database)
    for limit in (True, 0, 1001):
        with pytest.raises(ValueError): photos.purge_expired(database, limit=limit)
    with pytest.raises(ValueError): photos.purge_expired(database, at=-1)
    with database.engine.begin() as conn:
        conn.execute(photos.PhotoVersion.__table__.update().values(version=2))
    with pytest.raises(RuntimeError): photos.initialize(database)


@pytest.mark.parametrize('value', [1, 'true', 'on', False, None])
def test_consent_is_not_coerced(value):
    with pytest.raises(ValueError): photos.PhotoInput(**body(privacy_confirmed=value))
