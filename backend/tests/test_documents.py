import hashlib
import pytest
from reportlab.pdfgen import canvas
from bdt.documents import candidates, inspect_pdf, ocr_page


def test_reference_extraction_remains_candidate():
    text='CONVENIO N. 977950/2025. PROPOSTA 036806/2025. VALOR ESTIMADO: R$ 3.642.610,56. Ate 170 criancas.'
    found=candidates(text)
    assert {x['field'] for x in found}=={'agreement_reference','proposal_reference','estimated_cents','planned_capacity'}
    for x in found:
        assert text[x['start']:x['end']]==x['raw']
        assert x['state']=='candidate' and x['publication_allowed'] is False
    assert next(x['value'] for x in found if x['field']=='estimated_cents')==364261056


def test_native_pdf_preserved_without_ocr(tmp_path,monkeypatch):
    p=tmp_path/'synthetic.pdf';c=canvas.Canvas(str(p));c.drawString(72,700,'CONVENIO 977950/2025 - SYNTHETIC TEST');c.save()
    before=hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr('bdt.documents.subprocess.run',lambda *a,**k:pytest.fail('Native PDF must not invoke OCR'))
    result=inspect_pdf(p)
    assert result['sha256']==before==hashlib.sha256(p.read_bytes()).hexdigest()
    assert result['pages'][0]['route']=='native'
    assert result['pages'][0]['candidates'][0]['value']=='977950/2025'
    assert result['pages'][0]['words']


def test_blank_not_fabricated(tmp_path):
    p=tmp_path/'blank.pdf';c=canvas.Canvas(str(p));c.showPage();c.save()
    result=inspect_pdf(p)
    assert result['pages'][0]['route']=='inspect_blank_or_graphic'
    assert result['pages'][0]['candidates']==[]


def test_pdf_budget(tmp_path):
    p=tmp_path/'test.pdf';c=canvas.Canvas(str(p));c.drawString(20,20,'Test');c.save()
    with pytest.raises(ValueError):inspect_pdf(p,max_pages=0)
    with pytest.raises(ValueError):inspect_pdf(p,max_bytes=1)


def test_non_pdf_rejected(tmp_path):
    p=tmp_path/'x.pdf';p.write_text('<html>no PDF</html>')
    with pytest.raises(ValueError):inspect_pdf(p)

@pytest.mark.parametrize('number,lang',[(0,'por'),(1,'por;echo'),(1,'../../')])
def test_ocr_arguments_checked(tmp_path,number,lang):
    with pytest.raises(ValueError):ocr_page(tmp_path/'missing.pdf',number,lang)


def test_procurement_document_candidates():
    text = (
        "CONTRATO N. 45/2024. TERMO ADITIVO Nº 03/2025. "
        "PROCESSO ADMINISTRATIVO N. 23000.012345/2024-12. "
        "CONTRATADO: EMPRESA BRASILEIRA LTDA, CNPJ: 12.345.678/0001-90. "
        "VALOR GLOBAL: R$ 1.500.250,75. "
        "BASE LEGAL: LEI N. 14.133/2021."
    )
    found = candidates(text)
    fields = {x['field'] for x in found}
    assert 'contract_reference' in fields
    assert 'amendment_reference' in fields
    assert 'process_reference' in fields
    assert 'cnpj_reference' in fields
    assert 'global_value' in fields
    assert 'legal_basis' in fields

    contract = next(x for x in found if x['field'] == 'contract_reference')
    assert contract['value'] == '45/2024'
    assert contract['state'] == 'candidate'
    assert contract['publication_allowed'] is False

    aditivo = next(x for x in found if x['field'] == 'amendment_reference')
    assert aditivo['value'] == '03/2025'

    proc = next(x for x in found if x['field'] == 'process_reference')
    assert proc['value'] == '23000.012345/2024-12'

    cnpj_item = next(x for x in found if x['field'] == 'cnpj_reference')
    assert cnpj_item['value'] == '12.345.678/0001-90'

    val = next(x for x in found if x['field'] == 'global_value')
    assert val['value'] == 150025075

    lei = next(x for x in found if x['field'] == 'legal_basis')
    assert lei['value'] == '14.133/2021'

