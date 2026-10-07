// NO `require` AND NO `replace`, which is §4.3's standalone rule demonstrated rather than described:
// `go build` in this directory works with nothing else from either repository, so the build context
// `pack` uploads is this directory and the Go module cache is reusable across builds.
module github.com/medmahmoudi26/kontra-runtimes/fixtures/base

go 1.24
