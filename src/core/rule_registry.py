"""
rule_registry.py — SADP Administrative Control Layer
=====================================================
Provides the backend for the RULE command syntax that allows
administrative lock, unlock, suspension, and status of any rule
in the SADP governance framework.

COMMAND SYNTAX (typed in conversation — AI parses and executes)
---------------------------------------------------------------
  RULE LOCK    R<N> [--reason "..."]
  RULE UNLOCK  R<N> [--reason "..."]
  RULE SUSPEND R<N> --reason "..." [--expires v<X.X.X>]
  RULE RESTORE R<N>
  RULE STATUS  [R<N>]
  RULE LIST    [--locked | --unlocked | --suspended | --all]
  RULE AUDIT   [--last N]

LOCK STATES
-----------
  LOCKED      Active and immutable. AI cannot bypass, waive, or modify
              without explicit RULE UNLOCK from the administrator.
              Attempting to work around a LOCKED rule is a R25 violation.

  UNLOCKED    Active, normal operation. Rule may be temporarily waived
              or modified with explicit justification.

  SUSPENDED   Temporarily inactive. Mandatory reason required. Optional
              version expiry. AI notes suspension in every R25 re-read.

  DEPRECATED  Rule has been superseded by a newer rule. Retained for
              historical record. No longer enforced.

PROTECTION CLASSES
------------------
  CORE        Algorithm invariants (R1, R5, R10, R11, R12). Cannot be
              SUSPENDED or DEPRECATED — only LOCKED or UNLOCKED.
              Attempting to suspend a CORE rule returns an error.

  STANDARD    All other rules. Can be in any state.

PERSISTENCE
-----------
  State is stored in sadp/RULE_REGISTRY.json.
  The registry is machine-readable (R24: human docs → PDF, not JSON).
  The version_sweep (R25) reads the registry and flags anomalies.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT / "sadp" / "RULE_REGISTRY.json"

# ---------------------------------------------------------------------------
# Rule metadata
# ---------------------------------------------------------------------------

RULE_META = {
    "R1":  {"title": "Target increments after every fold",           "group": "A", "protection": "CORE"},
    "R2":  {"title": "Landing Strip v2 import path",                 "group": "A", "protection": "STANDARD"},
    "R3":  {"title": "No targeting_mode reset after scrum/fold",     "group": "A", "protection": "STANDARD"},
    "R4":  {"title": "Trend-hold override threshold",                "group": "A", "protection": "STANDARD"},
    "R5":  {"title": "Bearish candle base confidence = 0.15",        "group": "A", "protection": "CORE"},
    "R6":  {"title": "Two execution paths — change both or neither", "group": "A", "protection": "STANDARD"},
    "R7":  {"title": "HA candles only, no toggle",                   "group": "B", "protection": "STANDARD"},
    "R8":  {"title": "HBoxLayout centering with addStretch()",       "group": "B", "protection": "STANDARD"},
    "R9":  {"title": "init_live_monitor() startup sequence",         "group": "B", "protection": "STANDARD"},
    "R10": {"title": "BB Bullseye delta threshold >= interval",      "group": "A", "protection": "CORE"},
    "R11": {"title": "Hedge reserve — separate, never skimmed",      "group": "A", "protection": "CORE"},
    "R12": {"title": "Smart Target cap at holdings × price × 0.995","group": "A", "protection": "CORE"},
    "R13": {"title": "ASSET_PERIODS lookup — never positional",      "group": "A", "protection": "STANDARD"},
    "R14": {"title": "Battery constants are fixed",                   "group": "A", "protection": "STANDARD"},
    "R15": {"title": "Live data routing in run_portfolio",           "group": "A", "protection": "STANDARD"},
    "R16": {"title": "Module loading order in RAIntSimBat",          "group": "A", "protection": "STANDARD"},
    "R17": {"title": "No GUI dimension changes without approval",    "group": "B", "protection": "STANDARD"},
    "R18": {"title": "Pre/post dimension check on GUI work",         "group": "B", "protection": "STANDARD"},
    "R19": {"title": "Trace first, fix second",                      "group": "B", "protection": "STANDARD"},
    "R20": {"title": "Full battery default (all 39 sims)",           "group": "C", "protection": "STANDARD"},
    "R21": {"title": "All research → Product Manual",               "group": "D", "protection": "STANDARD"},
    "R22": {"title": "Pre/post battery on engine logic change",      "group": "C", "protection": "STANDARD"},
    "R23": {"title": "Hop file rename on new AI session",            "group": "E", "protection": "STANDARD"},
    "R24": {"title": "Human docs → PDF output",                      "group": "D", "protection": "STANDARD"},
    "R25": {"title": "Micro-Management Loop + version sweep",        "group": "E", "protection": "STANDARD"},
    "R26": {"title": "Development Chronicle — session-close update", "group": "D", "protection": "STANDARD"},
    "R27": {"title": "Documentation ecosystem + code consistency",   "group": "F", "protection": "STANDARD"},
    # SADP Group G — Financial Software Standards
    "R28": {"title": "Fail loudly — explicit failure over silent default",  "group": "G", "protection": "STANDARD"},
    "R29": {"title": "Idempotency — financial operations safe to retry",    "group": "G", "protection": "STANDARD"},
    # SADP Group H — Code Quality Standards
    "R30": {"title": "Semantic versioning — MAJOR.MINOR.PATCH discipline",  "group": "H", "protection": "STANDARD"},
    "R31": {"title": "McCabe complexity gate — CC limits per function",     "group": "H", "protection": "STANDARD"},
    "R32": {"title": "Circuit breaker — stop calling failing dependencies", "group": "H", "protection": "STANDARD"},
    # SADP Group I — Architecture Standards
    "R33": {"title": "Immutable audit log — append-only financial records", "group": "I", "protection": "STANDARD"},
    "R34": {"title": "Single responsibility — one reason to change",        "group": "I", "protection": "STANDARD"},
    # SADP Group J — Session Management
    "R35": {"title": "Context fill monitoring — report fill%% at every R25/R26", "group": "J", "protection": "STANDARD"},
}

VALID_RULES  = set(RULE_META.keys())  # auto-derived from RULE_META
CORE_RULES   = {r for r, m in RULE_META.items() if m["protection"] == "CORE"}
VALID_STATES = {"LOCKED", "UNLOCKED", "SUSPENDED", "DEPRECATED"}


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------

@dataclass
class RuleEntry:
    rule:       str
    state:      str          # LOCKED | UNLOCKED | SUSPENDED | DEPRECATED
    reason:     str = ""
    expires:    str = ""     # version string, e.g. "v3.7.0" — for SUSPENDED
    changed_by: str = "admin"
    timestamp:  str = ""
    history:    list = field(default_factory=list)  # previous states

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RuleEntry":
        # v3.19.56 FIX (sadp R28 FL): filter unknown keys before constructor.
        # Pre-fix, RuleEntry(**d) crashed with TypeError if the JSON had
        # any extra fields (e.g. depends_on / title / group — fields used
        # by sadp/RULE_REGISTRY.json but not part of the RuleEntry shape).
        # Discovered by tests/test_rule_registry_coverage.py invoking
        # parse_rule_command() which constructs RuleRegistry() with the
        # default REGISTRY_PATH pointing at the real schema-extended file.
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class RuleRegistry:
    """
    Manages the persistent state of all governance rules.
    Loaded from / saved to RULE_REGISTRY.json.
    """

    def __init__(self, path: Path = REGISTRY_PATH):
        self.path    = path
        self._entries: dict[str, RuleEntry] = {}
        self._load()

    def _load(self):
        """Load from JSON; initialise missing rules as LOCKED (default safe state)."""
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        for rule in VALID_RULES:
            if rule in data:
                self._entries[rule] = RuleEntry.from_dict(data[rule])
            else:
                # Default: all rules start LOCKED
                self._entries[rule] = RuleEntry(
                    rule=rule,
                    state="LOCKED",
                    reason="Default state — all rules locked on initialisation.",
                    timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                )

    def _save(self):
        self.path.write_text(
            json.dumps(
                {r: e.to_dict() for r, e in sorted(self._entries.items())},
                indent=2
            )
        )

    def _validate_rule(self, rule: str) -> str:
        """Normalise and validate rule identifier. Returns uppercase e.g. 'R6'."""
        rule = rule.upper().strip()
        if not rule.startswith("R"):
            rule = "R" + rule
        if rule not in VALID_RULES:
            raise ValueError(
                f"Unknown rule: {rule!r}. Valid rules: R1–R27."
            )
        return rule

    # ── Commands ─────────────────────────────────────────────────────────────

    def lock(self, rule: str, reason: str = "") -> str:
        rule = self._validate_rule(rule)
        entry = self._entries[rule]

        if entry.state == "LOCKED":
            return f"ℹ  {rule} is already LOCKED."

        old_state = entry.state
        entry.history.append({
            "from": old_state, "to": "LOCKED",
            "reason": reason, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        entry.state  = "LOCKED"
        entry.reason = reason or f"Locked by admin (was {old_state})."
        entry.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry.expires = ""
        self._save()

        meta = RULE_META[rule]
        return (
            f"🔒  {rule} LOCKED\n"
            f"   Title:  {meta['title']}\n"
            f"   Group:  {meta['group']}  |  Protection: {meta['protection']}\n"
            f"   Reason: {entry.reason}\n"
            f"   Effect: AI cannot bypass, waive, or modify this rule without "
            f"explicit RULE UNLOCK."
        )

    def unlock(self, rule: str, reason: str = "") -> str:
        rule = self._validate_rule(rule)
        entry = self._entries[rule]

        if entry.state == "UNLOCKED":
            return f"ℹ  {rule} is already UNLOCKED."

        old_state = entry.state
        entry.history.append({
            "from": old_state, "to": "UNLOCKED",
            "reason": reason, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        entry.state  = "UNLOCKED"
        entry.reason = reason or f"Unlocked by admin (was {old_state})."
        entry.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry.expires = ""
        self._save()

        meta = RULE_META[rule]
        return (
            f"🔓  {rule} UNLOCKED\n"
            f"   Title:  {meta['title']}\n"
            f"   Group:  {meta['group']}  |  Protection: {meta['protection']}\n"
            f"   Reason: {entry.reason}\n"
            f"   Effect: Rule remains active but may be modified or temporarily "
            f"waived with explicit justification."
        )

    def suspend(self, rule: str, reason: str, expires: str = "") -> str:
        rule = self._validate_rule(rule)

        if rule in CORE_RULES:
            meta = RULE_META[rule]
            return (
                f"⛔  Cannot suspend {rule} — CORE protection.\n"
                f"   Title:  {meta['title']}\n"
                f"   CORE rules (R1, R5, R10, R11, R12) encode fundamental algorithm "
                f"invariants that define the accumulation strategy. Suspending them "
                f"would invalidate the 39/39 battery guarantee.\n"
                f"   Use RULE UNLOCK {rule} if you need to modify it with full awareness."
            )

        if not reason:
            return (
                f"⚠  RULE SUSPEND requires a --reason.\n"
                f"   Syntax: RULE SUSPEND {rule} --reason \"explanation\""
            )

        entry = self._entries[rule]
        old_state = entry.state
        entry.history.append({
            "from": old_state, "to": "SUSPENDED",
            "reason": reason, "expires": expires,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        entry.state  = "SUSPENDED"
        entry.reason = reason
        entry.expires = expires
        entry.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()

        meta = RULE_META[rule]
        expiry_note = f"\n   Expires: {expires}" if expires else "\n   Expires: manually via RULE RESTORE"
        return (
            f"⏸  {rule} SUSPENDED\n"
            f"   Title:  {meta['title']}\n"
            f"   Group:  {meta['group']}\n"
            f"   Reason: {reason}{expiry_note}\n"
            f"   Effect: Rule is temporarily inactive. AI will note the suspension "
            f"in every R25 re-read. Use RULE RESTORE {rule} to reactivate."
        )

    def restore(self, rule: str) -> str:
        rule = self._validate_rule(rule)
        entry = self._entries[rule]

        if entry.state not in ("SUSPENDED", "DEPRECATED"):
            return (
                f"ℹ  {rule} is currently {entry.state} — nothing to restore.\n"
                f"   Use RULE LOCK / RULE UNLOCK to change lock state."
            )

        old_state = entry.state
        entry.history.append({
            "from": old_state, "to": "LOCKED",
            "reason": "Restored by admin.",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        entry.state  = "LOCKED"
        entry.reason = f"Restored from {old_state} by admin."
        entry.expires = ""
        entry.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save()

        return f"▶  {rule} restored — state: LOCKED"

    def status(self, rule: Optional[str] = None) -> str:
        if rule:
            rule = self._validate_rule(rule)
            return self._format_single(rule)
        # All rules summary
        lines = [
            "═══════════════════════════════════════════════════════",
            "  SADP RULE REGISTRY — STATUS OVERVIEW",
            "═══════════════════════════════════════════════════════",
            f"  {'Rule':<6} {'State':<12} {'Group':<7} {'Prot':<9} Title",
            "  " + "─" * 54,
        ]
        state_sym = {"LOCKED": "🔒", "UNLOCKED": "🔓",
                     "SUSPENDED": "⏸ ", "DEPRECATED": "✕ "}
        for rule_id in sorted(self._entries.keys(), key=lambda r: int(r[1:])):
            e = self._entries[rule_id]
            m = RULE_META[rule_id]
            sym = state_sym.get(e.state, "? ")
            title_trunc = m["title"][:38]
            lines.append(
                f"  {rule_id:<6} {sym} {e.state:<10} Grp:{m['group']}  "
                f"{m['protection']:<9} {title_trunc}"
            )
        # Summary counts
        from collections import Counter
        counts = Counter(e.state for e in self._entries.values())
        lines += [
            "  " + "─" * 54,
            f"  LOCKED: {counts['LOCKED']}  UNLOCKED: {counts['UNLOCKED']}  "
            f"SUSPENDED: {counts['SUSPENDED']}  DEPRECATED: {counts['DEPRECATED']}",
            "═══════════════════════════════════════════════════════",
        ]
        # Show any suspended rules prominently
        suspended = [r for r, e in self._entries.items() if e.state == "SUSPENDED"]
        if suspended:
            lines.append("  ⚠  SUSPENDED RULES (verify before proceeding):")
            for r in suspended:
                e = self._entries[r]
                exp = f" (expires {e.expires})" if e.expires else ""
                lines.append(f"     {r}: {e.reason}{exp}")
        return "\n".join(lines)

    def _format_single(self, rule: str) -> str:
        e   = self._entries[rule]
        m   = RULE_META[rule]
        state_sym = {"LOCKED": "🔒", "UNLOCKED": "🔓",
                     "SUSPENDED": "⏸ ", "DEPRECATED": "✕ "}
        lines = [
            f"{'─'*50}",
            f"  {rule}  {state_sym.get(e.state,'?')} {e.state}",
            f"  Title:      {m['title']}",
            f"  Group:      {m['group']}  |  Protection: {m['protection']}",
            f"  Reason:     {e.reason or '(none)'}",
        ]
        if e.expires:
            lines.append(f"  Expires:    {e.expires}")
        lines.append(f"  Changed:    {e.timestamp}")
        if e.history:
            lines.append(f"  History ({len(e.history)} changes):")
            for h in e.history[-3:]:   # last 3
                lines.append(f"    {h['timestamp']}  {h['from']} → {h['to']}")
                if h.get('reason'):
                    lines.append(f"      Reason: {h['reason']}")
        lines.append(f"{'─'*50}")
        return "\n".join(lines)

    def list_rules(self, filter_state: Optional[str] = None) -> str:
        state_sym = {"LOCKED": "🔒", "UNLOCKED": "🔓",
                     "SUSPENDED": "⏸ ", "DEPRECATED": "✕ "}
        rows = []
        for rule_id in sorted(self._entries.keys(), key=lambda r: int(r[1:])):
            e = self._entries[rule_id]
            if filter_state and e.state != filter_state.upper():
                continue
            m   = RULE_META[rule_id]
            sym = state_sym.get(e.state, "?")
            rows.append(f"  {sym} {rule_id:<5}  {e.state:<12}  {m['title']}")
        header = (
            f"{'─'*55}\n"
            f"  Rules — "
            f"filter: {filter_state.upper() if filter_state else 'ALL'}\n"
            f"{'─'*55}"
        )
        return header + "\n" + "\n".join(rows) + f"\n{'─'*55}"

    def audit(self, last: int = 10) -> str:
        """Return chronological audit trail of recent state changes."""
        events = []
        for rule_id, e in self._entries.items():
            for h in e.history:
                events.append({
                    "rule": rule_id, "timestamp": h.get("timestamp", ""),
                    "from": h.get("from", "?"), "to": h.get("to", "?"),
                    "reason": h.get("reason", ""),
                })
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        events = events[:last]

        if not events:
            return "  No state changes recorded yet."

        lines = [
            f"{'─'*55}",
            f"  RULE AUDIT — last {last} changes",
            f"{'─'*55}",
        ]
        state_sym = {"LOCKED": "🔒", "UNLOCKED": "🔓",
                     "SUSPENDED": "⏸", "DEPRECATED": "✕"}
        for ev in events:
            f_sym = state_sym.get(ev["from"], "?")
            t_sym = state_sym.get(ev["to"],   "?")
            lines.append(
                f"  {ev['timestamp']}  {ev['rule']:<5}  "
                f"{f_sym} {ev['from']:<12} → {t_sym} {ev['to']}"
            )
            if ev["reason"]:
                lines.append(f"    {ev['reason']}")
        lines.append(f"{'─'*55}")
        return "\n".join(lines)

    def get_suspended(self) -> list[str]:
        """Return list of currently suspended rule IDs — used by R25 re-read."""
        return [r for r, e in self._entries.items() if e.state == "SUSPENDED"]

    def is_locked(self, rule: str) -> bool:
        """True if rule is LOCKED. Use during R25 compliance checks."""
        rule = self._validate_rule(rule)
        return self._entries[rule].state == "LOCKED"

    def is_active(self, rule: str) -> bool:
        """True if rule is LOCKED or UNLOCKED (i.e. currently enforced)."""
        rule = self._validate_rule(rule)
        return self._entries[rule].state in ("LOCKED", "UNLOCKED")


# ---------------------------------------------------------------------------
# CLI — parse RULE commands from conversation
# ---------------------------------------------------------------------------

def parse_rule_command(
    text: str,
    registry_path: Path | None = None,
) -> Optional[str]:
    """
    Parse a RULE command from conversation text.
    Returns formatted response string, or None if not a RULE command.

    Args:
        text: The RULE command line.
        registry_path: Optional registry path. ``None`` (default) uses
        the production REGISTRY_PATH; tests MUST pass an explicit
        ``tmp_path`` so the helper never writes to the production
        registry. Added in v3.19.57 hotfix after coverage tests using
        ``patch("src.core.rule_registry.REGISTRY_PATH", ...)`` failed
        to isolate — function defaults bind at def-time, so the
        patched module-level path is never read by ``RuleRegistry()``.

    Supports:
      RULE LOCK   R<N> [--reason "..."]
      RULE UNLOCK R<N> [--reason "..."]
      RULE SUSPEND R<N> --reason "..." [--expires v<X.X.X>]
      RULE RESTORE R<N>
      RULE STATUS  [R<N>]
      RULE LIST    [--locked | --unlocked | --suspended | --all]
      RULE AUDIT   [--last N]

    sadp: R28 FL  R55 GOV  R68 DPA
    """
    text = text.strip()
    if not re.match(r'^RULE\s+', text, re.I):
        return None

    reg = (RuleRegistry(path=registry_path) if registry_path is not None
           else RuleRegistry())

    # Extract --reason "..."
    reason_m = re.search(r'--reason\s+"([^"]+)"', text, re.I)
    reason   = reason_m.group(1) if reason_m else ""

    # Extract --expires v<X.X.X>
    expires_m = re.search(r'--expires\s+(v[\d.]+)', text, re.I)
    expires   = expires_m.group(1) if expires_m else ""

    # Extract --last N
    last_m = re.search(r'--last\s+(\d+)', text, re.I)
    last_n = int(last_m.group(1)) if last_m else 10

    # Extract filter flags
    filter_state = None
    if re.search(r'--locked\b',     text, re.I): filter_state = "LOCKED"
    if re.search(r'--unlocked\b',   text, re.I): filter_state = "UNLOCKED"
    if re.search(r'--suspended\b',  text, re.I): filter_state = "SUSPENDED"
    if re.search(r'--deprecated\b', text, re.I): filter_state = "DEPRECATED"

    # Extract rule identifier
    rule_m = re.search(r'\b(R\d+)\b', text, re.I)
    rule   = rule_m.group(1).upper() if rule_m else None

    # Parse subcommand
    sub_m = re.match(r'^RULE\s+(\w+)', text, re.I)
    if not sub_m:
        return "⚠  Unrecognised RULE command. Try: RULE STATUS"
    sub = sub_m.group(1).upper()

    try:
        if sub == "LOCK":
            if not rule: return "⚠  Syntax: RULE LOCK R<N>"
            return reg.lock(rule, reason)
        elif sub == "UNLOCK":
            if not rule: return "⚠  Syntax: RULE UNLOCK R<N>"
            return reg.unlock(rule, reason)
        elif sub == "SUSPEND":
            if not rule: return "⚠  Syntax: RULE SUSPEND R<N> --reason \"...\""
            return reg.suspend(rule, reason, expires)
        elif sub == "RESTORE":
            if not rule: return "⚠  Syntax: RULE RESTORE R<N>"
            return reg.restore(rule)
        elif sub == "STATUS":
            return reg.status(rule)
        elif sub == "LIST":
            return reg.list_rules(filter_state)
        elif sub == "AUDIT":
            return reg.audit(last_n)
        else:
            return (
                f"⚠  Unknown RULE subcommand: {sub!r}\n"
                f"   Valid: LOCK, UNLOCK, SUSPEND, RESTORE, STATUS, LIST, AUDIT"
            )
    except ValueError as e:
        return f"⚠  {e}"


# ---------------------------------------------------------------------------
# Initialise registry with sensible defaults
# ---------------------------------------------------------------------------

def initialise_defaults(path: Path | None = None) -> RuleRegistry:
    """
    Create RULE_REGISTRY.json with all rules set to LOCKED by default.
    Idempotent — skips rules already in the registry.

    Args:
        path: Optional registry path. Defaults to production
        REGISTRY_PATH when ``None``. Pass an explicit path in tests
        so the helper never touches the production registry. (Adding
        this parameter was a v3.19.57 hotfix after a coverage test
        polluted sadp/RULE_REGISTRY.json by relying on the default —
        function defaults bind at def-time, so monkeypatching the
        module-level REGISTRY_PATH does not work.)

    sadp: R28 FL  R55 GOV  R68 DPA
    """
    reg = RuleRegistry(path=path) if path is not None else RuleRegistry()
    # Registry auto-initialises all rules to LOCKED in _load()
    reg._save()
    return reg


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        result = parse_rule_command("RULE " + cmd)
        print(result or "Not a RULE command.")
    else:
        reg = initialise_defaults()
        print(reg.status())
