"""tools/orphan_widget_scan.py — v3.24.0 thin shim.

Canonical implementation: sadp._tools.orphan_widget_scan.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sadp._tools.orphan_widget_scan as _impl  # noqa: E402
from sadp._tools.orphan_widget_scan import main  # noqa: E402

globals().update({k: v for k, v in vars(_impl).items()
                  if not k.startswith("__")})


if __name__ == "__main__":
    raise SystemExit(main())
