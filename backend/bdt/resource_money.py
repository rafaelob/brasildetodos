"""Exact PNCP metadata amounts; payment events continue to require integer cents.

The official PNCP consultation manual, page 37, admits four decimal places for
valorInicial/valorGlobal/valorAcumulado. Fractions of a cent are preserved as
bounded decimal text, never rounded into an integer-cent financial event.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

MAX_CENTS = 9_007_199_254_740_991
MAX_AMOUNT = Decimal('90071992547409.91')


def metadata_amount(value: str | int | Decimal | None) -> tuple[int | None, str | None]:
    """Return (exact cents, subcent decimal), with exactly one present if known.

    Tuple arithmetic avoids the ambient Decimal context rounding an input. A
    trailing zero is not an additional significant fractional place. Original
    numeric lexical spelling remains available in the hashed source page.
    """
    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError('money_requires_decimal_json_not_float')
    raw = str(value)
    if len(raw) > 128:
        raise ValueError('resource_amount_out_of_range')
    try:
        number = Decimal(raw)
    except InvalidOperation:
        raise ValueError('invalid_decimal_resource_amount') from None
    if not number.is_finite() or number < 0 or number > MAX_AMOUNT:
        raise ValueError('resource_amount_out_of_range')
    sign, digits, exponent = number.as_tuple()
    if not any(digits):
        return 0, None
    digits = list(digits)
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if exponent < -4:
        raise ValueError('pncp_amount_exceeds_four_decimal_places')
    coefficient = int(''.join(map(str, digits)))
    if exponent >= -2:
        cents = coefficient * 10 ** (exponent + 2)
        return cents, None
    # Nonzero subcent amount. Construction is exact even with a low context.
    scale = -exponent
    fixed = str(coefficient).zfill(scale + 1)
    return None, fixed[:-scale] + '.' + fixed[-scale:]
