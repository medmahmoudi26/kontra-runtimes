# python-browser:1 — Python plus a Chromium that Playwright will actually drive.
#
# SEE runtimes/base/Dockerfile for why the base is pinned by digest and why the `dev.kontra.runtime.*`
# labels are not written here.
FROM heroku/heroku@sha256:a2a63bd1b4e9f22ffcc60e4f5baf496b057c95517d063045dd9b0ffcf850890b

# THE BROWSER IS PLAYWRIGHT'S, NOT UBUNTU'S, and that is forced rather than preferred. On Ubuntu
# 24.04 the `chromium` apt package is a transitional shim to a snap, and snapd does not run in a
# container — so `apt-get install chromium` produces an image with a browser that cannot start.
#
# ONE VERSION, ONE SOURCE OF TRUTH. Playwright refuses to drive a browser build it was not shipped
# against, so the actor's own `playwright==` pin must match THIS number. It is not repeated in
# runtime.json: it is emitted as a label from this ARG (see below) so an actor author can read the
# pin off the published image instead of off this file.
#
# 1.58.0 because that is what the actors already on this path pin (`webcrawl`, `crawl4ai`), so moving
# them onto this runtime is a deletion of their deploy.sh and not a version bump as well.
ARG PLAYWRIGHT_VERSION=1.58.0

# /opt, NOT $HOME/.cache. The browser is downloaded by root at build time and opened by uid 1000 at
# run time; Playwright's default location is the *current user's* cache, so a browser under root's
# HOME is a browser the actor cannot find — and the failure lands at `@actor.load` on a Machine,
# not here where it would be seen.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

USER root

# THE DEPENDENCY LIST IS PLAYWRIGHT'S, NOT OURS. `--with-deps` resolves the apt names for the exact
# distro and browser build in play. Hand-maintaining the list is how a runtime breaks: the names the
# actors' own `deploy.sh` scripts carry are the 22.04 spellings, and on 24.04 the t64 transition
# renamed them — MEASURED, on this base image:
#
#   E: Package 'libasound2' has no installation candidate
#      Package libasound2 is a virtual package provided by: libasound2t64 1.2.11-1ubuntu0.3
#
# ONE `RUN`, so the interpreter that drove the download never reaches a published layer. Playwright's
# CLI needs a Python or a Node to run and heroku/heroku:24 has neither — on purpose, because the
# buildpack installs its own in a launch layer and puts it first on PATH. A second `/usr/bin/python3`
# left behind here would be the one a `docker exec` into a Worker finds, so `--auto-remove` takes the
# bootstrap back out and the published image has no interpreter at all (verified by
# `runtimes/python-browser/test` running on it, which brings its own).
#
# `chmod a+rX`: the download runs as root and the actor runs as uid 1000. A browser nobody can
# execute fails at `@actor.load` on a Machine, which is the most expensive place to learn it.
RUN set -eux; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates python3-venv; \
    python3 -m venv /tmp/pw; \
    /tmp/pw/bin/pip install --no-cache-dir --quiet "playwright==${PLAYWRIGHT_VERSION}"; \
    /tmp/pw/bin/playwright install --with-deps chromium; \
    rm -rf /tmp/pw /root/.cache; \
    apt-get purge -y --auto-remove python3-venv; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*; \
    test -d "${PLAYWRIGHT_BROWSERS_PATH}"; \
    chmod -R a+rX "${PLAYWRIGHT_BROWSERS_PATH}"

# BACK TO uid 1000 BEFORE THE IMAGE ENDS. At platform API 0.12 and above the lifecycle reads the run
# image's `User` field rather than the `CNB_USER_ID`/`CNB_GROUP_ID` labels, and pack negotiates the
# highest API the builder supports (0.15 here). A run image left on root would export an actor image
# that runs as root — silently, because nothing in the build fails.
USER heroku

# `provides` in runtime.json says WHICH capability; this says WHICH BUILD of it, because an actor
# that pins the wrong `playwright==` fails at load with "Executable doesn't exist" and the version it
# needed is otherwise only in this file.
LABEL dev.kontra.runtime.pins="playwright=${PLAYWRIGHT_VERSION}"

# A patch release of this runtime is a newer OS and a newer Chromium under an unchanged actor image —
# which is a stronger promise here than anywhere else in this repository, because a Chromium major
# that Playwright 1.58 refuses to drive would break every actor on this runtime without rebuilding
# one. A browser bump that moves `ARG PLAYWRIGHT_VERSION` is therefore a new MAJOR, not a patch.
# See runtimes/base/Dockerfile for what this label does and does not enforce.
LABEL io.buildpacks.rebasable="true"
