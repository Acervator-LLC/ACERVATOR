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
except Exception:
    _get_privacy_mask_registry = None  # type: ignore[assignment]

    def _mask_or(value, field_id: str, mask: str = "****") -> str:
        # Callers pass ``mask=`` by keyword, so the signature must match.
        del field_id, mask
        return str(value)
