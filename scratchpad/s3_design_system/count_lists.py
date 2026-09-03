"""Counts every published list in the design system and compares each pair by name."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.gui import design_system as qt
from src.gui.main_tabs import design_system_surface as dss

print("TOKEN_NAMES        :", len(dss.TOKEN_NAMES))
print("TOKENS             :", len(dss.TOKENS))
print("COLOR_NAMES        :", len(dss.COLOR_NAMES))
print("ALIAS_NAMES        :", len(dss.ALIAS_NAMES))
print("SHADOW_NAMES       :", len(dss.SHADOW_NAMES))
print("FONT_FAMILY_NAMES  :", len(dss.FONT_FAMILY_NAMES))
print("LINE_HEIGHT_NAMES  :", len(dss.LINE_HEIGHT_NAMES))

whole = [
    n
    for n in dss.TOKEN_NAMES
    if isinstance(dss.TOKENS[n], int) and not isinstance(dss.TOKENS[n], bool)
]
floats = [n for n in dss.TOKEN_NAMES if isinstance(dss.TOKENS[n], float)]
tuples = [n for n in dss.TOKEN_NAMES if isinstance(dss.TOKENS[n], tuple)]
strings = [n for n in dss.TOKEN_NAMES if isinstance(dss.TOKENS[n], str)]
colourish = [n for n in strings if dss.TOKENS[n].startswith(("#", "rgba"))]
print()
print("whole numbers      :", len(whole))
print("floats             :", len(floats))
print("tuples             :", len(tuples))
print("strings            :", len(strings))
print("colour strings     :", len(colourish))
print(
    "DOCSTRING CLAIM    : 195 names = 145 colours + 2 fonts + 40 whole"
    " numbers + 3 line heights + 5 shadows"
)
print("SUM OF CLAIM       :", 145 + 2 + 40 + 3 + 5)

print()
print("-- duplicates inside each published list --")
for label, names in [
    ("TOKEN_NAMES", dss.TOKEN_NAMES),
    ("COLOR_NAMES", dss.COLOR_NAMES),
    ("ALIAS_NAMES", dss.ALIAS_NAMES),
]:
    seen: dict = {}
    for n in names:
        seen[n] = seen.get(n, 0) + 1
    dupes = sorted(k for k, v in seen.items() if v > 1)
    print(f"  {label}: {len(dupes)} duplicated -> {dupes}")

print()
print("-- a name in TOKEN_NAMES that reaches no group --")
grouped: set = set()
for members in dss.GROUP_MEMBERS.values():
    grouped.update(members)
print("  ", sorted(set(dss.TOKEN_NAMES) - grouped))
print("-- a name in a group that is not in TOKEN_NAMES --")
print("  ", sorted(grouped - set(dss.TOKEN_NAMES)))

print()
print("-- the surface against the Qt module it replaces --")
qt_names = set(getattr(qt, "TOKEN_NAMES", ()))
print("  Qt TOKEN_NAMES     :", len(qt_names))
print("  surface TOKEN_NAMES:", len(set(dss.TOKEN_NAMES)))
only_qt = sorted(qt_names - set(dss.TOKEN_NAMES))
only_surface = sorted(set(dss.TOKEN_NAMES) - qt_names)
print("  only in Qt         :", len(only_qt), only_qt[:12])
print("  only in the surface:", len(only_surface), only_surface[:12])

differing = []
for name in sorted(qt_names & set(dss.TOKEN_NAMES)):
    left = getattr(qt, name, None)
    right = dss.TOKENS[name]
    if left != right:
        differing.append((name, left, right))
print("  values differing   :", len(differing))
for name, left, right in differing:
    print(f"    {name}: Qt {left!r} against surface {right!r}")

print()
print("-- alias against its target --")
for alias, target in dss.ALIAS_TARGETS.items():
    same = dss.TOKENS[alias] == dss.TOKENS.get(target)
    mark = "ok" if same else "DIFFERS"
    print(
        f"  {alias:18s} -> {target:20s} {mark}"
        f"  {dss.TOKENS[alias]!r} / {dss.TOKENS.get(target)!r}"
    )

print()
print("-- a value carried by more than one non-alias name --")
carriers: dict = {}
for name in dss.TOKEN_NAMES:
    if name in dss.ALIAS_TARGETS:
        continue
    value = dss.TOKENS[name]
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        continue
    carriers.setdefault(str(value), []).append(name)
shared = {v: n for v, n in carriers.items() if len(n) > 1}
print("  values carried by more than one name:", len(shared))
for value, names in sorted(shared.items())[:40]:
    print(f"    {value!r:14s} <- {names}")
