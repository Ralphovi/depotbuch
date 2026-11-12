"""Valuation per asset type (proposal 0001, *Valuation by asset type*; architecture §8.2).

The value of a slice on a day is the sum of its positions' values at the end of that day,
in EUR at full precision (an analytical figure, ADR-0013):

- A security: units x close, divided by the ECB rate for a foreign currency.
- A bond: nominal x price in percent / 100, converted the same way (ADR-0014).
- A cash balance (Verrechnungskonto, Tagesgeld): the sum of the cash its bookings moved.
  Each booking of a cash account names the account's cash asset.
- A Festgeld: its balance plus the interest accrued under the account's terms and not yet
  credited, until the bank pays it out (ADR-0015).

A close or rate missing on the day is carried forward from the last earlier one. A held
position with no close or rate on or before the day raises instead of counting as zero.
"""

from __future__ import annotations

import datetime as dt
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from depotbuch.engine.fx import FxRates
from depotbuch.engine.lots import build_lots
from depotbuch.engine.model import (
    Account,
    Activity,
    ActivityType,
    Asset,
    AssetKind,
    DayCount,
    DepositTerms,
)
from depotbuch.engine.money import MAX_BOOKED, exact_sum

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


class MissingPrice(LookupError):
    """A held security has no close on or before the day. Names the asset, not a value."""


class MissingTerms(LookupError):
    """A Festgeld position in an account without deposit terms."""


class Prices:
    """Daily closes per asset, in the asset's currency; a bond's in percent of nominal.
    A day without a close uses the last one before it."""

    def __init__(self, closes: Mapping[str, Mapping[dt.date, Decimal]] | None = None) -> None:
        self._dates: dict[str, list[dt.date]] = {}
        self._closes: dict[str, dict[dt.date, Decimal]] = {}
        for asset, series in (closes or {}).items():
            if not all(c.is_finite() and _ZERO <= c < MAX_BOOKED for c in series.values()):
                raise ValueError("a close is a finite amount from 0 to below 10^15")
            self._closes[asset] = dict(series)
            self._dates[asset] = sorted(series)

    def close(self, asset: str, on: dt.date) -> Decimal:
        dates = self._dates.get(asset, [])
        i = bisect_right(dates, on)
        if i == 0:
            raise MissingPrice(asset)
        return self._closes[asset][dates[i - 1]]


def _days_30e(start: dt.date, end: dt.date) -> int:
    return (
        360 * (end.year - start.year)
        + 30 * (end.month - start.month)
        + min(end.day, 30)
        - min(start.day, 30)
    )


_YEAR = {DayCount.ACT_365: 365, DayCount.ACT_360: 360, DayCount.E30_360: 360}


def interest_days(terms: DepositTerms, on: dt.date) -> int:
    """The interest days a deposit has earned by the end of `on`.

    Every day from start to maturity earns interest, except the start day unless
    `accrue_start` and the maturity day unless `accrue_maturity`; after maturity no more.
    Under 30E/360 the days between two dates are counted as the convention counts them.
    """
    if on < terms.start:
        return 0
    end = min(on, terms.maturity)
    if terms.day_count is DayCount.E30_360:
        between = _days_30e(terms.start, end)
    else:
        between = (end - terms.start).days
    days = between + 1
    if not terms.accrue_start:
        days -= 1
    if end == terms.maturity and not terms.accrue_maturity:
        days -= 1
    return max(days, 0)


def accrued_interest(terms: DepositTerms, on: dt.date) -> Decimal:
    """Simple interest on the principal for the days earned by the end of `on`, at full
    precision."""
    days = Decimal(interest_days(terms, on))
    return terms.principal * terms.rate / _HUNDRED * days / _YEAR[terms.day_count]


@dataclass(frozen=True)
class _Market:
    assets: Mapping[str, Asset]
    prices: Prices
    rates: FxRates
    accounts: Mapping[str, Account]

    def kind(self, asset: str | None) -> AssetKind:
        spec = self.assets.get(asset or "")
        return spec.kind if spec else AssetKind.SECURITY

    def currency(self, asset: str) -> str:
        spec = self.assets.get(asset)
        return spec.currency if spec else "EUR"


def value(
    activities: Iterable[Activity],
    on: dt.date,
    *,
    assets: Mapping[str, Asset],
    prices: Prices,
    fx: FxRates | None = None,
    accounts: Mapping[str, Account] | None = None,
    asset: str | None = None,
    account: str | None = None,
) -> Decimal:
    """The value in EUR of the positions in the slice at the end of `on`.

    An asset that isn't in `assets` is an EUR security. Only the slice's activities are
    replayed, so a problem in another position doesn't stop it.
    """
    market = _Market(assets, prices, fx or FxRates(), accounts or {})
    own = [
        a
        for a in activities
        if a.asset is not None
        and a.date <= on
        and (asset is None or a.asset == asset)
        and (account is None or a.account == account)
    ]
    parts: list[Decimal] = []
    traded = [a for a in own if market.kind(a.asset) in {AssetKind.SECURITY, AssetKind.BOND}]
    for (_, held_asset), units in _units(traded, on).items():
        if units:
            parts.append(_security(market, held_asset, units, on))
    held = [a for a in own if market.kind(a.asset) in {AssetKind.CASH, AssetKind.DEPOSIT}]
    for acc, cash_asset in sorted({(a.account, a.asset or "") for a in held}):
        bookings = [a for a in held if (a.account, a.asset) == (acc, cash_asset)]
        parts.append(_balance(market, bookings, acc, on))
    return exact_sum(parts)


def _units(activities: list[Activity], on: dt.date) -> dict[tuple[str, str], Decimal]:
    book = build_lots(activities, on, costs=False)
    out: dict[tuple[str, str], Decimal] = {}
    for lot in book.lots:
        key = (lot.account, lot.asset)
        out[key] = exact_sum([out.get(key, _ZERO), lot.units])
    return out


def _security(market: _Market, asset: str, units: Decimal, on: dt.date) -> Decimal:
    local = units * market.prices.close(asset, on)
    if market.kind(asset) is AssetKind.BOND:
        local /= _HUNDRED
    return market.rates.to_eur(local, market.currency(asset), on)


def _balance(market: _Market, bookings: list[Activity], account: str, on: dt.date) -> Decimal:
    """A cash or deposit position: one asset in one account."""
    asset = bookings[0].asset or ""
    if any(a.currency != market.currency(asset) for a in bookings):
        raise ValueError("a cash booking's currency differs from its asset's")
    balance = exact_sum(a.cash for a in bookings)
    if market.kind(asset) is AssetKind.DEPOSIT:
        spec = market.accounts.get(account)
        if spec is None or spec.deposit is None:
            raise MissingTerms(account)
        balance += _uncredited(bookings, spec.deposit, on)
    return market.rates.to_eur(balance, market.currency(asset), on)


def _uncredited(bookings: list[Activity], terms: DepositTerms, on: dt.date) -> Decimal:
    """Interest accrued but not yet credited. Nothing once the bank has paid the deposit
    out: a withdrawal on or after maturity closes it, and its balance is the value."""
    if any(a.type is ActivityType.WITHDRAWAL and a.date >= terms.maturity for a in bookings):
        return _ZERO
    credited = exact_sum(  # gross: the net credit plus the tax withheld from it
        a.cash + a.taxes
        for a in bookings
        if a.type is ActivityType.INTEREST and a.date >= terms.start
    )
    return accrued_interest(terms, on) - credited
