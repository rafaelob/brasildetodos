"""Metadata precision tests: no changes to cent-only financial events."""
from decimal import Decimal, localcontext
import pytest
from bdt.domain import decimal_cents
from bdt.resource_money import metadata_amount, MAX_CENTS
from bdt.resource_profiles import normalize_resource
from bdt.resource_sync import import_resources
from test_resource_sync import PNCP, contract, source, save_collection, current


@pytest.mark.parametrize('value,expected', [
    ('100.0001', (None, '100.0001')), (Decimal('0.0010'), (None, '0.001')),
    ('1E-4', (None, '0.0001')), ('100.01000000', (10001, None)),
    (0, (0, None)), ('-0.0000', (0, None)), (None, (None, None)),
    ('90071992547409.91', (MAX_CENTS, None)), ('90071992547409.9099', (None, '90071992547409.9099')),
])
def test_exact_bounded_metadata(value, expected):
    with localcontext() as ctx:
        ctx.prec = 2
        assert metadata_amount(value) == expected


@pytest.mark.parametrize('value', ['0.00001', '-1', 'NaN', 'Infinity', '-Infinity', 'bad',
                                  True, 1.23, '1E999999', '1E-999999', '90071992547409.9101'])
def test_reject_without_rounding(value):
    with pytest.raises(ValueError):
        metadata_amount(value)


def test_payment_parser_is_still_strict():
    with pytest.raises(ValueError):
        decimal_cents('100.0001')


def test_contract_preserves_precision_and_no_payment(database, tmp_path):
    folder = tmp_path / 'collection'
    save_collection(folder, [contract(valorInicial='100.0001', valorGlobal='200.0123')])
    result = import_resources(database, folder)
    assert result['created'] == 1 and result['financial_events_created'] == 0
    a = current(database)[0]['attributes']
    assert a['initial_cents'] is None and a['global_cents'] is None
    assert a['precise_amounts'] == {'initial': '100.0001', 'global': '200.0123'}
    assert import_resources(database, folder)['unchanged'] == 1


def test_existing_exact_cent_payload_stays_compatible():
    body = normalize_resource(PNCP, contract(), source(), {'1234567': ('Synthetic', 'BA')})
    assert 'precise_amounts' not in body.attributes
    assert body.attributes['initial_cents'] == 10001


def test_subcent_change_creates_version_without_rounding(database, tmp_path):
    from sqlalchemy import select
    from bdt.resource_sync import ResourceRevision
    a, b = tmp_path / 'a', tmp_path / 'b'
    save_collection(a, [contract(valorInicial='0.0001')])
    import_resources(database, a)
    save_collection(b, [contract(valorInicial='0.0002', dataAtualizacao='2026-09-05T12:00:00')])
    assert import_resources(database, b)['updated'] == 1
    with database.session() as session:
        versions = list(session.scalars(select(ResourceRevision).order_by(ResourceRevision.revision)))
        assert [v.payload['attributes']['precise_amounts']['initial'] for v in versions] == ['0.0001','0.0002']
