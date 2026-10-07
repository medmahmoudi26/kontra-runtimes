# base:1 — the builder's own run image, carrying kontra's declaration and nothing else.
#
# EVERY RUNTIME `FROM`s THE EXACT DIGEST IN builder.json's runImage. The builder names its run image
# by TAG (`io.buildpacks.builder.metadata`.stack.runImage = `docker.io/heroku/heroku:24`), so that
# tag moves under OS security patches. Pinning the digest here is what makes a
# `<major>.<minor>.<patch>` runtime tag reproducible, and moving this line is what a runtime patch
# release IS. `scripts/check.py` asserts every Dockerfile here names the same digest as builder.json.
FROM heroku/heroku@sha256:a2a63bd1b4e9f22ffcc60e4f5baf496b057c95517d063045dd9b0ffcf850890b

# NO `RUN` LINE, ON PURPOSE — and that is the point of this runtime rather than a gap in it.
# A run image with zero added layers shares every layer with the builder's own, so `base`, `python`
# and the stock run image cost ONE copy in the store between them. What distinguishes them is the
# declaration: `base` is where a runtime that needs no system package lands, and the seam exists so
# `python` can gain an apt package later without touching Go actors.
#
# `dev.kontra.runtime.*` labels are NOT written here. They are derived from runtime.json by
# `scripts/labels.py` and passed as `--label` at build time, so runtime.json is the single source of
# truth for what an actor and the Images page read. See README "Labels are derived, not written".

# A DECLARATION, NOT A SWITCH — AND MEASURED TO BE SO. The CNB spec lets a run image say whether an
# actor built on it may be rebased; `lifecycle` 0.21.22, which is what `heroku/builder:24` ships,
# records no `rebasable` field in `io.buildpacks.lifecycle.metadata` and rebases happily without this
# label at platform API 0.7, 0.12 and 0.13 alike. So nothing enforces it today, and the honest reason
# to carry it is that it is the one place the promise is written where a reader of the published image
# can find it:
#
#   a patch release of this runtime changes only OS layers, never the contract an already-built actor
#   image depends on. A change that could break one (a new libc soname, a removed interpreter) gets a
#   new MAJOR, because rebase does not rebuild the actor and cannot discover that it stopped working.
#
# WHAT DOES CONSTRAIN REBASE TODAY is the run image NAME recorded at build time. MEASURED: rebasing
# onto `…/python:1.0.1` when `…/python:1` was recorded is refused — "new base image not found in
# existing run image metadata … please provide -force to override" — while rebasing onto `…/python:1`
# after that tag has moved succeeds, keeps the app and dependency layer digests, and yields a new
# actor digest. The moving `:<major>` tag is therefore what both the build and the rebase must name;
# a digest reference is not interchangeable with it.
LABEL io.buildpacks.rebasable="true"
