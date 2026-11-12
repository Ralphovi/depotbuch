"""The private runner: refuses unsafe locations and never prints case data (proposal 0002).

Every corpus here is synthetic, built in pytest's temporary directory, which lies outside
the repository. The secrets below stand in for real account numbers, names and amounts.
"""

import os
import subprocess
from pathlib import Path

import pytest

from depotbuch.testing.reconcile import REPORT, main, run

SECRETS = (
    "SECRETASSET",
    "ACCT9876",
    "Jane Q Owner",
    "4321",
    "17.123",
    "99.5",
    "2019-07-13",
    "secretmetric",
    "1.5",
    "c01-secret-note",
)

GOOD = """
name = "Jane Q Owner"
rule = "c01-secret-note"

[[activities]]
date = 2019-07-13
type = "buy"
account = "ACCT9876"
asset = "SECRETASSET"
units = "17.123"
cash = "-4321.98"

[[expect]]
as_of = 2019-07-13
slice = { asset = "SECRETASSET", account = "ACCT9876" }
units = "{units}"
"""

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def git(*args: str, cwd: Path) -> None:
    subprocess.run(  # noqa: S603 - fixed program and arguments
        ["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],  # noqa: S607
        cwd=cwd,
        check=True,
        capture_output=True,
        env={**os.environ, **GIT_ENV},
    )


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    git("commit", "-q", "--allow-empty", "-m", f"root of {path.name}", cwd=path)
    return path


def corpus(path: Path, **files: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (path / name).write_text(text, encoding="utf-8")
    return path


def assert_no_secrets(text: str) -> None:
    for s in SECRETS:
        assert s not in text, "case data reached the output"


def test_passing_corpus(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    c = corpus(tmp_path / "c", **{"c01.toml": GOOD.replace("{units}", "17.123")})
    assert run(str(c), own_repo=None) == 0
    out = capsys.readouterr()
    assert "c01.toml: expect[0] units default ok" in out.out
    assert_no_secrets(out.out + out.err)
    assert (c / REPORT).read_text(encoding="utf-8") == ""


def test_failures_print_nothing_from_the_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    c = corpus(
        tmp_path / "c",
        **{
            "c01.toml": GOOD.replace("{units}", "99.5"),  # wrong expectation
            "c02.toml": GOOD.replace("{units}", "17.123") + "\nname = \n",  # malformed
            "c03.toml": GOOD.replace('"{units}"', "1.5"),  # float, fails validation
            "c04.toml": GOOD.replace("{units}", "17.123").replace(
                'units = "17', 'secretmetric = "17', 1
            ),
            "c05.toml": GOOD.replace("{units}", "17.123").replace(
                'type = "buy"', 'type = "split"'
            ),
        },
    )
    assert run(str(c), own_repo=None) == 1
    out = capsys.readouterr()
    assert "c01.toml: expect[0] units default FAIL" in out.out
    assert "c02.toml: error malformed-toml" in out.out
    assert "c03.toml: error expect[0]" in out.out
    assert "c04.toml: error" in out.out
    assert "c05.toml: error" in out.out
    assert_no_secrets(out.out + out.err)
    # The values are in the report, inside the corpus.
    assert "99.5" in (c / REPORT).read_text(encoding="utf-8")


def test_refuses_without_a_path(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "usage" in capsys.readouterr().out


def test_refuses_a_missing_directory(tmp_path: Path) -> None:
    assert run(str(tmp_path / "nope"), own_repo=None) == 2


def test_refuses_a_symlinked_report(tmp_path: Path) -> None:
    c = corpus(tmp_path / "c", **{"c01.toml": GOOD.replace("{units}", "17.123")})
    (c / REPORT).symlink_to(tmp_path / "elsewhere.txt")
    assert run(str(c), own_repo=None) == 2
    assert not (tmp_path / "elsewhere.txt").exists()


def test_refuses_inside_the_checkout(tmp_path: Path) -> None:
    own = make_repo(tmp_path / "own")
    assert run(str(corpus(own / "private")), own_repo=own) == 2


def test_refuses_inside_a_sibling_worktree(tmp_path: Path) -> None:
    own = make_repo(tmp_path / "own")
    git("worktree", "add", "-q", str(tmp_path / "wt"), cwd=own)
    assert run(str(corpus(tmp_path / "wt" / "private")), own_repo=own) == 2


def test_refuses_inside_a_separate_clone_without_a_remote(tmp_path: Path) -> None:
    own = make_repo(tmp_path / "own")
    git("clone", "-q", str(own), str(tmp_path / "clone"), cwd=tmp_path)
    git("remote", "remove", "origin", cwd=tmp_path / "clone")
    assert run(str(corpus(tmp_path / "clone" / "private")), own_repo=own) == 2


def test_refuses_inside_any_repository_with_a_remote(tmp_path: Path) -> None:
    other = make_repo(tmp_path / "other")
    git("remote", "add", "origin", "https://example.invalid/x.git", cwd=other)
    assert run(str(corpus(other / "private")), own_repo=None) == 2


def test_allows_a_local_repository_of_its_own(tmp_path: Path) -> None:
    own = make_repo(tmp_path / "own")
    private = make_repo(tmp_path / "private")
    corpus(private, **{"c01.toml": GOOD.replace("{units}", "17.123")})
    assert run(str(private), own_repo=own) == 0


def test_refusals_happen_before_anything_is_written(tmp_path: Path) -> None:
    own = make_repo(tmp_path / "own")
    c = corpus(own / "private", **{"c01.toml": GOOD.replace("{units}", "17.123")})
    assert run(str(c), own_repo=own) == 2
    assert not (c / REPORT).exists()
