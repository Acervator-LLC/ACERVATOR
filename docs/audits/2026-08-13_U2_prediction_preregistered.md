# U2 lot-book reconcile — prediction, registered BEFORE it runs

Reference. Written 2026-08-13, after U2 promoted and BEFORE the operator's
next launch. Nothing here is a result. Every number is a prediction, so the
run can falsify it instead of being explained by it.

## Why this document exists

Operator, 2026-08-13: "For expected results, we should have verifiable
measures after the program is running... The Emitter Network gives you a
network of a thousand whereby to perfect your own programming effort."

An island proof is a hypothesis about the running system. The claim below has
never met a live tick. Recording it now is what makes the next launch a test.

## What U2 changed

The periodic drift check audited `self._current_holdings`, a single number
that startup had already clamped DOWN to the wallet with `min`. The lot book
was therefore compared against nothing, and excess units stranded in it
permanently. Measured across three separate pins: **21 bots carry a book above
the scalar, ZERO below.** A one-way ratchet.

U2 audits `max(scalar, book)` against the venue, and reads the venue as
`total, else free, else zero` — the same chain the startup handshake and
`bootstrap_exchange_state` already use (MEM-255: total is what the operator
sees on the exchange screen).

## THE PREDICTION

Measured from a read-only pin taken 2026-08-13T23:54:06Z
(sha256 `f5b496ca8a2505b1aba2d48d4edae0b7b1ec90245a767251d6ae707ea5f66561`,
838,368 bytes) by driving the REAL `_reconcile_holdings` once per bot, all 37.

**On the first launch after U2, 11 bots fire drift-down and $29.94 total is
written off the lot books.**

| bot | percent | dollars |
|---|---|---|
| ORCA | 9.848% | $5.5214 |
| KAT | 2.526% | $5.2249 |
| ZEC | 2.614% | $4.0334 |
| ETH | 1.540% | $3.1505 |
| BTC | 1.099% | $2.7737 |
| LINK | 2.990% | $2.3814 |
| PENGU | 2.052% | $2.0801 |
| DOGE | 1.905% | $1.9384 |
| BONK | 1.681% | $1.7185 |
| XLM | 1.337% | $0.6709 |
| SOL | 0.572% | $0.4423 |
| **total** | | **$29.94** |

ORCA's correction is 5.32340782 units against a book of 54.053407815409216.

**10 further bots carry excess BELOW the 0.5% deadband and must NOT fire**,
$0.98 left stranded, from RE at 0.464% down to HYPE at 0.024%. U2 does not
widen the deadband; recalibrating around a defect is forbidden.

**16 bots are aligned and must stay silent.**

## HOW TO FALSIFY IT

Each of these is a way the prediction is WRONG, not a way it is explained.

1. **A bot fires that is not in the table.** The model missed it.
2. **A bot in the table does not fire.** Either the tolerance behaves
   differently live, or the pin was stale for that bot.
3. **A total materially past $29.94.** The pin drifts while the operator
   trades — an earlier pin gave $29.85 and the build's gave $29.8529, so a few
   cents of movement is expected. Dollars, not cents, means the model is wrong.
4. **Any bot's book rescaled to ZERO.** That is the absent-balance path
   firing, which U2 exists to refuse. A hard failure.
5. **A lot count that changes.** ORCA must keep all 48 lots and all 48
   `initial_buy_price` values. A dropped lot means the survivor filter ate a
   poisoned entry.
6. **Any exception out of the reconcile.** 26 conversion sites were driven
   with 16 hostile inputs across 3 readings, 48 rows, zero raises. A raise
   means a site was missed.

## WHAT TO READ AFTER THE LAUNCH

The bot log line, one per firing bot, in this shape:

    BALANCE DRIFT (periodic): internal=54.053408 exchange=48.730000
    drift=-5.323408 (9.85%). Resetting internal state to exchange reality.

Count the lines. Sum the drift. Compare against the table.

**Zero of 37 bots held an open buy or sell order at pin time**, so `total`
equals `free` on every row today, and the venue-field change cannot alter this
run's numbers. It matters on the run AFTER stack mode activates, when resting
orders make the two differ.

## WHAT THIS DOCUMENT DOES NOT CLAIM

The $29.94 is not a loss. Those units were never in the wallet — the book
claimed them and the exchange did not hold them. The correction moves the
record toward the venue, which is the truth. What it costs is the recorded
cost basis attached to units that did not exist.

Related: `docs/audits/2026-08-13_replay_findings_cold_read.md` for how the
ratchet was found, and the four instruments that failed to find it.
