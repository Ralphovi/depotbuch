"""Single-sourced gate definitions for depotbuch.

`nox -s gate` is THE gate. CI runs it and re-declares nothing; if a check is not here,
it is not a gate.

Missing external tools warn and skip; they never silently pass. A skipped step prints
why, and CI installs every tool so nothing is skipped there.
"""

from __future__ import annotations

import shutil
import sys

import nox

nox.options.sessions = ["gate"]
nox.options.reuse_existing_virtualenvs = True

# The supported interpreter range and the CI test matrix. Keep in step with
# requires-python in pyproject.toml and the matrix in .github/workflows/ci.yml.
PYTHONS = ["3.11", "3.12", "3.13", "3.14"]

# The interpreter running nox. Tool sessions use `python=None` (this interpreter) rather
# than a pinned version: a pinned version missing on a machine makes nox SKIP the session
# and still exit 0, so the gate would go green having checked nothing.
CURRENT_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"

LINT_DEPS = ["ruff==0.17.4"]
TEST_DEPS = ["pytest>=9", "pytest-django>=4.14", "pytest-cov>=7", "hypothesis>=6.170"]
# django-stubs 5.2 (matching Django 5.2 LTS) supports mypy below 1.20 only.
TYPE_DEPS = ["mypy==1.19.1", "django-stubs[compatible-mypy]>=5.2.9,<5.3", "nox", *TEST_DEPS]

SOURCES = ("src", "tests", "noxfile.py")


@nox.session(python=None)
def fmt(session: nox.Session) -> None:
    """Check formatting. Pass `-- --fix` to rewrite instead of reporting."""
    session.install(*LINT_DEPS)
    if "--fix" in session.posargs:
        session.run("ruff", "format", *SOURCES)
        session.run("ruff", "check", "--fix", *SOURCES)
    else:
        session.run("ruff", "format", "--check", "--diff", *SOURCES)


@nox.session(python=None)
def lint(session: nox.Session) -> None:
    """Lint with ruff, including the rule that keeps Django out of the engine."""
    session.install(*LINT_DEPS)
    session.run("ruff", "check", *SOURCES)


@nox.session(python=None)
def types(session: nox.Session) -> None:
    """Type-check with mypy --strict, with the django-stubs and pydantic plugins."""
    session.install(*TYPE_DEPS)
    session.install("-e", ".")
    session.run("mypy")


@nox.session(python=PYTHONS)
def test(session: nox.Session) -> None:
    """Run the test suite (pytest, Hypothesis), with Django's system checks first."""
    session.install(*TEST_DEPS)
    session.install("-e", ".")
    session.run("depot", "check", "--fail-level", "WARNING")
    session.run("depot", "makemigrations", "--check", "--dry-run")
    session.run("pytest", *session.posargs)


@nox.session(python=None, venv_backend="none")
def typos(session: nox.Session) -> None:
    """Spell-check prose, identifiers and comments."""
    if shutil.which("typos") is None:
        session.warn(
            "SKIPPED: `typos` is not installed (cargo install typos-cli --locked, or your "
            "distro's package). CI always runs it."
        )
        return
    session.run("typos", external=True)


@nox.session(python=None, venv_backend="none")
def docs(session: nox.Session) -> None:
    """The docs-check checkers and their tests, so the gate catches what `docs-check` does.

    The required `docs-check` job runs the base commit's copy of each checker; here the
    working tree's copy runs.
    """
    session.run(
        "python3", "-I", "-m", "unittest", "discover", "-s", ".github/docs-check", external=True
    )
    session.run("python3", "-I", ".github/docs-check/docs_links.py", external=True)
    session.run("python3", "-I", ".github/docs-check/adr_index.py", external=True)


@nox.session(python=None)
def reconcile(session: nox.Session) -> None:
    """Private reconciliation against a real history: `nox -s reconcile -- <corpus path>`.

    Not part of the gate and never run in CI. The corpus path is taken only from the
    command line, so an ordinary test run never learns where the corpus is. Run it only on
    code you wrote or have reviewed (proposal 0002, *Security impact*).
    """
    if len(session.posargs) != 1:
        session.error("usage: nox -s reconcile -- <corpus path>")
    session.install("-e", ".")
    session.run("python", "-I", "-m", "depotbuch.testing.reconcile", *session.posargs)


@nox.session(python=None, venv_backend="none")
def gate(session: nox.Session) -> None:
    """THE gate: everything CI requires, in one command.

    Tests run on the interpreter running nox, so the gate stays fast enough to run before
    every push. CI runs `test` across the full PYTHONS matrix in a separate job.
    """
    if CURRENT_PYTHON not in PYTHONS:
        session.error(
            f"nox is running on Python {CURRENT_PYTHON}, outside the supported range "
            f"{PYTHONS[0]} to {PYTHONS[-1]}. Run nox on a supported interpreter, or add "
            f"{CURRENT_PYTHON} to PYTHONS here and to requires-python in pyproject.toml."
        )
    for name in ("fmt", "lint", "types", f"test-{CURRENT_PYTHON}", "typos", "docs"):
        session.notify(name)
