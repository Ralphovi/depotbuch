from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from depotbuch.engine.model import Activity, ActivityType

D = date(2024, 1, 2)


def act(**kw: Any) -> Activity:
    return Activity.model_validate({"date": D, "account": "depot", **kw})


@pytest.mark.parametrize(
    "kw",
    [
        {"type": "buy", "asset": "X1", "units": "10", "cash": "-1004.95", "fees": "4.95"},
        {"type": "sell", "asset": "X1", "units": "-4", "cash": "480.00"},
        {"type": "dividend", "asset": "X1", "cash": "7.50", "taxes": "2.50", "ex_date": D},
        {"type": "interest", "cash": "1.20"},
        {"type": "transfer", "asset": "X1", "units": "3", "cost_basis": "300.00"},
        {"type": "expense", "asset": "X1", "cash": "-5"},
        {"type": "split", "asset": "X1", "ratio": "4"},
        {"type": "deposit", "cash": "1000"},
        {"type": "withdrawal", "cash": "-1000"},
        {"type": "fee", "cash": "-2"},
        {"type": "vorabpauschale", "asset": "X1", "amount": "5.97"},
        {"type": "tax", "cash": "-12.30"},
        {
            "type": "buy",
            "asset": "X1",
            "units": "1",
            "cash": "-90",
            "currency": "USD",
            "fx_rate": "1.08",
        },
    ],
)
def test_valid_activities(kw: dict[str, Any]) -> None:
    assert act(**kw).type is ActivityType(kw["type"])


@pytest.mark.parametrize(
    "kw",
    [
        {"type": "buy", "asset": "X1", "units": "-10", "cash": "-100"},  # buy removing units
        {"type": "buy", "asset": "X1", "units": "10", "cash": "100"},  # buy receiving cash
        {"type": "sell", "asset": "X1", "units": "4", "cash": "480"},  # sale adding units
        {"type": "buy", "units": "1", "cash": "-1"},  # no asset
        {"type": "dividend", "asset": "X1", "units": "1", "cash": "1"},  # income with units
        {"type": "transfer", "asset": "X1", "units": "3", "cash": "-1"},  # transfer with cash
        {"type": "transfer", "asset": "X1", "units": "3", "cost_basis": "-1"},
        {"type": "transfer", "asset": "X1", "units": "-3", "cost_basis": "100"},  # out
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1", "cost_basis": "1"},
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1.005"},  # a part cent
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1", "fees": "0.001"},
        {"type": "vorabpauschale", "asset": "X1", "amount": "5.975"},
        {"type": "transfer", "asset": "X1", "units": "3", "acquired": "2025-01-01"},  # later
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1", "acquired": "2020-01-01"},
        {"type": "split", "asset": "X1"},  # split without ratio
        {"type": "split", "asset": "X1", "ratio": "2", "cash": "-1"},  # split with cash
        {"type": "dividend", "asset": "X1", "cash": "-1"},  # negative income
        {"type": "interest", "cash": "-0.10"},
        {"type": "deposit", "cash": "-1"},
        {"type": "withdrawal", "cash": "1"},
        {"type": "fee", "cash": "2"},
        {"type": "vorabpauschale", "asset": "X1"},  # no amount
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1", "fx_rate": "0"},
        {"type": "buy", "asset": "X1", "units": 1.5, "cash": "-1"},  # float
        {"type": "buy", "asset": "X1", "units": "1", "cash": "-1", "colour": "red"},  # extra
        {"type": "swap", "asset": "X1"},  # unknown type
    ],
)
def test_invalid_activities(kw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        act(**kw)


def test_validation_errors_never_repeat_values() -> None:
    with pytest.raises(ValidationError) as err:
        act(type="buy", asset="X1", units="-98765", cash="-4321.98")
    messages = " ".join(e["msg"] for e in err.value.errors())
    assert "98765" not in messages
    assert "4321" not in messages


@pytest.mark.parametrize(
    "fields",
    [
        {"cash": "-1000000000000000.00"},
        {"cash": "-1E26"},
        {"fx_rate": "0.0000001", "currency": "USD"},
        {"fx_rate": "1000001", "currency": "USD"},
    ],
)
def test_amounts_and_rates_outside_the_decimal_context_are_rejected(
    fields: dict[str, str],
) -> None:
    """Bounds that keep every booking exact in the default 28-digit context (ADR-0013)."""
    with pytest.raises(ValidationError):
        act(**{"type": "buy", "asset": "X1", "units": "1", "cash": "-1.00", **fields})


def test_the_largest_booked_amount_is_accepted() -> None:
    assert act(type="buy", asset="X1", units="1", cash="-999999999999999.99").cash < 0


@pytest.mark.parametrize("units", ["1E15", "0.0000000000001"])
def test_units_outside_the_decimal_context_are_rejected(units: str) -> None:
    with pytest.raises(ValidationError, match="units"):
        act(type="buy", asset="X1", units=units, cash="-1.00")


@pytest.mark.parametrize("ratio", ["1E+999999", "0.0000001", "1000001", "1.0000000000001"])
def test_split_ratios_outside_the_bounds_are_rejected(ratio: str) -> None:
    with pytest.raises(ValidationError, match="ratio"):
        act(type="split", asset="X1", ratio=ratio)
