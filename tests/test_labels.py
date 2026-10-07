"""runtime.json -> the seven `dev.kontra.runtime.*` labels, and what cannot survive the trip.

§3.3's discovery reads nothing but these labels, so every claim here is a claim about whether a
published runtime is visible to the console and resolvable by `kontra deploy`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import GOOD_RUNTIME, ROOT, SCRIPTS, write_runtime

import labels

#: The published interface. A reader outside this repository depends on this exact set, so the count
#: is asserted as well as the names: a label added here is a label the console may start requiring.
EXPECTED = {
    "dev.kontra.runtime.name",
    "dev.kontra.runtime.major",
    "dev.kontra.runtime.description",
    "dev.kontra.runtime.provides",
    "dev.kontra.runtime.version",
    "dev.kontra.runtime.languages",
    "dev.kontra.runtime.builder",
}


def run(args: list[str], stdin: str | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "labels.py"), *args],
        cwd=cwd, input=stdin, capture_output=True, text=True,
    )


class MappingTest(unittest.TestCase):
    def test_the_seven_labels_and_their_values(self) -> None:
        out = labels.labels(
            {
                "name": "python-browser",
                "description": "Python, with a browser.",
                "builder": "heroku/builder:24",
                "languages": ["python"],
                "provides": ["chromium", "playwright-browsers"],
            },
            "1.2.3",
        )
        self.assertEqual(set(out), EXPECTED)
        self.assertEqual(
            out,
            {
                "dev.kontra.runtime.name": "python-browser",
                "dev.kontra.runtime.major": "1",
                "dev.kontra.runtime.description": "Python, with a browser.",
                "dev.kontra.runtime.provides": "chromium,playwright-browsers",
                "dev.kontra.runtime.version": "1.2.3",
                "dev.kontra.runtime.languages": "python",
                "dev.kontra.runtime.builder": "heroku/builder:24",
            },
        )

    def test_the_major_comes_from_the_version_and_not_from_runtime_json(self) -> None:
        # One spelling of the major on the image, so the moving `:<major>` tag and the label agree.
        out = labels.labels({**GOOD_RUNTIME, "major": 9}, "4.0.1")
        self.assertEqual(out["dev.kontra.runtime.major"], "4")

    def test_an_empty_list_is_an_empty_label_and_not_a_missing_one(self) -> None:
        out = labels.labels({**GOOD_RUNTIME, "provides": [], "languages": []}, "1.0.0")
        self.assertEqual(out["dev.kontra.runtime.provides"], "")
        self.assertEqual(set(out), EXPECTED)

    def test_every_real_runtime_produces_all_seven(self) -> None:
        for d in sorted(p for p in (ROOT / "runtimes").iterdir() if p.is_dir()):
            rt = json.loads((d / "runtime.json").read_text())
            with self.subTest(runtime=d.name):
                out = labels.labels(rt, f"{rt['major']}.0.0")
                self.assertEqual(set(out), EXPECTED)
                self.assertTrue(all(v != "" for k, v in out.items() if k.endswith(".description")))


class ValueConstraintTest(unittest.TestCase):
    """What a label value cannot carry, and what a comma list cannot carry."""

    def test_a_clean_runtime_has_no_problems(self) -> None:
        self.assertEqual(labels.value_problems(GOOD_RUNTIME), [])

    def test_quotes_dollars_and_backticks_are_data(self) -> None:
        # Nothing `eval`s these values, so a description reads like prose and not like shell.
        hostile = {**GOOD_RUNTIME, "description": """Chromium's "headless" $HOME `id` mode."""}
        self.assertEqual(labels.value_problems(hostile), [])
        self.assertEqual(
            labels.labels(hostile, "1.0.0")["dev.kontra.runtime.description"], hostile["description"]
        )

    def test_a_newline_in_a_value_is_refused(self) -> None:
        for key in ("name", "description", "builder"):
            with self.subTest(key=key):
                problems = labels.value_problems({**GOOD_RUNTIME, key: "one\ntwo"})
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("newline", problems[0])

    def test_a_comma_in_a_list_element_is_refused(self) -> None:
        for key in ("provides", "languages"):
            with self.subTest(key=key):
                problems = labels.value_problems({**GOOD_RUNTIME, key: ["chromium,fonts"]})
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("comma list", problems[0])

    def test_an_empty_or_nonstring_value_is_refused(self) -> None:
        self.assertTrue(labels.value_problems({**GOOD_RUNTIME, "description": "   "}))
        self.assertTrue(labels.value_problems({**GOOD_RUNTIME, "description": 7}))
        self.assertTrue(labels.value_problems({**GOOD_RUNTIME, "provides": ["chromium", ""]}))
        self.assertTrue(labels.value_problems({**GOOD_RUNTIME, "provides": "chromium"}))
        # `null` is not the same as absent: it would reach `",".join(None)` in labels().
        self.assertTrue(labels.value_problems({**GOOD_RUNTIME, "provides": None}))
        absent = {k: v for k, v in GOOD_RUNTIME.items() if k != "provides"}
        self.assertEqual(labels.value_problems(absent), [])


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_args_emits_one_argument_per_line(self) -> None:
        # The protocol `mapfile -t` reads. Two lines per label, `--label` then `k=v`, and never a
        # quoted blob that a caller would have to `eval`.
        d = write_runtime(self.tmp, "fixture")
        proc = run([str(d), "1.0.0", "--args"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(len(lines), 2 * len(EXPECTED))
        self.assertEqual(set(lines[0::2]), {"--label"})
        self.assertEqual({line.split("=", 1)[0] for line in lines[1::2]}, EXPECTED)
        self.assertNotIn('"', proc.stdout)

    def test_a_major_mismatch_exits_nonzero(self) -> None:
        d = write_runtime(self.tmp, "fixture", major=1)
        proc = run([str(d), "2.0.0", "--args"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")

    def test_a_malformed_version_exits_nonzero(self) -> None:
        d = write_runtime(self.tmp, "fixture")
        for version in ("1.0", "v1.0.0", "1.0.0-rc1", ""):
            with self.subTest(version=version):
                self.assertEqual(run([str(d), version, "--args"], cwd=self.tmp).returncode, 2)

    def test_a_value_that_cannot_be_a_label_exits_nonzero_and_prints_nothing(self) -> None:
        # The build step assigns from this, so a refusal here is what stops an unpublishable image.
        d = write_runtime(self.tmp, "fixture", description="one\ntwo")
        proc = run([str(d), "1.0.0", "--args"], cwd=self.tmp)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, "")
        self.assertIn("newline", proc.stderr)


class VerifyTest(unittest.TestCase):
    """Reading the built image back, which is the only thing that proves the labels were applied."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.dir = write_runtime(self.tmp, "fixture")
        self.want = labels.labels(json.loads((self.dir / "runtime.json").read_text()), "1.0.0")

    def test_an_image_carrying_them_all_verifies(self) -> None:
        self.assertEqual(labels.verify(self.want, dict(self.want)), [])

    def test_an_extra_label_is_not_a_problem(self) -> None:
        # `python-browser` carries `dev.kontra.runtime.pins` from an ARG in its Dockerfile.
        got = {**self.want, "dev.kontra.runtime.pins": "playwright=1.58.0"}
        self.assertEqual(labels.verify(self.want, got), [])

    def test_a_missing_label_is_reported(self) -> None:
        got = {k: v for k, v in self.want.items() if k != "dev.kontra.runtime.provides"}
        self.assertEqual(
            labels.verify(self.want, got),
            ["dev.kontra.runtime.provides is missing from the image"],
        )

    def test_a_changed_value_is_reported(self) -> None:
        got = {**self.want, "dev.kontra.runtime.description": "something else"}
        problems = labels.verify(self.want, got)
        self.assertEqual(len(problems), 1)
        self.assertIn("want", problems[0])

    def test_an_image_with_no_labels_at_all_reports_all_seven(self) -> None:
        # `docker image inspect --format '{{json .Config.Labels}}'` prints `null` for that image.
        self.assertEqual(len(labels.verify(self.want, None)), len(EXPECTED))

    def test_the_verify_cli_reads_the_inspect_output_on_stdin(self) -> None:
        ok = run([str(self.dir), "1.0.0", "--verify"], stdin=json.dumps(self.want), cwd=self.tmp)
        self.assertEqual(ok.returncode, 0, ok.stderr)

        for payload in ("null", json.dumps({"io.buildpacks.rebasable": "true"})):
            with self.subTest(payload=payload):
                bad = run([str(self.dir), "1.0.0", "--verify"], stdin=payload, cwd=self.tmp)
                self.assertEqual(bad.returncode, 1)
                self.assertIn("is missing from the image", bad.stderr)


if __name__ == "__main__":
    unittest.main()
