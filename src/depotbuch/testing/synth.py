"""Synthetic histories and the case files they make (issue #34).

`history(seed)` invents a depot shaped like a real long-term one: monthly savings plans
into a few funds, now and then a buy or a partial sale on an exchange, quarterly
distributions (some in two notices), a yearly Vorabpauschale on each fund, a bond bought
with accrued interest and its yearly coupon, and quarterly holdings statements. Only the
kinds of event and the bank's rules come from a real history; every asset, date, price and
amount is drawn from a seeded random generator.

The bank model (`depotbuch.testing.bank`) books the history and prints its documents, and
`to_case` turns them into a case: the activities an importer would read, and as
expectations the figures the documents print. The engine never computes an expectation.

    python -m depotbuch.testing.synth SEED [--years N] [--extreme] > case.toml

`--extreme` draws from wider ranges (prices from cents to tens of thousands, large plans,
many split notices) for adversarial runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import random
import sys
from dataclasses import dataclass
from decimal import Decimal

from depotbuch.testing.bank import Bank, Notice, half_up

_DAY = dt.timedelta(days=1)
_ACC = ("F2", "F3")
"""Accumulating funds: no distributions."""
_DIST = "F1"
"""The distributing equity fund: quarterly distributions, the partial sales. Every fund
gets a Vorabpauschale notice each January, so a sale deducts what was assessed on it."""
_BOND = "B1"
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))
_DIST_MONTHS = (2, 5, 8, 11)


_WEEKEND = 5
"""`date.weekday()` of Saturday."""
_EXCHANGE_CHANCE = 0.004
"""Per weekday, the chance of a buy on an exchange."""
_VP_TAX_CHANCE = 0.5
_SPLIT_FROM = 2
"""Units held from which a distribution may come as two notices."""


def _business(day: dt.date) -> dt.date:
    """`day`, or the next weekday."""
    while day.weekday() >= _WEEKEND:
        day += _DAY
    return day


def _previous_business(day: dt.date) -> dt.date:
    """The last weekday before `day`."""
    day -= _DAY
    while day.weekday() >= _WEEKEND:
        day -= _DAY
    return day


def _third_tuesday(year: int, month: int) -> dt.date:
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(1 - first.weekday()) % 7 + 14)


def _fees(units: Decimal, price: Decimal) -> Decimal:
    """An invented exchange fee: 4.95 plus 0.25 % of the trade."""
    return half_up(Decimal("4.95") + units * price * Decimal("0.0025"))


@dataclass
class _Walk:
    """A price that moves a little each time it is read."""

    rng: random.Random
    price: Decimal
    places: int

    def next(self) -> Decimal:
        step = Decimal(self.rng.randint(-40, 45)) / 1000
        moved = half_up(self.price * (1 + step), self.places)
        self.price = max(moved, Decimal(1).scaleb(-self.places))
        return self.price


@dataclass
class Synthetic:
    seed: int
    bank: Bank
    prices: dict[str, dict[dt.date, Decimal]]
    end: dt.date


def history(seed: int, *, years: int = 6, extreme: bool = False) -> Synthetic:
    """Invent and book a history of `years` years from `seed`."""
    rng = random.Random(seed)  # noqa: S311 - test data, not a secret
    start = dt.date(rng.randint(2012, 2020), rng.randint(1, 12), 1)
    end = dt.date(start.year + years, start.month, 1) - _DAY
    book = _Book(rng, extreme, start, end)
    day = start
    while day <= end:
        book.day(day)
        day += _DAY
    return Synthetic(seed, book.bank, book.prices, end)


class _Book:
    """The draws for one history, and the bank that books it day by day."""

    def __init__(self, rng: random.Random, extreme: bool, start: dt.date, end: dt.date) -> None:
        self.rng, self.extreme = rng, extreme
        low, high = (
            (Decimal("0.05"), Decimal(20000)) if extreme else (Decimal(20), Decimal(300))
        )
        # Log-uniform, so a wide range reaches its cents as often as its thousands.
        span = math.log(high) - math.log(low)
        self.walks = {
            a: _Walk(rng, max(half_up(low * Decimal(math.exp(rng.random() * span)), 2), low), 2)
            for a in (_DIST, *_ACC)
        }
        self.walks[_BOND] = _Walk(rng, Decimal(rng.randint(9500, 11500)) / 100, 3)
        amounts = (1, 5000, 99999) if extreme else (25, 50, 75, 100, 150, 250)
        self.plans = {a: Decimal(rng.choice(amounts)) for a in (_DIST, *_ACC)}
        self.plan_day = rng.choice((1, 15))
        self.coupon = Decimal(rng.choice(("0.5", "1.25", "2", "3.75")))
        self.coupon_day = (rng.randint(1, 12), rng.randint(1, 28))
        self.bond_buy = _business(start + dt.timedelta(days=rng.randint(200, 900)))
        last_sale = (end - start).days - 30
        self.sales = {
            _business(start + dt.timedelta(days=rng.randint(400, last_sale)))
            for _ in range(rng.randint(1, 2))
            if last_sale > 400  # noqa: PLR2004 - a sale after the first year
        }
        self.split_chance = 0.6 if extreme else 0.2
        self.bank = Bank(exemption={_DIST: Decimal(30)}, bonds={_BOND})
        self.prices: dict[str, dict[dt.date, Decimal]] = {a: {} for a in self.walks}
        self.payouts: list[tuple[dt.date, dt.date, str, Decimal]] = []
        """(Schlusstag, payment day, asset, amount per unit or per 100 nominal)."""

    def day(self, day: dt.date) -> None:
        """Book `day`: Vorabpauschale, trades, Schlusstag, statement, in that order."""
        if day.weekday() < _WEEKEND:
            self._vorabpauschale(day)
            self._trades(day)
            self._announce(day)
        self._pay_due(day)
        if (day.month, day.day) in _QUARTER_ENDS:
            quote = {a: w.next() for a, w in self.walks.items() if self.bank.held(a)}
            for a, p in quote.items():
                self.prices[a][day] = p
            if quote:
                self.bank.statement(day, quote)

    def _trades(self, day: dt.date) -> None:
        rng, bank = self.rng, self.bank
        for asset, amount in self.plans.items():
            if day == _business(day.replace(day=self.plan_day)):
                bank.plan(day, asset, amount, self.walks[asset].next())
        if rng.random() < _EXCHANGE_CHANCE:
            asset = rng.choice((_DIST, *_ACC))
            units = Decimal(rng.randint(1, 5000 if self.extreme else 60))
            price = self.walks[asset].next()
            bank.buy(day, asset, units, price, fees=_fees(units, price))
        if day == self.bond_buy:
            self._buy_bond(day)
        if day in self.sales and bank.held(_DIST) > 1:
            units = half_up(bank.held(_DIST) * Decimal(rng.randint(20, 60)) / 100, 5)
            price = self.walks[_DIST].next()
            rate = Decimal(rng.choice(("0", "26.375")))
            bank.sell(day, _DIST, units, price, fees=_fees(units, price), tax_rate=rate)

    def _announce(self, day: dt.date) -> None:
        """Note the distributions and coupons whose Schlusstag is `day`."""
        if (
            day.month in _DIST_MONTHS
            and day == _third_tuesday(day.year, day.month)
            and self.bank.held(_DIST) > 0
        ):
            per = Decimal(self.rng.randint(500, 9000)) / 10000
            paid = _business(day + dt.timedelta(days=16))
            self.payouts.append((day, paid, _DIST, per))
        coupon_date = _business(dt.date(day.year, *self.coupon_day))
        if self.bank.held(_BOND) > 0 and day == _previous_business(coupon_date):
            self.payouts.append((day, coupon_date, _BOND, self.coupon))

    def _pay_due(self, day: dt.date) -> None:
        """Book every distribution whose Schlusstag is `day` on the units held then."""
        for schlusstag, paid, asset, per in self.payouts:
            if schlusstag != day:
                continue
            held = self.bank.held(asset)
            split = None
            if asset != _BOND and held > _SPLIT_FROM and self.rng.random() < self.split_chance:
                split = half_up(held * Decimal(self.rng.randint(10, 90)) / 100, 0)
            kind = "interest" if asset == _BOND else "dividend"
            tax = Decimal(self.rng.choice(("0", "0", "26.375")))
            self.bank.distribute(
                schlusstag, paid, asset, per, kind=kind, split_at=split, tax_rate=tax
            )

    def _vorabpauschale(self, day: dt.date) -> None:
        """On the first business day after New Year, last year's notice per fund held. A
        distributing fund gets one too when it paid out less than the Vorabpauschale."""
        if day != _business(dt.date(day.year, 1, 2)):
            return
        for asset in (_DIST, *_ACC):
            if self.bank.held(asset) > 0:
                top = 20000 if self.extreme else 9000
                amount = half_up(Decimal(self.rng.randint(0, top)) / 100)
                tax = Decimal(0)
                if self.rng.random() < _VP_TAX_CHANCE:
                    tax = half_up(amount * Decimal("0.7") * Decimal("0.26375"))
                self.bank.vorabpauschale(day, asset, amount, tax)

    def _buy_bond(self, day: dt.date) -> None:
        nominal = Decimal(self.rng.choice((1000, 2000, 5000, 10000)))
        last = dt.date(day.year, *self.coupon_day)
        if last > day:
            last = dt.date(day.year - 1, *self.coupon_day)
        accrued = half_up(nominal * self.coupon / 100 * (day - last).days / 365)
        price = self.walks[_BOND].next()
        self.bank.buy(day, _BOND, nominal, price, fees=Decimal("2.50"), accrued=accrued)


# ---------------------------------------------------------------------------
# The case file
# ---------------------------------------------------------------------------


def _q(value: object) -> str:
    return f'"{value}"'


def to_case(syn: Synthetic, name: str | None = None) -> str:
    """The case file for a synthetic history: activities from its documents, and the
    documents' figures as expectations."""
    bank = syn.bank
    name = name or f"synthetic-{syn.seed}"
    out = [
        f"name = {_q(name)}",
        'rule = "issue #34: a synthetic history matches its bank documents"',
        f'working = "generated by depotbuch.testing.synth from seed {syn.seed}"',
        "",
        f"[assets.{_DIST}]",
        'partial_exemption = "30"',
        "",
        f"[assets.{_BOND}]",
        'kind = "bond"',
        "",
    ]
    for asset, series in sorted(syn.prices.items()):
        if series:
            out += [f"[prices.{asset}]"]
            out += [f"{d} = {_q(p)}" for d, p in sorted(series.items())] + [""]
    for t in bank.trades:
        kind = "buy" if t.units > 0 else "sell"
        out += [
            "[[activities]]",
            f"date = {t.date}",
            f"type = {_q(kind)}",
            f"asset = {_q(t.asset)}",
            f"units = {_q(t.units)}",
            f"cash = {_q(t.cash)}",
            f"fees = {_q(t.fees)}",
            f"taxes = {_q(t.tax)}",
            "",
        ]
    for v in bank.vps:
        out += [
            "[[activities]]",
            f"date = {v.posted}",
            'type = "vorabpauschale"',
            f"asset = {_q(v.asset)}",
            f"amount = {_q(v.amount)}",
            f"cash = {_q(-v.tax)}",
            "",
        ]
    payments: dict[tuple[dt.date, str], list[Notice]] = {}
    for n in bank.notices:
        payments.setdefault((n.paid, n.asset), []).append(n)
    for (paid, asset), notices in sorted(payments.items()):
        out += [
            "[[activities]]",
            f"date = {paid}",
            f"type = {_q(notices[0].kind)}",
            f"asset = {_q(asset)}",
            f"cash = {_q(sum(n.net for n in notices))}",
            f"taxes = {_q(sum(n.tax for n in notices))}",
            f"ex_date = {notices[0].schlusstag + _DAY}",
            "",
        ]
    out += _expectations(syn, payments)
    return "\n".join(out)


def _expectations(
    syn: Synthetic, payments: dict[tuple[dt.date, str], list[Notice]]
) -> list[str]:
    bank = syn.bank
    out: list[str] = []
    for st in bank.statements:
        for asset, p in st.positions.items():
            out += [
                "[[expect]]",
                f"as_of = {st.date}",
                f"slice = {{ asset = {_q(asset)} }}",
                f"units = {_q(p.units)}",
                f"value = {_q(p.value)}",
                "",
            ]
        out += ["[[expect]]", f"as_of = {st.date}", f"value = {_q(st.total)}", ""]
    for (paid, asset), notices in sorted(payments.items()):
        out += [
            "[[expect]]",
            f"as_of = {paid}",
            f"since = {paid - _DAY}",
            f"slice = {{ asset = {_q(asset)} }}",
            f"income = {_q(sum(n.net for n in notices))}",
            f"withheld_tax = {_q(sum(n.tax for n in notices))}",
            f"entitled_units = {_q(sum(n.units for n in notices))}",
            "",
        ]
    for s in bank.sale_taxes:
        out += [
            "[[expect]]",
            f"as_of = {s.date}",
            f"since = {s.date - _DAY}",
            f"slice = {{ asset = {_q(s.asset)} }}",
            f"taxable_gain = {_q(s.taxable)}",
            "",
        ]
    paid_tax: dict[str, Decimal] = {}
    for t in bank.trades:
        paid_tax[t.asset] = paid_tax.get(t.asset, Decimal(0)) + t.tax
    for n in bank.notices:
        paid_tax[n.asset] = paid_tax.get(n.asset, Decimal(0)) + n.tax
    for v in bank.vps:
        paid_tax[v.asset] = paid_tax.get(v.asset, Decimal(0)) + v.tax
    # A distribution due before the end can be paid after it.
    last = max([syn.end, *(n.paid for n in bank.notices)])
    for asset, tax in sorted(paid_tax.items()):
        out += [
            "[[expect]]",
            f"as_of = {last}",
            f"slice = {{ asset = {_q(asset)} }}",
            f"taxes = {_q(tax)}",
            "",
        ]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("seed", type=int)
    parser.add_argument("--years", type=int, default=6)
    parser.add_argument("--extreme", action="store_true")
    args = parser.parse_args(argv)
    sys.stdout.write(to_case(history(args.seed, years=args.years, extreme=args.extreme)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
