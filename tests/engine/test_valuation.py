from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from depotbuch.engine.model import Account, Activity, Asset, AssetKind, DayCount, DepositTerms
from depotbuch.engine.valuation import (
    MissingPrice,
    MissingTerms,
    Prices,
    interest_days,
    value,
)

D = date(2024, 6, 3)


def act(**kw: Any) -> Activity:
    return Activity.model_validate({"date": D, "account": "depot", **kw})


def terms(**kw: Any) -> DepositTerms:
    base = {
        "principal": "10000.00",
        "rate": "3.65",
        "start": date(2024, 1, 10),
        "maturity": date(2024, 1, 20),
    }
    return DepositTerms.model_validate({**base, **kw})


def test_a_held_security_without_any_close_is_never_valued_at_zero() -> None:
    acts = [act(type="buy", asset="X1", units="1", cash="-10.00")]
    with pytest.raises(MissingPrice) as err:
        value(acts, D, assets={}, prices=Prices())
    assert str(err.value) == "X1"


def test_a_position_sold_out_needs_no_close() -> None:
    acts = [
        act(type="buy", asset="X1", units="1", cash="-10.00"),
        act(type="sell", asset="X1", units="-1", cash="11.00"),
    ]
    assert value(acts, D, assets={}, prices=Prices()) == 0


def test_a_close_from_after_the_day_is_not_used() -> None:
    acts = [act(type="buy", asset="X1", units="1", cash="-10.00")]
    with pytest.raises(MissingPrice):
        value(acts, D, assets={}, prices=Prices({"X1": {date(2024, 6, 4): Decimal(10)}}))


@pytest.mark.parametrize("close", ["-1", "Infinity", "NaN", "1E15"])
def test_invalid_closes_are_rejected(close: str) -> None:
    with pytest.raises(ValueError, match="close"):
        Prices({"X1": {D: Decimal(close)}})


@pytest.mark.parametrize(
    ("start", "maturity", "days"),
    [
        ((True, False), 10, 10),
        ((False, True), 10, 10),
        ((True, True), 10, 11),
        ((False, False), 10, 9),
    ],
)
def test_interest_days_at_maturity_follow_the_terms(
    start: tuple[bool, bool], maturity: int, days: int
) -> None:
    t = terms(accrue_start=start[0], accrue_maturity=start[1])
    assert (t.maturity - t.start).days == maturity
    assert interest_days(t, t.maturity) == days
    assert interest_days(t, date(2024, 2, 1)) == days  # no accrual after maturity
    assert interest_days(t, date(2024, 1, 9)) == 0


def test_a_deposit_needs_its_terms() -> None:
    acts = [act(type="deposit", account="fg", asset="FG", cash="100.00")]
    assets = {"FG": Asset(id="FG", kind=AssetKind.DEPOSIT)}
    with pytest.raises(MissingTerms):
        value(acts, D, assets=assets, prices=Prices())


def test_interest_already_credited_is_not_accrued_twice() -> None:
    """1.00 a day from 10 January; on 15 January 6 days have earned 6.00, of which 4.00 was
    credited on the 13th: balance 10004.00 + 2.00 still accrued = 10006.00."""
    t = terms()
    acts = [
        act(date=t.start, type="deposit", account="fg", asset="FG", cash="10000.00"),
        act(date=date(2024, 1, 13), type="interest", account="fg", asset="FG", cash="4.00"),
    ]
    taxed = [
        acts[0],
        act(
            date=date(2024, 1, 13),
            type="interest",
            account="fg",
            asset="FG",
            cash="2.95",
            taxes="1.05",
        ),
    ]
    assets = {"FG": Asset(id="FG", kind=AssetKind.DEPOSIT)}
    accounts = {"fg": Account(id="fg", provider="bank", deposit=t)}
    got = value(acts, date(2024, 1, 15), assets=assets, prices=Prices(), accounts=accounts)
    assert got == Decimal("10006.00")
    # 4.00 gross credited as 2.95 after 1.05 tax: 10002.95 + 2.00 still accrued.
    got = value(taxed, date(2024, 1, 15), assets=assets, prices=Prices(), accounts=accounts)
    assert got == Decimal("10004.95")


def test_a_cash_booking_in_another_currency_is_rejected() -> None:
    acts = [act(type="deposit", account="tg", asset="TG", cash="1.00", currency="USD")]
    assets = {"TG": Asset(id="TG", kind=AssetKind.CASH)}
    with pytest.raises(ValueError, match="currency"):
        value(acts, D, assets=assets, prices=Prices())


def test_a_slice_values_only_its_own_positions() -> None:
    acts = [
        act(type="buy", asset="X1", units="2", cash="-20.00"),
        act(type="buy", asset="X2", units="1", cash="-10.00"),  # no close: not in the slice
    ]
    prices = Prices({"X1": {D: Decimal("12.50")}})
    assert value(acts, D, assets={}, prices=prices, asset="X1") == 25


@pytest.mark.parametrize(
    "kw",
    [
        {"maturity": date(2024, 1, 10)},
        {"principal": "0"},
        {"principal": "1.001"},
        {"rate": "101"},
        {"day_count": "act/act"},
    ],
)
def test_invalid_deposit_terms_are_rejected(kw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        terms(**kw)


def test_day_counts_have_their_names() -> None:
    assert {d.value for d in DayCount} == {"act/365", "act/360", "30E/360"}


def test_bookings_without_an_asset_are_the_accounts_own_balance() -> None:
    """A Tagesgeld booked without an asset is cash; a Festgeld account (with terms) accrues."""
    t = terms()
    acts = [
        act(type="deposit", account="tg", cash="500.00"),
        act(type="fee", account="tg", cash="-1.50"),
        act(date=t.start, type="deposit", account="fg", cash="10000.00"),
    ]
    accounts = {"fg": Account(id="fg", provider="bank", deposit=t)}
    on = date(2024, 1, 11)  # two days earned at 1.00
    assert value(acts, D, assets={}, prices=Prices(), account="tg") == Decimal("498.50")
    got = value(acts, on, assets={}, prices=Prices(), accounts=accounts, account="fg")
    assert got == Decimal("10002.00")
    assert value(acts, D, assets={}, prices=Prices(), asset="X1") == 0


@pytest.mark.parametrize("convention", list(DayCount))
@pytest.mark.parametrize("flags", [(True, False), (False, True), (True, True), (False, False)])
def test_interest_days_never_decrease(convention: DayCount, flags: tuple[bool, bool]) -> None:
    """Over terms starting and ending on every kind of month end, day by day."""
    for start, maturity in [
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 1, 31), date(2025, 3, 31)),
        (date(2024, 2, 28), date(2024, 3, 1)),
        (date(2025, 2, 28), date(2026, 2, 28)),
    ]:
        t = terms(
            start=start,
            maturity=maturity,
            day_count=convention,
            accrue_start=flags[0],
            accrue_maturity=flags[1],
        )
        days = [interest_days(t, start + timedelta(days=i)) for i in range(-2, 400)]
        assert days == sorted(days)


def test_a_festgeld_is_one_balance_whatever_its_bookings_name() -> None:
    """Placement names the deposit asset, the statement's credit and payout don't: one
    balance, accrued once, and closed by the payout."""
    t = terms()
    acts = [
        act(date=t.start, type="deposit", account="fg", asset="FG", cash="10000.00"),
        act(date=date(2024, 1, 22), type="interest", account="fg", cash="10.00"),
        act(date=date(2024, 1, 22), type="withdrawal", account="fg", cash="-10010.00"),
    ]
    assets = {"FG": Asset(id="FG", kind=AssetKind.DEPOSIT)}
    accounts = {"fg": Account(id="fg", provider="bank", deposit=t)}
    kw: dict[str, Any] = {"assets": assets, "prices": Prices(), "accounts": accounts}
    assert value(acts, date(2024, 1, 21), **kw) == Decimal("10010.00")
    assert value(acts, date(2024, 1, 22), **kw) == 0
    assert value(acts, date(2024, 1, 21), asset="FG", **kw) == Decimal("10010.00")
    assert value(acts, date(2024, 1, 22), asset="FG", **kw) == 0
    assert value(iter(acts), date(2024, 1, 22), asset="FG", **kw) == 0


def test_a_credit_rounded_up_leaves_nothing_to_accrue() -> None:
    """One day at 2 % act/365 on 100.00 earns 0.005479..., credited as 0.01: the value is the
    booked 100.01, not less."""
    t = terms(principal="100.00", rate="2", maturity=date(2024, 1, 11))
    acts = [
        act(date=t.start, type="deposit", account="fg", cash="100.00"),
        act(date=t.start, type="interest", account="fg", cash="0.01"),
    ]
    accounts = {"fg": Account(id="fg", provider="bank", deposit=t)}
    got = value(acts, t.start, assets={}, prices=Prices(), accounts=accounts)
    assert got == Decimal("100.01")
