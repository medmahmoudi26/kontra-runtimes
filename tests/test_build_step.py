"""The shell fragment that both `scripts/build.sh` and every build step in publish.yml use.

THE DEFECT THIS PINS. `docker build … "$(python3 scripts/labels.py …)"` exits 0 when labels.py
refuses — errexit does not fire inside an argument list — so the step went green and the image carried
no `dev.kontra.*` label at all. An assignment is where errexit fires, and `mapfile` then turns one
argument per line into an argv array without a shell ever looking at runtime.json's values.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, write_runtime

#: What a build step does with the labels, verbatim apart from `docker build` being replaced by a
#: printf so the test needs no daemon. `$DIR` and `$VERSION` come from the environment, as in the job.
FRAGMENT = """
set -euo pipefail
labels=$(python3 "$SCRIPTS/labels.py" "$DIR" "$VERSION" --args)
mapfile -t label_args <<<"$labels"
printf '%s\\n' "${label_args[@]}"
"""

SHELL_FILES = (ROOT / "scripts" / "build.sh", ROOT / ".github" / "workflows" / "publish.yml")


class FragmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def fragment(self, directory: Path, version: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", FRAGMENT],
            cwd=ROOT, capture_output=True, text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "SCRIPTS": str(ROOT / "scripts"),
                "DIR": str(directory),
                "VERSION": version,
            },
        )

    def test_a_refused_derivation_fails_the_step(self) -> None:
        # runtime.json says major 1; the tag says 2. labels.py refuses, and the step must not build.
        proc = self.fragment(write_runtime(self.tmp, "fixture", major=1), "2.0.0")
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(proc.stdout, "")
        self.assertIn("declares major", proc.stderr)

    def test_a_value_that_cannot_be_a_label_fails_the_step(self) -> None:
        proc = self.fragment(write_runtime(self.tmp, "fixture", description="one\ntwo"), "1.0.0")
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(proc.stdout, "")

    def test_a_good_derivation_becomes_fourteen_arguments(self) -> None:
        proc = self.fragment(write_runtime(self.tmp, "fixture"), "1.0.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = proc.stdout.splitlines()
        self.assertEqual(len(argv), 14)
        self.assertEqual(set(argv[0::2]), {"--label"})

    def test_a_hostile_description_reaches_the_argument_verbatim(self) -> None:
        # A quote, a `$`, a backtick and a command substitution are all data here. Under `eval` the
        # quote broke the build and the substitution ran in CI.
        description = """Chromium's "headless" $HOME `id` $(id) mode, with fonts."""
        proc = self.fragment(write_runtime(self.tmp, "fixture", description=description), "1.0.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"dev.kontra.runtime.description={description}", proc.stdout.splitlines())

    def test_a_description_with_a_space_survives_as_one_argument(self) -> None:
        # The reason the old code quoted and `eval`ed at all; `mapfile` does it without a shell.
        proc = self.fragment(write_runtime(self.tmp, "fixture", description="two words"), "1.0.0")
        self.assertIn("dev.kontra.runtime.description=two words", proc.stdout.splitlines())


class CallersTest(unittest.TestCase):
    """Every caller uses that shape. A grep, because the next one will copy an existing line."""

    def test_nothing_evals(self) -> None:
        for path in SHELL_FILES:
            with self.subTest(path=path.name):
                self.assertIsNone(re.search(r"(?m)^\s*eval\s", path.read_text()))

    def test_labels_is_never_substituted_into_an_argument_list(self) -> None:
        for path in SHELL_FILES:
            with self.subTest(path=path.name):
                text = path.read_text()
                for match in re.finditer(r"\S*labels\.py[^\n]*--args", text):
                    line = text[text.rfind("\n", 0, match.start()) + 1 : match.end()]
                    self.assertRegex(line.strip(), r"^labels=\$\(", line)


if __name__ == "__main__":
    unittest.main()
