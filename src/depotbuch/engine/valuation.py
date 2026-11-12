"""Valuation per asset type (proposal 0001, *Valuation by asset type*; architecture §8.2).

The value of a slice on a day is the sum of its positions' values at the end of that day,
in EUR at full precision (an analytical figure, ADR-0013):

- A security: units x close, divided by the ECB rate for a foreign currency.
- A bond: nominal x price in percent / 100, converted the same way (ADR-0014).
- A cash balance (Verrechnungskonto, Tagesgeld): the sum of the cash its bookings moved.
  A booking without an asset belongs to its account's own balance.
- A Festgeld: its balance plus the interest accrued under the account's terms and not yet
  credited, until the bank pays it out (ADR-0015).

Closes are adjusted for splits, as price providers give them: on a day before a split,
the units held are restated by its ratio. A close or rate missing on the day is carried
forward from the last earlier one. A held position with no close or rate on or before the
day raises instead of counting as zero.
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
from depotbuch.engine.money import MAX_BOOKED, exact_sum, multiply_units

_ZERO = Decimal(0)
_TRADED = {AssetKind.SECURITY, AssetKind.BOND}
_FESTGELD_LINES = {
    ActivityType.DEPOSIT,
    ActivityType.WITHDRAWAL,
    ActivityType.INTEREST,
    ActivityType.FEE,
    ActivityType.TAX,
}
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


def _days(convention: DayCount, start: dt.date, end: dt.date) -> int:
    if convention is DayCount.E30_360:
        return _days_30e(start, end)
    return (end - start).days


def interest_days(terms: DepositTerms, on: dt.date) -> int:
    """The interest days a deposit has earned by the end of `on`.

    The earning days run from the start (or the day after, unless `accrue_start`) to the
    maturity (or the day before, unless `accrue_maturity`), and stop there. Each earning day
    counts as the convention counts it to the next day: under 30E/360 a 31st counts 0 and
    the last day of February up to 3. So the count never decreases from one day to the next.
    """
    first = terms.start if terms.accrue_start else terms.start + dt.timedelta(days=1)
    last_earning = (
        terms.maturity if terms.accrue_maturity else terms.maturity - dt.timedelta(days=1)
    )
    last = min(on, last_earning)
    if last < first:
        return 0
    return _days(terms.day_count, first, last + dt.timedelta(days=1))


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

    def terms(self, account: str) -> DepositTerms | None:
        spec = self.accounts.get(account)
        return spec.deposit if spec else None

    def is_balance(self, a: Activity) -> bool:
        """A booking of a cash or Festgeld balance rather than a security: everything in a
        Festgeld account, a booking without an asset, or one naming a cash or deposit
        asset."""
        return (
            self.terms(a.account) is not None
            or not a.asset
            or self.kind(a.asset) not in _TRADED
        )

    def balance_key(self, a: Activity) -> tuple[str, str]:
        """Which balance a cash booking belongs to: in a Festgeld account (one with deposit
        terms) the account's one deposit, whatever asset the booking names; elsewhere the
        named cash asset, or the account's own balance without one."""
        if self.terms(a.account) is not None:
            return (a.account, "")
        return (a.account, a.asset or "")


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

    An asset that isn't in `assets` is an EUR security. A booking without an asset
    (deposit, withdrawal, interest, fee, tax) belongs to its account's own balance: a
    Festgeld if the account has deposit terms, cash otherwise; a slice by asset leaves it
    out. Only the slice's activities are replayed, so a problem in another position
    doesn't stop it.
    """
    market = _Market(assets, prices, fx or FxRates(), accounts or {})
    every = [a for a in activities if account is None or a.account == account]
    scope = [a for a in every if a.date <= on]
    if asset is None:
        own = scope
    else:  # a Festgeld account is one balance: its asset's slice is the whole account,
        # known from its whole history, not only the bookings up to `on`
        festgeld = {a.account for a in every if a.asset == asset and market.terms(a.account)}
        own = [a for a in scope if a.asset == asset or a.account in festgeld]
    traded = [a for a in own if not market.is_balance(a)]
    held = [a for a in own if market.is_balance(a)]
    parts: list[Decimal] = []
    for (acc, held_asset), units in _units(traded, on).items():
        if units:
            restated = _in_todays_units(units, every, acc, held_asset, on)
            parts.append(_security(market, held_asset, restated, on))
    groups: dict[tuple[str, str], list[Activity]] = {}
    for a in held:
        groups.setdefault(market.balance_key(a), []).append(a)
    for (acc, _), bookings in sorted(groups.items()):
        parts.append(_balance(market, bookings, acc, on))
    return exact_sum(parts)


def _in_todays_units(
    units: Decimal, activities: list[Activity], account: str, asset: str, on: dt.date
) -> Decimal:
    """`units` held at the end of `on`, restated by every later split of that position:
    closes are adjusted for splits (architecture §8.2), so a close before a split is per
    unit of today."""
    for a in sorted(
        (
            a
            for a in activities
            if a.type is ActivityType.SPLIT
            and a.date > on
            and (a.account, a.asset) == (account, asset)
        ),
        key=lambda a: a.date,
    ):
        units = multiply_units(units, a.ratio or Decimal(1))
    return units


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
    currency = market.currency(asset)
    rate = market.rates.rate(currency, on)  # a held position needs its rate, even at 0
    return market.rates.to_eur(local, currency, on, rate)


def _balance(market: _Market, bookings: list[Activity], account: str, on: dt.date) -> Decimal:
    """A cash or deposit position: one asset in one account, or the account's own balance
    (bookings without an asset)."""
    terms = market.terms(account)
    named = {a.asset for a in bookings if a.asset}
    deposit = terms is not None or any(market.kind(n) is AssetKind.DEPOSIT for n in named)
    currency = bookings[0].currency
    if any(a.currency != currency for a in bookings) or any(
        market.currency(n) != currency for n in named
    ):
        raise ValueError("a cash booking's currency differs from its balance's")
    if terms is not None and any(a.type not in _FESTGELD_LINES for a in bookings):
        raise ValueError(
            "a Festgeld account books only deposits, withdrawals, interest, fees and tax"
        )
    balance = exact_sum(a.cash for a in bookings)
    if deposit:
        if terms is None:
            raise MissingTerms(account)
        balance += _uncredited(bookings, terms, on)
    return market.rates.to_eur(balance, currency, on)


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
    # A credit rounded to the cent may exceed the accrual: then nothing is left to accrue.
    return max(accrued_interest(terms, on) - credited, _ZERO)
