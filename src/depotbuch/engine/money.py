"""Amounts: `decimal.Decimal` from parsing to output, never a binary float (ADR-0013).

Two kinds of number follow different rules:

- **Booked amounts** (cash, fees, taxes, a lot's cost, the share of cost or proceeds a sale
  assigns to a lot, an amount converted to EUR) are ledger entries. Each is in cents,
  rounded half up when it comes into existence (`book`), and an allocation splits a booked
  amount into cents that add up to it exactly (`allocate`).
- **Analytical figures** (values, TTWROR, IZF) keep full precision and are rounded only for
  display. Units, prices and FX rates keep the digits their source gives.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict

CENT = Decimal("0.01")
MAX_BOOKED = Decimal(10) ** 15
"""Booked amounts and units stay below 10^15, units have at most `UNIT_PLACES` decimals and
FX rates lie within `MIN_RATE`..`MAX_RATE`, so sums of them and every booked result fit the
default 28-digit decimal context (ADR-0013). Real amounts, holdings and ECB rates are orders
of magnitude inside these bounds."""
UNIT_PLACES = 12
MIN_RATE, MAX_RATE = Decimal("1E-6"), Decimal("1E6")
_CURRENCY = re.compile(r"[A-Z]{3}")


def to_decimal(value: object) -> Decimal:
    """Accept a Decimal, an int or a numeric string; reject floats and booleans.

    A float has already lost precision by the time it arrives, so it is refused rather
    than converted. Error messages never repeat the value, so a log of a failed private
    case carries no amounts.
    """
    if isinstance(value, (bool, float)):
        raise ValueError("binary floats are not accepted; write the amount as a string")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value.strip())
        except InvalidOperation:
            raise ValueError("not a decimal number") from None
    else:
        raise ValueError("expected a decimal number as a string")
    if not result.is_finite():
        raise ValueError("amounts must be finite")
    return result


def round_cent(amount: Decimal) -> Decimal:
    """Round to the cent, half up."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


book = round_cent
"""Book an amount: to the cent, half up, as German banks round."""


def book_exact(value: Fraction) -> Decimal:
    """Book an exact value to the cent, half up (a tie away from zero, as `round_cent`).

    Shares and conversions are computed as fractions and rounded once here: a quotient
    rounded to the decimal context's digits first could round to the wrong cent.
    """
    cents = abs(value) * 100
    whole = int(cents)
    if cents - whole >= Fraction(1, 2):
        whole += 1
    return Decimal((0 if value >= 0 else 1, tuple(int(d) for d in str(whole)), -2))


def is_units(units: Decimal) -> bool:
    """True if `units` is a unit count depotbuch computes with exactly (see `MAX_BOOKED`)."""
    _, _, exponent = units.as_tuple()
    return isinstance(exponent, int) and exponent >= -UNIT_PLACES and abs(units) < MAX_BOOKED


def is_rate(rate: Decimal) -> bool:
    """True if `rate` is an FX rate depotbuch can convert with (see `MAX_BOOKED`)."""
    return MIN_RATE <= rate <= MAX_RATE


def is_booked(amount: Decimal) -> bool:
    """True if `amount` is a whole number of cents. Read from its digits, so no decimal
    context limits it: a huge amount is checked as reliably as a small one."""
    _, digits, exponent = amount.as_tuple()
    if not isinstance(exponent, int):  # NaN or infinity
        return False
    below_cent = -2 - exponent
    return below_cent <= 0 or not any(digits[-below_cent:])


def share(amount: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    """The booked share `part / whole` of a booked `amount`: amount x part / whole, to the
    cent. The rest is `amount - share(...)`, so the two always add up to `amount`."""
    if whole == 0:
        raise ValueError("a share of nothing")
    return book_exact(Fraction(amount) * Fraction(part) / Fraction(whole))


def allocate(amount: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split a booked `amount` in cents, pro rata to non-negative `weights`.

    Cumulative shares are booked and each part is the difference to the previous one, so
    the parts add up to `amount` exactly, each is within a cent of its exact share, and no
    part has the opposite sign of `amount`.
    """
    if any(w < 0 for w in weights):
        raise ValueError("weights can't be negative")
    total = sum(weights, Decimal(0))
    if total <= 0:
        raise ValueError("an allocation needs a positive weight")
    parts: list[Decimal] = []
    booked = Decimal(0)
    cumulative = Decimal(0)
    for w in weights:
        cumulative += w
        upto = amount if cumulative == total else share(amount, cumulative, total)
        parts.append(upto - booked)
        booked = upto
    return parts


def _currency(code: str) -> str:
    if not _CURRENCY.fullmatch(code):
        raise ValueError("currency must be a three-letter upper-case ISO 4217 code")
    return code


Dec = Annotated[Decimal, BeforeValidator(to_decimal)]
"""A Decimal field that refuses floats."""

Currency = Annotated[str, AfterValidator(_currency)]
"""An ISO 4217 currency code, such as EUR."""


class Money(BaseModel):
    """An amount and its currency, kept together until it is converted to EUR."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Dec
    currency: Currency = "EUR"
