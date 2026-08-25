"""
tools/build_agents_md.py — v3.20.48 thin shim.

The canonical implementation now lives at `sadp._tools.build_agents_md`.
This shim preserves the dev-tree invocation surface
(`python tools/build_agents_md.py ...`) by delegating to the bundled
implementation in the SADP package.

For programmatic use, import from `sadp._tools.build_agents_md` directly.
"""

import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `from sadp._tools import ...`
# works regardless of how tools/build_agents_md.py was invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sadp._tools.build_agents_md as _impl  # noqa: E402
from sadp._tools.build_agents_md import main  # noqa: E402

# Re-export full module namespace (including underscore-prefixed
# private helpers that test files import) by copying module dict.
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})


if __name__ == "__main__":
    raise SystemExit(main())
