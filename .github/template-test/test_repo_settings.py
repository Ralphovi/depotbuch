"""Run scripts/repo-settings.py against the fake GitHub in stub/gh.

    python3 -I -m unittest discover -s .github/template-test -v

Each test starts from stub/fresh-repo.json (a repo as GitHub creates it), so `apply` has
everything to do. It checks that apply leaves `check` clean and that a second apply
changes nothing; that apply reads again while GitHub's reads lag its writes; that `check`
fails and names the setting when any one setting is wrong; and the cases where GitHub
decides: generic-secret scanning on personal and organization accounts, a private repo,
and a repo whose OIDC subject a federation rule uses.

init-repo.sh deletes this folder from repos created from the template.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent.parent / "scripts" / "repo-settings.py"
REPO = "repos/eduralph/demo"
CHECKS = ["dco", "gate", "require-linked-issue"]

# (state path, keys, wrong value, the setting `check` names): one wrong setting each.
WRONG = [
    (REPO, ["has_wiki"], True, "wiki"),
    (REPO, ["delete_branch_on_merge"], False, "delete branch on merge"),
    (f"{REPO}/private-vulnerability-reporting", ["enabled"], False,
     "private vulnerability reporting"),
    (f"{REPO}/vulnerability-alerts", None, None, "Dependabot alerts"),
    (f"{REPO}/automated-security-fixes", ["enabled"], False, "Dependabot security updates"),
    (REPO, ["security_and_analysis", "secret_scanning", "status"], "disabled",
     "secret scanning"),
    (REPO, ["security_and_analysis", "secret_scanning_push_protection", "status"], "disabled",
     "secret scanning push protection"),
    (f"{REPO}/code-scanning/default-setup", ["state"], "not-configured",
     "code scanning (CodeQL)"),
    (f"{REPO}/actions/permissions/workflow", ["default_workflow_permissions"], "write",
     "Actions token"),
    (f"{REPO}/actions/permissions/workflow", ["can_approve_pull_request_reviews"], True,
     "Actions token approves PRs"),
    (f"{REPO}/actions/oidc/customization/sub", ["use_immutable_subject"], False,
     "OIDC subject uses immutable IDs"),
    (f"{REPO}/branches/main/protection", None, None, "branch protection on main"),
    (f"{REPO}/branches/main/protection", ["required_status_checks", "contexts"], ["dco"],
     "main: required checks"),
    (f"{REPO}/branches/main/protection", ["required_status_checks", "strict"], True,
     "main: checks must be up to date with main"),
    (f"{REPO}/branches/main/protection", ["required_pull_request_reviews"], None,
     "main: pull requests required (approvals)"),
    (f"{REPO}/branches/main/protection",
     ["required_pull_request_reviews", "required_approving_review_count"], 1,
     "main: pull requests required (approvals)"),
    (f"{REPO}/branches/main/protection", ["enforce_admins", "enabled"], False,
     "main: rules apply to admins"),
    (f"{REPO}/branches/main/protection", ["required_conversation_resolution", "enabled"], False,
     "main: conversations resolved"),
    (f"{REPO}/branches/main/protection", ["allow_force_pushes", "enabled"], True,
     "main: force-push allowed"),
    (f"{REPO}/branches/main/protection", ["allow_deletions", "enabled"], True,
     "main: deletion allowed"),
]


class RepoSettings(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        # The stub serves the repo's files from the directory the script runs in.
        (self.tmp / ".github").mkdir()
        (self.tmp / ".github" / "required-checks.txt").write_text(
            "# a comment\n" + "\n".join(CHECKS) + "\n", encoding="utf-8")
        self.state_file = self.tmp / "state.json"
        shutil.copy(HERE / "stub" / "fresh-repo.json", self.state_file)
        self.log = self.tmp / "gh.log"
        self.env = {**os.environ, "PATH": f"{HERE / 'stub'}{os.pathsep}{os.environ['PATH']}",
                    "STUB_STATE": str(self.state_file), "STUB_LOG": str(self.log),
                    "REPO_SETTINGS_READ_DELAY": "0"}

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.log.write_text("", encoding="utf-8")
        return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], cwd=self.tmp,
                              env=self.env, capture_output=True, text=True, timeout=60)

    def state(self) -> dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def edit(self, change) -> None:
        state = self.state()
        change(state)
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    def writes(self) -> list[str]:
        return [line for line in self.log.read_text(encoding="utf-8").splitlines()
                if line.startswith("gh ")]

    def assert_exit(self, result: subprocess.CompletedProcess[str], code: int) -> None:
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)

    def test_apply_then_check_is_clean(self) -> None:
        self.assert_exit(self.run_script("check"), 1)
        self.assert_exit(self.run_script("apply"), 0)
        state = self.state()
        self.assertFalse(state[REPO]["has_wiki"])
        self.assertTrue(state[REPO]["delete_branch_on_merge"])
        self.assertEqual(state[f"{REPO}/code-scanning/default-setup"]["state"], "configured")
        protection = state[f"{REPO}/branches/main/protection"]
        self.assertEqual(protection["required_status_checks"]["contexts"], CHECKS)
        self.assertTrue(state[f"{REPO}/actions/oidc/customization/sub"]["use_immutable_subject"])

        result = self.run_script("check")
        self.assert_exit(result, 0)
        self.assertEqual(self.writes(), [], "check must not change anything")
        self.assertIn("note  generic-secret scanning", result.stdout)
        self.assertIn("repo-settings: 0 settings differ", result.stdout)

        self.assert_exit(self.run_script("apply", "eduralph/demo"), 0)
        self.assertEqual(self.writes(), [], "a second apply must change nothing")

    def test_apply_waits_for_reads_to_catch_up(self) -> None:
        # Each read of the repo's settings is a dozen gh calls, so a lag of 20 reads makes
        # apply's first read-back stale and a later one current.
        self.env["STUB_LAG"] = "20"
        result = self.run_script("apply")
        self.assert_exit(result, 0)
        self.assertIn("repo-settings: 0 settings differ", result.stdout)
        # A write that never shows up is still reported once the reads run out.
        self.env["STUB_LAG"] = "1000"
        self.edit(lambda s: s[REPO].update(has_wiki=True))
        result = self.run_script("apply")
        self.assert_exit(result, 1)
        self.assertIn("  DIFF  wiki:", result.stdout)

    def test_check_names_each_wrong_setting(self) -> None:
        self.assert_exit(self.run_script("apply"), 0)
        good = self.state_file.read_text(encoding="utf-8")
        for path, keys, value, name in WRONG:
            with self.subTest(name, keys=keys):
                self.state_file.write_text(good, encoding="utf-8")

                def change(state, path=path, keys=keys, value=value):
                    if keys is None:
                        del state[path]
                        return
                    target = state[path]
                    for key in keys[:-1]:
                        target = target[key]
                    target[keys[-1]] = value

                self.edit(change)
                result = self.run_script("check")
                self.assert_exit(result, 1)
                self.assertIn(f"  DIFF  {name}:", result.stdout)
                self.assertIn("repo-settings: 1 setting differs", result.stdout)

    def test_generic_secret_scanning_in_an_organization(self) -> None:
        self.edit(lambda s: s[REPO]["owner"].update(type="Organization"))
        self.assert_exit(self.run_script("apply"), 0)
        self.assertIn("  ok    generic-secret scanning: enabled", self.run_script("check").stdout)
        self.edit(lambda s: s[REPO]["security_and_analysis"]
                  ["secret_scanning_non_provider_patterns"].update(status="disabled"))
        result = self.run_script("check")
        self.assert_exit(result, 1)
        self.assertIn("  DIFF  generic-secret scanning:", result.stdout)

    def test_private_repo_skips_what_github_does_not_offer(self) -> None:
        def private(state):
            state[REPO]["visibility"] = "private"
            del state[f"{REPO}/private-vulnerability-reporting"]
            del state[f"{REPO}/code-scanning/default-setup"]

        self.edit(private)
        self.assert_exit(self.run_script("apply"), 0)
        result = self.run_script("check")
        self.assert_exit(result, 0)
        self.assertIn("  skip  private vulnerability reporting", result.stdout)
        self.assertIn("  skip  code scanning (CodeQL)", result.stdout)

    def test_federation_rule_keeps_the_oidc_subject(self) -> None:
        self.edit(lambda s: s.update({
            f"{REPO}/actions/variables/ANTHROPIC_FEDERATION_RULE_ID": {"value": "rule"}}))
        result = self.run_script("apply")
        self.assert_exit(result, 1)
        self.assertIn("left the OIDC subject alone", result.stdout)
        self.assertFalse(any("oidc" in w for w in self.writes()))
        self.assertIn("  DIFF  OIDC subject uses immutable IDs", result.stdout)

        self.assert_exit(self.run_script("apply", "--change-oidc-subject"), 0)
        self.assertTrue(any("oidc" in w for w in self.writes()))

    def test_required_checks_source(self) -> None:
        other = self.tmp / "other-checks.txt"
        other.write_text("dco\ntests (3.12)\n", encoding="utf-8")
        self.assert_exit(self.run_script("apply", "--checks-file", str(other)), 0)
        protection = self.state()[f"{REPO}/branches/main/protection"]
        self.assertEqual(protection["required_status_checks"]["contexts"], ["dco", "tests (3.12)"])
        # The file in the repo now disagrees with what main requires.
        self.assert_exit(self.run_script("check"), 1)

        (self.tmp / ".github" / "required-checks.txt").unlink()
        result = self.run_script("check")
        self.assert_exit(result, 2)
        self.assertIn("has no .github/required-checks.txt", result.stderr)


if __name__ == "__main__":
    unittest.main()
