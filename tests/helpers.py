"""Shared setup for the script tests. Stdlib only, so `python3 -m unittest discover -s tests` works.

`scripts/` is on the path because CI runs these scripts as scripts, where their own directory is
sys.path[0]; a test importing them has to put it there itself.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

#: A runtime.json that check.py and labels.py both accept, as the base for one-field variations.
GOOD_RUNTIME = {
    "schemaVersion": "kontra.runtime.v1",
    "name": "fixture",
    "major": 1,
    "description": "A fixture runtime.",
    "builder": "heroku/builder:24",
    "languages": ["python"],
    "provides": ["chromium"],
    "platforms": ["linux/amd64"],
}


def write_runtime(root: Path, name: str, **overrides) -> Path:
    """Write `<root>/runtimes/<name>/runtime.json`, defaulting every field to a legal value."""
    runtime = {**GOOD_RUNTIME, "name": name, **overrides}
    d = root / "runtimes" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "runtime.json").write_text(json.dumps(runtime))
    return d
