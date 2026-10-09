"""Issue #4: abstain rather than invent an identifier by truncating source text."""
import pytest
from bdt.documents import candidates


@pytest.mark.parametrize('text,field', [
    ('CONVENIO 123/20255', 'agreement_reference'),
    ('PROPOSTA 123/20255', 'proposal_reference'),
    ('CONTRATO 12/20255', 'contract_reference'),
    ('TERMO ADITIVO 12/20255', 'amendment_reference'),
    ('PROCESSO 123/20255', 'process_reference'),
    ('PROCESSO 23000.012345/2024-123', 'process_reference'),
    ('CONTRATO 12/2025/99', 'contract_reference'),
    ('CONTRATO 12/2025A', 'contract_reference'),
    ('CNPJ: 12.345.678/0001-900', 'cnpj_reference'),
    ('912.345.678/0001-90', 'cnpj_reference'),
    ('x12.345.678/0001-90', 'cnpj_reference'),
    ('LEI 14.133/20255', 'legal_basis'),
    ('LEI 14.133/2025X', 'legal_basis'),
    ('SUBCONTRATO 45/2024', 'contract_reference'),
    ('PREPROPOSTA 123/2025', 'proposal_reference'),
    ('SUPERCONVENIO 123/2025', 'agreement_reference'),
])
def test_partial_identifier_or_label_never_becomes_candidate(text, field):
    assert not [item for item in candidates(text) if item['field'] == field]


@pytest.mark.parametrize('label,raw,field', [
    ('CONVENIO', '123/2025', 'agreement_reference'),
    ('PROPOSTA', '036806/2025', 'proposal_reference'),
    ('CONTRATO', '45/2024', 'contract_reference'),
    ('TERMO ADITIVO', '03/2025', 'amendment_reference'),
    ('PROCESSO ADMINISTRATIVO', '23000.012345/2024-12', 'process_reference'),
    ('CNPJ:', '12.345.678/0001-90', 'cnpj_reference'),
    ('LEI N.', '14.133/2021', 'legal_basis'),
])
@pytest.mark.parametrize('punctuation', ['.', ',', ';', ')', '\n'])
def test_valid_punctuation_preserves_exact_source_span(label, raw, field, punctuation):
    text = f'({label} {raw}{punctuation} Texto sintético.'
    found = [item for item in candidates(text) if item['field'] == field]
    assert len(found) == 1
    item = found[0]
    assert item['value'] == raw == item['raw'] == text[item['start']:item['end']]
    assert item['state'] == 'candidate' and item['publication_allowed'] is False


def test_bad_identifier_does_not_suppress_later_valid_candidate():
    text = 'CONTRATO 12/20255; CONTRATO N. 45/2024.'
    assert [x['value'] for x in candidates(text) if x['field'] == 'contract_reference'] == ['45/2024']
