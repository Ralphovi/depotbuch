"""Run .github/cargo/advisory-db.sh against a local database and a stub cargo.

    python3 -I -m unittest discover -s .github/template-test -v

The script moves cargo-deny's advisory database to the commit the .github/advisory-db
gitlink pins. Here the database is a local repo with two commits, and the stub cargo
answers `cargo deny fetch db` by cloning it to where cargo-deny would, so the test needs
no network. It checks a fresh start (no database yet), a pin that moves, and a missing
gitlink.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / ".github" / "cargo" / "advisory-db.sh"
STUB_CARGO = """#!/usr/bin/env bash
echo "cargo $*" >> "$CARGO_LOG"
if [ "$*" = "deny fetch db" ]; then
  git clone -q "$ADVISORY_DB_SOURCE" target/advisory-dbs/advisory-db-0123456789abcdef
fi
"""


def git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


class AdvisoryDb(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "cargo").write_text(STUB_CARGO, encoding="utf-8")
        (bin_dir / "cargo").chmod(0o755)
        self.log = self.tmp / "cargo.log"
        self.env = {
            **os.environ,
            "HOME": str(self.tmp),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Template Test",
            "GIT_AUTHOR_EMAIL": "template-test@example.invalid",
            "GIT_COMMITTER_NAME": "Template Test",
            "GIT_COMMITTER_EMAIL": "template-test@example.invalid",
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CARGO_LOG": str(self.log),
        }

        source = self.tmp / "advisory-db"
        git(self.tmp, "init", "-q", "-b", "main", str(source))
        git(source, "config", "uploadpack.allowAnySHA1InWant", "true")
        git(source, "commit", "-q", "--allow-empty", "-m", "older", env=self.env)
        self.older = git(source, "rev-parse", "HEAD")
        git(source, "commit", "-q", "--allow-empty", "-m", "newer", env=self.env)
        self.newer = git(source, "rev-parse", "HEAD")
        self.env["ADVISORY_DB_SOURCE"] = str(source)

        self.repo = self.tmp / "project"
        git(self.tmp, "init", "-q", "-b", "main", str(self.repo))
        (self.repo / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.repo / "scripts" / "advisory-db.sh")

    def pin(self, sha: str) -> None:
        git(self.repo, "update-index", "--add", "--cacheinfo",
            f"160000,{sha},.github/advisory-db")

    def run_script(self) -> subprocess.CompletedProcess[str]:
        self.log.unlink(missing_ok=True)
        return subprocess.run(["bash", "scripts/advisory-db.sh"], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, timeout=60)

    def db_head(self) -> str:
        db = self.repo / "target" / "advisory-dbs" / "advisory-db-0123456789abcdef"
        return git(db, "rev-parse", "HEAD")

    def test_fresh_start_then_a_moved_pin(self) -> None:
        self.pin(self.older)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.db_head(), self.older)
        self.assertEqual(self.log.read_text().splitlines(),
                         ["cargo deny fetch db", "cargo fetch --locked"])

        self.pin(self.newer)
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.db_head(), self.newer)
        self.assertEqual(self.log.read_text().splitlines(), ["cargo fetch --locked"],
                         "an existing clone is moved, not fetched again")

    def test_refuses_a_stale_pin(self) -> None:
        # The fetch makes FETCH_HEAD new, so only the commit's own date can show the age.
        source = Path(self.env["ADVISORY_DB_SOURCE"])
        git(source, "commit", "-q", "--allow-empty", "-m", "stale",
            env={**self.env, "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z"})
        self.pin(git(source, "rev-parse", "HEAD"))
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("days old (limit 90)", result.stderr)
        self.assertNotIn("cargo fetch --locked", self.log.read_text())

    def test_the_daily_audit_fails_through_tee(self) -> None:
        # Without pipefail, tee's exit status hides a failed audit and no issue opens.
        workflow = (ROOT / ".github" / "cargo" / "advisories.yml").read_text(encoding="utf-8")
        self.assertIn("        shell: bash\n        run: cargo deny check advisories 2>&1 | tee",
                      workflow)

    def test_refuses_without_a_gitlink(self) -> None:
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a submodule gitlink", result.stderr)
        self.assertFalse(self.log.exists(), "nothing runs without a pin")


if __name__ == "__main__":
    unittest.main()
