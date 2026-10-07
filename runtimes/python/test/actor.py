"""The `python:1` fixture: what a published runtime has to be true of, checked by running it.

NOT AN `@actor.defn`, AND NOT BY CHOICE. `kontra-sdk` is published to no index — `pip index` and
`https://pypi.org/pypi/kontra-sdk/json` both answer 404 — so a `uv.lock` here cannot resolve it, and
a fixture that reached into the kontra checkout would stop being buildable from this repository alone.
Nothing in this file is therefore the shape an actor author writes; `../..//README.md` says what a
real Python actor's `actor.py` looks like.

WHAT THIS FIXTURE IS FOR: a runtime image is published once and then sits under every actor on the
install, so the properties below are the ones that are expensive to discover later. Each is a
property of the RUN IMAGE, not of this program — which is why the gate is `docker run`, after a real
`pack build`, rather than a unit test.

    uid 1000, not root     the run image's `User` survived export (platform API >= 0.12 reads it)
    /workspace             §4.4's path replaced /actor/<name>/, and the launcher put us there
    a pure-python wheel    `heroku/python:venv` built from uv.lock and is importable at run time
    a C-extension wheel    a manylinux wheel's glibc floor is met by this run image's glibc

The process is `worker:` because that is what §4.2 names, and it EXITS 0 rather than serving: a
kontra `worker` runs `actor.serve()` and waits for a Temporal task queue, which is a control plane
this repository does not have and cannot stand up. Exiting is the most this gate can honestly claim.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, saw: object) -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {saw}")
        if not ok:
            failures.append(name)

    # THE RUN IMAGE'S USER, read back from the process rather than from the image config, because the
    # exporter is what carries it across and the exporter is the thing being tested.
    check("uid is 1000 (not root)", os.getuid() == 1000, f"uid={os.getuid()} gid={os.getgid()}")

    # §4.4: with buildpacks the app lands at /workspace. Every reader of /actor/<name>/ has to move
    # with it, so the fixture states the new path as a fact rather than a convention.
    cwd = os.getcwd()
    check("cwd is /workspace", cwd == "/workspace", cwd)
    here = os.path.dirname(os.path.abspath(__file__))
    check("actor.py is under /workspace", here == "/workspace", here)

    # A PURE-PYTHON WHEEL FROM uv.lock. Proves the venv layer exists and is on this interpreter's
    # path at run time, not merely that the build step reported success.
    try:
        import httpx

        check("httpx imports", True, httpx.__version__)
    except Exception as exc:  # pragma: no cover - the failure is the report
        check("httpx imports", False, repr(exc))

    # A C-EXTENSION WHEEL. The venv is built on the BUILD image and runs on the RUN image; a manylinux
    # wheel links against a glibc floor, so this is the one check that would catch a run image whose
    # libc is older than the wheels the builder resolves. A pure-python dependency cannot see it.
    try:
        import orjson

        check("orjson (C extension) loads", orjson.dumps({"a": 1}) == b'{"a":1}', orjson.__version__)
    except Exception as exc:  # pragma: no cover - the failure is the report
        check("orjson (C extension) loads", False, repr(exc))

    if failures:
        print(f"\npython:1 fixture FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\npython:1 fixture ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
