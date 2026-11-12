"""Amounts: `decimal.Decimal` from parsing to output, never a binary float.

Intermediate results keep full precision. An amount is rounded to the cent only where a
provider rounds (a booked cash amount, a reported tax) and for display, half up, as German
banks round (ADR-0013).
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict

CENT = Decimal("0.01")
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
