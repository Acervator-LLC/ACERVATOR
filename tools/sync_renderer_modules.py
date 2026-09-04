"""Write ``MANIFEST`` from the modules on disk.

``modules_on_disk`` lists every ``.js`` under ``WEB_DIR``, and
``modules_named_by_page`` lists the ones ``INDEX_HTML`` already loads; the
manifest carries the difference. ``tests/test_desktop_shell_assets.py`` fails
and names the module when the two disagree.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "src" / "gui" / "web"
RENDERER_DIR = REPO_ROOT / "desktop" / "renderer"
INDEX_HTML = RENDERER_DIR / "index.html"
MANIFEST = RENDERER_DIR / "module_manifest.js"

HEADER = (
    "// Written by tools/sync_renderer_modules.py; one file a line so a"
    " merge keeps both sides.\n"
    "\n"
    '"use strict";\n'
    "\n"
    "window.ACERVATOR_MODULES = [\n"
)
FOOTER = "];\n"


def modules_on_disk() -> list[str]:
    """Every JavaScript module the renderer may load, by file name."""
    return sorted(path.name for path in WEB_DIR.glob("*.js"))


def modules_named_by_page() -> list[str]:
    """The ``src/gui/web`` modules ``index.html`` names, in document order."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    named = []
    for ref in re.findall(r'src="([^"]+)"', html):
        if not ref.endswith(".js") or "/vendor/" in ref:
            continue
        if (INDEX_HTML.parent / ref).resolve().parent == WEB_DIR:
            named.append(Path(ref).name)
    return named


def manifest_entries(text: str) -> list[str]:
    """The file names a rendered manifest declares, in declared order."""
    body = re.search(r"ACERVATOR_MODULES\s*=\s*\[(.*?)\]", text, re.S)
    return re.findall(r'"([^"]+)"', body.group(1)) if body else []


def wanted_entries() -> list[str]:
    """Page-named modules first, then the rest in manifest order, then new."""
    on_disk = modules_on_disk()
    ordered = [name for name in modules_named_by_page() if name in on_disk]
    previous = (
        manifest_entries(MANIFEST.read_text(encoding="utf-8"))
        if MANIFEST.is_file()
        else []
    )
    for name in previous:
        if name in on_disk and name not in ordered:
            ordered.append(name)
    for name in on_disk:
        if name not in ordered:
            ordered.append(name)
    return ordered


def render(entries: list[str]) -> str:
    return HEADER + "".join('  "' + name + '",\n' for name in entries) + FOOTER


def main() -> int:
    text = render(wanted_entries())
    if MANIFEST.is_file() and MANIFEST.read_text(encoding="utf-8") == text:
        return 0
    MANIFEST.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
