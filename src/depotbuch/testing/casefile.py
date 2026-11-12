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
from pathlib import Path
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from depotbuch.engine.fx import FxRates
from depotbuch.engine.holdings import units_held
from depotbuch.engine.lots import LotBook, build_lots
from depotbuch.engine.model import Activity, ActivityType, Asset, AssetKind
from depotbuch.engine.money import Currency, Dec, round_cent

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
            if any(r <= 0 for r in rates.values()):
                raise ValueError("FX rates must be positive")
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


def _vp_factor(opened: date, record: date) -> Decimal:
    """The share of a year's Vorabpauschale a lot carries (§18 Abs. 2 InvStG).

    A notice recorded at the start of year Y+1 covers year Y. A lot bought before Y carries
    all of it; one bought in month m of Y carries (13 - m)/12; one bought later, none.
    """
    year = record.year - 1
    if opened.year < year:
        return Decimal(1)
    if opened.year > year:
        return Decimal(0)
    return Decimal(13 - opened.month) / 12


def _vp_per_unit(case: Case, asset: str, account: str, vp: Activity) -> dict[date, Decimal]:
    """Per unit of a lot opened on each date: the notice's amount spread over the units held
    at the end of the year it covers, weighted by `_vp_factor`."""
    record = vp.ex_date or vp.date
    year_end = date(record.year - 1, 12, 31)
    held = build_lots(case.activities, year_end, costs=False).open_lots(
        asset=asset, account=account
    )
    weight = sum((lot.units * _vp_factor(lot.opened, record) for lot in held), Decimal(0))
    if not vp.amount or weight == 0:
        return {}
    return {lot.opened: vp.amount * _vp_factor(lot.opened, record) / weight for lot in held}


def _taxable_gain(case: Case, expect: Expect, parqet: bool) -> Decimal:
    """For the private corpus: a provider's taxable gain on fund sales, rebuilt from FIFO.

    (gain before tax - Vorabpauschale already assessed on the units sold)
    x (1 - partial exemption). Each notice applies to the account it was booked in and to the
    lots held when its year started; a sale deducts, per unit closed, what its lot carried.
    Not an engine figure: the engine computes no German tax.
    """
    del parqet
    asset = _asset(expect, "taxable_gain")
    spec = case.assets.get(asset)
    if spec is None or spec.partial_exemption is None:
        raise ValueError("taxable_gain needs the asset's partial_exemption")
    rs = _book(case, expect).realizations(
        asset=asset, account=expect.slice.account, since=expect.since
    )
    notices = [
        a
        for a in case.activities
        if a.type is ActivityType.VORABPAUSCHALE and a.asset == asset and a.amount
    ]
    splits = [a for a in case.activities if a.type is ActivityType.SPLIT and a.asset == asset]
    deducted = Decimal(0)
    for r in rs:
        for vp in notices:
            record = vp.ex_date or vp.date
            if vp.account == r.account and r.lot_opened < record <= r.date:
                # A split between the notice and the sale would change what a unit is;
                # one anywhere else doesn't matter.
                if any(s.account == r.account and record <= s.date <= r.date for s in splits):
                    raise NotImplementedError("Vorabpauschale per unit across a split")
                share = _vp_per_unit(case, asset, r.account, vp).get(r.lot_opened, Decimal(0))
                deducted += share * r.units
    before_tax = sum((r.gain + r.taxes for r in rs), Decimal(0))
    return (before_tax - deducted) * (1 - spec.partial_exemption / 100)


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
