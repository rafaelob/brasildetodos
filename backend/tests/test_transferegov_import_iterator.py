# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from bdt.domain import Source
from bdt.storage import Municipality
from bdt.transferegov_finance import (
    import_transferegov_financial,
    normalize_agreements,
    normalize_amendments,
    normalize_disbursements,
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


CROSSWALK = {'948971': ('3550308', 'MUNICIPIO DE SAO PAULO')}
ROWS_AGREEMENTS = [{
    'NR_CONVENIO': '948971', 'IND_ASSINADO': 'SIM', 'VL_GLOBAL_CONV': '2.606.359,37',
    'VL_REPASSE_CONV': '2.603.659,37', 'DIA_ASSIN_CONV': '19/12/2023', 'ANO': '2023',
    'SIT_CONVENIO': 'Em execução',
}]
ROWS_AMENDMENTS = [{
    'NR_CONVENIO': '948971', 'NUMERO_TA': '1/2024', 'TIPO_TA': 'Supressão',
    'VL_GLOBAL_TA': '-50.000,00', 'DT_ASSINATURA_TA': '10/06/2024',
}]
ROWS_DISBURSEMENTS = [{
    'ID_DESEMBOLSO': '366482', 'NR_CONVENIO': '948971',
    'DATA_DESEMBOLSO': '03/01/2025', 'VL_DESEMBOLSADO': '288.497,91',
}]


def _financial_events(source):
    yield from normalize_agreements(ROWS_AGREEMENTS, CROSSWALK, source)
    yield from normalize_amendments(ROWS_AMENDMENTS, CROSSWALK, source)
    yield from normalize_disbursements(ROWS_DISBURSEMENTS, CROSSWALK, source)


def test_import_transferegov_financial_iterator_flushes_between_events(database, fake_source):
    with database.session() as session:
        session.add(Municipality(
            id='3550308', name='São Paulo', state='SP',
            source=fake_source.model_dump(),
        ))
    events = _financial_events(fake_source)
    assert not isinstance(events, list)

    counts = import_transferegov_financial(database, events, fake_source, batch_size=1)
    assert counts['agreed'] == 1
    assert counts['amendments'] == 1
    assert counts['transferred'] == 1
    assert counts['total'] == 3

    counts_re = import_transferegov_financial(
        database, _financial_events(fake_source), fake_source, batch_size=1,
    )
    assert counts_re['unchanged'] == 3


def test_import_transferegov_financial_rejects_zero_batch_size(database, fake_source):
    with pytest.raises(ValueError, match='batch_size_must_be_positive'):
        import_transferegov_financial(database, _financial_events(fake_source), fake_source, batch_size=0)
