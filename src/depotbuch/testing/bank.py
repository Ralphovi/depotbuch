"""A broker's own arithmetic, for synthetic test data (issue #34).

The bank model books what a broker would book for a history of orders and prints the
documents it would send: trade confirmations, distribution and Vorabpauschale notices,
holdings statements, and the taxable gain of a fund sale. It follows the rules observed in
a real Consorsbank history, each checked there to the cent:

- A savings-plan buy: units = amount / price, half up to 5 decimals; the charge = units x
  price, half up to the cent; no fee.
- A holdings statement: each position's value = units x price (a bond's price in percent),
  half up to the cent; the total is the sum of those cents.
- A distribution: the units held at the end of the Schlusstag are entitled (the ex-date is
  the day after); gross = units x amount per unit, half up. A distribution may come as two
  notices, each rounded on its own.
- The taxable gain of a fund sale: proceeds after fees, less the FIFO cost of the units
  sold, less the Vorabpauschale already assessed on them, less the partial exemption,
  worked out per lot from a price per unit rounded to 4 decimals and rounded to the cent
  per lot.
- A partial sale takes its lot's cost share in cents, half up; a Vorabpauschale for year Y
  falls on the lots held at its end, a lot bought in month m of Y carrying (13 - m) / 12.

It imports nothing from `depotbuch.engine`, so its figures are an expectation the engine
did not produce.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

_CENT = Decimal("0.01")
_ZERO = Decimal(0)


def half_up(value: Decimal | Fraction, places: int = 2) -> Decimal:
    """`value` rounded half up (away from zero on a tie) to `places` decimals, exactly."""
    exact = Fraction(value)
    scaled = abs(exact) * 10**places
    whole = int(scaled)
    if scaled - whole >= Fraction(1, 2):
        whole += 1
    return (Decimal(whole) if exact >= 0 else -Decimal(whole)).scaleb(-places)


@dataclass(frozen=True)
class Trade:
    """A trade confirmation. `cash` is what the account is debited (< 0) or credited."""

    date: dt.date
    asset: str
    units: Decimal
    """Signed: positive for a buy. A bond's in nominal EUR."""
    price: Decimal
    charged: Decimal
    """Units x price (a bond's / 100), to the cent: the Kurswert."""
    fees: Decimal
    accrued: Decimal
    tax: Decimal
    cash: Decimal


@dataclass(frozen=True)
class Notice:
    """A distribution or coupon notice."""

    paid: dt.date
    schlusstag: dt.date
    asset: str
    kind: str
    """"dividend" or "interest"."""
    units: Decimal
    per_unit: Decimal
    gross: Decimal
    tax: Decimal

    @property
    def net(self) -> Decimal:
        return self.gross - self.tax


@dataclass(frozen=True)
class VpNotice:
    posted: dt.date
    asset: str
    year: int
    amount: Decimal
    tax: Decimal


@dataclass(frozen=True)
class Position:
    units: Decimal
    price: Decimal
    value: Decimal


@dataclass(frozen=True)
class Statement:
    date: dt.date
    positions: dict[str, Position]
    total: Decimal


@dataclass(frozen=True)
class SaleTax:
    date: dt.date
    asset: str
    taxable: Decimal


@dataclass
class _Lot:
    opened: dt.date
    units: Decimal
    cost: Decimal
    vp_per_unit: Fraction = Fraction(0)


@dataclass
class Bank:
    """One depot. Orders must come in date order; on one day, a Vorabpauschale first, then
    trades, then distributions' Schlusstag, then statements."""

    exemption: dict[str, Decimal] = field(default_factory=dict)
    """Partial exemption in percent, per fund whose sales get a taxable gain."""
    bonds: set[str] = field(default_factory=set)
    trades: list[Trade] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)
    vps: list[VpNotice] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    sale_taxes: list[SaleTax] = field(default_factory=list)
    _lots: dict[str, list[_Lot]] = field(default_factory=dict)

    def held(self, asset: str) -> Decimal:
        return sum((lot.units for lot in self._lots.get(asset, [])), _ZERO)

    def _charged(self, asset: str, units: Decimal, price: Decimal) -> Decimal:
        quote = Fraction(price) / 100 if asset in self.bonds else Fraction(price)
        return half_up(Fraction(units) * quote)

    def plan(self, day: dt.date, asset: str, amount: Decimal, price: Decimal) -> Trade:
        """A savings-plan buy of `amount` EUR."""
        units = half_up(Fraction(amount) / Fraction(price), 5)
        return self.buy(day, asset, units, price)

    def buy(
        self,
        day: dt.date,
        asset: str,
        units: Decimal,
        price: Decimal,
        *,
        fees: Decimal = _ZERO,
        accrued: Decimal = _ZERO,
    ) -> Trade:
        charged = self._charged(asset, units, price)
        cash = -(charged + fees + accrued)
        self._lots.setdefault(asset, []).append(_Lot(day, units, -cash))
        trade = Trade(day, asset, units, price, charged, fees, accrued, _ZERO, cash)
        self.trades.append(trade)
        return trade

    def sell(
        self,
        day: dt.date,
        asset: str,
        units: Decimal,
        price: Decimal,
        *,
        fees: Decimal = _ZERO,
        tax_rate: Decimal = _ZERO,
    ) -> Trade:
        """Sell `units` (positive). With a partial exemption on the asset, the taxable gain
        is recorded, and `tax_rate` (percent) of a positive one is withheld."""
        charged = self._charged(asset, units, price)
        received = charged - fees
        closed = self._close(asset, units)
        tax = _ZERO
        if asset in self.exemption:
            taxable = self._taxable(received, units, closed, self.exemption[asset])
            self.sale_taxes.append(SaleTax(day, asset, taxable))
            if taxable > 0:
                tax = half_up(Fraction(taxable) * Fraction(tax_rate) / 100)
        trade = Trade(day, asset, -units, price, charged, fees, _ZERO, tax, received - tax)
        self.trades.append(trade)
        return trade

    def _close(self, asset: str, units: Decimal) -> list[tuple[Decimal, Decimal, Fraction]]:
        """Close `units` FIFO: per lot slice, its units, cost in cents and Vorabpauschale."""
        queue = self._lots.get(asset, [])
        if sum((lot.units for lot in queue), _ZERO) < units:
            raise ValueError("the bank sells no more than the depot holds")
        out = []
        left = units
        while left > 0:
            lot = queue[0]
            take = min(lot.units, left)
            if take == lot.units:
                cost = lot.cost
                queue.pop(0)
            else:
                cost = half_up(Fraction(lot.cost) * Fraction(take) / Fraction(lot.units))
                lot.units -= take
                lot.cost -= cost
            out.append((take, cost, lot.vp_per_unit * Fraction(take)))
            left -= take
        return out

    @staticmethod
    def _taxable(
        received: Decimal,
        units: Decimal,
        closed: list[tuple[Decimal, Decimal, Fraction]],
        exemption: Decimal,
    ) -> Decimal:
        rate = Fraction(exemption) / 100
        price = half_up(Fraction(received) / Fraction(units), 4)
        exempt = _ZERO
        for take, cost, vp in closed:
            lot_gain = Fraction(half_up(Fraction(price) * Fraction(take))) - Fraction(cost) - vp
            exempt += half_up(lot_gain * rate)
        cost = sum((c for _, c, _ in closed), _ZERO)
        vp = sum((v for _, _, v in closed), Fraction(0))
        return half_up(Fraction(received) - Fraction(cost) - vp) - exempt

    def vorabpauschale(
        self, posted: dt.date, asset: str, amount: Decimal, tax: Decimal = _ZERO
    ) -> VpNotice:
        """The notice for the year before `posted`, spread over the lots held at its end."""
        year = posted.year - 1
        queue = self._lots.get(asset, [])

        def factor(lot: _Lot) -> Fraction:
            if lot.opened.year < year:
                return Fraction(1)
            return (
                Fraction(13 - lot.opened.month, 12) if lot.opened.year == year else Fraction(0)
            )

        weight = sum((Fraction(lot.units) * factor(lot) for lot in queue), Fraction(0))
        if weight:
            for lot in queue:
                lot.vp_per_unit += Fraction(amount) * factor(lot) / weight
        notice = VpNotice(posted, asset, year, amount, tax)
        self.vps.append(notice)
        return notice

    def distribute(
        self,
        schlusstag: dt.date,
        paid: dt.date,
        asset: str,
        per_unit: Decimal,
        *,
        kind: str = "dividend",
        split_at: Decimal | None = None,
        tax_rate: Decimal = _ZERO,
    ) -> list[Notice]:
        """A distribution on the units held at the end of `schlusstag`, in one notice, or in
        two when `split_at` units go on the first. `tax_rate` percent of each gross is
        withheld. A bond's coupon is per 100 nominal."""
        units = self.held(asset)
        if units <= 0:
            raise ValueError("nothing held on the Schlusstag")
        parts = [units] if split_at is None else [split_at, units - split_at]
        per = Fraction(per_unit) / 100 if asset in self.bonds else Fraction(per_unit)
        out = []
        for part in parts:
            gross = half_up(Fraction(part) * per)
            tax = half_up(Fraction(gross) * Fraction(tax_rate) / 100)
            out.append(Notice(paid, schlusstag, asset, kind, part, per_unit, gross, tax))
        self.notices.extend(out)
        return out

    def statement(self, day: dt.date, prices: dict[str, Decimal]) -> Statement:
        positions = {}
        for asset in sorted(self._lots):
            units = self.held(asset)
            if units:
                price = prices[asset]
                positions[asset] = Position(units, price, self._charged(asset, units, price))
        total = sum((p.value for p in positions.values()), _ZERO)
        st = Statement(day, positions, total)
        self.statements.append(st)
        return st
