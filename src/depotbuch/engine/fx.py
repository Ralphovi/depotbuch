"""Converting amounts to EUR (architecture §8.2).

Rates are kept as the ECB quotes them: units of the foreign currency per EUR. An amount in
that currency is converted by dividing by the rate. A booked amount converts to a booked
amount, in cents (`book_eur`); a value for analysis keeps full precision (`to_eur`,
ADR-0013).
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from depotbuch.engine.money import book

EUR = "EUR"


class MissingRate(LookupError):
    """No rate on or before the date for that currency."""


class FxRates:
    """Daily rates per currency. A day without a rate (weekend, holiday) uses the last
    rate before it; a date before the first rate has none."""

    def __init__(self, rates: Mapping[str, Mapping[date, Decimal]] | None = None) -> None:
        self._dates: dict[str, list[date]] = {}
        self._rates: dict[str, dict[date, Decimal]] = {}
        for currency, series in (rates or {}).items():
            if any(r <= 0 for r in series.values()):
                raise ValueError("FX rates must be positive")
            self._rates[currency] = dict(series)
            self._dates[currency] = sorted(series)

    def rate(self, currency: str, on: date) -> Decimal:
        """The rate for `currency` on `on`, carried forward over gaps. EUR is 1."""
        if currency == EUR:
            return Decimal(1)
        dates = self._dates.get(currency, [])
        i = bisect_right(dates, on)
        if i == 0:
            raise MissingRate(currency)
        return self._rates[currency][dates[i - 1]]

    def to_eur(
        self, amount: Decimal, currency: str, on: date, broker_rate: Decimal | None = None
    ) -> Decimal:
        """`amount` in EUR at full precision: divided by the broker's rate when given, else
        the ECB rate. For values and other analytical figures."""
        if currency == EUR:
            return amount
        return amount / (broker_rate if broker_rate is not None else self.rate(currency, on))

    def book_eur(
        self, amount: Decimal, currency: str, on: date, broker_rate: Decimal | None = None
    ) -> Decimal:
        """A booked amount in EUR: converted as `to_eur`, then booked to the cent."""
        return book(self.to_eur(amount, currency, on, broker_rate))
