"""Units held, the first figure the engine derives from activities.

Lots, invested capital and realized gains arrive with #22; this is the plain unit count
the case harness needs to check holdings statements.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from depotbuch.engine.model import Activity, ActivityType


def units_held(
    activities: Iterable[Activity],
    as_of: date,
    *,
    asset: str,
    account: str | None = None,
) -> Decimal:
    """Units of `asset` held at the end of `as_of`, in one account or across all."""
    total = Decimal(0)
    for a in sorted(activities, key=lambda a: a.date):
        if a.date > as_of or a.asset != asset or (account is not None and a.account != account):
            continue
        if a.type is ActivityType.SPLIT:
            raise NotImplementedError("splits arrive with the FIFO lots (#22)")
        total += a.units
    return total
