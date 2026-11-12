from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from depotbuch.engine.fx import FxRates
from depotbuch.engine.income import NotEntitled, income, taxes
from depotbuch.engine.model import Account, Activity, Asset, AssetKind

D = date(2024, 6, 28)


def act(**kw: Any) -> Activity:
    return Activity.model_validate({"date": date(2024, 1, 2), "account": "A", **kw})


BUY = act(type="buy", asset="X1", units="10", cash="-100.00")


def test_a_dividend_without_ex_date_is_marked_approximate() -> None:
    div = act(date=D, type="dividend", asset="X1", cash="5.00")
    (share,) = income([BUY, div], D)
    assert share.approximate
    assert share.units == 10
    assert share.lot_opened == BUY.date
    exact = div.model_copy(update={"ex_date": date(2024, 6, 20)})
    (share,) = income([BUY, exact], D)
    assert not share.approximate


def test_a_dividend_before_any_units_is_rejected() -> None:
    early = act(date=date(2024, 1, 10), type="dividend", asset="X1", cash="5.00")
    with pytest.raises(NotEntitled):
        income([BUY, early.model_copy(update={"ex_date": date(2024, 1, 2)})], D)
    with pytest.raises(NotEntitled):
        income([early.model_copy(update={"date": date(2024, 1, 1)})], D)
    assert "5" not in str(NotEntitled("no units held on the day before the ex-date"))


def test_a_sale_on_the_ex_date_keeps_the_entitlement() -> None:
    sale = act(date=date(2024, 6, 20), type="sell", asset="X1", units="-10", cash="110.00")
    div = act(date=D, type="dividend", asset="X1", cash="5.00", ex_date=date(2024, 6, 20))
    assert [s.units for s in income([BUY, sale, div], D)] == [10]
    on_eve = sale.model_copy(update={"date": date(2024, 6, 19)})
    with pytest.raises(NotEntitled):
        income([BUY, on_eve, div], D)


def test_interest_on_an_account_has_no_lots() -> None:
    interest = act(date=D, type="interest", account="tg", cash="2.50", taxes="0.66")
    named = act(date=D, type="interest", account="vk", asset="VK", cash="1.00")
    shares = income([interest, named], D, assets={"VK": Asset(id="VK", kind=AssetKind.CASH)})
    assert [(s.asset, s.net, s.taxes, s.lot_opened) for s in shares] == [
        (None, Decimal("2.50"), Decimal("0.66"), None),
        ("VK", Decimal("1.00"), Decimal("0.00"), None),
    ]
    assert shares[0].gross == Decimal("3.16")


def test_a_bond_coupon_is_split_across_its_lots() -> None:
    bond = Asset(id="B1", kind=AssetKind.BOND)
    acts = [
        act(type="buy", asset="B1", units="1000", cash="-1000.00"),
        act(date=date(2024, 3, 1), type="buy", asset="B1", units="3000", cash="-3000.00"),
        act(date=D, type="interest", asset="B1", cash="40.00", ex_date=date(2024, 6, 27)),
    ]
    assert [s.net for s in income(acts, D, assets={"B1": bond})] == [
        Decimal("10.00"),
        Decimal("30.00"),
    ]


def test_foreign_income_is_booked_in_eur_at_the_rate_given() -> None:
    div = act(
        date=D,
        type="dividend",
        asset="X1",
        cash="10.71",
        taxes="1.07",
        currency="USD",
        fx_rate="1.0712",
    )
    (share,) = income([BUY, div], D, FxRates())
    assert (share.net, share.taxes) == (Decimal("10.00"), Decimal("1.00"))


def test_the_split_adds_up_to_the_booked_amounts() -> None:
    lots = [
        act(date=date(2024, 1, i), type="buy", asset="X1", units="1", cash="-1.00")
        for i in range(1, 8)
    ]
    div = act(date=D, type="dividend", asset="X1", cash="1.00", taxes="0.01")
    shares = income([*lots, div], D)
    assert sum(s.net for s in shares) == Decimal("1.00")
    assert sum(s.taxes for s in shares) == Decimal("0.01")
    assert all(s.net >= 0 and s.taxes >= 0 for s in shares)


def test_a_provider_slice_needs_its_accounts() -> None:
    settle = act(date=D, type="tax", account="vk", cash="-10.00")
    assert taxes([settle], D, provider="cb") == 0
    known = {"vk": Account(id="vk", provider="cb")}
    assert taxes([settle], D, accounts=known, provider="cb") == Decimal("10.00")
    assert taxes([settle], D, accounts=known, asset="X1") == 0


def test_income_elsewhere_doesnt_stop_the_slice() -> None:
    stray = act(date=D, type="dividend", asset="X2", cash="1.00", ex_date=D)
    div = act(date=D, type="dividend", asset="X1", cash="5.00")
    assert [s.net for s in income([BUY, stray, div], D, asset="X1")] == [Decimal("5.00")]
