# kontra-runtimes

The OS that kontra actors run on, as code.

A **runtime** is a Cloud Native Buildpacks **run image**: the operating system plus whatever system
packages an actor needs underneath it. An actor declares one by name and major in its `actor.json` —

```json
{ "schemaVersion": "kontra.actor.v1", "name": "webcrawl", "version": "0.3.0", "runtime": "python-browser:1" }
```

— and `kontra deploy` resolves it, pins its digest, and builds the actor on top of it with `pack`. The
actor image is then runtime layers, then dependency layers, then one app layer. Nothing about the
actor's own code reaches the runtime, and nothing about the OS reaches the actor's build.

**Why this is a separate repository.** Three reasons, in the order they bite:

1. **A runtime changes on the OS's schedule, an actor changes on yours.** Ubuntu ships a `libnss3`
   fix; every actor in the install needs it and not one of them needs rebuilding. `pack rebase`
   rewrites their manifests onto a new runtime digest without re-running a single build.
2. **System packages stop being per-actor.** Before this, `webcrawl` installed Chromium in a
   `deploy.sh` that ran inside its own image — so did `crawl4ai`, separately, at 1.44–2.26 GiB each.
   Now there is one `python-browser` and ten actors share its layers.
3. **Adding a runtime must not be a change to kontra.** The orchestrator discovers runtimes by
   querying the registry for repositories under `kontra-runtimes/` and reading their labels. Adding a
   runtime is adding a directory here and pushing a tag. There is no list in kontra to edit, and that
   is enforced: `scripts/plan.py` builds CI's job matrix from the directory listing.

---

## What is pinned, and where

Everything a build depends on is pinned by digest in **`builder.json`**, which is the one file to edit
when any of it moves:

| | pin | why it is pinned |
|---|---|---|
| builder | `heroku/builder:24` @ `sha256:97aa835c…4098c1` | the builder decides what every actor image contains |
| run image | `heroku/heroku:24` @ `sha256:a2a63bd1…50890b` | every runtime here `FROM`s this exact digest |
| `pack` | `v0.40.9`, tarball `sha256:dc0ee1e9…758e9` | a floating download is an unreviewed change to every build |
| lifecycle | `0.21.22`, platform API 0.7 (max 0.15) | what the builder ships; it decides the rules below |

The builder names its run image **by tag** (`io.buildpacks.builder.metadata`.stack.runImage =
`docker.io/heroku/heroku:24`), so that tag moves under OS security patches. Pinning the digest in each
`Dockerfile` is what makes a `<major>.<minor>.<patch>` runtime tag reproducible — and moving that one
line is what a runtime **patch release** is. `scripts/check.py` asserts every Dockerfile here names the
same digest as `builder.json`, because a runtime one patch behind the others is a runtime whose actors
cannot be rebased together, and the drift is otherwise invisible: both build, both push, nothing
compares them.

---

## Layout

```
builder.json                  the pinned builder, run image, pack and lifecycle
runtimes/
  base/                       the run image unmodified — Go actors and plain binaries
    Dockerfile
    runtime.json
    test/                     a fixture actor that must build and run on this runtime
  python/                     the default for Python actors
    Dockerfile
    runtime.json
    test/
  python-browser/             Python + Chromium + the fonts a headless browser needs
    Dockerfile
    runtime.json
    test/
scripts/
  check.py                    every invariant that can be checked without building
  plan.py                     what one CI run builds, from the git ref
  labels.py                   runtime.json -> the image's dev.kontra.runtime.* labels
  build.sh                    build one runtime locally, labelled as CI labels it
tests/                        the scripts' own tests — `python3 -m unittest discover -s tests`
.github/workflows/publish.yml build, gate, push, sign
```

**`tests/` exists because the two scripts that decide what is built and what it is labelled fail
silently.** A wrong answer from either produces a green build: §3.3's discovery reads nothing but the
`dev.kontra.runtime.*` labels, so an unlabelled runtime pushes and signs successfully and is then
missing from the console and unresolvable by `kontra deploy`. stdlib `unittest`, so it needs nothing
installed, and CI runs it before any build.

**`base/` has a Dockerfile**, which the original design did not call for — it described `base` as the
stock run image "re-tagged". A re-tag cannot work: discovery reads each image's `dev.kontra.runtime.*`
labels, and a tag copy carries the bytes it was given. Every runtime therefore has a Dockerfile, even
when it adds no layer. `base` and `python` add none today and share **both layers** with
`heroku/heroku:24` — measured, identical diff IDs — so the three cost one copy in the store between
them. What distinguishes them is the declaration, which is the seam: the day a Python actor needs
`libpq5` it goes in `python/`, and no Go actor gets it.

---

## `runtime.json`

```json
{
  "schemaVersion": "kontra.runtime.v1",
  "name": "python-browser",
  "major": 1,
  "description": "Python run image with Chromium and the fonts headless browsers need.",
  "builder": "heroku/builder:24",
  "languages": ["python"],
  "provides": ["chromium", "playwright-browsers"],
  "platforms": ["linux/amd64"]
}
```

| field | meaning |
|---|---|
| `name` | becomes a path component of `<prefix>/<name>`, so it is lowercase alphanumerics and single hyphens. `scripts/check.py` refuses anything else and refuses a name that does not match its directory. |
| `major` | the **contract** actors reference. `python-browser:1` is a promise about what is in the image, not about which build of it. |
| `description` | one line, shown on the console's Runtimes tab. |
| `builder` | must equal `builder.json`'s builder image. A runtime built for a different builder is refused here, which is the same refusal `kontra runtime build` makes one repository later — except here the mismatch is a typo rather than a failure on somebody's laptop. |
| `languages` | the actor engines this runtime is **declared** for, from `{go, python}`. It is what the default-runtime rule reads (`python:1` for Python, `base:1` for Go). `base` is the unmodified run image and the builder will happily compile any of its eight languages on it; the list records what kontra supports, not what is possible. |
| `provides` | capabilities beyond the stock run image, as names. Empty is a real answer. Published as a comma list in `dev.kontra.runtime.provides`, which the console renders as chips. |
| `platforms` | the architectures CI builds. **Not** in the original design, and it earns its place by being the thing that keeps the build matrix out of the workflow file. |

**There is no `version` field, deliberately.** The git tag is the release (`python-browser/1.0.0`);
`runtime.json` is the contract. Two spellings of one release is one of them being wrong, and
`scripts/labels.py` refuses a tag whose major disagrees with `runtime.json`.

### Labels are derived, not written

The `dev.kontra.runtime.*` labels are generated from `runtime.json` by `scripts/labels.py` and passed
as `--label` at build time. No Dockerfile here spells them out, because a `description` that drifts
from `runtime.json` is a description the Images page shows and nobody can find.

| label | from |
|---|---|
| `dev.kontra.runtime.name` | `name` |
| `dev.kontra.runtime.major` | the tag's major |
| `dev.kontra.runtime.description` | `description` |
| `dev.kontra.runtime.provides` | `provides`, comma-joined |
| `dev.kontra.runtime.version` | the tag's `<major>.<minor>.<patch>` |
| `dev.kontra.runtime.languages` | `languages`, comma-joined |
| `dev.kontra.runtime.builder` | `builder` |

Plus, where a runtime pins a third-party build, `dev.kontra.runtime.pins` — `python-browser` publishes
`playwright=1.58.0` there, because an actor that pins the wrong `playwright==` fails at `@actor.load`
with `Executable doesn't exist` and the version it needed is otherwise only in a Dockerfile.

**CI reads the seven labels back off the built image** (`labels.py … --verify` against
`docker image inspect`'s config blob), because deriving them correctly and *applying* them are two
different claims. They were not applied: `build … "$(labels.py …)"` exits 0 when `labels.py` refuses —
errexit does not fire inside an argument list — so every build step now assigns the arguments first and
expands them with `mapfile`, which also means no `eval` ever runs a `description` through a shell. A
value that could not survive the trip is refused by `scripts/check.py` before anything is built: a
newline would truncate the label list, and a comma inside a `provides` element would publish two
capabilities where the file declares one.

**Off a tag the version is `<major>.0.0`,** per runtime, from `runtime.json`'s own `major` — because
`labels.py` refuses a version whose major disagrees with `runtime.json`, and a single global `0.0.0`
was refused for every runtime on every branch and pull-request build. Nothing is pushed off a tag; the
labels exist so the build CI gates is the build a tag performs.

**Labels, not OCI annotations,** which is a departure from the original design's wording. The reason is
measured: zot's GraphQL `Labels` field answers `''` for an image carrying ten labels, and the reader
that works is the **config blob** at `/v2/<repo>/blobs/<configDigest>`. `docker build --label` writes
there; `--annotation` writes the manifest, where nothing on the Images page looks. One mechanism, and
it is the one that can be read.

### The CNB labels a run image must carry

Inherited from `heroku/heroku:24` and verified by `scripts/check.py` and by CI reading the built image:

| | value | consequence |
|---|---|---|
| `io.buildpacks.stack.id` | `heroku-24` | the builder refuses a run image from another stack |
| `io.buildpacks.base.distro.name` / `.version` | `ubuntu` / `24.04` | buildpack target matching at platform API ≥ 0.12 |
| config `User` | `heroku` (uid/gid 1000) | at platform API ≥ 0.12 the lifecycle reads this instead of `CNB_USER_ID`/`CNB_GROUP_ID`. **A Dockerfile that switches to `USER root` must switch back**, or every actor on that runtime runs as root and nothing in the build says so. check.py refuses it; CI also asserts `id -u` is 1000 on the built image. |
| `io.buildpacks.rebasable` | `"true"`, set here | see below |

**`io.buildpacks.rebasable` is a declaration, not a switch — measured.** `lifecycle` 0.21.22, which is
what `heroku/builder:24` ships, records no `rebasable` field in `io.buildpacks.lifecycle.metadata` and
rebases happily without the label at platform API 0.7, 0.12 and 0.13 alike. It is carried anyway
because it is the one place in the published image where the promise is written: *a patch release of
this runtime changes only OS layers, never the contract an already-built actor image depends on.* A
change that could break one — a new libc soname, a Chromium major Playwright will not drive — gets a
new **major**, because rebase does not rebuild the actor and cannot discover that it stopped working.

**What does constrain rebase today is the run image NAME recorded at build time.** Measured, on this
builder:

```
pack rebase <actor> --run-image <prefix>/python:1.0.1    # recorded :1  -> REFUSED
    ERROR: new base image '…/python:1.0.1' not found in existing run image metadata: {… "image": "…/python:1"}
           please provide -force to override
pack rebase <actor> --run-image <prefix>/python:1        # after :1 moved -> succeeds
    app layer digest unchanged, dependency layer digests unchanged, new actor digest
```

The recorded `image` is **literally the string passed to `--run-image`**, so pinning the run image by
digest at build time — which is what reproducibility argues for — makes the actor unrebasable by tag.
Measured directly:

```
pack build  … --run-image heroku/heroku@sha256:a2a63bd1…
    recorded: {"image": "heroku/heroku@sha256:a2a63bd1…", …}
pack rebase … --run-image heroku/heroku:24
    ERROR: new base image 'heroku/heroku:24' not found in existing run image metadata …
```

So the moving `:<major>` tag is what both the build and the rebase must name, and a digest reference is
not interchangeable with it. **Something has to give between "pin the digest at build time" and "rebase
by moving tag": they cannot both hold without `-force`,** which skips the validation rather than
satisfying it. The two honest options are to build against the `:<major>` tag and record the resolved
digest in the catalog for provenance only, or to rebase with `-force` and accept that the lifecycle no
longer checks that the new base belongs under this actor. That choice belongs to the step that owns
`kontra deploy` and `kontra rebase`; this repository publishes both tag forms either way.

CI gates the working path per runtime: it moves `:<major>`, rebases the fixture, and asserts the app and
dependency layer digests did not change while the actor digest did.

---

## Publishing

Two tags per release, as the design requires:

- `<prefix>/<name>:<major>` — **moves.** This is what an `actor.json` references and what a rebase
  follows.
- `<prefix>/<name>:<major>.<minor>.<patch>` — **immutable.** This is what a rebase moves away from, and
  what retention keeps three of per repository.

`<prefix>` is `ghcr.io/<owner>/kontra-runtimes`, derived from `github.repository` so a fork publishes
to its own namespace with no edit.

**Release by git tag:**

```sh
git tag python-browser/1.0.0
git push origin python-browser/1.0.0
```

The workflow then, for that one runtime:

1. `scripts/check.py` and `tests/` — before any build, because every failure they catch would otherwise
   arrive four minutes later with a worse message, or not at all.
2. Installs `pack` and verifies the tarball's sha256 against `builder.json`; pulls the builder **by
   digest** and re-points the `heroku/builder:24` tag at it, so `--builder heroku/builder:24` resolves
   to reviewed bytes while still matching the string every `runtime.json` declares.
3. Builds the runtime for `linux/amd64` and asserts the image's `User` is `heroku` and `id -u` is 1000.
4. **Reads the seven `dev.kontra.runtime.*` labels back off the built image.** Discovery reads nothing
   else, so a runtime missing one is a runtime the console cannot show.
5. **`pack build`s the runtime's `test/` fixture actor on it, with `--trust-builder=false`** — the same
   untrusted mode `kontra deploy` uses, because untrusted mode runs the lifecycle phases in separate
   containers and a gate that built trusted would prove a build nobody performs.
6. **Runs the fixture's `worker` process.** It must exit 0.
7. Moves `:<major>`, rebases the fixture, and asserts the layer/digest properties above.
8. Only then: `buildx build --push` for every declared platform, with the derived labels and both tags.
9. `cosign sign` the pushed **digest** (never the tag — a tag can move between the push and the sign),
   then `cosign verify` in the same run, because a signature nobody has verified is a file.

A push to `dev` or `main`, or a pull request, runs steps 1–7 for **every** runtime and pushes nothing.

**No QEMU, and `check.py` keeps that honest.** Every runtime declaring a second architecture has no
`RUN` instruction, so buildx assembles it from manifests it never executes. check.py refuses the
combination that would need emulation (`RUN` + a non-amd64 platform), so the absence is an asserted
property rather than an assumption. `python-browser` is `linux/amd64` only for that reason; actor
images target `linux/amd64` in v1 regardless.

---

## Adding a runtime

1. `mkdir runtimes/<name>` with a `runtime.json` and a `Dockerfile` that `FROM`s `builder.json`'s
   `runImage.from` digest. Add packages under `USER root` and end on `USER heroku`.
2. Add `test/` — a fixture actor whose `worker:` process exercises what the runtime `provides` and
   exits 0. See the two existing ones; they are short.
3. `python3 scripts/check.py && python3 -m unittest discover -s tests` and then, locally:

```sh
./scripts/build.sh runtimes/<name> 1.0.0          # builds kontra-runtimes/<name>:1 and :1.0.0
pack build fixture/<name>:gate \
  --builder heroku/builder:24 \
  --run-image kontra-runtimes/<name>:1 \
  --path runtimes/<name>/test \
  --trust-builder=false --pull-policy if-not-present
docker run --rm --entrypoint worker fixture/<name>:gate
```

4. Open a PR. CI runs the same thing. Tag `<name>/1.0.0` to publish.

**`docker run --entrypoint worker <image>`, not `docker run <image> worker`.** The CNB launcher execs a
trailing argument as a command, so the second spelling fails with `worker: command not found` and reads
as a broken fixture. The process type is selected by the entrypoint.

### What a fixture actor must contain

Python (**four** build-relevant files, not three):

```
actor.py            the worker process
actor.json          declares runtime: "<name>:<major>"
pyproject.toml      dependencies
uv.lock             `uv lock`
Procfile            worker: python actor.py
.python-version     REQUIRED
```

`.python-version` is not optional and the failure is not obvious: the Heroku Python buildpack refuses a
uv-based build without it — *"When using the package manager uv on Heroku, you must specify your app's
Python version with a `.python-version` file"* — and the build fails with status 51 **after** the
upload. `scripts/check.py` requires it in every Python fixture for that reason.

Go: `main.go`, `actor.json`, `go.mod` with **no `replace` pointing outside the directory**, and a
`Procfile` whose `worker:` names the binary. The Go buildpack derives the binary name from the module
path's last element and puts it at `/layers/heroku_go/go_target/bin/<name>`, which is on the launch
`PATH` — so `/workspace` holds the sources and the binary lives elsewhere. A Go actor that
self-locates `actor.json` "next to the binary" has to know that; `runtimes/base/test` states both paths
in its output so the difference shows up in a CI log rather than in somebody's afternoon.

---

## Forking, and custom runtimes

Fork this repository, change or add a runtime, publish to your own registry, and point kontra at it:

```sh
KONTRA_RUNTIMES_PREFIX=registry.example.com/team/runtimes
```

Default is the install's own zot under `kontra-runtimes/`, which the install mirrors from the published
images by digest. Nothing in kontra needs to know your runtime's name: it reads the registry.

Keep `builder.json` in step with the install's pinned builder. A runtime built for a different builder
is refused — in `scripts/check.py` here, and by `kontra runtime build` there.

---

## Signed, and not yet checked

The publish workflow signs every pushed digest with keyless cosign and verifies it in the same run.
**Nothing verifies it at pull.** This is net-new ground, and the gap is worth stating precisely because
a signature that nobody checks is not a security control:

- Before this, kontra signed only its **own control-plane images and release blobs**, in CI, with
  GitHub OIDC. No actor image and no runtime image was signed anywhere, and `kontra deploy`,
  `kontra build --push` and `kontra bundle` have no signing path at all.
- The Warden's trust policy is implemented, and in all four shipped configurations
  `KONTRA_TRUST_UNSIGNED` equals `KONTRA_TRUST_REGISTRIES` — so the policy returns the digest
  immediately and `Verify` is never called. Turning verification on is a configuration change in
  kontra, not a change here.

The signature is produced anyway: a store that has signatures and a consumer that starts checking is a
switch to flip, and a store without them is a republication of everything.

The identity to verify against is printed to each run's job summary, and is
`https://github.com/<owner>/kontra-runtimes/.github/workflows/publish.yml@<ref>` with issuer
`https://token.actions.githubusercontent.com`. Note that the ref is **in** the identity, so an exact
`KONTRA_TRUST_IDENTITY` pins one tag.

---

## Things that are not true yet, and whose they are

This repository is finished; several things it hands off are not. Each is listed so nobody reads a gap
as a bug here.

**`kontra runtime build|test|import` are not implemented, and `build` cannot be specified as the design
describes it.** The design has them driving the **rootless** podman socket. There is no rootless podman
socket on the controller and root cannot have one: `/run/user/0/podman/` does not exist,
`/run/podman/podman.sock` is a rootful socket owned by `root:root`, `systemctl --user is-active
podman.socket` is `inactive`, and `/etc/subuid` has no entry for root, so rootless podman as root has
no subuid range to map. A non-root build user has to be created first. The commands live in kontra, not
here; `scripts/build.sh` is the local-iteration path in the meantime and uses whatever container
runtime is already on the box.

**The CLI has no registry credentials.** Every push and pull it makes is anonymous —
`ImagePush`/`ImagePull` send `RegistryAuth: base64("{}")` and the oras client sets only `PlainHTTP` —
so a `push-runtimes` credential has nowhere to go until that plumbing exists. The install's zot is
configured anonymous for exactly this reason, with delete refused even anonymously.

**Fixture actors carry no `kontra-sdk`, and cannot.** The distribution is published to no index
(`https://pypi.org/pypi/kontra-sdk/json` → 404) and the Go SDK is in a private repository, so neither
a `uv.lock` nor a `go.mod` here can resolve it. The fixtures are therefore plain programs that check
**run image** properties — uid, `/workspace`, a C-extension wheel, a browser that launches — and the
gate is "the `worker` process exits 0", not "a Method ran". A Method needs a Temporal task queue and a
control plane, which this repository does not have and should not stand up. When the SDK is published,
a fixture can become a real `@actor.defn` and the gate can dispatch one Method; nothing else changes.

**No runtime carries `/kontra/handler`.** Buildpack-built images do not contain it, and until the
in-process backing workflow lands, a worker image needs the handler and the two-process entrypoint that
`kontra-worker-base` supplies. The design offers a stopgap — every runtime copies them in from a pinned
`kontra-handler` image — and this repository does **not** take it, deliberately:

- there is no published `kontra-handler` image (the handler is built inside
  `control/images/Dockerfile.workerbase` and never published on its own), so the step cannot be
  written;
- it would make a public runtimes repository depend on a private registry at build time, which is the
  coupling splitting the repositories exists to remove;
- and it would bake a handler version into an OS image, so a handler fix would become a runtime patch
  release for every runtime.

The choice between the stopgap and waiting therefore belongs to the step that switches `kontra deploy`
to buildpacks, where both halves are visible. If the stopgap is taken, it belongs in a thin
`kontra-worker` layer built in kontra **from** these runtimes, not in these runtimes.

**`python-browser` is 1.42 GiB.** The base is 464 MiB; `playwright install --with-deps chromium`
installs Chromium, the headless shell, ffmpeg, and the fonts and X libraries Playwright's own
dependency list names. Trimming that list by hand is the failure this runtime exists to avoid — the
names in the actors' existing `deploy.sh` scripts are Ubuntu 22.04 spellings, and on this base image
`apt-get install libasound2` answers *"Package 'libasound2' has no installation candidate … provided by
libasound2t64"*. The size is paid once per install and shared by every actor on the runtime, which is
the point.

---

## When this becomes a conformance rule

Two mappings in this repository currently have **one** implementation each, and both are about to have
two:

- **`runtime.json` → `dev.kontra.runtime.*` labels** (`scripts/labels.py`, tested in
  `tests/test_labels.py`). `kontra runtime build` must produce byte-identical labels from the same file,
  or an operator's own runtime is discovered differently from a published one. The constraints on the
  values travel with the mapping: a label value carries no newline, and a comma-list element carries no
  comma.
- **`<prefix>/<name>:<major>` resolution** — the reference an `actor.json` writes, what it resolves
  against, and what a rebase may name.

The moment kontra gains a reader for either, the rule belongs in kontra's `shared/conformance/` corpus
**first**, with this repository as one of the implementations — the corpus exists precisely to stop a
second implementation from disagreeing silently.
