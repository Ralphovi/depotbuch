"""Engine invariants as Hypothesis properties (issue #37).

Five rules the engine depends on, checked on drawn histories rather than hand-picked
examples:

1. A dividend's parts add up: the per-lot net and tax of an income booking sum exactly to
   the booking's, and no part has the opposite sign of its whole (ADR-0013).
2. Order doesn't matter: the figures are the same whatever order activities with distinct
   dates are passed in.
3. Positions are independent: activities of another asset or account change no figure of a
   slice that doesn't include them.
4. A value is the sum of its positions, each booked to the cent (ADR-0013).
5. Taxes are attributed once: every asset's taxes plus every account's asset-less taxes
   are the portfolio's (ADR-0016).

Two designed behaviours are allowed for, not treated as a broken rule: a split recorded in
any account restates the asset in every account, so a split of a slice's asset stays in
that slice's history whatever its account; and in an asset slice a Festgeld account counts
whole, its asset-less bookings included (ADR-0015). Invariant 5 is checked only for a
Festgeld account that books at most one asset.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

from hypothesis import Phase, find, given, settings
from hypothesis import strategies as st

from depotbuch.engine.fx import FxRates
from depotbuch.engine.income import IncomeShare, income, tax_of, taxes
from depotbuch.engine.lots import build_lots
from depotbuch.engine.model import (
    Account,
    Activity,
    Asset,
    AssetKind,
    DayCount,
    DepositTerms,
)
from depotbuch.engine.money import exact_sum, is_booked
from depotbuch.engine.valuation import Prices, value

START = date(2024, 1, 1)
SECURITIES = ("X1", "X2")
BROKERS = ("A", "B")
FESTGELD = "F"
DEPOSIT = "FG"
ASSETS = {
    "X1": Asset(id="X1"),
    "X2": Asset(id="X2"),
    DEPOSIT: Asset(id=DEPOSIT, kind=AssetKind.DEPOSIT),
}
NO_FX = FxRates()

amounts = st.decimals(min_value=Decimal("0.00001"), max_value=Decimal(10_000), places=5)
money = st.decimals(min_value=Decimal(0), max_value=Decimal(100_000), places=2)
signed = st.decimals(min_value=Decimal(-1_000), max_value=Decimal(10_000), places=2)
withheld = st.one_of(st.just(Decimal(0)), signed)
cents = st.decimals(min_value=Decimal("0.01"), max_value=Decimal(10), places=2)
"""Small amounts, where a split across lots most often lands between two cents."""


def act(day: int, kind: str, account: str, **kw: Any) -> Activity:
    """An activity on day `day` of the history; Decimals are passed as strings."""
    fields = {k: str(v) if isinstance(v, Decimal) else v for k, v in kw.items()}
    return Activity.model_validate(
        {"date": START + timedelta(days=day), "type": kind, "account": account, **fields}
    )


@dataclass(frozen=True)
class History:
    activities: list[Activity]
    accounts: dict[str, Account]
    prices: Prices
    end: date
    """The last activity's date."""


class _Units:
    """Units per (account, asset) at the end of each day, as the history is drawn."""

    def __init__(self) -> None:
        self.changes: dict[tuple[str, str], list[tuple[int, Decimal]]] = {}
        self.splits = 0

    def now(self, pos: tuple[str, str]) -> Decimal:
        steps = self.changes.get(pos)
        return steps[-1][1] if steps else Decimal(0)

    def on(self, pos: tuple[str, str], day: int) -> Decimal:
        held = Decimal(0)
        for when, units in self.changes.get(pos, []):
            if when <= day:
                held = units
        return held

    def set(self, pos: tuple[str, str], day: int, units: Decimal) -> None:
        self.changes.setdefault(pos, []).append((day, units))

    def ever(self) -> list[tuple[str, str]]:
        return sorted(p for p, steps in self.changes.items() if any(u for _, u in steps))


@dataclass(frozen=True)
class Step:
    """One drawn day of a history, read by `_activity` against what is held then. Every
    step draws the same fields, so Hypothesis shrinks a history by dropping steps."""

    kind: str
    account: str
    asset: str
    units: Decimal
    """A buy's units."""
    cash: Decimal
    """The amount paid, received or credited, >= 0."""
    tax: Decimal
    """Tax withheld (a refund if negative); a tax booking's signed cash."""
    part: int
    """A sale's quarters of the holding (4: all of it); a split's ratio."""
    pick: int
    """Which held position a dividend falls on, and which ex-date it has."""
    ex_date: bool
    fx_rate: Decimal | None
    """A dividend in USD at this broker rate; None for EUR."""


CASH_KINDS = ("deposit", "withdrawal", "interest", "fee", "tax")
KINDS = ("buy", "buy", "buy", "sell", "dividend", "dividend", "split", "vorabpauschale")
RATIOS = (Decimal(2), Decimal(3), Decimal("0.5"))


def _steps(
    kinds: Sequence[str], accounts: Sequence[str], assets: Sequence[str]
) -> st.SearchStrategy[Step]:
    return st.builds(
        Step,
        kind=st.sampled_from(kinds),
        account=st.sampled_from(accounts),
        asset=st.sampled_from(assets),
        units=amounts,
        cash=st.one_of(cents, money),
        tax=st.one_of(cents, withheld),
        part=st.integers(1, 4),
        pick=st.integers(0, 63),
        ex_date=st.booleans(),
        fx_rate=st.none()
        | st.decimals(min_value=Decimal("0.5"), max_value=Decimal(2), places=4),
    )


# Weighted to one position, so lots pile up there and other positions stay few.
steps = _steps(
    KINDS + CASH_KINDS,
    (BROKERS[0], BROKERS[0], *BROKERS, FESTGELD),
    (SECURITIES[0], *SECURITIES),
)


@st.composite
def histories(draw: st.DrawFn) -> History:
    """One activity a day, so every date is distinct: buys and sales of two securities in
    two accounts (a sale never exceeds what its account holds), splits, dividends with and
    without an ex-date and in a foreign currency at the broker's rate, Vorabpauschalen,
    withheld taxes and refunds, asset-less deposits, withdrawals, interest, fees and tax
    bookings, and maybe a Festgeld account whose deposit names its asset or not."""
    accounts = {acc: Account(id=acc, provider=f"P{acc}") for acc in BROKERS}
    out: list[Activity] = []
    if draw(st.booleans()):
        accounts[FESTGELD], opening = _festgeld(draw)
        out.append(opening)
    units = _Units()
    for step in draw(st.lists(steps, min_size=1, max_size=30)):
        out.append(_activity(step, len(out), units, accounts))
    return _priced(draw, out, accounts)


@st.composite
def dividend_histories(draw: st.DrawFn) -> History:
    """Buys, sales and splits of one position, then a dividend on it: any lots, any
    dividend."""
    accounts = {acc: Account(id=acc, provider=f"P{acc}") for acc in BROKERS}
    trades = _steps(("buy", "buy", "sell", "split"), BROKERS[:1], SECURITIES[:1])
    units = _Units()
    out: list[Activity] = []
    for step in [
        *draw(st.lists(trades, min_size=2, max_size=12)),
        draw(_steps(("dividend",), BROKERS[:1], SECURITIES[:1])),
    ]:
        out.append(_activity(step, len(out), units, accounts))
    return _priced(draw, out, accounts)


def _priced(draw: st.DrawFn, out: list[Activity], accounts: dict[str, Account]) -> History:
    closes = st.decimals(min_value=Decimal("0.001"), max_value=Decimal(1_000), places=3)
    prices = Prices({s: {START: draw(closes)} for s in SECURITIES})
    return History(out, accounts, prices, out[-1].date)


def _festgeld(draw: st.DrawFn) -> tuple[Account, Activity]:
    """A Festgeld account and its opening deposit on day 0, naming its asset or not."""
    principal = draw(st.decimals(min_value=Decimal(1), max_value=Decimal(100_000), places=2))
    terms = DepositTerms(
        principal=principal,
        rate=draw(st.decimals(min_value=Decimal(0), max_value=Decimal(5), places=3)),
        start=START,
        maturity=START + timedelta(days=400),
        day_count=draw(st.sampled_from(list(DayCount))),
    )
    named = {"asset": DEPOSIT} if draw(st.booleans()) else {}
    opening = act(0, "deposit", FESTGELD, cash=principal, **named)
    return Account(id=FESTGELD, provider="PF", deposit=terms), opening


def _activity(step: Step, day: int, units: _Units, accounts: dict[str, Account]) -> Activity:
    """`step` as an activity on `day`: an asset-less booking in its account (the first
    one if there is no Festgeld), else a trade of a security in a broker account."""
    if step.kind in CASH_KINDS:
        return _cash(step, day, step.account if step.account in accounts else BROKERS[0])
    account = step.account if step.account in BROKERS else BROKERS[0]
    if step.kind == "vorabpauschale":
        cash = -abs(step.tax)
        return act(day, step.kind, account, asset=step.asset, amount=step.cash, cash=cash)
    return _trade(step, day, (account, step.asset), units)


def _trade(step: Step, day: int, pos: tuple[str, str], units: _Units) -> Activity:
    """A sale, dividend or split where the holdings allow it, else a buy."""
    account, asset = pos
    held = units.now(pos)
    if step.kind == "sell" and held > 0:
        sold = held
        if step.part < 4 and held >= Decimal("0.00002"):
            quarters = (held * step.part / 4).quantize(Decimal("0.00001"), ROUND_DOWN)
            sold = max(quarters, Decimal("0.00001"))
        units.set(pos, day, held - sold)
        return act(
            day, "sell", account, asset=asset, units=-sold, cash=step.cash, taxes=step.tax
        )
    if step.kind == "dividend" and (ever := units.ever()):
        return _dividend(step, day, ever[step.pick % len(ever)], units)
    if step.kind == "split" and units.splits < 2:
        # either security alike, so a split often falls beside another held one
        asset = SECURITIES[step.pick % len(SECURITIES)]
        pos = account, asset
        held = units.now(pos)
        units.splits += 1
        ratio = RATIOS[step.part % len(RATIOS)]
        units.set(pos, day, held * ratio)
        return act(day, "split", account, asset=asset, ratio=ratio)
    units.set(pos, day, held + step.units)
    return act(day, "buy", account, asset=asset, units=step.units, cash=-step.cash)


def _dividend(step: Step, day: int, pos: tuple[str, str], units: _Units) -> Activity:
    """A dividend on a position that has held units: with an ex-date on a day after one
    that held units, or without one; in EUR or in USD at the broker's rate."""
    account, asset = pos
    entitled = [e for e in range(1, day + 1) if units.on(pos, e - 1) > 0]
    extra: dict[str, Any] = {}
    if step.ex_date and entitled:
        extra["ex_date"] = START + timedelta(days=entitled[step.pick % len(entitled)])
    if step.fx_rate is not None:
        extra |= {"currency": "USD", "fx_rate": step.fx_rate}
    return act(day, "dividend", account, asset=asset, cash=step.cash, taxes=step.tax, **extra)


def _cash(step: Step, day: int, account: str) -> Activity:
    """A booking without an asset: deposit, withdrawal, interest, fee or tax."""
    kind, cash = step.kind, step.cash
    if kind == "deposit":
        return act(day, kind, account, cash=cash + Decimal("0.01"))
    if kind == "withdrawal":
        return act(day, kind, account, cash=-cash - Decimal("0.01"))
    if kind == "interest":
        return act(day, kind, account, cash=cash, taxes=step.tax)
    if kind == "fee":
        return act(day, kind, account, cash=-cash)
    return act(day, kind, account, cash=step.tax)


def _value(
    h: History,
    acts: Sequence[Activity],
    on: date,
    *,
    asset: str | None = None,
    account: str | None = None,
) -> Decimal:
    return value(
        acts,
        on,
        assets=ASSETS,
        prices=h.prices,
        accounts=h.accounts,
        asset=asset,
        account=account,
    )


def _figures(
    h: History, acts: Sequence[Activity], on: date, asset: str | None, account: str | None
) -> dict[str, object]:
    """Every figure of a slice: value on `on`; invested capital, realized gain, income per
    lot and taxes up to the end."""
    book = build_lots(acts, h.end)
    shares = income(
        acts, h.end, assets=ASSETS, accounts=h.accounts, asset=asset, account=account
    )
    return {
        "value": _value(h, acts, on, asset=asset, account=account),
        "invested": book.invested_capital(asset=asset, account=account),
        "realized": book.realized_gain(asset=asset, account=account),
        "income": Counter(shares),
        "taxes": taxes(acts, h.end, accounts=h.accounts, asset=asset, account=account),
    }


def _days(h: History) -> st.SearchStrategy[date]:
    """A day of the history, counted back from its end so that it stays put while
    Hypothesis drops earlier steps."""
    return st.integers(0, (h.end - START).days).map(lambda d: h.end - timedelta(days=d))


def _whole(h: History, asset: str) -> set[str]:
    """The Festgeld accounts that book `asset`: its slice holds them whole (ADR-0015)."""
    return {
        a.account
        for a in h.activities
        if a.asset == asset and h.accounts[a.account].deposit is not None
    }


@settings(max_examples=200, deadline=None)
@given(st.one_of(dividend_histories(), histories()))
def test_income_splits_add_up(h: History) -> None:
    """Invariant 1: the parts of an income booking add up to its EUR net and withheld tax,
    to the cent, and no part has the opposite sign of its whole."""
    shares = income(h.activities, h.end, assets=ASSETS, accounts=h.accounts)
    parts: dict[tuple[date, str], list[IncomeShare]] = {}
    for s in shares:
        parts.setdefault((s.date, s.account), []).append(s)
    for a in h.activities:
        if a.type not in {"dividend", "interest"}:
            continue
        net = NO_FX.book_eur(a.cash, a.currency, a.date, a.fx_rate)
        tax = NO_FX.book_eur(a.taxes, a.currency, a.date, a.fx_rate)
        mine = parts[a.date, a.account]  # one activity a day
        assert exact_sum(s.net for s in mine) == net
        assert exact_sum(s.taxes for s in mine) == tax
        for s in mine:
            assert is_booked(s.net)
            assert is_booked(s.taxes)
            assert s.net * net >= 0
            assert s.taxes * tax >= 0


@settings(max_examples=100, deadline=None)
@given(st.data())
def test_order_does_not_matter(data: st.DataObject) -> None:
    """Invariant 2: activities with distinct dates give the same figures in any order."""
    h = data.draw(histories())
    shuffled = data.draw(st.permutations(h.activities))
    on = data.draw(_days(h))
    for account in (None, *h.accounts):
        given_order = _figures(h, h.activities, on, None, account)
        assert _figures(h, shuffled, on, None, account) == given_order, account
    for asset in ASSETS:
        given_order = _figures(h, h.activities, on, asset, None)
        assert _figures(h, shuffled, on, asset, None) == given_order, asset


@settings(max_examples=300, deadline=None)
@given(st.data())
def test_positions_are_independent(data: st.DataObject) -> None:
    """Invariant 3: dropping every activity of another asset or account leaves each
    slice's figures as they were. A split of the slice's asset stays, from any account: a
    split in one account restates the asset in all. A split of another asset goes. A
    Festgeld account that books the slice's asset stays whole (ADR-0015). The value is
    also compared on the day before each split, where a split restates what is held."""
    h = data.draw(histories())
    on = data.draw(_days(h))
    before_splits = {a.date - timedelta(days=1) for a in h.activities if a.type == "split"}
    for asset in (None, *ASSETS):
        whole = _whole(h, asset) if asset is not None else set()
        for account in (None, *h.accounts):
            own = [
                a
                for a in h.activities
                if (a.type == "split" and (asset is None or a.asset == asset))
                or (
                    (account is None or a.account == account)
                    and (asset is None or a.asset == asset or a.account in whole)
                )
            ]
            alone = _figures(h, own, on, asset, account)
            assert alone == _figures(h, h.activities, on, asset, account), (asset, account)
            for day in before_splits:
                assert _value(h, own, day, asset=asset, account=account) == _value(
                    h, h.activities, day, asset=asset, account=account
                ), (asset, account, day)


@settings(max_examples=150, deadline=None)
@given(st.data())
def test_a_value_is_the_sum_of_its_positions(data: st.DataObject) -> None:
    """Invariant 4: the value of the portfolio, and of each account, is the sum of its
    positions' values, each booked to the cent. A position is one asset in one account,
    an account's own balance (its bookings without an asset), or a Festgeld account."""
    h = data.draw(histories())
    on = data.draw(_days(h))
    total: list[Decimal] = []
    for account, spec in h.accounts.items():
        positions: list[Decimal] = []
        mine = [a for a in h.activities if a.account == account]
        if spec.deposit is not None:
            positions.append(_value(h, h.activities, on, account=account))
        else:
            for asset in sorted({a.asset for a in mine if a.asset is not None}):
                positions.append(_value(h, h.activities, on, asset=asset, account=account))
            balance = [a for a in mine if a.asset is None]
            positions.append(_value(h, balance, on, account=account))
        assert all(is_booked(p) for p in positions)
        assert _value(h, h.activities, on, account=account) == exact_sum(positions)
        total.extend(positions)
    assert _value(h, h.activities, on) == exact_sum(total)


@settings(max_examples=150, deadline=None)
@given(histories())
def test_taxes_are_attributed_once(h: History) -> None:
    """Invariant 5: the taxes of every asset, plus the tax of every account's asset-less
    bookings, are the portfolio's taxes. A Festgeld account's asset-less bookings count
    with the asset it books, not again with the account (ADR-0015). This covers only a
    Festgeld account that books at most one asset, as the histories draw it: one that
    books two would count its taxes once per asset."""
    by_asset = [taxes(h.activities, h.end, accounts=h.accounts, asset=s) for s in ASSETS]
    whole = set[str]().union(*(_whole(h, s) for s in ASSETS))
    assetless = [
        NO_FX.book_eur(tax_of(a), a.currency, a.date, a.fx_rate)
        for a in h.activities
        if a.asset is None and a.account not in whole
    ]
    total = taxes(h.activities, h.end, accounts=h.accounts)
    assert exact_sum([*by_asset, *assetless]) == total


def _lots_paid(h: History) -> int:
    """The most lots one income booking of `h` is split across."""
    shares = income(h.activities, h.end, assets=ASSETS, accounts=h.accounts)
    return max(Counter((s.date, s.account) for s in shares if s.lot_opened).values(), default=0)


def _held_positions(h: History) -> int:
    """The positions of `h` that hold units at the end."""
    return len({(lot.account, lot.asset) for lot in build_lots(h.activities, h.end).lots})


def _usd_ex_date(h: History) -> bool:
    return any(a.ex_date and a.currency == "USD" for a in h.activities) and _lots_paid(h) >= 2


def _split_beside(h: History) -> bool:
    """A split of one security while another security is held."""
    split = {a.asset for a in h.activities if a.type == "split"}
    held = {lot.asset for lot in build_lots(h.activities, h.end).lots}
    return any(held - {s} for s in split)


def _festgeld_named(h: History) -> bool:
    taxed = any(a.account == FESTGELD and a.type == "tax" for a in h.activities)
    return bool(_whole(h, DEPOSIT)) and taxed


def test_the_histories_reach_what_they_are_for() -> None:
    """Each fault the properties guard against needs a history that shows it: a dividend
    split across several lots, with an ex-date and in USD; a split of one security while
    another is held; a tax refund; a
    Festgeld whose deposit names its asset next to an asset-less tax; and positions held
    in several accounts and assets at once. `find` raises if none is drawn."""
    once = settings(max_examples=2_000, database=None, phases=[Phase.generate])
    find(dividend_histories(), lambda h: _lots_paid(h) >= 3, settings=once)
    find(histories(), _usd_ex_date, settings=once)
    find(histories(), _split_beside, settings=once)
    find(histories(), lambda h: any(tax_of(a) < 0 for a in h.activities), settings=once)
    find(histories(), _festgeld_named, settings=once)
    find(histories(), lambda h: _held_positions(h) >= 3, settings=once)
