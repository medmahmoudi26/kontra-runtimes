#!/usr/bin/env python3
"""Decide what one CI run builds, from the git ref and the directory listing.

    python3 scripts/plan.py refs/tags/python-browser/1.0.0
    python3 scripts/plan.py refs/heads/dev

Prints `key=value` lines for `$GITHUB_OUTPUT` and a human summary on stderr. Exit 1 on a tag that
names no runtime.

THE MATRIX IS THE DIRECTORY LISTING, because §3.3's rule is "adding a runtime means adding a directory
and pushing". A job list written out in publish.yml would be the hardcoded list that rule forbids, one
directory behind the registry and silently not publishing.

IT IS A SCRIPT AND NOT A YAML HEREDOC so it can be run and read: inline Python inside a `run: |` block
must be indented to the block's margin, which puts the module's statements at a column YAML chose, and
the first person to reflow the step breaks the parse. It is also how this logic gets tested at all —
`tests/test_plan.py`, which passes `root` rather than the repository it happens to live in.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG_RE = re.compile(r"^refs/tags/(?P<name>[a-z0-9][a-z0-9-]*)/(?P<version>\d+\.\d+\.\d+)$")

def plan(ref: str, root: Path = ROOT) -> tuple[bool, str | None, list[str]]:
    """`(publish, version, names)`. `version` is None off a tag: each runtime takes its own major."""
    tag = TAG_RE.match(ref)
    if tag:
        name, version = tag["name"], tag["version"]
        # A TAG THAT NAMES NO RUNTIME MUST FAIL, not publish nothing and report success. A typo in a
        # tag is otherwise indistinguishable from a release that happened.
        if not (root / "runtimes" / name / "runtime.json").is_file():
            raise SystemExit(f"::error::tag {ref} names runtimes/{name}, which has no runtime.json")
        return True, version, [name]

    if ref.startswith("refs/tags/"):
        raise SystemExit(
            f"::error::tag {ref} is not `<name>/<major>.<minor>.<patch>`; nothing would be published"
        )

    names = sorted(p.name for p in (root / "runtimes").iterdir() if (p / "runtime.json").is_file())
    return False, None, names


def matrix(names: list[str], version: str | None, root: Path = ROOT) -> dict:
    include = []
    for name in names:
        rt = json.loads((root / "runtimes" / name / "runtime.json").read_text())
        major = rt["major"]
        include.append(
            {
                "name": name,
                "major": major,
                # THE VERSION IS PER RUNTIME, AND OFF A TAG IT IS THE RUNTIME'S OWN MAJOR. The labels
                # are derived from a version, `scripts/labels.py` refuses a version whose major
                # disagrees with runtime.json, and a refusal there means the image is built with no
                # `dev.kontra.*` label at all — invisible to §3.3's discovery. A single global
                # `0.0.0` was refused for every runtime on every non-tag run.
                "version": version or f"{major}.0.0",
                # A COMMA LIST, because that is what `docker buildx build --platform` takes. Turning a
                # JSON array into it inside the workflow would be a second place this shape is known.
                "platforms": ",".join(rt["platforms"]),
            }
        )
    return {"include": include}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: scripts/plan.py <git-ref>", file=sys.stderr)
        return 2
    publish, version, names = plan(argv[0])
    include = matrix(names, version)
    print(f"publish={'true' if publish else 'false'}")
    print(f"matrix={json.dumps(include, separators=(',', ':'))}")
    built = " ".join(f"{e['name']}:{e['version']}" for e in include["include"])
    print(f"plan: {argv[0]} -> publish={'true' if publish else 'false'} {built}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
