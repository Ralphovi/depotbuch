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
    assert [(r.metric, r.mode) for r in results] == [("units", "default"), ("units", "parqet")]
    assert all(r.ok for r in results)


@pytest.mark.parametrize(
    "change",
    [
        ('units = "2"\ncash', "units = 2.0\ncash"),  # a float amount
        ('units = "2"\nparqet', 'colour = "2"\nparqet'),  # an unknown metric
        ("[fx.USD]", "[fx.usd]"),  # a lower-case currency
        ('type = "buy"', 'type = "buy"\nnote = "x"'),  # an unknown activity field
        ('units = "2"\nparqet = { units = "2" }', ""),  # an expectation without metrics
        ('units = "2"\nparqet', "parqet"),  # a parqet value without a default
        ('2024-01-02 = "1.0956"', '2024-01-02 = "0"'),  # a zero FX rate
        ('2024-01-02 = "1.0956"', '2024-01-02 = "-1.0956"'),  # a negative FX rate
    ],
)
def test_invalid_cases_are_rejected(tmp_path: Path, change: tuple[str, str]) -> None:
    text = USD_CASE.replace(*change, 1)
    assert text != USD_CASE
    with pytest.raises(ValidationError):
        load_case(write(tmp_path, text))


def test_a_tolerance_applies_to_money_only(tmp_path: Path) -> None:
    # 185.00 USD at the broker's 1.0950 is 168.95 EUR: within 0.05 of 168.92, so the money
    # metric passes, while 2 units never pass for 2.01, whatever the tolerance.
    text = USD_CASE.replace(
        'units = "2"\nparqet = { units = "2" }',
        'units = "2.01"\ninvested_capital = "168.92"\ntolerance = "0.05"',
    )
    results = {(r.metric, r.mode): r.ok for r in check(load_case(write(tmp_path, text)))}
    assert results == {
        ("units", "default"): False,
        ("units", "parqet"): False,
        ("invested_capital", "default"): True,
        ("invested_capital", "parqet"): True,
    }


def test_provider_slices_are_not_supported_yet(tmp_path: Path) -> None:
    old = 'slice = { asset = "U1" }'
    text = USD_CASE.replace(old, 'slice = { asset = "U1", provider = "p" }')
    with pytest.raises(NotImplementedError):
        check(load_case(write(tmp_path, text)))


def test_malformed_toml_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(tomllib.TOMLDecodeError):
        load_case(write(tmp_path, "name = \n"))


VP_CASE = """
name = "vp"
rule = "private taxable_gain"

[assets.F1]
partial_exemption = "30"

[[activities]]
date = 2021-06-01
type = "buy"
asset = "F1"
units = "10"
cash = "-1000.00"

[[activities]]
date = 2022-04-15
type = "buy"
asset = "F1"
units = "10"
cash = "-1100.00"

[[activities]]
date = 2023-01-01
type = "vorabpauschale"
asset = "F1"
amount = "19.00"

[[activities]]
date = 2023-01-01
type = "vorabpauschale"
account = "other"
asset = "F1"
amount = "500.00"

[[activities]]
date = 2023-06-01
type = "sell"
asset = "F1"
units = "-15"
cash = "1800.00"

[[expect]]
as_of = 2023-06-30
slice = { asset = "F1" }
taxable_gain = "164.55"
"""


def test_taxable_gain_deducts_the_vorabpauschale_of_the_units_sold(tmp_path: Path) -> None:
    """The 2023 notice covers 2022: lot 1 (bought 2021) carries all of it, lot 2 (bought in
    April 2022) 9/12. Weight 10 x 1 + 10 x 0.75 = 17.5, so 19.00 is 19/17.5 per unit of
    lot 1 and 0.75 x that per unit of lot 2. The sale of 15 closes lot 1 and 5 of lot 2:
    gain 1800 - 1000 - 550 = 250, Vorabpauschale 10 x 19/17.5 + 5 x 0.75 x 19/17.5 =
    14.928571..., taxable (250 - 14.928571...) x 0.7 = 164.55. The notice in the other
    account doesn't apply."""
    results = check(load_case(write(tmp_path, VP_CASE)))
    assert all(r.ok for r in results), results
