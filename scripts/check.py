#!/usr/bin/env python3
"""Every invariant this repository has that can be checked without building anything.

THIS FILE IS THE TEST. A runtime is published once and then sits under every actor on an install, so
the failures worth catching are the ones that are cheap here and expensive there: a `builder` that
does not match the pinned builder, a base image that drifted in one Dockerfile and not the others, a
fixture missing the `.python-version` the Heroku Python CNB refuses to build without, a `playwright`
pin that agrees with nothing.

Run it with no arguments from anywhere:

    python3 scripts/check.py

Exit status is the number of problems, so `&&` chains work. CI runs this before it builds, because a
build that fails on a missing lockfile has spent four minutes to say what one second could.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from labels import value_problems

ROOT = Path(__file__).resolve().parent.parent
RUNTIMES = ROOT / "runtimes"

#: `<name>` becomes a path component of `<registry>/kontra-runtimes/<name>`, and an OCI repository
#: path component is lowercase alphanumerics with separators. Refusing anything else here means the
#: reference an actor writes in `actor.json` is always a legal reference.
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
KNOWN_PLATFORMS = {"linux/amd64", "linux/arm64"}
#: The engines §4.1's default-runtime rule knows. A runtime declaring anything else would be
#: undiscoverable by the thing that has to choose it.
KNOWN_LANGUAGES = {"go", "python"}

#: §4.2 as corrected: FOUR files, not three. The Heroku Python CNB refuses a uv-based build without a
#: `.python-version` — "When using the package manager uv on Heroku, you must specify your app's
#: Python version with a .python-version file" — and the build fails at status 51, after the upload.
PYTHON_FIXTURE_FILES = ("pyproject.toml", "uv.lock", "Procfile", ".python-version")
GO_FIXTURE_FILES = ("go.mod", "Procfile")

problems: list[str] = []


def bad(msg: str) -> None:
    problems.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        bad(f"{rel(path)} is missing")
    except json.JSONDecodeError as exc:
        bad(f"{rel(path)} is not valid JSON: {exc}")
    return None


def check_builder() -> dict:
    builder = load(ROOT / "builder.json") or {}
    if not builder:
        return {}
    for path in ("builder.image", "builder.digest", "runImage.image", "runImage.from", "runImage.digest"):
        head, _, tail = path.partition(".")
        if not isinstance(builder.get(head), dict) or not builder[head].get(tail):
            bad(f"builder.json is missing {path}")
    b = builder.get("builder", {})
    r = builder.get("runImage", {})
    for label, value in (("builder.digest", b.get("digest")), ("runImage.digest", r.get("digest"))):
        if value and not DIGEST_RE.match(value):
            bad(f"builder.json {label} is not a sha256 digest: {value!r}")
    # `from` is what a Dockerfile writes and `digest` is what a reader compares; they are two
    # spellings of one fact, so they have to agree or one of them is decoration.
    if r.get("from") and r.get("digest") and not r["from"].endswith("@" + r["digest"]):
        bad(f"builder.json runImage.from does not end in runImage.digest: {r['from']!r}")
    pack = builder.get("pack", {})
    if not DIGEST_RE.match("sha256:" + str(pack.get("sha256", {}).get("tarball", ""))):
        bad("builder.json pack.sha256.tarball is not a 64-hex sha256")
    if pack.get("version") and pack.get("url") and pack["version"] not in pack["url"]:
        bad(f"builder.json pack.url does not name pack.version {pack['version']}")
    return builder


def check_runtime(d: Path, builder: dict) -> None:
    rt = load(d / "runtime.json")
    if rt is None:
        return

    required = {
        "name": str,
        "major": int,
        "description": str,
        "builder": str,
        "languages": list,
        "provides": list,
        "platforms": list,
    }
    for key, kind in required.items():
        if key not in rt:
            bad(f"{rel(d)}/runtime.json has no {key!r}")
        elif not isinstance(rt[key], kind) or isinstance(rt[key], bool):
            bad(f"{rel(d)}/runtime.json {key!r} is {type(rt[key]).__name__}, want {kind.__name__}")

    # EVERY VALUE HERE BECOMES A LABEL ON A PUBLISHED IMAGE, so the characters a label cannot carry are
    # refused before anything is built. `scripts/labels.py` owns the rule because it owns the mapping;
    # this is the same refusal one step earlier, where it costs a second instead of a build.
    for problem in value_problems(rt):
        bad(f"{rel(d)}/runtime.json {problem}")

    name = rt.get("name")
    if isinstance(name, str):
        if not NAME_RE.match(name):
            bad(f"{rel(d)}/runtime.json name {name!r} is not a legal OCI path component")
        if name != d.name:
            bad(f"{rel(d)}/runtime.json name {name!r} does not match its directory {d.name!r}")
    if isinstance(rt.get("major"), int) and rt["major"] < 1:
        bad(f"{rel(d)}/runtime.json major must be >= 1, got {rt['major']}")

    # EVERY RUNTIME TARGETS THE INSTALL'S PINNED BUILDER. §3.4 says `kontra runtime build` refuses a
    # runtime whose `builder` does not match; this is the same refusal one repository earlier, where
    # the mismatch is a typo rather than a 403 on somebody's laptop.
    want_builder = builder.get("builder", {}).get("image")
    if want_builder and rt.get("builder") != want_builder:
        bad(f"{rel(d)}/runtime.json builder is {rt.get('builder')!r}, builder.json pins {want_builder!r}")

    for lang in rt.get("languages", []) if isinstance(rt.get("languages"), list) else []:
        if lang not in KNOWN_LANGUAGES:
            bad(f"{rel(d)}/runtime.json language {lang!r} is not one of {sorted(KNOWN_LANGUAGES)}")
    platforms = rt.get("platforms") if isinstance(rt.get("platforms"), list) else []
    if not platforms:
        bad(f"{rel(d)}/runtime.json platforms is empty; the publish workflow reads it as the build matrix")
    for plat in platforms:
        if plat not in KNOWN_PLATFORMS:
            bad(f"{rel(d)}/runtime.json platform {plat!r} is not one of {sorted(KNOWN_PLATFORMS)}")

    check_dockerfile(d, builder)
    check_fixture(d, rt)


def check_dockerfile(d: Path, builder: dict) -> None:
    df = d / "Dockerfile"
    if not df.exists():
        bad(f"{rel(d)}/Dockerfile is missing; discovery reads labels, and a re-tag cannot add one")
        return
    text = df.read_text()
    froms = re.findall(r"(?mi)^\s*FROM\s+(\S+)", text)
    if not froms:
        bad(f"{rel(df)} has no FROM")
        return
    want = builder.get("runImage", {}).get("from")
    # THE BASE IS PINNED BY DIGEST IN EVERY RUNTIME, TO THE SAME DIGEST. A runtime one patch behind
    # the others is a runtime whose actors cannot be rebased together, and the drift is invisible:
    # both Dockerfiles build, both push, and nothing compares them but this line.
    for ref in froms:
        if want and ref != want:
            bad(f"{rel(df)} FROM {ref!r} does not match builder.json runImage.from {want!r}")
    # A `LABEL` DIRECTIVE, NOT THE STRING. Every Dockerfile here discusses this label in a comment, so
    # a substring search passes on prose and the published image carries nothing.
    if not re.search(r'(?mi)^\s*LABEL\s+io\.buildpacks\.rebasable=(?:"true"|true)\s*$', text):
        bad(f"{rel(df)} has no `LABEL io.buildpacks.rebasable=\"true\"`; `pack rebase` would refuse every actor on it")
    # A run image that ends on root exports actor images that run as root, and nothing in the build
    # says so. Only a Dockerfile that switched away has to switch back.
    if re.search(r"(?mi)^\s*USER\s+root", text) and not re.search(r"(?mi)^\s*USER\s+heroku\s*$", text):
        bad(f"{rel(df)} switches to USER root and never back to USER heroku")

    # A `RUN` HAS TO EXECUTE ON THE TARGET ARCHITECTURE. publish.yml sets up no QEMU, because a
    # runtime with no `RUN` needs none: buildx assembles the other platform from manifests it never
    # runs. A `RUN` on linux/arm64 under those conditions dies with `exec format error` ten minutes
    # into the job; saying so here costs a second.
    rt = load(d / "runtime.json") or {}
    platforms = rt.get("platforms") if isinstance(rt.get("platforms"), list) else []
    if re.search(r"(?mi)^\s*RUN\s", text) and [p for p in platforms if p != "linux/amd64"]:
        bad(
            f"{rel(df)} has a RUN instruction, so {rel(d)}/runtime.json platforms must be "
            f'["linux/amd64"] until publish.yml sets up QEMU; it declares {platforms}'
        )


def check_fixture(d: Path, rt: dict) -> None:
    """§3.3's CI gate needs a fixture; this is the part of it that does not need a builder."""
    test = d / "test"
    if not test.is_dir():
        bad(f"{rel(d)}/test/ is missing; §3.3 gates publication on a fixture that builds and runs")
        return

    languages = rt.get("languages") or []
    wanted = PYTHON_FIXTURE_FILES if "python" in languages else GO_FIXTURE_FILES
    for f in wanted:
        if not (test / f).exists():
            bad(f"{rel(test)}/{f} is missing (required for a {'python' if 'python' in languages else 'go'} fixture)")

    procfile = test / "Procfile"
    if procfile.exists() and not re.search(r"(?m)^worker:\s*\S", procfile.read_text()):
        bad(f"{rel(procfile)} declares no `worker:` process; the CI gate runs `docker run --entrypoint worker <image>`")

    # The fixture is also the first actor.json in the system to declare §4.1's `runtime` field, so it
    # is the one place a wrong spelling of the reference would be caught before `kontra deploy` exists.
    actor = test / "actor.json"
    if not actor.exists():
        bad(f"{rel(test)}/actor.json is missing")
    else:
        man = load(actor) or {}
        want = f"{rt.get('name')}:{rt.get('major')}"
        if man.get("runtime") != want:
            bad(f"{rel(actor)} runtime is {man.get('runtime')!r}, want {want!r}")
        if man.get("schemaVersion") != "kontra.actor.v1":
            bad(f"{rel(actor)} schemaVersion is {man.get('schemaVersion')!r}, want 'kontra.actor.v1'")

    check_pin_agreement(d, test)


def check_pin_agreement(d: Path, test: Path) -> None:
    """A version pinned in a Dockerfile ARG and in a fixture's lockfile is ONE fact in two files.

    Playwright refuses to drive a browser build it was not shipped against, so the fixture would fail
    at run time with "Executable doesn't exist" — after a full build. Comparing the strings is free.
    """
    df = (d / "Dockerfile")
    if not df.exists():
        return
    args = dict(re.findall(r"(?mi)^\s*ARG\s+([A-Z0-9_]+)=(\S+)", df.read_text()))
    pyproject = test / "pyproject.toml"
    if "PLAYWRIGHT_VERSION" in args and pyproject.exists():
        want = args["PLAYWRIGHT_VERSION"]
        body = pyproject.read_text()
        if f'"playwright=={want}"' not in body:
            bad(f"{rel(pyproject)} does not pin playwright=={want} (the ARG in {rel(df)})")
        probe = test / "actor.py"
        if probe.exists() and f'EXPECTED_PLAYWRIGHT = "{want}"' not in probe.read_text():
            bad(f"{rel(probe)} EXPECTED_PLAYWRIGHT is not {want!r} (the ARG in {rel(df)})")
        lock = test / "uv.lock"
        if lock.exists() and f'version = "{want}"' not in lock.read_text():
            bad(f"{rel(lock)} does not resolve playwright to {want} — re-run `uv lock`")


def main() -> int:
    builder = check_builder()
    dirs = sorted(p for p in RUNTIMES.iterdir() if p.is_dir()) if RUNTIMES.is_dir() else []
    if not dirs:
        bad("runtimes/ holds no runtime directories")
    for d in dirs:
        check_runtime(d, builder)

    for p in problems:
        print(f"check: {p}", file=sys.stderr)
    if problems:
        print(f"\n{len(problems)} problem(s)", file=sys.stderr)
        return len(problems)
    print(f"check: {len(dirs)} runtime(s) ok: {', '.join(d.name for d in dirs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
