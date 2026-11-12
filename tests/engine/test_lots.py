from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from depotbuch.engine.fx import FxRates, MissingRate
from depotbuch.engine.holdings import units_held
from depotbuch.engine.lots import MissingCostBasis, Oversold, build_lots
from depotbuch.engine.model import Activity
from depotbuch.engine.money import round_cent

START = date(2024, 1, 1)
END = date(2024, 12, 31)
TINY = Decimal("1e-18")


def buy(day: int, units: str, cash: str, account: str = "A", **kw: str) -> Activity:
    return Activity.model_validate(
        {
            "date": START + timedelta(days=day),
            "type": "buy",
            "account": account,
            "asset": "X1",
            "units": units,
            "cash": cash,
            **kw,
        }
    )


def sell(day: int, units: str, cash: str, account: str = "A", **kw: str) -> Activity:
    return Activity.model_validate(
        {
            "date": START + timedelta(days=day),
            "type": "sell",
            "account": account,
            "asset": "X1",
            "units": units,
            "cash": cash,
            **kw,
        }
    )


amounts = st.decimals(min_value=Decimal("0.00001"), max_value=Decimal(10_000), places=5)
money = st.decimals(min_value=Decimal(0), max_value=Decimal(1_000_000), places=2)


@st.composite
def histories(draw: st.DrawFn) -> list[Activity]:
    """Buys and sales in two accounts; a sale never exceeds what its account holds."""
    held = {"A": Decimal(0), "B": Decimal(0)}
    out = []
    for day in range(draw(st.integers(1, 40))):
        account = draw(st.sampled_from(["A", "B"]))
        if held[account] > 0 and draw(st.booleans()):
            units = draw(
                st.decimals(min_value=Decimal("0.00001"), max_value=held[account], places=5)
            )
            held[account] -= units
            out.append(sell(day, str(-units), str(draw(money)), account))
        else:
            units = draw(amounts)
            held[account] += units
            out.append(buy(day, str(units), str(-draw(money)), account))
    return out


@given(histories())
def test_lots_sum_to_holdings(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    for account in ("A", "B"):
        raw = sum((a.units for a in acts if a.account == account), Decimal(0))
        assert book.units(asset="X1", account=account) == raw
        assert units_held(acts, END, asset="X1", account=account) == raw


@given(histories())
def test_every_euro_of_cost_is_either_held_or_realized(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    paid = sum((-a.cash for a in acts if a.type == "buy"), Decimal(0))
    closed = sum((r.cost for r in book.realized), Decimal(0))
    assert abs(book.invested_capital() + closed - paid) < TINY


@given(histories())
def test_proceeds_are_split_without_loss(acts: list[Activity]) -> None:
    book = build_lots(acts, END)
    received = sum((a.cash for a in acts if a.type == "sell"), Decimal(0))
    assert abs(sum((r.proceeds for r in book.realized), Decimal(0)) - received) < TINY
    for sale in (a for a in acts if a.type == "sell"):
        slices = [r for r in book.realized if (r.date, r.account) == (sale.date, sale.account)]
        assert abs(sum((r.proceeds for r in slices), Decimal(0)) - sale.cash) < TINY


def test_a_half_cent_gain_survives_the_split_across_lots() -> None:
    """Lots of 1 @ 1.00, 1 @ 1.00 and 2 @ 2.01; selling 3 for 3.01 closes cost
    1.00 + 1.00 + 1.005 = 3.005, a gain of 0.005, which rounds half up to 0.01. Thirds of
    3.01 sum to just under 3.01 unless the last slice takes the remainder."""
    acts = [
        buy(0, "1", "-1.00"),
        buy(1, "1", "-1.00"),
        buy(2, "2", "-2.01"),
        sell(3, "-3", "3.01"),
    ]
    book = build_lots(acts, END)
    assert book.realized_gain() == Decimal("0.005")
    assert round_cent(book.realized_gain()) == Decimal("0.01")


def test_oversold_is_rejected_with_its_date() -> None:
    acts = [buy(0, "5", "-500"), sell(3, "-6", "700")]
    with pytest.raises(Oversold) as err:
        build_lots(acts, END)
    assert err.value.when == START + timedelta(days=3)
    assert err.value.missing == 1
    assert "6" not in str(err.value)


def test_a_sale_cannot_use_another_accounts_lots() -> None:
    with pytest.raises(Oversold):
        build_lots([buy(0, "5", "-500", "A"), sell(1, "-1", "100", "B")], END)


def test_a_delivery_in_needs_its_cost_basis() -> None:
    delivery = Activity.model_validate(
        {"date": START, "type": "transfer", "account": "A", "asset": "X1", "units": "3"}
    )
    with pytest.raises(MissingCostBasis):
        build_lots([delivery], END)
    assert units_held([delivery], END, asset="X1") == 3


def test_activities_after_as_of_are_ignored() -> None:
    acts = [buy(0, "5", "-500"), sell(10, "-5", "700")]
    book = build_lots(acts, START + timedelta(days=9))
    assert book.units(asset="X1") == 5
    assert book.realized == []


def test_foreign_currency_without_any_rate_fails_loudly() -> None:
    usd = buy(0, "1", "-100", currency="USD")
    with pytest.raises(MissingRate):
        build_lots([usd], END)
    assert units_held([usd], END, asset="X1") == 1  # units need no rate


def test_fx_rates_carry_forward_and_never_backward() -> None:
    rates = FxRates({"USD": {date(2024, 6, 7): Decimal("1.2")}})
    assert rates.rate("USD", date(2024, 6, 9)) == Decimal("1.2")
    assert rates.rate("EUR", date(2000, 1, 1)) == 1
    with pytest.raises(MissingRate):
        rates.rate("USD", date(2024, 6, 6))
    assert rates.to_eur(Decimal(120), "USD", date(2024, 6, 7)) == 100
    assert rates.to_eur(Decimal(125), "USD", date(2024, 6, 7), Decimal("1.25")) == 100
    with pytest.raises(ValueError, match="positive"):
        FxRates({"USD": {date(2024, 6, 7): Decimal(0)}})
