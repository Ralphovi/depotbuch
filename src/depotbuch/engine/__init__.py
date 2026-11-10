"""The calculation engine: lots, valuation, TTWROR, IZF, trade-to-cash matching and tax
attribution.

Plain Python with `decimal.Decimal` and pydantic types. It takes activities, prices and
FX rates and returns results; it never imports Django (ruff's banned-api rule and
`tests/test_boundaries.py` enforce this), so Autobook can take it over unchanged.
"""
