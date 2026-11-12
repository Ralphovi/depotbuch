"""The engine's object model: assets, accounts and activities.

An activity is the only fact depotbuch stores about a position (ADR-0006). Its fields
follow the activity mapping in proposal 0001 (*Data ingestion*), so an OFX investment
transaction becomes one activity field for field:

| Activity      | OFX                                  | units | cash                        |
|---------------|--------------------------------------|-------|-----------------------------|
| buy           | BUYSTOCK, BUYMF, BUYDEBT             | > 0   | <= 0, incl. fees and taxes  |
| sell          | SELLSTOCK, SELLMF, SELLDEBT          | < 0   | >= 0, after fees and taxes  |
| dividend      | INCOME (DIV, CGLONG, CGSHORT)        | 0     | net amount credited         |
| interest      | INCOME (INTEREST), bank interest     | 0     | net amount credited         |
| transfer      | TRANSFER                             | != 0  | 0; cost_basis on a delivery |
| expense       | INVEXPENSE                           | 0     | <= 0                        |
| split         | (manual or corporate action)         | 0     | 0; ratio new per old        |
| deposit       | bank credit from an untracked account| 0     | > 0                         |
| withdrawal    | bank debit to an untracked account   | 0     | < 0                         |
| fee           | account fee                          | 0     | <= 0                        |
| vorabpauschale| (provider notice)                    | 0     | <= 0, the tax withheld      |
| tax           | yearly tax settlement                | 0     | signed; refunds positive    |

A REINVEST is split into a dividend and a buy on import. Validation messages never repeat
a value, so a failed private case logs no amounts.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from depotbuch.engine.money import Currency, Dec


class AssetKind(StrEnum):
    SECURITY = "security"
    """Quoted per unit; units are shares or fund units."""
    BOND = "bond"
    """Quoted in percent of the nominal amount; units are the nominal amount."""
    CASH = "cash"
    """A cash balance: Verrechnungskonto, Tagesgeld. Valued at its balance."""
    DEPOSIT = "deposit"
    """Festgeld: principal plus interest accrued under the account's terms."""


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    kind: AssetKind = AssetKind.SECURITY
    currency: Currency = "EUR"
    isin: str | None = None


class Account(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)


class ActivityType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    TRANSFER = "transfer"
    EXPENSE = "expense"
    SPLIT = "split"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    VORABPAUSCHALE = "vorabpauschale"
    TAX = "tax"


_NO_UNITS = {
    ActivityType.DIVIDEND,
    ActivityType.INTEREST,
    ActivityType.EXPENSE,
    ActivityType.SPLIT,
    ActivityType.DEPOSIT,
    ActivityType.WITHDRAWAL,
    ActivityType.FEE,
    ActivityType.VORABPAUSCHALE,
    ActivityType.TAX,
}
_NEEDS_ASSET = {
    ActivityType.BUY,
    ActivityType.SELL,
    ActivityType.DIVIDEND,
    ActivityType.TRANSFER,
    ActivityType.EXPENSE,
    ActivityType.SPLIT,
    ActivityType.VORABPAUSCHALE,
}
_ZERO = Decimal(0)


class Activity(BaseModel):
    """One booking. Amounts are signed from the account's point of view."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    date: dt.date
    type: ActivityType
    account: str = Field(min_length=1)
    asset: str | None = None
    units: Dec = Field(default=Decimal(0))
    cash: Dec = Field(default=Decimal(0))
    currency: Currency = "EUR"
    """Settlement currency of `cash`, `fees` and `taxes`."""
    fx_rate: Dec | None = None
    """The broker's rate, in units of `currency` per EUR; the ECB rate applies without it."""
    fees: Dec = Field(default=Decimal(0))
    taxes: Dec = Field(default=Decimal(0))
    """Tax withheld on this activity (positive) or refunded (negative)."""
    cost_basis: Dec | None = None
    """For a delivery in: the stated cost basis that stays with the lot, in EUR."""
    ratio: Dec | None = None
    """For a split: new units per old unit."""
    amount: Dec | None = None
    """For a Vorabpauschale: its gross amount, from the notice."""
    ex_date: dt.date | None = None
    fitid: str | None = None

    def _violations(self) -> Iterator[tuple[bool, str]]:
        """(broken, message) for every rule; messages never repeat a value."""
        t, units, cash, z = self.type, self.units, self.cash, _ZERO
        yield t in _NEEDS_ASSET and not self.asset, "this activity type needs an asset"
        yield t in _NO_UNITS and units != z, "this activity type carries no units"
        yield (
            self.cost_basis is not None
            and (t is not ActivityType.TRANSFER or units <= z or self.cost_basis < z),
            "a cost basis belongs to a delivery in and can't be negative",
        )
        yield self.fx_rate is not None and self.fx_rate <= z, "fx_rate must be positive"
        yield (
            t is ActivityType.BUY and (units <= z or cash > z),
            "a buy adds units and pays cash (units > 0, cash <= 0)",
        )
        yield (
            t is ActivityType.SELL and (units >= z or cash < z),
            "a sale removes units and receives cash (units < 0, cash >= 0)",
        )
        yield (
            t is ActivityType.TRANSFER and (units == z or cash != z),
            "a transfer moves units and no cash",
        )
        yield (
            t is ActivityType.SPLIT and (self.ratio is None or self.ratio <= z or cash != z),
            "a split needs a positive ratio and moves no cash",
        )
        yield (
            t in {ActivityType.EXPENSE, ActivityType.FEE} and cash > z,
            "an expense or fee pays cash (cash <= 0)",
        )
        yield t is ActivityType.DEPOSIT and cash <= z, "a deposit receives cash (cash > 0)"
        yield t is ActivityType.WITHDRAWAL and cash >= z, "a withdrawal pays cash (cash < 0)"
        yield (
            t in {ActivityType.DIVIDEND, ActivityType.INTEREST} and cash < z,
            "income is credited (cash >= 0)",
        )
        yield (
            t is ActivityType.VORABPAUSCHALE and (self.amount is None or cash > z),
            "a Vorabpauschale needs its amount and at most pays tax",
        )

    @model_validator(mode="after")
    def _check_signs(self) -> Self:
        for broken, message in self._violations():
            if broken:
                raise ValueError(message)
        return self
