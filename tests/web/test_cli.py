import pytest

from depotbuch.cli import main


def test_depot_runs_django_system_checks(capsys: pytest.CaptureFixture[str]) -> None:
    main(["depot", "check"])
    assert "no issues" in capsys.readouterr().out
