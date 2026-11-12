"""The TOML case format (proposal 0002, *Two kinds of test case*).

A case holds activities, assets, prices and FX rates, and the results expected from them:

```toml
name = "..."
rule = "proposal 0001, Lots"
working = "the hand computation"

[[activities]]            # engine activity fields; amounts as strings
date = 2024-01-02
type = "buy"
asset = "X1"              # account defaults to "depot"
units = "10"
cash = "-1004.95"

[assets.X1]
currency = "USD"          # EUR by default

[prices.X1]               # closes in the asset's currency
2024-06-28 = "125.00"

[fx.USD]                  # USD per EUR, as the ECB quotes it
2024-06-28 = "1.0712"

[[expect]]
as_of = 2024-06-28
since = 2024-01-01        # for range metrics (realized_gain): after this day, up to as_of
slice = { asset = "X1" }
units = "3"               # one key per metric
parqet = { units = "3" }  # only where --parqet differs
```

Money metrics are compared to the cent, rounded half up (ADR-0013); units exactly. A
`tolerance` (EUR) is for the private corpus only, where a provider's own figure may differ
by its rounding; public cases never use one.

Public cases live in `tests/engine/cases/`; private ones in a corpus outside the
repository, run by `depotbuch.testing.reconcile`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from depotbuch.engine.fx import FxRates
from depotbuch.engine.holdings import units_held
from depotbuch.engine.lots import LotBook, Realization, build_lots
from depotbuch.engine.model import Activity, ActivityType, Asset, AssetKind
from depotbuch.engine.money import (
    Currency,
    Dec,
    book_exact,
    is_rate,
    multiply_units,
    round_cent,
)

DEFAULT_ACCOUNT = "depot"


class Slice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    asset: str | None = None
    account: str | None = None
    provider: str | None = None


class AssetSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: AssetKind = AssetKind.SECURITY
    currency: Currency = "EUR"
    isin: str | None = None
    partial_exemption: Dec | None = None
    """Teilfreistellung in percent, for the private `taxable_gain` check only; not an engine
    attribute (the engine computes no German tax)."""


class Expect(BaseModel):
    """One expectation: a date, a slice, and a value per metric."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: date
    since: date | None = None
    slice: Slice = Field(default_factory=Slice)
    metrics: dict[str, Dec]
    parqet: dict[str, Dec] = Field(default_factory=dict)
    tolerance: Dec | None = None

    @model_validator(mode="before")
    @classmethod
    def _collect_metrics(cls, data: Any) -> Any:
        """Every key that isn't `as_of`, `slice` or `parqet` is a metric."""
        if isinstance(data, dict) and "metrics" not in data:
            fixed = {"as_of", "since", "slice", "parqet", "tolerance"}
            data = {
                **{k: v for k, v in data.items() if k in fixed},
                "metrics": {k: v for k, v in data.items() if k not in fixed},
            }
        return data

    @model_validator(mode="after")
    def _known_metrics(self) -> Expect:
        if not self.metrics:
            raise ValueError("an expectation needs at least one metric")
        for name in (*self.metrics, *self.parqet):
            if name not in METRICS:
                raise ValueError("unknown metric")
        if not set(self.parqet) <= set(self.metrics):
            raise ValueError("a parqet value needs the same metric's default value")
        if self.tolerance is not None and self.tolerance < 0:
            raise ValueError("a tolerance can't be negative")
        if self.since is not None and self.since >= self.as_of:
            raise ValueError("since must be before as_of")
        return self


class Case(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    rule: str
    working: str = ""
    activities: list[Activity]
    assets: dict[str, AssetSpec] = Field(default_factory=dict)
    prices: dict[str, dict[date, Dec]] = Field(default_factory=dict)
    fx: dict[Currency, dict[date, Dec]] = Field(default_factory=dict)
    expect: list[Expect] = Field(min_length=1)

    @model_validator(mode="after")
    def _positive_rates(self) -> Case:
        for rates in self.fx.values():
            if not all(is_rate(r) for r in rates.values()):
                raise ValueError("FX rates must be between 0.000001 and 1000000")
        return self

    @model_validator(mode="before")
    @classmethod
    def _default_account(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("activities"), list):
            data = {
                **data,
                "activities": [
                    {"account": DEFAULT_ACCOUNT, **a} if isinstance(a, dict) else a
                    for a in data["activities"]
                ],
            }
        return data

    def asset_list(self) -> list[Asset]:
        """The case's assets as engine types; an asset used but not declared is EUR."""
        used = {a.asset for a in self.activities if a.asset}
        engine_fields = set(Asset.model_fields)
        return [
            Asset(
                id=i,
                **(
                    self.assets[i].model_dump(include=engine_fields) if i in self.assets else {}
                ),
            )
            for i in sorted(used | set(self.assets))
        ]

    def fx_rates(self) -> FxRates:
        return FxRates(self.fx)


def load_case(path: Path) -> Case:
    """Read and validate one case file. Raises tomllib.TOMLDecodeError or ValidationError."""
    with path.open("rb") as f:
        return Case.model_validate(tomllib.load(f))


# ---------------------------------------------------------------------------
# Metrics: what an expectation can check. Each later engine PR adds its own.
# ---------------------------------------------------------------------------

Metric = Callable[[Case, Expect, bool], Decimal]
"""(case, expectation, parqet mode) -> the engine's value."""


class Result(NamedTuple):
    expect: int
    metric: str
    mode: str
    want: Decimal
    got: Decimal
    ok: bool


def _asset(expect: Expect, metric: str) -> str:
    if expect.slice.provider is not None:
        raise NotImplementedError("provider slices arrive with the slice rule (#26)")
    if expect.slice.asset is None:
        raise ValueError(f"{metric} needs an asset in the slice")
    return expect.slice.asset


def _units(case: Case, expect: Expect, parqet: bool) -> Decimal:
    del parqet  # units don't depend on the mode
    return units_held(
        case.activities,
        expect.as_of,
        asset=_asset(expect, "units"),
        account=expect.slice.account,
    )


def _book(case: Case, expect: Expect) -> LotBook:
    return build_lots(case.activities, expect.as_of, case.fx_rates())


def _invested_capital(case: Case, expect: Expect, parqet: bool) -> Decimal:
    del parqet  # the cost of open lots doesn't depend on the mode
    if expect.slice.provider is not None:
        raise NotImplementedError("provider slices arrive with the slice rule (#26)")
    return _book(case, expect).invested_capital(
        asset=expect.slice.asset, account=expect.slice.account
    )


def _realized_gain(case: Case, expect: Expect, parqet: bool) -> Decimal:
    del parqet  # whether --parqet changes realized gains is settled with #29
    if expect.slice.provider is not None:
        raise NotImplementedError("provider slices arrive with the slice rule (#26)")
    return _book(case, expect).realized_gain(
        asset=expect.slice.asset, account=expect.slice.account, since=expect.since
    )


def _vp_factor(opened: date, year: int) -> Decimal:
    """The share of year `year`'s Vorabpauschale a lot carries (§18 Abs. 2 InvStG): all of
    it if bought before that year, (13 - m)/12 if bought in month m of it, none if later."""
    if opened.year < year:
        return Decimal(1)
    if opened.year > year:
        return Decimal(0)
    return Decimal(13 - opened.month) / 12


class _TaxLot:
    """A FIFO lot as the private check replays it: units, when it was acquired, and the
    Vorabpauschale per unit assessed on it so far."""

    def __init__(self, opened: date, units: Decimal) -> None:
        self.opened = opened
        self.units = units
        self.vp_per_unit = Decimal(0)


_LOT_MOVES = {ActivityType.SPLIT, ActivityType.BUY, ActivityType.SELL, ActivityType.TRANSFER}


def _vp_events(case: Case, asset: str, as_of: date) -> list[tuple[date, int, Activity]]:
    """The asset's notices and lot moves in replay order. A notice covering year Y takes
    effect at the start of Y+1, before splits and trades, whenever it was posted."""
    events: list[tuple[date, int, int, Activity]] = []
    for n, a in enumerate(case.activities):
        if a.asset != asset or a.date > as_of:
            continue
        if a.type is ActivityType.VORABPAUSCHALE and a.amount:
            events.append((date((a.ex_date or a.date).year, 1, 1), 0, n, a))
        elif a.type in _LOT_MOVES:
            events.append((a.date, 1 if a.type is ActivityType.SPLIT else 2, n, a))
    return [(e[0], e[2], e[3]) for e in sorted(events, key=lambda e: e[:3])]


def _assess(queue: list[_TaxLot], amount: Decimal, year: int) -> None:
    """Spread a notice for `year` over the lots held at its end, by `_vp_factor`."""
    weight = sum((lot.units * _vp_factor(lot.opened, year) for lot in queue), Decimal(0))
    if weight:
        for lot in queue:
            lot.vp_per_unit += amount * _vp_factor(lot.opened, year) / weight


def _close_tax_lots(queue: list[_TaxLot], units: Decimal) -> list[Decimal]:
    """Close `units` FIFO; return the Vorabpauschale each closed lot slice carried, in the
    order the engine's realizations close them."""
    left, carried = units, []
    while left > 0 and queue:
        lot = queue[0]
        take = min(lot.units, left)
        carried.append(lot.vp_per_unit * take)
        lot.units -= take
        left -= take
        if lot.units == 0:
            queue.pop(0)
    return carried


def _vp_deductions(case: Case, asset: str, as_of: date) -> dict[int, list[Decimal]]:
    """Per sale (its position in `case.activities`, as `Realization.sale`): the
    Vorabpauschale already assessed on the units it sold, per lot slice it closed.

    Replays the asset's lots in each account in the engine's FIFO order (a delivery by its
    acquisition date). Each lot carries the Vorabpauschale per unit assessed on it; a split
    divides that by its ratio; a sale deducts per unit closed what its lot carries.
    """
    lots: dict[str, list[_TaxLot]] = {}
    out: dict[int, list[Decimal]] = {}
    for when, n, a in _vp_events(case, asset, as_of):
        queue = lots.setdefault(a.account, [])
        if a.type is ActivityType.VORABPAUSCHALE:
            _assess(queue, a.amount or Decimal(0), when.year - 1)
        elif a.type is ActivityType.SPLIT:
            for lot in queue:
                lot.units = multiply_units(lot.units, a.ratio or Decimal(1))
                lot.vp_per_unit /= a.ratio or Decimal(1)
        elif a.units > 0:
            opened = a.acquired if a.type is ActivityType.TRANSFER and a.acquired else a.date
            k = len(queue)
            while k > 0 and queue[k - 1].opened > opened:
                k -= 1
            queue.insert(k, _TaxLot(opened, a.units))
        else:
            carried = _close_tax_lots(queue, -a.units)
            if a.type is ActivityType.SELL:
                out[n] = carried
    return out


def _taxable_gain(case: Case, expect: Expect, parqet: bool) -> Decimal:
    """For the private corpus: a provider's taxable gain on fund sales, rebuilt from FIFO
    the way Consorsbank computes it. Not an engine figure: the engine computes no German tax.

    Per sale, the gain before tax less the Vorabpauschale already assessed on the units
    sold (`_vp_deductions`), less the partial exemption. The exemption is worked out per
    lot and rounded to the cent there: each lot's proceeds are its units x the sale's
    proceeds per unit rounded to 4 decimals, booked to the cent, and its exemption is
    (those proceeds - its cost - its Vorabpauschale) x the exemption rate. Taking the rate
    of the whole gain instead is 1 to 3 cents off the bank's statements.
    """
    del parqet
    asset = _asset(expect, "taxable_gain")
    spec = case.assets.get(asset)
    if spec is None or spec.partial_exemption is None:
        raise ValueError("taxable_gain needs the asset's partial_exemption")
    rate = spec.partial_exemption / 100
    rs = _book(case, expect).realizations(
        asset=asset, account=expect.slice.account, since=expect.since
    )
    vp = _vp_deductions(case, asset, expect.as_of)
    sales: dict[int, list[Realization]] = {}
    for r in rs:
        sales.setdefault(r.sale, []).append(r)
    total = Decimal(0)
    for key, slices in sales.items():
        carried = vp.get(key) or [Decimal(0)] * len(slices)
        if len(carried) != len(slices):
            raise ValueError("the Vorabpauschale replay is out of step with the lots")
        units = sum((r.units for r in slices), Decimal(0))
        received = sum((r.proceeds + r.taxes for r in slices), Decimal(0))
        price = book_exact(Fraction(received) / Fraction(units) * 100) / 100  # 4 decimals
        for r, deducted in zip(slices, carried, strict=True):
            lot_gain = round_cent(price * r.units) - r.cost - deducted
            total += r.gain + r.taxes - deducted - round_cent(lot_gain * rate)
    return total


METRICS: dict[str, Metric] = {
    "units": _units,
    "invested_capital": _invested_capital,
    "realized_gain": _realized_gain,
    "taxable_gain": _taxable_gain,
}
MONEY = frozenset({"invested_capital", "realized_gain", "taxable_gain"})
"""Metrics compared to the cent."""
PRIVATE_ONLY = frozenset({"taxable_gain"})
"""Metrics for the private corpus, never used in a public case."""


def check(case: Case) -> list[Result]:
    """Evaluate every expectation in both modes.

    A metric without a `parqet` value must give the same result in both modes. Money is
    rounded to the cent before it is compared; a tolerance, where given, allows that much
    difference in EUR.
    """
    results = []
    for i, e in enumerate(case.expect):
        allowed = e.tolerance or Decimal(0)
        for name, expected in e.metrics.items():
            for mode, parqet in (("default", False), ("parqet", True)):
                want = e.parqet.get(name, expected) if parqet else expected
                got = METRICS[name](case, e, parqet)
                if name in MONEY:
                    got = round_cent(got)
                    ok = abs(got - want) <= allowed
                else:
                    ok = got == want  # units are exact; a tolerance is in EUR
                results.append(Result(i, name, mode, want, got, ok))
    return results
