"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ THE RELEASE NUMBER IS DECLARED IN src/_version.py.          │
# │ The build count and the commit after the + come from git.   │
# │ Do not restate the version here or anywhere else — see      │
# │ src/_version.py.                                            │
# │                                                             │
# │ Acervator is an accumulation trading platform.              │
# │ NOT a grid bot. NOT a DCA bot. NOT portfolio rebalancing.   │
# │ See AI_DEVELOPER_GUIDE.md for full architecture.            │
# └─────────────────────────────────────────────────────────────┘
"""

from ._version import resolve_version

__version__ = resolve_version()
__app_name__ = "Acervator"
