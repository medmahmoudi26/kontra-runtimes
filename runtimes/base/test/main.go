// The `base:1` fixture: what a published run image has to be true of for a Go actor.
//
// NOT A kontra ACTOR, AND NOT BY CHOICE. §4.3 wants `require github.com/medmahmoudi26/kontra/sdk/go`
// with no `replace` — but that module is in a private repository, so `go mod download` from this
// repository's CI has nothing to fetch and no credential to fetch it with. A fixture that needed one
// would make the runtime gate depend on the kontra repo being reachable, which is the coupling the
// split into two repositories exists to remove.
//
// WHAT IT CHECKS is the run image, not this program:
//
//	uid 1000, not root   the run image's `User` survived export (platform API >= 0.12 reads it)
//	/workspace           §4.4's path replaced /actor/<name>/, and the launcher put us there
//	a dynamic binary runs the Go buildpack links against this run image's libc, and finds it
//
// It also demonstrates §4.3's standalone rule by being standalone: `go.mod` has no `require` and no
// `replace`, so `go build` in this directory works with nothing else from either repository.
package main

import (
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	failed := 0
	check := func(name string, ok bool, saw any) {
		mark := "ok  "
		if !ok {
			mark = "FAIL"
			failed++
		}
		fmt.Printf("%s %s: %v\n", mark, name, saw)
	}

	// The run image's user, read back from the process rather than from the image config, because the
	// exporter is what carries it across and the exporter is the thing being tested.
	check("uid is 1000 (not root)", os.Getuid() == 1000, fmt.Sprintf("uid=%d gid=%d", os.Getuid(), os.Getgid()))

	cwd, err := os.Getwd()
	check("cwd is /workspace", err == nil && cwd == "/workspace", cwd)

	// §4.4 keeps the Go SDK's `resolveIdentity` behaviour: an actor self-locates `actor.json` next to
	// its binary. Under buildpacks the binary is in a launch layer and the sources are at /workspace,
	// so "next to the binary" and "next to actor.json" stop being the same directory — which is the
	// thing a Go actor author has to know before they port. The fixture states both paths so the
	// difference is in the CI log rather than in somebody's afternoon.
	exe, err := os.Executable()
	check("binary is outside /workspace (a launch layer)", err == nil && filepath.Dir(exe) != "/workspace", exe)

	if _, err := os.Stat(filepath.Join(cwd, "actor.json")); err != nil {
		check("actor.json is at /workspace", false, err)
	} else {
		check("actor.json is at /workspace", true, filepath.Join(cwd, "actor.json"))
	}

	if failed > 0 {
		fmt.Fprintf(os.Stderr, "\nbase:1 fixture FAILED: %d check(s)\n", failed)
		os.Exit(1)
	}
	fmt.Println("\nbase:1 fixture ok")
}
