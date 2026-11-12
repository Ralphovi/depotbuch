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


def _git(cwd: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(  # noqa: S603 - fixed program, no shell
            ["git", "-C", str(cwd), *args],  # noqa: S607 - git from PATH, as nox uses it
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _worktree(path: Path) -> Path | None:
    """The Git worktree enclosing `path`, if any."""
    probe = path if path.is_dir() else path.parent
    top = _git(probe, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def _roots(top: Path) -> set[str]:
    out = _git(top, "rev-list", "--max-parents=0", "--all")
    return set(out.split()) if out else set()


def _has_commit(top: Path, sha: str | None) -> bool:
    return bool(sha) and _git(top, "cat-file", "-e", f"{sha}^{{commit}}") is not None


def unsafe_location(path: Path, own_repo: Path | None) -> bool:
    """True if `path` is inside a Git worktree that could commit or push it.

    That is a worktree with a remote, a shallow clone, or any clone or worktree of
    `own_repo`: one that shares a root commit with it, or whose HEAD is a commit of the
    other. A local repository with no remote and its own history is fine: keeping the
    corpus under version control is encouraged.
    """
    top = _worktree(path)
    if top is None:
        return False
    if _git(top, "remote") or _git(top, "rev-parse", "--is-shallow-repository") == "true":
        return True
    if own_repo is None:
        return False
    own_top = _worktree(own_repo)
    if own_top is None:
        return False
    return (
        top == own_top
        or bool(_roots(top) & _roots(own_top))
        or _has_commit(own_top, _git(top, "rev-parse", "HEAD"))
        or _has_commit(top, _git(own_top, "rev-parse", "HEAD"))
    )


def _safe_loc(loc: tuple[int | str, ...]) -> str:
    return ".".join(
        f"[{p}]" if isinstance(p, int) else (p if p in _FIELDS else "<key>") for p in loc
    ).replace(".[", "[")


def run(corpus_arg: str, own_repo: Path | None = _HERE.parents[3]) -> int:
    """Check every case in the corpus. Returns 0 if all pass, 1 on a failure, 2 if refused."""
    corpus = Path(corpus_arg).expanduser().resolve()
    report = corpus / REPORT
    if not corpus.is_dir():
        _out("refused: the corpus path is not a directory")
        return 2
    if report.is_symlink():
        _out(f"refused: {REPORT} is a symlink")
        return 2
    if unsafe_location(corpus, own_repo):
        _out(
            "refused: the corpus is inside a Git worktree with a remote, or inside a clone "
            "or worktree of depotbuch, where it could be committed or pushed"
        )
        return 2

    cases = sorted(corpus.glob("*.toml"))
    if not cases:
        _out("FAILED: no case files (*.toml) in the corpus")
        return 1
    failed = 0
    details: list[str] = []
    for path in cases:
        name = path.name
        try:
            case = load_case(path)
        except tomllib.TOMLDecodeError:
            _out(f"{name}: error malformed-toml")
            failed += 1
            continue
        except ValidationError as e:
            for err in e.errors():
                _out(f"{name}: error {_safe_loc(tuple(err['loc']))} {err['type']}")
            failed += 1
            continue
        try:
            results = check(case)
        except Exception as e:
            _out(f"{name}: error {type(e).__name__}")
            failed += 1
            continue
        for i, metric, mode, want, got in results:
            ok = want == got
            _out(f"{name}: expect[{i}] {metric} {mode} {'ok' if ok else 'FAIL'}")
            if not ok:
                failed += 1
                details.append(f"{name} expect[{i}] {metric} {mode}: want {want} got {got}")
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
    except Exception as e:
        _out(f"error {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
