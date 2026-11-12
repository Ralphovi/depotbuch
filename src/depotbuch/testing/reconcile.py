"""Private reconciliation: run the engine on a real history kept outside the repository.

    nox -s reconcile -- <corpus path>

The corpus is a directory of case files (`*.toml`, named synthetically such as `c01.toml`)
transcribed from real statements, with the results the provider states. It holds account
numbers, names and amounts, so (proposal 0002, *Security impact*; architecture §14.7):

- The path comes only from the command line, never from an environment variable, and
  neither the gate nor CI runs this.
- A corpus or report inside a Git worktree with a remote, or inside any clone or worktree
  of this repository, is refused before anything is read or written, and so is a
  symlinked report.
- Output names only the case file, the fixed field names of the format, the metric, the
  mode and an error kind. Values and differences go to `reconcile-report.txt` inside the
  corpus directory. Nothing taken from a case file reaches stdout or stderr.

Run it only on code you wrote or have reviewed: the code under test sees the real values.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from pydantic import ValidationError

from depotbuch.engine.model import Activity
from depotbuch.testing.casefile import AssetSpec, Case, Expect, Slice, check, load_case

REPORT = "reconcile-report.txt"
_HERE = Path(__file__).resolve()

# Field names the output may show: the format's own, never keys a case defines.
_FIELDS = frozenset().union(
    *(m.model_fields for m in (Case, Expect, Slice, AssetSpec, Activity))
) | {"metrics", "parqet"}


def _out(line: str) -> None:
    sys.stdout.write(line + "\n")


GIT = "git"


class LocationUnknown(Exception):
    """Git could not say whether a path is inside a repository; the runner refuses."""


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603 - fixed program, no shell
            [GIT, "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        raise LocationUnknown from None


def _git(cwd: Path, *args: str) -> str | None:
    r = _run_git(cwd, *args)
    return r.stdout.strip() if r.returncode == 0 else None


def _worktree(path: Path) -> Path | None:
    """The innermost Git worktree enclosing `path`, None outside any.

    Any failure other than "not a git repository" (a missing git, a repository git refuses
    to read) raises LocationUnknown, so the guard fails closed.
    """
    probe = path if path.is_dir() else path.parent
    r = _run_git(probe, "rev-parse", "--show-toplevel")
    if r.returncode == 0:
        return Path(r.stdout.strip()).resolve()
    if "not a git repository" in r.stderr:
        return None
    raise LocationUnknown


def _enclosing_worktrees(path: Path) -> list[Path]:
    """Every Git worktree enclosing `path`, innermost first, including nested ones."""
    tops: list[Path] = []
    probe = path
    while (top := _worktree(probe)) is not None:
        tops.append(top)
        if top.parent == top:
            break
        probe = top.parent
    return tops


def _roots(top: Path) -> set[str]:
    out = _git(top, "rev-list", "--max-parents=0", "--all")
    return set(out.split()) if out else set()


def _has_commit(top: Path, sha: str | None) -> bool:
    return bool(sha) and _git(top, "cat-file", "-e", f"{sha}^{{commit}}") is not None


def _related(top: Path, own_top: Path) -> bool:
    """True if `top` is `own_top`, or a clone or worktree of it."""
    return (
        top == own_top
        or bool(_roots(top) & _roots(own_top))
        or _has_commit(own_top, _git(top, "rev-parse", "HEAD"))
        or _has_commit(top, _git(own_top, "rev-parse", "HEAD"))
    )


def unsafe_location(path: Path, own_repo: Path | None) -> bool:
    """True if `path` is somewhere it could be committed or pushed.

    That is inside `own_repo`'s directory, or inside any enclosing Git worktree (nested ones
    included) that has a remote, is a shallow clone, or is a clone or worktree of
    `own_repo`. A local repository with no remote and its own history, outside the
    checkout, is fine: keeping the corpus under version control is encouraged. Raises
    LocationUnknown when Git can't tell.
    """
    if own_repo is not None and path.is_relative_to(own_repo.resolve()):
        return True
    own_top = _worktree(own_repo) if own_repo is not None else None
    for top in _enclosing_worktrees(path):
        if _git(top, "remote") or _git(top, "rev-parse", "--is-shallow-repository") == "true":
            return True
        if own_top is not None and _related(top, own_top):
            return True
    return False


def _safe_loc(loc: tuple[int | str, ...]) -> str:
    return ".".join(
        f"[{p}]" if isinstance(p, int) else (p if p in _FIELDS else "<key>") for p in loc
    ).replace(".[", "[")


def _refusal(corpus: Path, report: Path, own_repo: Path | None) -> str | None:
    """Why the corpus must not be read, or None if it may."""
    if not corpus.is_dir():
        return "the corpus path is not a directory"
    if report.is_symlink():
        return f"{REPORT} is a symlink"
    try:
        unsafe = unsafe_location(corpus, own_repo)
    except LocationUnknown:
        return "git could not tell whether the corpus is inside a repository"
    if unsafe:
        return (
            "the corpus is inside a Git worktree with a remote, or inside a clone or "
            "worktree of depotbuch, where it could be committed or pushed"
        )
    return None


def _check_file(path: Path, details: list[str]) -> int:
    """Check one case file; print safe lines, append values to `details`. Returns failures."""
    name = path.name
    try:
        case = load_case(path)
    except tomllib.TOMLDecodeError:
        _out(f"{name}: error malformed-toml")
        return 1
    except (UnicodeDecodeError, OSError):
        _out(f"{name}: error unreadable")
        return 1
    except ValidationError as e:
        for err in e.errors():
            _out(f"{name}: error {_safe_loc(tuple(err['loc']))} {err['type']}")
        return 1
    try:
        results = check(case)
    except Exception as e:  # report the kind, never the message
        _out(f"{name}: error {type(e).__name__}")
        return 1
    failed = 0
    for i, metric, mode, want, got in results:
        ok = want == got
        _out(f"{name}: expect[{i}] {metric} {mode} {'ok' if ok else 'FAIL'}")
        if not ok:
            failed += 1
            details.append(f"{name} expect[{i}] {metric} {mode}: want {want} got {got}")
    return failed


def run(corpus_arg: str, own_repo: Path | None = _HERE.parents[3]) -> int:
    """Check every case in the corpus. Returns 0 if all pass, 1 on a failure, 2 if refused."""
    corpus = Path(corpus_arg).expanduser().resolve()
    report = corpus / REPORT
    if (why := _refusal(corpus, report, own_repo)) is not None:
        _out(f"refused: {why}")
        return 2
    cases = sorted(corpus.glob("*.toml"))
    if not cases:
        _out("FAILED: no case files (*.toml) in the corpus")
        return 1
    details: list[str] = []
    failed = sum(_check_file(path, details) for path in cases)
    report.write_text("\n".join(details) + ("\n" if details else ""), encoding="utf-8")
    _out(f"{'FAILED' if failed else 'passed'}; details in {REPORT} inside the corpus")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        _out("usage: nox -s reconcile -- <corpus path>")
        return 2
    try:
        return run(args[0])
    except Exception as e:  # never let a traceback print case data
        _out(f"error {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
