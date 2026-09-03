"""Compares the surface token table against the Qt module, pairing by name."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.gui import design_system as qt
from src.gui.main_tabs import design_system_surface as dss

published = list(qt.__all__)
surface = list(dss.TOKEN_NAMES)
print("Qt __all__ length      :", len(published))
print("surface TOKEN_NAMES len:", len(surface))

undefined = [n for n in published if not hasattr(qt, n)]
print("\nnamed in Qt __all__ but not defined in the Qt module:", len(undefined))
for name in undefined:
    print("   ", name)

defined_public = sorted(
    n
    for n in vars(qt)
    if n.isupper() and not n.startswith("_") and n not in set(published)
)
print("\ndefined in the Qt module but absent from __all__:", len(defined_public))
for name in defined_public:
    print("   ", name, "=", repr(getattr(qt, name))[:60])

only_qt = [n for n in published if n not in set(surface)]
only_surface = [n for n in surface if n not in set(published)]
print("\nin Qt __all__ only  :", len(only_qt), only_qt)
print("in the surface only :", len(only_surface), only_surface)

differing = []
for name in published:
    if name in set(surface) and hasattr(qt, name):
        left = getattr(qt, name)
        right = dss.TOKENS[name]
        if left != right:
            differing.append((name, left, right))
print("\nvalues differing between the pair:", len(differing))
for name, left, right in differing:
    print(f"   {name}: Qt {left!r} against surface {right!r}")
