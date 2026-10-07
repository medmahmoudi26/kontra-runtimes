#!/usr/bin/env bash
# Build one runtime into the local docker store, labelled exactly as CI labels it.
#
#     scripts/build.sh runtimes/python-browser 1.0.0 [tag-prefix]
#
# THE SAME LABEL DERIVATION AS THE PUBLISH WORKFLOW, from the same file, so a runtime that works
# locally and fails in CI differs in something other than its declaration.
#
# ASSIGNED FIRST, AND NEVER `eval`ed. `build … "$(labels.py …)"` exits 0 when labels.py refuses —
# errexit does not fire inside an argument list — and builds an image with no `dev.kontra.*` label at
# all. The assignment is where it fires; `mapfile` then turns one argument per line into an array, so
# a `description` carrying a quote, a `$` or a backtick is data and not shell.
#
# NO `--push` HERE, ON PURPOSE. Pushing is the publish workflow's job: it signs, and an unsigned image
# in the runtimes repository is indistinguishable from a signed one at the tag. See the README on
# what `kontra runtime build` does instead for an operator's own fork.
set -euo pipefail

dir=${1:?usage: scripts/build.sh <runtime-dir> <major.minor.patch> [tag-prefix]}
version=${2:?usage: scripts/build.sh <runtime-dir> <major.minor.patch> [tag-prefix]}
prefix=${3:-kontra-runtimes}

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

name=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["name"])' "$dir/runtime.json")
major=${version%%.*}
labels=$(python3 scripts/labels.py "$dir" "$version" --args)
mapfile -t label_args <<<"$labels"

set -x
docker build \
  -t "$prefix/$name:$major" \
  -t "$prefix/$name:$version" \
  "${label_args[@]}" \
  -f "$dir/Dockerfile" \
  "$dir"
