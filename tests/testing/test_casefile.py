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


def test_a_split_scales_the_vorabpauschale_per_unit(tmp_path: Path) -> None:
    """A 2-for-1 split on 2023-03-01 doubles every lot's units and halves its per-unit
    Vorabpauschale. Selling 30 of the 40 units closes lot 1 (20, carrying 10 x 19/17.5)
    and 10 of lot 2's 20 (carrying half of 10 x 0.75 x 19/17.5): deduction 10.857142... +
    4.071428... = 14.928571..., the same as selling 15 before the split. Gain 1800.00 - 1000.00
    - 550.00 = 250.00; taxable (250.00 - 14.93) x 0.7 = 164.55."""
    text = (
        VP_CASE.replace('units = "-15"', 'units = "-30"').replace(
            "date = 2023-06-01", "date = 2023-06-01"
        )
        + '\n[[activities]]\ndate = 2023-03-01\ntype = "split"\nasset = "F1"\nratio = "2"\n'
    )
    assert all(r.ok for r in check(load_case(write(tmp_path, text))))


def test_a_late_notice_applies_to_a_sale_before_it_was_posted(tmp_path: Path) -> None:
    """The notice covering 2022 is posted on 2023-02-15; the sale of 15 on 2023-01-10 comes
    first but after the start of 2023, so it deducts the same 14.928571... as before:
    taxable (250.00 - 14.93) x 0.7 = 164.55."""
    text = VP_CASE.replace(
        'date = 2023-01-01\ntype = "vorabpauschale"\nasset',
        'date = 2023-02-15\ntype = "vorabpauschale"\nasset',
    ).replace("date = 2023-06-01", "date = 2023-01-10")
    assert all(r.ok for r in check(load_case(write(tmp_path, text))))


def test_lots_acquired_on_the_same_day_keep_their_own_vorabpauschale(tmp_path: Path) -> None:
    """Lot 1 (2021-06-01) is held at the end of 2022 and carries the whole 10.00 notice.
    A delivery in 2023 brings a second lot also acquired on 2021-06-01, which carries none.
    Selling both (20 units for 2200.00, cost 1000.00 + 1000.00) deducts 10.00 once:
    taxable (200.00 - 10.00) x 0.7 = 133.00."""
    text = """
name = "same-day"
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
date = 2023-01-02
type = "vorabpauschale"
asset = "F1"
amount = "10.00"
[[activities]]
date = 2023-03-01
type = "transfer"
asset = "F1"
units = "10"
cost_basis = "1000.00"
acquired = 2021-06-01
[[activities]]
date = 2023-06-01
type = "sell"
asset = "F1"
units = "-20"
cash = "2200.00"
[[expect]]
as_of = 2023-06-30
slice = { asset = "F1" }
taxable_gain = "133.00"
"""
    assert all(r.ok for r in check(load_case(write(tmp_path, text))))


def test_taxable_gain_deducts_the_vorabpauschale_of_the_units_sold(tmp_path: Path) -> None:
    """The 2023 notice covers 2022: lot 1 (bought 2021) carries all of it, lot 2 (bought in
    April 2022) 9/12. Weight 10 x 1 + 10 x 0.75 = 17.5, so 19.00 is 19/17.5 per unit of
    lot 1 and 0.75 x that per unit of lot 2. The sale of 15 closes lot 1 and 5 of lot 2:
    gain 1800 - 1000 - 550 = 250, Vorabpauschale 10 x 19/17.5 + 5 x 0.75 x 19/17.5 =
    14.928571..., taxable (250 - 14.928571...) x 0.7 = 164.55. The notice in the other
    account doesn't apply."""
    results = check(load_case(write(tmp_path, VP_CASE)))
    assert all(r.ok for r in results), results


def test_vorabpauschale_is_spread_over_the_year_end_holding(tmp_path: Path) -> None:
    """The notice is booked on 2023-02-15, after 5 units of lot 1 were sold on 2023-01-10.
    It covers 2022, so it is spread over the 2022 year-end holding: weight 10 x 1 +
    10 x 0.75 = 17.5, 19/17.5 per unit of lot 1. The June sale of 10 closes the other 5 of
    lot 1 (500.00) and 5 of lot 2 (550.00): gain 1300.00 - 1050.00 = 250.00, Vorabpauschale
    5 x 19/17.5 + 5 x 0.75 x 19/17.5 = 9.50, taxable (250.00 - 9.50) x 0.7 = 168.35.
    (Spreading it over the holding on 2023-02-14 would give 13.30 and 165.69.)"""
    text = (
        VP_CASE.replace(
            'date = 2023-01-01\ntype = "vorabpauschale"\nasset',
            'date = 2023-02-15\ntype = "vorabpauschale"\nasset',
        )
        .replace('units = "-15"\ncash = "1800.00"', 'units = "-10"\ncash = "1300.00"')
        .replace('taxable_gain = "164.55"', 'since = 2023-01-10\ntaxable_gain = "168.35"')
        + '\n[[activities]]\ndate = 2023-01-10\ntype = "sell"\nasset = "F1"\n'
        'units = "-5"\ncash = "600.00"\n'
    )
    results = check(load_case(write(tmp_path, text)))
    assert all(r.ok for r in results), results
