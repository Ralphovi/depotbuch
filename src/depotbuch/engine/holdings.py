"""Units held: the unit count of the open FIFO lots (`depotbuch.engine.lots`)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from depotbuch.engine.lots import build_lots
from depotbuch.engine.model import Activity


def units_held(
    activities: Iterable[Activity],
    as_of: date,
    *,
    asset: str,
    account: str | None = None,
) -> Decimal:
    """Units of `asset` held at the end of `as_of`, in one account or across all.

    Splits apply; a sale of more than the account holds raises `Oversold`.
    """
    return build_lots(activities, as_of, costs=False).units(asset=asset, account=account)
