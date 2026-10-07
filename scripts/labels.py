#!/usr/bin/env python3
"""Derive a runtime image's `dev.kontra.runtime.*` labels from its runtime.json.

    python3 scripts/labels.py runtimes/python-browser 1.0.0         # k=v, one per line
    python3 scripts/labels.py runtimes/python-browser 1.0.0 --args   # one build argument per line
    docker image inspect "$I" --format '{{json .Config.Labels}}' | labels.py <dir> 1.0.0 --verify

WHY DERIVED AND NOT WRITTEN IN THE DOCKERFILE. §3.3's discovery rule is "no hardcoded list in
kontra": the orchestrator lists runtimes by querying the registry under `kontra-runtimes/` and reading
each image's labels. So the labels ARE the published interface, and runtime.json is the source they
come from. A Dockerfile that spelled them out would be a second copy of every field — and a
description that drifts from runtime.json is a description the Images page shows and nobody can find.

WHY LABELS AND NOT OCI ANNOTATIONS, which is what spec §3.3 asks for. MEASURED (FINDINGS §4): zot's
GraphQL `Labels` field answers `''` for an image carrying ten labels, and the reader that works is the
CONFIG BLOB at `/v2/<repo>/blobs/<configDigest>`. `docker build --label` puts a value in the config
blob; `--annotation` puts it in the manifest, where nothing on the Images page looks. One mechanism,
chosen because it is the one that can be read.

`kontra runtime build` (spec §3.4) has to produce the same labels from the same file. The day it does,
this mapping has two implementations and belongs in kontra's `shared/conformance/` corpus — see the
README's "When this becomes a conformance rule".

`--args` EMITS ONE ARGUMENT PER LINE, FOR `mapfile`, AND IS NEVER `eval`ed. A caller that expanded a
quoted string would be running runtime.json's `description` through a shell. Tested in
`tests/test_labels.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

#: `<major>.<minor>.<patch>`, the immutable half of §3.3's tag pair. The moving `:<major>` tag is
#: derived from it rather than passed, so the two can never disagree about which major this is.
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

#: A newline or a control character in a value would truncate `--args`'s one-argument-per-line
#: protocol and the label a reader gets back from the config blob.
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: The runtime.json fields published as a comma-joined label value.
COMMA_LISTS = ("provides", "languages")


def value_problems(runtime: dict) -> list[str]:
    """runtime.json strings that cannot survive the trip into a label.

    TWO CHARACTERS CANNOT APPEAR, and nothing downstream can recover from either. A newline ends an
    argument in `--args` and a label value in the config blob, so the labels after it are silently
    dropped. A comma inside a `provides` or `languages` element publishes two capabilities where the
    file declares one, and the console renders the halves as chips.
    """
    problems = []
    for key in ("name", "description", "builder"):
        value = runtime.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{key} is not a non-empty string: {value!r}")
        elif CONTROL_RE.search(value):
            problems.append(f"{key} contains a newline or control character: {value!r}")
    for key in COMMA_LISTS:
        # An absent field and an empty list publish the same empty label, so only a present one is
        # constrained. `null` is not absent: it would reach `",".join(None)`.
        if key not in runtime:
            continue
        value = runtime[key]
        if not isinstance(value, list):
            problems.append(f"{key} is {type(value).__name__}, want list")
            continue
        for element in value:
            if not isinstance(element, str) or not element.strip():
                problems.append(f"{key} has an element that is not a non-empty string: {element!r}")
            elif CONTROL_RE.search(element) or "," in element:
                problems.append(
                    f"{key} element {element!r} contains a comma or newline, and "
                    f"dev.kontra.runtime.{key} is a comma list"
                )
    return problems


def labels(runtime: dict, version: str) -> dict[str, str]:
    major, _, _ = version.partition(".")
    return {
        # §3.3's three required annotations, verbatim.
        "dev.kontra.runtime.name": runtime["name"],
        "dev.kontra.runtime.major": major,
        "dev.kontra.runtime.description": runtime["description"],
        # A COMMA LIST, as §3.3 specifies, because a label value is a string and JSON in a label is a
        # thing every reader then has to parse and fail at differently. Empty means "nothing beyond
        # the stock run image", which is a real answer and not a missing one.
        "dev.kontra.runtime.provides": ",".join(runtime.get("provides", [])),
        # Not in §3.3's list, and each earns its place by answering a question the Images page asks:
        # `version` is the immutable tag behind the moving one, `languages` is what §4.1's
        # default-runtime rule reads, and `builder` is what §3.4's compatibility check compares.
        "dev.kontra.runtime.version": version,
        "dev.kontra.runtime.languages": ",".join(runtime.get("languages", [])),
        "dev.kontra.runtime.builder": runtime["builder"],
    }


def verify(want: dict[str, str], got: dict[str, str] | None) -> list[str]:
    """What is wrong with a built image's labels, against what runtime.json says they should be.

    Extra labels are not a problem: `python-browser` carries `dev.kontra.runtime.pins` from its
    Dockerfile, because the Playwright build is pinned by an ARG and not by runtime.json.
    """
    got = got or {}
    problems = []
    for key, value in want.items():
        if key not in got:
            problems.append(f"{key} is missing from the image")
        elif got[key] != value:
            problems.append(f"{key} is {got[key]!r} on the image, want {value!r}")
    return problems


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        usage = "usage: scripts/labels.py <runtime-dir> <major.minor.patch> [--args|--verify]"
        print(usage, file=sys.stderr)
        return 2
    directory, version = args
    if not VERSION_RE.match(version):
        print(f"labels: {version!r} is not <major>.<minor>.<patch>", file=sys.stderr)
        return 2

    runtime = json.loads((Path(directory) / "runtime.json").read_text())
    major = version.split(".", 1)[0]
    # THE TAG IS THE RELEASE AND runtime.json IS THE CONTRACT, so `major` appears in both and has to
    # agree. A `python-browser/2.0.0` tag on a tree whose runtime.json still says `major: 1` would
    # publish `:2` and `:2.0.0` labelled `major=2` on an image built to a `:1` contract.
    if str(runtime.get("major")) != major:
        print(
            f"labels: tag version {version} is major {major}, "
            f"{directory}/runtime.json declares major {runtime.get('major')}",
            file=sys.stderr,
        )
        return 1

    if problems := value_problems(runtime):
        for p in problems:
            print(f"labels: {directory}/runtime.json {p}", file=sys.stderr)
        return 1

    out = labels(runtime, version)
    if "--verify" in argv:
        problems = verify(out, json.load(sys.stdin))
        for p in problems:
            print(f"labels: {p}", file=sys.stderr)
        if problems:
            return 1
        print(f"labels: {len(out)} dev.kontra.runtime.* labels verified on the image")
        return 0
    if "--args" in argv:
        # ONE ARGUMENT PER LINE, so a caller reads them with `mapfile -t` and never with `eval`. A
        # value cannot contain a newline — value_problems() above refuses one — so the lines and the
        # arguments are the same count.
        for k, v in out.items():
            print("--label")
            print(f"{k}={v}")
    else:
        for k, v in out.items():
            print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
