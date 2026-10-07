"""The `python-browser:1` fixture: start the browser the runtime claims to provide, and read a page.

See `runtimes/python/test/actor.py` for why this is not an `@actor.defn` and why the `worker:` process
exits instead of serving.

WHY IT DRIVES A REAL BROWSER AND NOT `--version`. `provides: ["chromium"]` is a claim that an actor
can open a page, and every way this runtime has broken in the past is invisible to a version string:
a missing `libnss3` kills the renderer at launch, a missing font makes text render as boxes, a browser
bundle Playwright was not shipped against is refused by the client, and a bundle under root's HOME is
simply not found by uid 1000. Launching and reading `document.title` back exercises all four.

NO NETWORK. The page is a `data:` URL, so the gate cannot fail because a site was slow — the failure
mode that makes a CI gate get disabled. A runtime test that depends on somebody else's uptime is a
runtime test nobody trusts.
"""

from __future__ import annotations

import os
import sys

#: The one thing this fixture and the runtime must agree about. Playwright refuses a browser build it
#: was not shipped against, so the pin here is the same number as the Dockerfile's
#: `ARG PLAYWRIGHT_VERSION` — and `scripts/check.py` asserts that rather than trusting this comment.
EXPECTED_PLAYWRIGHT = "1.58.0"

#: A page with nothing in it but a title and a styled word, so a renderer that started but cannot
#: paint still fails: `document.title` comes from the parser, `offsetWidth` comes from layout.
PAGE = (
    "data:text/html,"
    "<!doctype html><title>kontra-runtime-probe</title>"
    "<body><span id=w style='font-family:sans-serif;font-size:40px'>kontra</span>"
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, ok: bool, saw: object) -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {saw}")
        if not ok:
            failures.append(name)

    check("uid is 1000 (not root)", os.getuid() == 1000, f"uid={os.getuid()} gid={os.getgid()}")

    # THE RUN IMAGE'S `ENV` HAD TO SURVIVE EXPORT. The exporter builds the app image's config from the
    # run image's, then the launcher adds layer env on top. If that ordering ever changed, Playwright
    # would look in $HOME/.cache, find nothing, and the actor would fail at load on a Machine.
    browsers = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    check("PLAYWRIGHT_BROWSERS_PATH is /opt/ms-playwright", browsers == "/opt/ms-playwright", browsers or "(unset)")

    import importlib.metadata as md

    installed = md.version("playwright")
    check(
        f"playwright pin matches the runtime ({EXPECTED_PLAYWRIGHT})",
        installed == EXPECTED_PLAYWRIGHT,
        installed,
    )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # `--no-sandbox`: the actor's container is the sandbox. Chromium's own sandbox needs user
        # namespaces the Warden's container does not grant, and a fixture that passed here only
        # because CI runs privileged would be measuring the wrong box.
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            check("chromium launched", True, browser.version)
            page = browser.new_page()
            page.goto(PAGE, wait_until="load")
            check("title parsed", page.title() == "kontra-runtime-probe", repr(page.title()))
            width = page.eval_on_selector("#w", "el => el.offsetWidth")
            # A renderer with no font at all lays text out at zero width. Any real glyph set puts a
            # 40px six-character word well past 50px, so this is a font check without pinning a
            # number to one font's metrics.
            check("text laid out (a font is present)", isinstance(width, (int, float)) and width > 50, width)
        finally:
            browser.close()

    if failures:
        print(f"\npython-browser:1 fixture FAILED: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("\npython-browser:1 fixture ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
