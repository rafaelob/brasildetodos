# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import prepare_photo as command
from test_photos import picture


def test_actual_derivative_written_without_changing_original(tmp_path):
    source=tmp_path/'source.png';source.write_bytes(base64.b64decode(picture()))
    before=source.read_bytes();target=tmp_path/'out.jpg'
    result=command.prepare(source,target,masks=[dict(x=.25,y=.25,width=.5,height=.5)])
    assert source.read_bytes()==before and result['sha256']==hashlib.sha256(target.read_bytes()).hexdigest()
    with Image.open(target) as image: assert max(image.getpixel((80,60)))<10 and not image.getexif()
    assert not result['uploaded'] and not result['approved'] and not result['original_stored']
    if os.name!='nt': assert target.stat().st_mode & 0o777==0o600


@pytest.mark.parametrize('kind',['file','symlink','directory'])
def test_destination_never_overwritten(tmp_path,kind):
    source=tmp_path/'source.png';source.write_bytes(base64.b64decode(picture()));target=tmp_path/'out'
    if kind=='file':target.write_bytes(b'previous')
    elif kind=='directory':target.mkdir()
    else:target.symlink_to(tmp_path/'absent')
    with pytest.raises(FileExistsError):command.prepare(source,target)
    if kind=='file':assert target.read_bytes()==b'previous'


def test_output_race_and_bad_input_leave_no_temporary_files(tmp_path,monkeypatch):
    source=tmp_path/'source';source.write_bytes(base64.b64decode(picture()));target=tmp_path/'out'
    original=command.os.link
    def race(src,dst):Path(dst).write_bytes(b'another operator');return original(src,dst)
    monkeypatch.setattr(command.os,'link',race)
    with pytest.raises(FileExistsError):command.prepare(source,target)
    assert target.read_bytes()==b'another operator' and not list(tmp_path.glob('.bdt-photo-*'))
    source.write_bytes(b'not a photograph')
    with pytest.raises(ValueError):command.prepare(source,tmp_path/'invalid.jpg')
    assert not (tmp_path/'invalid.jpg').exists()


def test_cli_receipt_has_no_source_path_and_masks_are_bounded(tmp_path,capsys):
    source=tmp_path/'private_filename.png';source.write_bytes(base64.b64decode(picture()))
    masks=tmp_path/'masks.json';masks.write_text('[{"x":0,"y":0,"width":0.2,"height":0.2}]')
    result=command.main([str(source),'--output',str(tmp_path/'out.jpg'),'--masks',str(masks)])
    output=capsys.readouterr().out
    assert json.loads(output)==result and str(tmp_path) not in output and 'private_filename' not in output
    masks.write_text('{}')
    with pytest.raises(ValueError):command.main([str(source),'--output',str(tmp_path/'other.jpg'),'--masks',str(masks)])
    masks.write_text(' '*32769)
    with pytest.raises(ValueError):command.main([str(source),'--output',str(tmp_path/'other.jpg'),'--masks',str(masks)])
