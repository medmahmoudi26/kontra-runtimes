"""What one CI run builds, from the git ref.

THE TEST THAT MATTERS HERE IS `test_every_version_this_emits_is_accepted_by_labels`. plan.py chooses
the version the labels are derived from, labels.py refuses a version whose major disagrees with
runtime.json, and a refusal means the image is built with no `dev.kontra.runtime.*` label at all — so
these two scripts agreeing is the difference between a published runtime and an invisible one.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, SCRIPTS, write_runtime

import plan


class PlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        write_runtime(self.tmp, "python", major=1, platforms=["linux/amd64", "linux/arm64"])
        write_runtime(self.tmp, "base", major=2, platforms=["linux/amd64"])

    def test_a_tag_publishes_only_the_runtime_it_names(self) -> None:
        self.assertEqual(plan.plan("refs/tags/python/1.2.3", self.tmp), (True, "1.2.3", ["python"]))

    def test_a_tag_naming_no_runtime_fails(self) -> None:
        # A typo in a tag must not be indistinguishable from a release that happened.
        with self.assertRaises(SystemExit):
            plan.plan("refs/tags/pythn/1.0.0", self.tmp)

    def test_a_tag_that_is_not_name_slash_semver_fails(self) -> None:
        for ref in ("refs/tags/v1.0.0", "refs/tags/python/1.0", "refs/tags/python/1.0.0-rc1"):
            with self.subTest(ref=ref), self.assertRaises(SystemExit):
                plan.plan(ref, self.tmp)

    def test_a_branch_builds_every_runtime_and_publishes_nothing(self) -> None:
        self.assertEqual(plan.plan("refs/heads/dev", self.tmp), (False, None, ["base", "python"]))

    def test_off_a_tag_the_version_is_the_runtimes_own_major(self) -> None:
        # THE REGRESSION. A single global `0.0.0` was refused by labels.py for every runtime on every
        # non-tag run, which built unlabelled images and reported success.
        publish, version, names = plan.plan("refs/heads/dev", self.tmp)
        include = plan.matrix(names, version, self.tmp)["include"]
        self.assertEqual(
            {e["name"]: e["version"] for e in include}, {"base": "2.0.0", "python": "1.0.0"}
        )

    def test_on_a_tag_the_version_is_the_tags(self) -> None:
        include = plan.matrix(["python"], "1.4.9", self.tmp)["include"]
        self.assertEqual(include[0]["version"], "1.4.9")

    def test_platforms_become_the_comma_list_buildx_takes(self) -> None:
        include = plan.matrix(["python"], None, self.tmp)["include"]
        self.assertEqual(include[0]["platforms"], "linux/amd64,linux/arm64")

    def test_the_cli_prints_matrix_and_publish_for_github_output(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "plan.py"), "refs/heads/dev"],
            capture_output=True, text=True, check=True,
        )
        out = dict(line.split("=", 1) for line in proc.stdout.strip().splitlines())
        self.assertEqual(out["publish"], "false")
        self.assertEqual(
            sorted(e["name"] for e in json.loads(out["matrix"])["include"]),
            sorted(p.name for p in (ROOT / "runtimes").iterdir() if p.is_dir()),
        )


class PlanAgreesWithLabelsTest(unittest.TestCase):
    """The two scripts have to agree about the version, on this repository's real runtimes."""

    def run_labels(self, name: str, version: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "labels.py"), f"runtimes/{name}", version],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_every_version_this_emits_is_accepted_by_labels(self) -> None:
        for ref in ("refs/heads/dev", "refs/heads/main", "refs/pull/7/merge"):
            publish, version, names = plan.plan(ref)
            self.assertFalse(publish)
            for entry in plan.matrix(names, version)["include"]:
                with self.subTest(ref=ref, runtime=entry["name"]):
                    proc = self.run_labels(entry["name"], entry["version"])
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    keys = [line.split("=", 1)[0] for line in proc.stdout.strip().splitlines()]
                    self.assertEqual(len(keys), 7, keys)

    def test_a_tag_whose_major_is_not_the_runtimes_is_still_refused(self) -> None:
        # The reason the unpublished version cannot be a constant: this check has to keep biting.
        for d in sorted(p for p in (ROOT / "runtimes").iterdir() if p.is_dir()):
            major = json.loads((d / "runtime.json").read_text())["major"]
            with self.subTest(runtime=d.name):
                proc = self.run_labels(d.name, f"{major + 1}.0.0")
                self.assertEqual(proc.returncode, 1, proc.stdout)
                self.assertIn("declares major", proc.stderr)


if __name__ == "__main__":
    unittest.main()
