"""No ambient rounding, impossible dates or last-row-wins reconciliation."""
from decimal import Inexact, localcontext

import pytest

from bdt.transferegov_finance import load_municipality_crosswalk, parse_brl_cents, parse_date_to_iso


@pytest.mark.parametrize('value, expected', [
    ('1.234,56', 123456), ('-32.400,55', -3240055),
    ('123.45', 12345), ('-0.01', -1), ('90.071.992.547.409,91', 9007199254740991),
])
@pytest.mark.parametrize('precision', [2, 6, 28])
def test_cents_do_not_depend_on_decimal_context(value, expected, precision):
    with localcontext() as ctx:
        ctx.prec = precision
        ctx.traps[Inexact] = True
        assert parse_brl_cents(value) == expected


@pytest.mark.parametrize('value', [1.23, -0.1, True, False])
def test_binary_float_and_boolean_are_not_exact_source_amounts(value):
    with pytest.raises(ValueError, match='ambiguous_brl_amount'):
        parse_brl_cents(value)


@pytest.mark.parametrize('value', ['31/02/2026', '29/02/2025', '2026-04-31',
    '2026-13', '0000', '0000-01-01', '2026-00-12', 'not-a-date'])
def test_invalid_present_date_cannot_fall_back_to_year(value):
    with pytest.raises(ValueError, match='invalid_date_format'):
        parse_date_to_iso(value, fallback_year='2026')


@pytest.mark.parametrize('value, expected', [
    ('29/02/2024', '2024-02-29'), ('2024-02', '2024-02'),
    ('2024-02-29', '2024-02-29'), ('2026', '2026-01-01'),
    ('   ', '2025-01-01'), (None, '2025-01-01'),
])
def test_valid_dates_and_absent_date_year_fallback(value, expected):
    assert parse_date_to_iso(value, fallback_year='2025') == expected


def row(code='3550308', recipient='MUNICIPIO SINTETICO'):
    return {'NR_CONVENIO': '123', 'COD_MUNIC_IBGE': code, 'NM_PROPONENTE': recipient}


@pytest.mark.parametrize('other', [row(code='2927408'), row(recipient='OUTRO PROPONENTE'),
                                   row(recipient='A' * 201), row(recipient='')])
def test_crosswalk_conflicts_are_order_independent(other):
    for rows in ([row(), other], [other, row()]):
        with pytest.raises(ValueError, match='conflicting_municipality_crosswalk'):
            load_municipality_crosswalk(rows)


def test_crosswalk_does_not_hide_conflicts_after_truncation():
    with pytest.raises(ValueError, match='conflicting_municipality_crosswalk'):
        load_municipality_crosswalk([row(recipient='A' * 200 + 'B'), row(recipient='A' * 200 + 'C')])


def test_exact_duplicate_and_reviewed_code_alias_remain_idempotent():
    lookup = {'355030': ('3550308', 'SP'), '3550308': ('3550308', 'SP')}
    assert load_municipality_crosswalk([row(), row(), row(code='355030')], lookup) == {
        '123': ('3550308', 'MUNICIPIO SINTETICO')}
