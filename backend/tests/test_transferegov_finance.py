# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from decimal import Decimal
from sqlalchemy import select

from bdt.domain import Source
from bdt.storage import Database, Finance, Ingestion, Municipality
from bdt.transferegov_finance import (
    parse_date_to_iso,
    parse_brl_cents,
    load_municipality_crosswalk,
    normalize_agreements,
    normalize_amendments,
    normalize_disbursements,
    import_transferegov_financial,
)


@pytest.fixture
def fake_source():
    return Source(
        dataset='transferegov',
        url='https://api-publica.transferegov.gestao.gov.br/downloads/dadosgov/siconv_convenio.zip',
        record_id='test-run',
        collected_at='2026-09-08T00:00:00+00:00',
        snapshot_sha256='a' * 64,
        reference_date='2026',
    )


def test_parse_brl_cents():
    assert parse_brl_cents('1.200,50') == 120050
    assert parse_brl_cents('2606359,37') == 260635937
    assert parse_brl_cents('-32.400,55') == -3240055
    assert parse_brl_cents('-32400,55') == -3240055
    assert parse_brl_cents('23080') == 2308000
    assert parse_brl_cents('0') == 0
    assert parse_brl_cents('0,00') == 0
    assert parse_brl_cents('') == 0
    assert parse_brl_cents(None) == 0
    with pytest.raises(ValueError, match='ambiguous_brl_amount'):
        parse_brl_cents('invalid-amount')


def test_parse_date_to_iso():
    assert parse_date_to_iso('19/12/2023') == '2023-12-19'
    assert parse_date_to_iso('2023-12-19') == '2023-12-19'
    assert parse_date_to_iso('2023-12') == '2023-12'
    assert parse_date_to_iso('2023') == '2023-01-01'
    assert parse_date_to_iso('', fallback_year='2024') == '2024-01-01'
    with pytest.raises(ValueError, match='invalid_date_format'):
        parse_date_to_iso('invalid/date')


def test_crosswalk_loader():
    lookup = {'3550308': ('3550308', 'SP')}
    rows = [
        {'NR_CONVENIO': '948971', 'COD_MUNIC_IBGE': '3550308', 'NM_PROPONENTE': 'MUNICIPIO DE SAO PAULO'},
        {'NR_CONVENIO': '999999', 'COD_MUNIC_IBGE': '9999999', 'NM_PROPONENTE': 'UNKNOWN'},  # Not in lookup
    ]
    crosswalk = load_municipality_crosswalk(rows, lookup)
    assert '948971' in crosswalk
    assert crosswalk['948971'] == ('3550308', 'MUNICIPIO DE SAO PAULO')
    assert '999999' not in crosswalk


def test_normalize_agreements_signed_vs_preconvenio(fake_source):
    crosswalk = {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO'), '966185': ('3550308', 'PRE-CONVENIO')}
    rows = [
        {
            'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '2.606.359,37',
            'VL_REPASSE_CONV': '2.603.659,37', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
            'SIT_CONVENIO': 'Em execução'
        },
        {
            'NR_CONVENIO': '966185', 'IND_ASSINADO': 'NÃO', 'VL_GLOBAL_CONV': '1.912.000,00',
            'VL_REPASSE_CONV': '1.910.000,00', 'DIA_ASSIN_CONV': '', 'ANO': '2024',
            'SIT_CONVENIO': 'Proposta Aprovada'
        },
        {
            'NR_CONVENIO': '888888', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '500.000,00',
            'VL_REPASSE_CONV': '500.000,00', 'DIA_ASSIN_CONV': '01/01/2024', 'ANO': '2024',
            'SIT_CONVENIO': 'Em execução'
        }  # Orphan: not in crosswalk
    ]
    events = list(normalize_agreements(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:agreement:948971'
    assert ev.phase == 'agreed'
    assert ev.cents == 260635937
    assert ev.municipality_id == '3550308'
    assert ev.recipient == 'MUNICIPIO DE SAO PAULO'
    assert ev.nature == 'estimate'


def test_normalize_amendments_negative_supressao(fake_source):
    crosswalk = {'858176': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows = [
        {
            'NR_CONVENIO': '858176', 'NUMERO_TA': '2/2020', 'TIPO_TA': 'Supressão',
            'VL_GLOBAL_TA': '-32.400,55', 'DT_ASSINATURA_TA': '15/05/2020'
        },
        {
            'NR_CONVENIO': '858176', 'NUMERO_TA': '1/2020', 'TIPO_TA': 'Alteração da Vigência',
            'VL_GLOBAL_TA': '0,00', 'DT_ASSINATURA_TA': '10/01/2020'
        }
    ]
    events = list(normalize_amendments(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:amendment:858176:2-2020'
    assert ev.phase == 'agreed'
    assert ev.cents == -3240055  # Preserved negative adjustment!
    assert ev.nature == 'event'


def test_normalize_disbursements_transferred_phase(fake_source):
    crosswalk = {'946645': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows = [
        {
            'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '946645',
            'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91'
        },
        {
            'ID_DESEMBOLSO': '366483', 'NR_CONVENIO': '946645',
            'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '0,00'
        }
    ]
    events = list(normalize_disbursements(rows, crosswalk, fake_source))
    assert len(events) == 1
    ev = events[0]
    assert ev.id == 'transferegov:disbursement:366482'
    assert ev.phase == 'transferred'
    assert ev.cents == 28849791
    assert ev.instrument_id == '946645'


def test_import_transferegov_financial_transactional(database, fake_source):
    # Ensure municipality exists in database
    with database.session() as session:
        session.add(Municipality(
            id='3550308', name='São Paulo', state='SP',
            source=fake_source.model_dump()
        ))
    crosswalk = {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO')}
    rows_agreements = [{
        'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '2.606.359,37',
        'VL_REPASSE_CONV': '2.603.659,37', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
        'SIT_CONVENIO': 'Em execução'
    }]
    rows_amendments = [{
        'NR_CONVENIO': '948971', 'NUMERO_TA': '1/2024', 'TIPO_TA': 'Supressão',
        'VL_GLOBAL_TA': '-50.000,00', 'DT_ASSINATURA_TA': '10/06/2024'
    }]
    rows_disbursements = [{
        'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '948971',
        'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91'
    }]
    events = list(normalize_agreements(rows_agreements, crosswalk, fake_source)) + \
             list(normalize_amendments(rows_amendments, crosswalk, fake_source)) + \
             list(normalize_disbursements(rows_disbursements, crosswalk, fake_source))
    assert len(events) == 3

    counts = import_transferegov_financial(database, events, fake_source)
    assert counts['agreed'] == 1
    assert counts['amendments'] == 1
    assert counts['transferred'] == 1
    assert counts['total'] == 3

    with database.session() as session:
        finances = list(session.scalars(select(Finance).where(Finance.municipality_id == '3550308')))
        assert len(finances) == 3
        # Check that negative amendment was preserved
        amendment_rec = next(f for f in finances if ':amendment:' in f.payload['id'])
        assert amendment_rec.cents == -5000000
        assert amendment_rec.payload['phase'] == 'agreed'
        ingestion = session.scalar(select(Ingestion).where(Ingestion.dataset == 'transferegov'))
        assert ingestion is not None
        assert ingestion.status == 'success'
        assert ingestion.counts['total'] == 3

    # Idempotent re-import
    counts_re = import_transferegov_financial(database, events, fake_source)
    assert counts_re['unchanged'] == 3
    assert counts_re['total'] == 0

