"""Every public hand-computed case, in both modes (proposal 0002)."""

from pathlib import Path

import pytest

from depotbuch.testing.casefile import PRIVATE_ONLY, check, load_case

CASES = sorted((Path(__file__).parent / "cases").glob("*.toml"))


def test_there_are_cases() -> None:
    assert CASES


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(path: Path) -> None:
    case = load_case(path)
    assert case.name == path.stem, "a case's name matches its file name"
    for e in case.expect:
        assert e.tolerance is None, "public cases are exact"
        assert not set(e.metrics) & PRIVATE_ONLY, "taxable_gain is for the private corpus"
    for r in check(case):
        assert r.ok, f"expect[{r.expect}] {r.metric} ({r.mode}): want {r.want}, got {r.got}"
