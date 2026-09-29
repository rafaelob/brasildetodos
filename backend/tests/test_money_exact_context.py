"""Issue #3: source cents must not depend on another task's Decimal context."""
from decimal import Decimal, Inexact, Rounded, localcontext
import pytest
from bdt.domain import brl, decimal_cents
from bdt.documents import candidates


@pytest.mark.parametrize('precision', [1, 3, 6, 28])
@pytest.mark.parametrize('raw,expected', [
    ('1234.56', 123456), ('-1234.56', -123456),
    ('90071992547409.91', 9007199254740991), ('0.01', 1),
    ('1.2300', 123), ('-0.0000', 0), ('123E-2', 123),
])
def test_decimal_conversion_is_exact_at_every_precision(precision, raw, expected):
    with localcontext() as context:
        context.prec = precision
        assert decimal_cents(raw) == expected
        assert decimal_cents(Decimal(raw)) == expected


@pytest.mark.parametrize('raw', ['1.0001', '-1.0001', '1234.567', '0.00000001'])
@pytest.mark.parametrize('precision', [1, 3, 6, 28])
def test_rounding_cannot_hide_fractional_cents(raw, precision):
    with localcontext() as context:
        context.prec = precision
        with pytest.raises(ValueError):
            decimal_cents(raw)


@pytest.mark.parametrize('raw,expected', [
    ('R$ 1.234,56', 123456), ('-1.234,56', -123456),
    ('R$\u00a090.071.992.547.409,91', 9007199254740991),
])
def test_brazilian_money_ignores_context(raw, expected):
    with localcontext() as context:
        context.prec = 3
        assert brl(raw) == expected


def test_valid_conversions_neither_trigger_traps_nor_change_flags():
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        context.traps[Inexact] = context.traps[Rounded] = True
        context.clear_flags()
        assert decimal_cents('1234.5600') == 123456
        assert brl('R$ 1.234,56') == 123456
        assert not any(context.flags.values())


def test_document_candidate_uses_the_same_exact_converter():
    with localcontext() as context:
        context.prec = 3
        found = candidates('VALOR GLOBAL: R$ 1.234,56')
    assert len(found) == 1
    assert found[0]['value'] == 123456
    assert found[0]['state'] == 'candidate'
    assert found[0]['publication_allowed'] is False


@pytest.mark.parametrize('value', [True, False, 1.5, None, [], {}, '', 'not-money',
                                  'NaN', 'sNaN', 'Infinity', '-Infinity'])
def test_invalid_decimal_values_fail_closed(value):
    with pytest.raises(ValueError):
        decimal_cents(value)


@pytest.mark.parametrize('raw', ['1e1000000000', '-1e1000000000', '1e4094'])
def test_large_positive_exponent_is_rejected_before_integer_expansion(raw):
    with pytest.raises(ValueError, match='Monetary digit budget'):
        decimal_cents(raw)


@pytest.mark.parametrize('raw', ['1e-1000000000', '-1e-1000000000'])
def test_tiny_nonzero_exponent_remains_fractional_not_zero(raw):
    with pytest.raises(ValueError, match='fractional cents'):
        decimal_cents(raw)


@pytest.mark.parametrize('raw', ['0e1000000000', '-0e-1000000000'])
def test_extreme_exponent_zero_is_still_exact_zero(raw):
    assert decimal_cents(raw) == 0


def test_digit_budget_boundary_does_not_round():
    assert decimal_cents('1e4093') == 10**4095


def test_random_decimal_tuples_match_an_independent_fraction_oracle():
    from fractions import Fraction
    import random
    import decimal
    randomizer = random.Random(20260929)
    rounding_modes = [decimal.ROUND_CEILING, decimal.ROUND_DOWN, decimal.ROUND_FLOOR,
        decimal.ROUND_HALF_DOWN, decimal.ROUND_HALF_EVEN, decimal.ROUND_HALF_UP,
        decimal.ROUND_UP, decimal.ROUND_05UP]
    for _ in range(500):
        coefficient = randomizer.randrange(-10**18, 10**18)
        exponent = randomizer.randrange(-25, 10)
        digits = tuple(int(char) for char in str(abs(coefficient)))
        value = Decimal((int(coefficient < 0), digits, exponent))
        expected = Fraction(coefficient) * Fraction(10) ** (exponent + 2)
        with localcontext() as context:
            context.prec = randomizer.choice([1, 3, 6, 28])
            context.rounding = randomizer.choice(rounding_modes)
            if expected.denominator == 1:
                assert decimal_cents(value) == expected.numerator
            else:
                with pytest.raises(ValueError):
                    decimal_cents(value)
