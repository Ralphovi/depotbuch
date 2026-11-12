"""Every public hand-computed case, in both modes (proposal 0002)."""

from pathlib import Path

import pytest

from depotbuch.testing.casefile import check, load_case

CASES = sorted((Path(__file__).parent / "cases").glob("*.toml"))


def test_there_are_cases() -> None:
    assert CASES


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_case(path: Path) -> None:
    case = load_case(path)
    assert case.name == path.stem, "a case's name matches its file name"
    for i, metric, mode, want, got in check(case):
        assert got == want, f"expect[{i}] {metric} ({mode})"
