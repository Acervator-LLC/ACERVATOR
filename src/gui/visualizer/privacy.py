"""Privacy-mask helpers for the visualizer widget modules.

Mirrors the shim in ``bot_visualizer``: the registry import is optional
and the fallback masks nothing.
"""

from __future__ import annotations

__all__ = ["_get_privacy_mask_registry", "_mask_or"]

# The registry is a process singleton shared with the Trading tab.
try:
    from ...core.privacy_mask_registry import (
        get_privacy_mask_registry as _get_privacy_mask_registry,
        mask_or as _mask_or,
    )
except Exception:  # R28-OK: defensive — the widget modules must import even
    # if the registry module fails to load; render falls back to plain
    # strings (no masking) and the GUI continues to function.
    _get_privacy_mask_registry = None  # type: ignore[assignment]

    def _mask_or(value, field_id: str, mask: str = "****") -> str:
        # Signature parity with the real mask_or is load-bearing:
        # callers pass mask= by keyword. This fallback masks nothing,
        # so it discards both masking parameters rather than reading
        # them.
        del field_id, mask
        return str(value)
