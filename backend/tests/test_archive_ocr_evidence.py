"""Archive validation uses newly generated test bytes; production pins never change."""
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
TEXT='DOCUMENTO SINTETICO PARA TESTE\nCONVENIO 977950/2025\nPROPOSTA 036806/2025\nVALOR ESTIMADO: R$ 3.642.610,56\nATE 170 CRIANCAS\nDados ficticios, sem validade administrativa.'

@pytest.fixture
def archiver(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'ops'))
    return importlib.import_module('archive_ocr_evidence')

@pytest.fixture
def corpus(archiver,tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir()
    native=canvas.Canvas(str(source/'SYNTHETIC-native.pdf'),pagesize=(600,800))
    for i,line in enumerate(TEXT.splitlines()):native.drawString(30,760-i*25,line)
    native.save()
    image=source/'SYNTHETIC-page.png';Image.new('RGB',(600,800),'white').save(image)
    scanned=canvas.Canvas(str(source/'SYNTHETIC-scanned.pdf'),pagesize=(600,800))
    scanned.drawImage(str(image),0,0,width=600,height=800);scanned.save()
    evidence={'fixture':'synthetic-scanned-Portuguese','official_corpus_evaluated':False,
        'revision':archiver.SOURCE['revision'],'expected_fields':archiver.FIELDS,
        'result':{'original_preserved':True,'public':False,'original_sha256':hashlib.sha256((source/'SYNTHETIC-scanned.pdf').read_bytes()).hexdigest()},
        'recognized_test_text':TEXT}
    (source/'result.json').write_text(json.dumps(evidence))
    expected={p.name:(p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest()) for p in source.iterdir()}
    monkeypatch.setattr(archiver,'EXPECTED',expected)
    return source


def test_archive_preserves_original_bytes_and_revalidates_without_ocr(archiver,corpus,tmp_path,monkeypatch):
    import bdt.documents
    monkeypatch.setattr(bdt.documents,'ocr_page',lambda *args,**kwargs:pytest.fail('archive must not rerun OCR'))
    target=tmp_path/'out'
    report=archiver.archive(corpus,target)
    assert report['files']==6 and report['originals']==4
    assert report['official_corpus'] is False and report['ocr_executed'] is False
    for name in archiver.EXPECTED:assert (target/name).read_bytes()==(corpus/name).read_bytes()
    manifest=json.loads((target/'manifest.json').read_text())
    assert not manifest['production_import_allowed'] and not manifest['official_document']
    assert manifest['source']==archiver.SOURCE
    assert archiver.archive(corpus,target)['already_present']
    assert archiver.verify(target)['status']=='passed'

@pytest.mark.parametrize('failure',['extra','missing','changed','symlink','directory'])
def test_unreviewed_or_corrupt_input_never_publishes(archiver,corpus,tmp_path,failure):
    p=corpus/'SYNTHETIC-native.pdf'
    if failure=='extra':(corpus/'private.txt').write_text('not reviewed')
    elif failure=='missing':p.unlink()
    elif failure=='changed':p.write_bytes(p.read_bytes()+b'\n')
    elif failure=='symlink':
        p.rename(tmp_path/'elsewhere.pdf');p.symlink_to(tmp_path/'elsewhere.pdf')
    else:p.unlink();p.mkdir()
    with pytest.raises((ValueError,OSError)):archiver.archive(corpus,tmp_path/'out')
    assert not (tmp_path/'out').exists()

@pytest.mark.parametrize('field,value',[('official_corpus_evaluated',True),('revision','a'*40),('expected_fields',{}),('recognized_test_text','Unlabelled content')])
def test_inconsistent_original_report_refused_even_with_matching_bytes(archiver,corpus,tmp_path,monkeypatch,field,value):
    p=corpus/'result.json';data=json.loads(p.read_text());data[field]=value;p.write_text(json.dumps(data))
    pins=dict(archiver.EXPECTED);pins[p.name]=(p.stat().st_size,hashlib.sha256(p.read_bytes()).hexdigest());monkeypatch.setattr(archiver,'EXPECTED',pins)
    with pytest.raises(ValueError):archiver.archive(corpus,tmp_path/'out')
    assert not (tmp_path/'out').exists()

@pytest.mark.parametrize('file',['recognized-text.txt','native-extraction.json','manifest.json'])
def test_tampered_output_not_accepted_or_replaced(archiver,corpus,tmp_path,file):
    target=tmp_path/'out';archiver.archive(corpus,target)
    p=target/file;p.write_text('{}');saved=p.read_bytes()
    with pytest.raises(ValueError):archiver.archive(corpus,target)
    assert p.read_bytes()==saved


def test_destination_collision_is_never_overwritten(archiver,corpus,tmp_path):
    target=tmp_path/'out';target.mkdir();(target/'keep').write_text('existing')
    with pytest.raises(ValueError):archiver.archive(corpus,target)
    assert (target/'keep').read_text()=='existing'


def test_input_directory_symlink_is_not_followed(archiver,corpus,tmp_path):
    target=tmp_path/'link';target.symlink_to(corpus,target_is_directory=True)
    with pytest.raises(ValueError,match='folder_invalid'):archiver.archive(target,tmp_path/'out')


def test_file_budget_and_fifo_fail_without_blocking(archiver,tmp_path,monkeypatch):
    p=tmp_path/'large';p.write_bytes(b'1234');monkeypatch.setattr(archiver,'MAX_FILE_BYTES',2)
    with pytest.raises(ValueError,match='budget'):archiver.read_regular(p)
    if hasattr(os, 'mkfifo'):
        fifo=tmp_path/'pipe';os.mkfifo(fifo)
        with pytest.raises(ValueError,match='type'):archiver.read_regular(fifo)


def test_cli_requires_destination_and_emits_only_manifest_result(archiver,corpus,tmp_path,capsys):
    with pytest.raises(SystemExit):archiver.main(['archive',str(corpus)])
    capsys.readouterr()
    archiver.main(['archive',str(corpus),'--destination',str(tmp_path/'out')])
    output=capsys.readouterr().out
    assert json.loads(output)['status']=='passed'
    assert 'CONVENIO' not in output
    archiver.main(['verify',str(tmp_path/'out')]);assert json.loads(capsys.readouterr().out)['status']=='passed'
