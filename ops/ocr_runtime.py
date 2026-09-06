"""One real Portuguese OCR pass on a clearly synthetic scanned fixture.

This proves engine/worker wiring, not accuracy on government documents. The
native source and scan are test artifacts only, never production seed data.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select

from bdt.document_job import ingest_document
from bdt.document_ocr import process_ocr
from bdt.evidence import Document, validate_excerpt
from bdt.storage import Database, User


def main():
    root=Path('test-results/ocr-runtime');root.mkdir(parents=True,exist_ok=True)
    source=root/'SYNTHETIC-native.pdf'
    document=canvas.Canvas(str(source),pagesize=A4)
    document.setTitle('SYNTHETIC OCR TEST - NOT A GOVERNMENT DOCUMENT')
    lines=['DOCUMENTO SINTETICO PARA TESTE', 'CONVENIO 977950/2025',
           'PROPOSTA 036806/2025', 'VALOR ESTIMADO: R$ 3.642.610,56',
           'ATÉ 170 CRIANÇAS', 'Sem validade administrativa. Dados fictícios.']
    document.setFont('Helvetica',17)
    for index,line in enumerate(lines):document.drawString(45,770-index*45,line)
    document.save()
    prefix=root/'SYNTHETIC-page'
    subprocess.run(['pdftoppm','-f','1','-l','1','-singlefile','-r','150','-png',str(source),str(prefix)],
                   check=True,capture_output=True,timeout=60)
    scan=root/'SYNTHETIC-scanned.pdf'
    document=canvas.Canvas(str(scan),pagesize=A4)
    document.drawImage(str(prefix)+'.png',0,0,width=A4[0],height=A4[1]);document.save()
    before=hashlib.sha256(scan.read_bytes()).hexdigest()
    database=Database('sqlite:///'+str(root/'private-test.db'));database.initialize()
    try:
        with database.session() as session:
            session.add(User(username='synthetic_ocr_operator',password_hash='not-a-login',role='reviewer'))
        registered=ingest_document(database,scan,operator='synthetic_ocr_operator',
            title='Synthetic Portuguese OCR fixture',dataset='synthetic-ocr-test-only',
            url='https://example.org/synthetic-not-official.pdf')
        with database.session() as session:
            extracted=session.get(Document,registered['document_id']).extraction
            assert extracted['pages'][0]['route']=='ocr_candidate'
            assert not extracted['pages'][0]['text'].strip()
        # Exactly one real OCR engine invocation. No broad corpus OCR in unit CI.
        result=process_ocr(database,registered['document_id'],scan,operator='synthetic_ocr_operator',pages=[1],language='por')
        with database.session() as session:
            row=session.get(Document,registered['document_id'])
            page=row.extraction['pages'][0]
            facts={candidate['field']:candidate['value'] for candidate in page['ocr_candidates']}
            assert facts['agreement_reference']=='977950/2025'
            assert facts['proposal_reference']=='036806/2025'
            assert facts['estimated_cents']==364261056
            assert facts['planned_capacity']==170
            validate_excerpt(row,1,'977950/2025')
            assert page['ocr_provenance']['publication_allowed'] is False
            recognized=page['ocr_candidate_text']
        assert before==hashlib.sha256(scan.read_bytes()).hexdigest()
        version=subprocess.run(['tesseract','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
        (root/'result.json').write_text(json.dumps({'revision':os.getenv('GITHUB_SHA','development'),
            'fixture':'synthetic-scanned-Portuguese','official_corpus_evaluated':False,
            'engine':version,'engine_calls':1,'expected_fields':facts,'recognized_test_text':recognized,
            'result':result},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        database.engine.dispose()
        for path in root.glob('private-test.db*'):path.unlink(missing_ok=True)


if __name__=='__main__':main()
