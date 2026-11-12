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
slice = { asset = "X1" }
units = "3"               # one key per metric
parqet = { units = "3" }  # only where --parqet differs
```

Public cases live in `tests/engine/cases/`; private ones in a corpus outside the
repository, run by `depotbuch.testing.reconcile`.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from depotbuch.engine.holdings import units_held
from depotbuch.engine.model import Activity, Asset, AssetKind
from depotbuch.engine.money import Currency, Dec

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


class Expect(BaseModel):
    """One expectation: a date, a slice, and a value per metric."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: date
    slice: Slice = Field(default_factory=Slice)
    metrics: dict[str, Dec]
    parqet: dict[str, Dec] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _collect_metrics(cls, data: Any) -> Any:
        """Every key that isn't `as_of`, `slice` or `parqet` is a metric."""
        if isinstance(data, dict) and "metrics" not in data:
            fixed = {"as_of", "slice", "parqet"}
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
        return [
            Asset(id=i, **(self.assets[i].model_dump() if i in self.assets else {}))
            for i in sorted(used | set(self.assets))
        ]


def load_case(path: Path) -> Case:
    """Read and validate one case file. Raises tomllib.TOMLDecodeError or ValidationError."""
    with path.open("rb") as f:
        return Case.model_validate(tomllib.load(f))


# ---------------------------------------------------------------------------
# Metrics: what an expectation can check. Each later engine PR adds its own.
# ---------------------------------------------------------------------------

Metric = Callable[[Case, Expect, bool], Decimal]
"""(case, expectation, parqet mode) -> the engine's value."""


def _units(case: Case, expect: Expect, parqet: bool) -> Decimal:
    del parqet  # units don't depend on the mode
    if expect.slice.asset is None:
        raise ValueError("units need an asset in the slice")
    if expect.slice.provider is not None:
        raise NotImplementedError("provider slices arrive with the slice rule (#26)")
    return units_held(
        case.activities, expect.as_of, asset=expect.slice.asset, account=expect.slice.account
    )


METRICS: dict[str, Metric] = {"units": _units}


def check(case: Case) -> list[tuple[int, str, str, Decimal, Decimal]]:
    """Evaluate every expectation in both modes.

    Returns (expect index, metric, mode, expected, actual) for each comparison. A metric
    without a `parqet` value must give the same result in both modes.
    """
    results = []
    for i, e in enumerate(case.expect):
        for name, expected in e.metrics.items():
            for mode, parqet in (("default", False), ("parqet", True)):
                want = e.parqet.get(name, expected) if parqet else expected
                results.append((i, name, mode, want, METRICS[name](case, e, parqet)))
    return results
