"""`scripts/check.py` against this repository, and against a tree with one thing wrong in it.

check.py derives its root from `__file__`, so a negative case is a copy of the tree with one edit —
which is also the only honest way to assert it fails, since the real tree must pass.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT


def copy_tree() -> Path:
    tmp = Path(tempfile.mkdtemp()) / "kontra-runtimes"
    tmp.mkdir()
    shutil.copytree(ROOT / "scripts", tmp / "scripts")
    shutil.copytree(ROOT / "runtimes", tmp / "runtimes")
    shutil.copy(ROOT / "builder.json", tmp / "builder.json")
    return tmp


def check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "check.py")], capture_output=True, text=True
    )


class CheckTest(unittest.TestCase):
    def test_this_repository_passes(self) -> None:
        proc = check(ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_copy_of_this_repository_passes(self) -> None:
        # So a failure below is the edit and not the copying.
        proc = check(copy_tree())
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_value_that_cannot_become_a_label_is_refused_before_any_build(self) -> None:
        # The same rule labels.py enforces, one step earlier, where it costs a second and not a build.
        for field, value, expected in (
            ("description", "one\ntwo", "newline"),
            ("provides", ["chromium,fonts"], "comma list"),
            ("description", "", "non-empty"),
        ):
            with self.subTest(field=field):
                root = copy_tree()
                path = root / "runtimes" / "python" / "runtime.json"
                path.write_text(json.dumps({**json.loads(path.read_text()), field: value}))
                proc = check(root)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn(expected, proc.stderr)


if __name__ == "__main__":
    unittest.main()
