import tomllib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from depotbuch.engine.model import AssetKind
from depotbuch.testing.casefile import DEFAULT_ACCOUNT, Case, check, load_case

USD_CASE = """
name = "usd-round-trip"
rule = "proposal 0002, case format"

[[activities]]
date = 2024-01-02
type = "buy"
asset = "U1"
units = "2"
cash = "-185.00"
currency = "USD"
fx_rate = "1.0950"

[assets.U1]
currency = "USD"

[assets.B1]
kind = "bond"

[prices.U1]
2024-01-02 = "92.50"

[fx.USD]
2024-01-02 = "1.0956"

[[expect]]
as_of = 2024-01-02
slice = { asset = "U1" }
units = "2"
parqet = { units = "2" }
"""


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "case.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_case_loads_into_engine_types_and_round_trips(tmp_path: Path) -> None:
    case = load_case(write(tmp_path, USD_CASE))
    buy = case.activities[0]
    assert buy.account == DEFAULT_ACCOUNT
    assert buy.currency == "USD"
    assert buy.fx_rate == Decimal("1.0950")
    assert case.fx["USD"][date(2024, 1, 2)] == Decimal("1.0956")
    assert case.prices["U1"][date(2024, 1, 2)] == Decimal("92.50")
    assets = {a.id: a for a in case.asset_list()}
    assert assets["U1"].currency == "USD"
    assert assets["B1"].kind is AssetKind.BOND
    again = Case.model_validate(case.model_dump(mode="json"))
    assert again == case


def test_check_runs_both_modes(tmp_path: Path) -> None:
    results = check(load_case(write(tmp_path, USD_CASE)))
    assert [(m, mode) for _, m, mode, _, _ in results] == [
        ("units", "default"),
        ("units", "parqet"),
    ]
    assert all(want == got for *_, want, got in results)


@pytest.mark.parametrize(
    "change",
    [
        ('units = "2"\ncash', "units = 2.0\ncash"),  # a float amount
        ('units = "2"\nparqet', 'colour = "2"\nparqet'),  # an unknown metric
        ("[fx.USD]", "[fx.usd]"),  # a lower-case currency
        ('type = "buy"', 'type = "buy"\nnote = "x"'),  # an unknown activity field
        ('units = "2"\nparqet = { units = "2" }', ""),  # an expectation without metrics
        ('units = "2"\nparqet', "parqet"),  # a parqet value without a default
    ],
)
def test_invalid_cases_are_rejected(tmp_path: Path, change: tuple[str, str]) -> None:
    text = USD_CASE.replace(*change, 1)
    assert text != USD_CASE
    with pytest.raises(ValidationError):
        load_case(write(tmp_path, text))


def test_provider_slices_are_not_supported_yet(tmp_path: Path) -> None:
    old = 'slice = { asset = "U1" }'
    text = USD_CASE.replace(old, 'slice = { asset = "U1", provider = "p" }')
    with pytest.raises(NotImplementedError):
        check(load_case(write(tmp_path, text)))


def test_malformed_toml_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        load_case(write(tmp_path, "name = \n"))
