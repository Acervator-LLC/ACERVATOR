"""Pre-start wallet sufficiency check, in the units each bot mode uses.

``check_start_balance`` reads the pool balance for the bot's base asset and
compares it in USD wherever a price is available. An Extractor is sized by
``extractor_chunk_size_usd``, so ``target_balance`` is not its threshold.
"""

from __future__ import annotations

from typing import Optional, Tuple

# USD-like assets — for these, wallet balance is already in USD and
# no price oracle is needed.
_USD_LIKE = frozenset({"USD", "USDC", "USDT", "DAI", "BUSD", "PYUSD", "FDUSD"})


def check_start_balance(
    *,
    is_extractor: bool,
    exchange_label: str,
    base: str,
    base_free: float,
    target: str = "",
    target_free: float = 0.0,
    chunk_size_usd: float = 0.0,
    target_balance: float = 0.0,
    base_usd_price: Optional[float] = None,
) -> Tuple[bool, Optional[str], str]:
    """Mode-aware pre-start wallet sufficiency check.

    Returns ``(sufficient, error_msg, bal_summary)``.

    ``sufficient`` is True if the wallet has enough to start the bot.
    ``error_msg`` is None on success, otherwise an operator-facing
    error message that uses the *correct* concept and value for the
    bot's mode. ``bal_summary`` is the formatted balance summary
    used for logging (and embedded in error_msg).

    For Extractor mode:
      • The check compares the *USD value* of base balance against
        ``chunk_size_usd``. If ``base`` is in ``_USD_LIKE``,
        ``base_free`` is treated as USD directly. Otherwise
        ``base_usd_price`` must be supplied to convert; without it,
        the check only blocks on a literally-zero balance (because
        we'd rather start the bot and let it report its own sizing
        error than block on an unknown price).
      • The error message references "Extractor chunk size" and
        the configured ``chunk_size_usd`` value — NEVER
        ``target_balance``.

    For Scrumming mode:
      • Needs base_free ≥ 1.0 OR target_free > 0
        (the latter lets the bot start with
        existing positions even if the spend wallet is depleted).
      • The error message references "target balance" and
        ``target_balance``.
    """
    if is_extractor:
        sym_tag = f"*/{base}"
        # Convert base balance to USD value for threshold check
        if base.upper() in _USD_LIKE:
            base_free_usd: Optional[float] = base_free
        elif base_usd_price is not None and base_usd_price > 0:
            base_free_usd = base_free * base_usd_price
        else:
            # `None` skips the USD comparison below; any base balance
            # is enough to start.
            base_free_usd = None

        if base_free_usd is None:
            bal_summary = (
                f"[EXTRACTOR {sym_tag}] " f"{base}: {base_free:.6f} free (pool)"
            )
        else:
            bal_summary = (
                f"[EXTRACTOR {sym_tag}] "
                f"{base}: {base_free:.6f} free (pool, "
                f"~${base_free_usd:.2f})"
            )

        # Sufficiency: USD value ≥ chunk size when we can compute USD,
        # else fall back to any non-zero base balance.
        if base_free_usd is None:
            sufficient = base_free > 0.0
        else:
            sufficient = base_free_usd >= chunk_size_usd

        if sufficient:
            return True, None, bal_summary

        msg = (
            f"Insufficient pool balance on {exchange_label}: "
            f"{bal_summary}. Extractor needs ${chunk_size_usd:.2f} "
            f"worth of {base} in the pool to fund chunks. "
            f"Deposit {base} or reduce the Extractor chunk size "
            f"(currently ${chunk_size_usd:.2f})."
        )
        return False, msg, bal_summary

    # ── Scrumming branch ──────────────────────────────────────────
    sym_tag = f"{target}/{base}" if target else base
    bal_summary = f"[SCRUMMING {sym_tag}] " f"{base}: {base_free:.4f} free (spend)"
    if target_free > 0:
        bal_summary += f", {target}: {target_free:.6f} free (target)"

    sufficient = (base_free >= 1.0) or (target_free > 0)
    if sufficient:
        return True, None, bal_summary

    msg = (
        f"Insufficient balance on {exchange_label}: {bal_summary}. "
        f"Bot requires {base} to place orders. Deposit funds or "
        f"reduce target balance (currently ${target_balance:.2f})."
    )
    return False, msg, bal_summary
