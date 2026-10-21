"""Issue #2: untrusted collection JSON cannot smuggle IEEE infinity via exponent."""
from decimal import Decimal
import pytest
from bdt.json_codec import decode


@pytest.mark.parametrize('number', [b'1e999', b'-1e999', b'1.7976931348623159e308'])
@pytest.mark.parametrize('wrapper', [lambda n: n, lambda n: b'{"items": [{"amount": '+n+b'}]}'])
def test_overflowing_default_float_is_rejected_at_decode_boundary(number, wrapper):
    with pytest.raises(ValueError, match='non_finite_json_number'):
        decode(wrapper(number))


@pytest.mark.parametrize('constant', [b'NaN', b'Infinity', b'-Infinity'])
def test_explicit_non_finite_constants_remain_forbidden(constant):
    with pytest.raises(ValueError, match='non_finite_json_number'):
        decode(constant)


def test_explicit_exact_decimal_parser_does_not_lose_precision():
    result = decode(b'{"amount": 90071992547409.9101, "large": 1e999}', parse_float=Decimal)
    assert result == {'amount': Decimal('90071992547409.9101'), 'large': Decimal('1e999')}
    assert all(value.is_finite() for value in result.values())


def test_finite_coordinates_and_integers_preserve_default_types():
    result = decode(b'{"latitude": -12.9714, "longitude": -38.5014, "count": 10}')
    assert result == {'latitude': -12.9714, 'longitude': -38.5014, 'count': 10}
    assert type(result['latitude']) is float
    assert type(result['count']) is int


def test_duplicate_keys_remain_rejected():
    with pytest.raises(ValueError, match='duplicate_json_key'):
        decode(b'{"items": [{"count": 1, "count": 2}]}')
