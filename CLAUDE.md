# kontra-runtimes

## Branches

**Work on `dev`. Never commit to `main`.**

`dev` is the default branch and the base for every pull request. `main` is what has been released —
it moves only by merging `dev`, and only deliberately.

Same two branches, same rule, in all six repositories: `kontra`, `kontra-actors`,
`kontra-workflows`, `kontra-console`, `kontra-cloud`, `kontra-runtimes`.

**This repository is PUBLIC**, as are `kontra` and `kontra-console`; `kontra-actors`,
`kontra-workflows` and `kontra-cloud` are private. It is public because the documented way to add a
runtime is to fork this repository, and nobody can fork what they cannot read.

**The repository name is load-bearing.** `publish.yml` builds
`ghcr.io/${{ github.repository }}/<runtime>`, so `kontra-runtimes` IS the image namespace that
kontra's runtime discovery lists, that `KONTRA_RUNTIMES_PREFIX` defaults to, and that zot's
retention policies key on. Renaming this repository re-points every one of those at nothing.

## Releasing

A tag publishes exactly one runtime, and nothing publishes without a tag:

```sh
git tag python-browser/1.0.0 && git push origin python-browser/1.0.0
```

`scripts/plan.py` derives the job matrix from the directory listing, so adding a runtime is adding a
directory — there is no list here to edit, and no list in kontra either.

## Verification

**A runtime that builds is not a runtime that works.** The gate is a real actor, built on the
candidate image by the pinned builder, run, then `pack rebase`d onto a rebuilt image and run again.
Each runtime carries its own fixture actor under `runtimes/*/test` for exactly that. A Dockerfile
that builds and exports actors nobody can run is the failure mode this repository exists to prevent,
and it is invisible to anything that only inspects the image.

`python3 scripts/check.py` and `python3 -m unittest discover -s tests` run with nothing installed and
catch the tree-consistency failures the build would otherwise reach four minutes later: a missing
`.python-version`, a drifted base digest, a pin that agrees with nothing.
