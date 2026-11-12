"""FIFO lots, invested capital and realized gains (proposal 0001, *Lots*; architecture §8.3).

Each buy or delivery in opens a lot. A sale or delivery out closes lots first in, first out,
within the same account, as German tax law does. Amounts are converted to EUR when the
lot opens or closes: a trade at the broker's rate when its activity carries one, else at
the ECB rate for its date.

- A lot's cost is the cash paid for it, so purchase fees and any tax or accrued interest
  paid with it are part of invested capital. A delivery in carries its stated cost basis.
- A sale's realized gain is its cash received (after fees and taxes) less the cost of the
  units it closed. A delivery out closes lots without realizing a gain.
- A split multiplies the units of every open lot in its account by its ratio and leaves the
  cost unchanged. It takes effect at the start of its day, before that day's trades.
- Bonds are lots like any other, with the nominal amount as units (ADR-0014).

Nothing is rounded here (ADR-0013).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from decimal import Decimal

from depotbuch.engine.fx import FxRates
from depotbuch.engine.model import Activity, ActivityType

_ZERO = Decimal(0)


class Oversold(ValueError):
    """A sale or delivery out needs more units than the account holds.

    Carries the date and the missing units for the import report (architecture §8.7). The
    message names neither, so a log of a private case shows no figures.
    """

    def __init__(self, when: dt.date, missing: Decimal) -> None:
        super().__init__("more units sold than held")
        self.when = when
        self.missing = missing


class MissingCostBasis(ValueError):
    """A delivery in without a stated cost basis."""


@dataclass(frozen=True)
class Lot:
    account: str
    asset: str
    opened: dt.date
    units: Decimal
    cost: Decimal
    """In EUR, for the units still open."""
    source: str | None = None
    """The opening activity's FITID, when it has one."""


@dataclass(frozen=True)
class Realization:
    """The part of one sale that closed one lot."""

    date: dt.date
    account: str
    asset: str
    units: Decimal
    """Units closed, positive."""
    proceeds: Decimal
    """In EUR, after fees and taxes: this part's share of the sale's cash."""
    cost: Decimal
    taxes: Decimal
    """In EUR: this part's share of the tax withheld on the sale."""
    lot_opened: dt.date

    @property
    def gain(self) -> Decimal:
        return self.proceeds - self.cost


@dataclass
class LotBook:
    """Open lots and realizations, as of a date."""

    lots: list[Lot] = field(default_factory=list)
    realized: list[Realization] = field(default_factory=list)

    def open_lots(self, *, asset: str | None = None, account: str | None = None) -> list[Lot]:
        return [
            lot
            for lot in self.lots
            if (asset is None or lot.asset == asset)
            and (account is None or lot.account == account)
        ]

    def units(self, *, asset: str, account: str | None = None) -> Decimal:
        return sum((lot.units for lot in self.open_lots(asset=asset, account=account)), _ZERO)

    def invested_capital(
        self, *, asset: str | None = None, account: str | None = None
    ) -> Decimal:
        return sum((lot.cost for lot in self.open_lots(asset=asset, account=account)), _ZERO)

    def realizations(
        self,
        *,
        asset: str | None = None,
        account: str | None = None,
        since: dt.date | None = None,
    ) -> list[Realization]:
        """Realizations after `since` (exclusive), or all of them."""
        return [
            r
            for r in self.realized
            if (asset is None or r.asset == asset)
            and (account is None or r.account == account)
            and (since is None or r.date > since)
        ]

    def realized_gain(
        self,
        *,
        asset: str | None = None,
        account: str | None = None,
        since: dt.date | None = None,
    ) -> Decimal:
        rs = self.realizations(asset=asset, account=account, since=since)
        return sum((r.gain for r in rs), _ZERO)


_TRADES = {ActivityType.BUY, ActivityType.SELL, ActivityType.TRANSFER, ActivityType.SPLIT}


def _order(indexed: tuple[int, Activity]) -> tuple[dt.date, int, int]:
    i, a = indexed
    return (a.date, 0 if a.type is ActivityType.SPLIT else 1, i)


def build_lots(
    activities: Iterable[Activity],
    as_of: dt.date,
    fx: FxRates | None = None,
    *,
    costs: bool = True,
) -> LotBook:
    """Replay every unit-moving activity up to the end of `as_of` into FIFO lots.

    With `costs=False` only units are tracked (costs and proceeds stay 0), so no FX rate is
    needed; that is what a unit count uses.
    """
    rates = fx or FxRates()
    queues: dict[tuple[str, str], deque[Lot]] = defaultdict(deque)
    realized: list[Realization] = []
    for _, a in sorted(enumerate(activities), key=_order):
        if a.date > as_of or a.type not in _TRADES or a.asset is None:
            continue
        key = (a.account, a.asset)
        if a.type is ActivityType.SPLIT:
            ratio = a.ratio if a.ratio is not None else Decimal(1)  # the model requires it
            queues[key] = deque(replace(lot, units=lot.units * ratio) for lot in queues[key])
        elif a.units > _ZERO:
            queues[key].append(_open(a, rates, costs=costs))
        else:
            realized.extend(_close(queues[key], a, rates, costs=costs))
    lots = [lot for q in queues.values() for lot in q]
    return LotBook(lots=lots, realized=realized)


def _eur(a: Activity, amount: Decimal, rates: FxRates) -> Decimal:
    return rates.to_eur(amount, a.currency, a.date, a.fx_rate)


def _open(a: Activity, rates: FxRates, *, costs: bool) -> Lot:
    asset = a.asset or ""  # the caller skips activities without an asset
    if not costs:
        cost = _ZERO
    elif a.type is ActivityType.TRANSFER:
        if a.cost_basis is None:
            raise MissingCostBasis("a delivery in needs its stated cost basis")
        cost = a.cost_basis
    else:
        cost = _eur(a, -a.cash, rates)
    return Lot(a.account, asset, a.date, a.units, cost, a.fitid)


def _close(queue: deque[Lot], a: Activity, rates: FxRates, *, costs: bool) -> list[Realization]:
    """Close `-a.units` units FIFO. A sale realizes its cash pro rata; a delivery out
    realizes nothing."""
    asset = a.asset or ""  # the caller skips activities without an asset
    total = -a.units
    held = sum((lot.units for lot in queue), _ZERO)
    if held < total:
        raise Oversold(a.date, total - held)
    is_sale = a.type is ActivityType.SELL
    proceeds = _eur(a, a.cash, rates) if is_sale and costs else _ZERO
    taxes = _eur(a, a.taxes, rates) if is_sale and costs else _ZERO
    out: list[Realization] = []
    left = total
    while left > _ZERO:
        lot = queue[0]
        take = min(lot.units, left)
        share = take / total
        cost = lot.cost if take == lot.units else lot.cost * take / lot.units
        if take == lot.units:
            queue.popleft()
        else:
            queue[0] = replace(lot, units=lot.units - take, cost=lot.cost - cost)
        left -= take
        if is_sale:
            out.append(
                Realization(
                    a.date,
                    a.account,
                    asset,
                    take,
                    proceeds * share,
                    cost,
                    taxes * share,
                    lot.opened,
                )
            )
    return out
