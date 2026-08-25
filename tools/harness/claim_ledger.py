"""Claim ledger — structural show-don't-tell.

Every claim Claude makes is logged to a JSONL file with a status:
`open` (asserted, unverified), `verified` (evidence attached), or
`refuted` (claim disproven by evidence).

Pre-cascade check: fail if any `open` claim remains in the current
session's ledger. This closes the loophole where "I audited X" is
shipped without proof of the audit.

Ledger path: `docs/audits/CLAIMS.jsonl` (project-level, cumulative).

Schema per line (JSONL):
  {
    "id": "CLM-YYYYMMDD-NNN",
    "created": "2026-07-24T20:15:00Z",
    "session": "session27",              # optional
    "claim": "GUI archetype passes all 5 ground-truth defects",
    "evidence_required": "gui_raw/archetype_known_bad.json + reviewer transcripts",
    "status": "open" | "verified" | "refuted",
    "evidence": null | {"note": "...", "files": [...]},
    "resolved": null | "2026-07-24T20:20:00Z"
  }

CLI:
  python -m tools.harness.claim_ledger log "claim text" --evidence "what would verify"
  python -m tools.harness.claim_ledger verify CLM-20260724-001 --note "text" [--file path ...]
  python -m tools.harness.claim_ledger refute  CLM-20260724-001 --note "text"
  python -m tools.harness.claim_ledger open              # list open claims
  python -m tools.harness.claim_ledger check             # exit 1 if any open

FALSIFICATION: this ledger is wrong if (a) the JSONL file is edited
outside these CLI commands so IDs collide, (b) a claim marked
'verified' points to evidence files that don't exist on disk, (c) a
process bypasses the ledger and ships a claim without logging it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
LEDGER_PATH = REPO / "docs" / "audits" / "CLAIMS.jsonl"


@dataclass
class Claim:
    id: str
    created: str
    claim: str
    evidence_required: str
    status: str = "open"  # "open" | "verified" | "refuted"
    session: str | None = None
    evidence: dict | None = None
    resolved: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _load_all() -> list[Claim]:
    if not LEDGER_PATH.exists():
        return []
    out: list[Claim] = []
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append(Claim(**d))
    return out


def _write_all(claims: list[Claim]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("w", encoding="utf-8") as fh:
        for c in claims:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")


def _next_id(claims: list[Claim]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"CLM-{today}-"
    n = 1
    used = {c.id for c in claims if c.id.startswith(prefix)}
    while f"{prefix}{n:03d}" in used:
        n += 1
    return f"{prefix}{n:03d}"


def log_claim(
    claim_text: str, evidence_required: str, session: str | None = None
) -> Claim:
    """Log a new claim in `open` state. Returns the created Claim."""
    claims = _load_all()
    c = Claim(
        id=_next_id(claims),
        created=_now(),
        claim=claim_text,
        evidence_required=evidence_required,
        session=session,
    )
    claims.append(c)
    _write_all(claims)
    return c


def verify(claim_id: str, note: str, files: list[str] | None = None) -> Claim:
    claims = _load_all()
    for c in claims:
        if c.id == claim_id:
            if c.status != "open":
                raise ValueError(f"{claim_id} is {c.status}, not open")
            c.status = "verified"
            c.evidence = {"note": note, "files": files or []}
            c.resolved = _now()
            _write_all(claims)
            return c
    raise KeyError(f"claim not found: {claim_id}")


def refute(claim_id: str, note: str) -> Claim:
    claims = _load_all()
    for c in claims:
        if c.id == claim_id:
            if c.status != "open":
                raise ValueError(f"{claim_id} is {c.status}, not open")
            c.status = "refuted"
            c.evidence = {"note": note, "files": []}
            c.resolved = _now()
            _write_all(claims)
            return c
    raise KeyError(f"claim not found: {claim_id}")


def list_open(session: str | None = None) -> list[Claim]:
    return [
        c
        for c in _load_all()
        if c.status == "open" and (session is None or c.session == session)
    ]


def check_no_open(session: str | None = None) -> int:
    """Pre-cascade check: return exit code (0 = clean, 1 = open claims)."""
    open_claims = list_open(session)
    if not open_claims:
        print("[OK] no open claims" + (f" for session {session}" if session else ""))
        return 0
    print(f"[FAIL] {len(open_claims)} open claim(s):")
    for c in open_claims:
        print(f"  {c.id}: {c.claim!r}")
        print(f"    evidence required: {c.evidence_required}")
    print()
    print("Resolve each with:")
    print(
        "  python -m tools.harness.claim_ledger verify <ID> --note '...' [--file path ...]"
    )
    print("or, if the claim was wrong:")
    print("  python -m tools.harness.claim_ledger refute <ID> --note '...'")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="claim_ledger", description="structural show-don't-tell"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    log = sub.add_parser("log", help="log a new claim")
    log.add_argument("claim", help="the assertion")
    log.add_argument(
        "--evidence", required=True, help="what would verify or refute this claim"
    )
    log.add_argument("--session", default=None)

    ver = sub.add_parser("verify", help="mark a claim verified")
    ver.add_argument("claim_id")
    ver.add_argument("--note", required=True)
    ver.add_argument(
        "--file",
        action="append",
        default=[],
        dest="files",
        help="evidence file (repeatable)",
    )

    ref = sub.add_parser("refute", help="mark a claim refuted")
    ref.add_argument("claim_id")
    ref.add_argument("--note", required=True)

    op = sub.add_parser("open", help="list open claims")
    op.add_argument("--session", default=None)

    ck = sub.add_parser("check", help="fail if any open claims (pre-cascade gate)")
    ck.add_argument("--session", default=None)

    args = p.parse_args(argv)

    if args.cmd == "log":
        c = log_claim(args.claim, args.evidence, args.session)
        print(f"logged: {c.id}")
        return 0
    if args.cmd == "verify":
        try:
            c = verify(args.claim_id, args.note, args.files)
        except (KeyError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"verified: {c.id}")
        return 0
    if args.cmd == "refute":
        try:
            c = refute(args.claim_id, args.note)
        except (KeyError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(f"refuted: {c.id}")
        return 0
    if args.cmd == "open":
        rows = list_open(args.session)
        if not rows:
            print("no open claims")
            return 0
        for c in rows:
            print(f"{c.id}: {c.claim}")
            print(f"  evidence required: {c.evidence_required}")
        return 0
    if args.cmd == "check":
        return check_no_open(args.session)
    return 2


if __name__ == "__main__":
    sys.exit(main())
