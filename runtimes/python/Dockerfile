# python:1 — the default runtime for Python actors.
#
# SEE runtimes/base/Dockerfile for why the base is pinned by digest and why the `dev.kontra.runtime.*`
# labels are not written here.
FROM heroku/heroku@sha256:a2a63bd1b4e9f22ffcc60e4f5baf496b057c95517d063045dd9b0ffcf850890b

# THE INTERPRETER IS NOT IN THIS IMAGE, AND THAT IS CORRECT. `heroku/python` 6.7.0 installs CPython
# into a build layer (`heroku/python:python`) and the virtualenv into another (`heroku/python:venv`),
# both of which land on top of this run image at export. An interpreter baked in here would be a
# second Python on PATH that the buildpack's layer then shadows — one more thing to be wrong about.
#
# So this runtime is byte-identical to `base:1` today and differs only in its declaration. That is
# the seam, not an oversight: the day a Python actor needs `libpq5` it is added HERE, and no Go actor
# gets it. `languages: ["python"]` is also what §4.1's default-runtime rule reads to pick `python:1`
# for an actor.json with no `runtime` field.

# See runtimes/base/Dockerfile for what this label does and does not enforce.
LABEL io.buildpacks.rebasable="true"
