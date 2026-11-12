"""Income and taxes (proposal 0001, *Lots* and *Taxes are attributed where they arise*).

**Income** is a dividend, distribution, coupon or interest, net of the tax withheld on it.
A dividend or coupon of a security is split across the lots entitled to it, in proportion
to their units:

- With an ex-date, the lots held at the end of the day before it. A position that held
  nothing then is not entitled, and the dividend is rejected rather than guessed.
- Without one, the lots held at the end of the payment date, and the split is marked
  approximate. A dividend paid after the position was sold goes to the lots held on its
  last held day.

The payment date stays the date of the income. Interest on a cash or deposit account, or
on a booking without an asset, belongs to that account and has no lots.

**Taxes** are attributed where they arise: the tax withheld on a trade, a dividend or
interest, and the tax a Vorabpauschale costs, belong to that asset (ADR-0016). A tax
booking without an asset, such as a yearly settlement, belongs to its account and so to
its provider. A refund is a negative tax.

Amounts are converted to EUR on the activity's date and booked in cents (ADR-0013); a
dividend's net amount and withheld tax are split across its lots in cents that add up to
them exactly.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from depotbuch.engine.fx import FxRates
from depotbuch.engine.lots import Lot, build_lots
from depotbuch.engine.model import Account, Activity, ActivityType, Asset, AssetKind
from depotbuch.engine.money import allocate, exact_sum

_ZERO = Decimal(0)
_DAY = dt.timedelta(days=1)
_INCOME = {ActivityType.DIVIDEND, ActivityType.INTEREST}
_BALANCES = {AssetKind.CASH, AssetKind.DEPOSIT}


class NotEntitled(ValueError):
    """A dividend on a position that held no units when it was due: before its ex-date,
    or, without one, on any day up to its payment. Names no figure."""


@dataclass(frozen=True)
class IncomeShare:
    """The part of one income booking that falls on one lot, or on an account."""

    date: dt.date
    """The payment date."""
    account: str
    asset: str | None
    """None for interest on the account's own balance."""
    net: Decimal
    """In EUR: credited, after withheld tax."""
    taxes: Decimal
    """In EUR: the tax withheld on this part."""
    lot_opened: dt.date | None = None
    lot_source: str | None = None
    units: Decimal = _ZERO
    """The lot's units entitled to the income; 0 without a lot."""
    approximate: bool = False
    """True when the source gave no ex-date, so the entitled lots are a guess."""

    @property
    def gross(self) -> Decimal:
        return self.net + self.taxes


def income(
    activities: Iterable[Activity],
    as_of: dt.date,
    fx: FxRates | None = None,
    *,
    assets: Mapping[str, Asset] | None = None,
    asset: str | None = None,
    account: str | None = None,
    since: dt.date | None = None,
) -> list[IncomeShare]:
    """Income paid after `since` (exclusive) up to the end of `as_of`, per lot.

    Only the slice's positions are replayed, so a problem in another position doesn't stop
    it. An asset that isn't in `assets` is a security.
    """
    rates = fx or FxRates()
    kinds = {i: a.kind for i, a in (assets or {}).items()}
    every = [
        a
        for a in activities
        if (asset is None or a.asset == asset) and (account is None or a.account == account)
    ]
    out: list[IncomeShare] = []
    for a in every:
        if a.type not in _INCOME or a.date > as_of or (since is not None and a.date <= since):
            continue
        net = rates.book_eur(a.cash, a.currency, a.date, a.fx_rate)
        tax = rates.book_eur(a.taxes, a.currency, a.date, a.fx_rate)
        if a.asset is None or kinds.get(a.asset) in _BALANCES:
            out.append(IncomeShare(a.date, a.account, a.asset, net, tax))
            continue
        position = [b for b in every if b.asset == a.asset and b.account == a.account]
        lots, approximate = _entitled(position, a)
        units = [lot.units for lot in lots]
        for lot, part, part_tax in zip(
            lots, allocate(net, units), allocate(tax, units), strict=True
        ):
            out.append(
                IncomeShare(
                    a.date,
                    a.account,
                    a.asset,
                    part,
                    part_tax,
                    lot.opened,
                    lot.source,
                    lot.units,
                    approximate,
                )
            )
    return out


def _held(position: list[Activity], day: dt.date) -> list[Lot]:
    return build_lots(position, day, costs=False).lots


def _entitled(position: list[Activity], dividend: Activity) -> tuple[list[Lot], bool]:
    """The lots entitled to `dividend`, and whether that is a guess (no ex-date)."""
    if dividend.ex_date is not None:
        lots = _held(position, dividend.ex_date - _DAY)
        if not lots:
            raise NotEntitled("no units held on the day before the ex-date")
        return lots, False
    paid = dividend.date
    # Units only change on the position's activity days, so the last day on or before the
    # payment that held units is the payment day itself, an activity day or the day
    # before one.
    days = {paid}
    for b in position:
        if b.date <= paid and b.type not in _INCOME:
            days |= {b.date, b.date - _DAY}
    for day in sorted(days, reverse=True):
        if day <= paid and (lots := _held(position, day)):
            return lots, True
    raise NotEntitled("no units held on any day up to the payment")


def tax_of(a: Activity) -> Decimal:
    """The tax an activity costs, in its currency: withheld on a trade, income or expense;
    a Vorabpauschale's or a tax booking's cash paid. A refund is negative."""
    if a.type in {ActivityType.VORABPAUSCHALE, ActivityType.TAX}:
        return -a.cash
    return a.taxes


def taxes(
    activities: Iterable[Activity],
    as_of: dt.date,
    fx: FxRates | None = None,
    *,
    accounts: Mapping[str, Account] | None = None,
    asset: str | None = None,
    account: str | None = None,
    provider: str | None = None,
    since: dt.date | None = None,
) -> Decimal:
    """The taxes of the slice after `since` (exclusive) up to the end of `as_of`, in EUR.

    A tax belongs to its activity's asset; without an asset (a yearly settlement), to its
    account, and so to the account's provider. A slice by asset leaves those out. An
    account not in `accounts` belongs to no named provider.
    """
    rates = fx or FxRates()
    known = accounts or {}

    def in_slice(a: Activity) -> bool:
        return (
            (asset is None or a.asset == asset)
            and (account is None or a.account == account)
            and (
                provider is None
                or (a.account in known and known[a.account].provider == provider)
            )
            and a.date <= as_of
            and (since is None or a.date > since)
        )

    return exact_sum(
        rates.book_eur(tax_of(a), a.currency, a.date, a.fx_rate)
        for a in activities
        if in_slice(a) and tax_of(a)
    )
