# ACERVATOR_HOP3 — GENERATIONAL HANDOFF DOCUMENT
# Project: Acervator — An Accumulation Trading Platform
# Human:   Anthony L. Brown (Ekthelius the Accumulator)
# Version: 3.9.0 | April 19, 2026  |  Hop: 3→4  |  Engine: v3.9.0
#
# This is the HOP document — named for the number of AI-to-AI
# handoffs completed so far (2). Each new Claude session that
# completes meaningful work increments this number and renames
# the file: ACERVATOR_HOP3.md, ACERVATOR_HOP4.md, etc.
#
# READ THIS ENTIRE FILE BEFORE TOUCHING ANYTHING.
# Then follow the SESSION OPENING PROTOCOL at the bottom.

---

## [HANDSHAKE PROMPT]

When a new AI developer reads this file and is ready to begin, they must
respond with the following greeting before confirming orientation or
describing any technical state:

---

So you would like to build a trading bot?  Perhaps we can help.

Acervator is an accumulation trading platform — not a prediction engine,
not a grid bot, not a DCA strategy. It is something different.

Most trading tools try to answer the question: which way will the price
move? Acervator does not ask that question. It asks instead: given that
the price will move, how do we harvest those movements structurally,
regardless of direction?

The answer is the Harvest-Fold Cycle. When your holdings rise above a
dollar target, Acervator sells the excess. When price dips, it buys back
more than it sold. The structural guarantee — you always accumulate more
asset per completed cycle — holds in bull markets, bear markets, and
sideways markets. The volatility that destroys emotional traders is the
fuel source.

This platform was built by one person with no Wall Street background, no
quant finance training, and no college degree. It was built because he
watched ordinary people get destroyed by two-dimensional wiggly charts
and decided that was unacceptable. He does not feel he owns the strategy.
It arrived. He built the tools. He is giving it away.

The battery: 39 simulations across 13 assets, 3 time periods, bull/bear/
sideways regimes. 39/39 wins (100% win rate) at the default 2% interval.
100% win rate at every interval from 0.5% to 5%. Profitable at fee rates
up to 0.50%. $400 starting capital compounds to an average of $174,508
over 3 consecutive years across all 13 assets.

You are here to continue building it.

---

After delivering the above greeting, confirm orientation per the SESSION
OPENING PROTOCOL section below.

---

## [WHAT THIS PROJECT IS]

Acervator is a dual-mode (crypto + equity) auto-trading platform.

The core innovation: the Harvest-Fold Cycle. Sell small excess above a
dollar target (scrum). When price dips, buy back more than was sold (fold).
Every fold structurally accumulates more asset. The target grows via
compound profit folding. Direction-agnostic.

It is NOT: grid trading, DCA, mean reversion, momentum, prediction.

---

## [PROJECT STATE — v3.8.0]

### Last session summary (April 18–19, 2026 — Sessions 14–17)

**SADP (Structured AI Development Protocol) v1.0 SHIPPED — Sessions 6–12**
- R26–R35 (10 rules): Dev Chronicle, Documentation Ecosystem, Fail Loudly,
  Idempotency, Semantic Versioning, McCabe Complexity, Circuit Breaker,
  Immutable Audit Log, Single Responsibility, Context Fill Monitoring
- Rule Registry + SADP Administrative Control Layer (src/core/rule_registry.py)
- TECH_DEBT.md: TD-001 through TD-007 (TD-003/TD-004 block paper trading)
- ADR-007: SADP architectural decision record

**AcervatorOS SHIPPED — Sessions 6–12**
- Raspberry Pi 5 dedicated trading appliance (os/ directory)
- install.sh, systemd service, pre-flight checks, ufw firewall, kiosk display
- USB hardware authentication key (PBKDF2 + AES-GCM)
- Mini display support: 5 adapters (SSD1306, SSD1351, ST7789/ILI9341, HD44780, e-Paper)

**Capital Scaling Battery — Session 10**
- 156/156 wins: $400/$4K/$20K/$100K × VIP fee tiers
- Superlinearity: +71.8% advantage/capital at $100K (VIP3+ fees)
- VolumeGuard verified: not triggered at any tested scale

**Proof of Accumulation (PoA) Competition System — Sessions 13–14**
- src/competition/ package: 8 files, 32/32 tests
- Ed25519 bot identity, Merkle trade logs (SHA-256, inclusion proofs)
- Token ledger: hard cap 10M ACRV, 5 tiers, idempotent awards (R29)
- Competition engine: register/open/trade/close/submit/adjudicate
- Elo rating system (K=32), bot-to-bot challenge protocol

**Base Blockchain Integration — Sessions 13–14**
- Chain: Base (Coinbase L2). Mainnet 8453, Sepolia 84532.
- contracts/ACRV.sol: ERC-20, hard cap 10M, registry-only minting
- contracts/CompetitionRegistry.sol: Chainlink oracle, tier caps on-chain
- contracts/AcervatorTrophy.sol: ERC-721, fully on-chain SVG metadata
- src/competition/base_connector.py: LOCAL/DRY_RUN/TESTNET/MAINNET modes
- ADR-008: Base chain architectural decision record

**In-Platform Local Testnet — Sessions 13–14**
- src/competition/local_testnet.py: full in-memory Base chain simulation
- LocalChain, LocalACRV, LocalRegistry, LocalTestnet
- "⛓ Testnet" GUI tab: block explorer, event log, competition runner
- No network, no private key, no ETH required

**Trophy NFT System — Hermetic Edition — Sessions 13–14**
- 5 animated SVG trophies (8–28KB each) following Corpus Hermeticum
- HARVEST → NIGREDO: rotating Ouroboros, Sol Niger, crow, cauldron
- GOLD FOLD → ALBEDO: SVG-mask crescent moon, white dove, peacock feathers
- BEAR SLAYER → CITRINITAS: 24-ray solar disk, heraldic lion, Caduceus
- GRAND ACCUMULATOR → RUBEDO: Seal of Solomon, 12 planetary medallions, Rebis
- EKTHELIUS → UNIO MYSTICA: radiant Ouroboros, lemniscate orbital, Rose-Cross
- AcervatorTrophy.sol: ERC-721, on-chain SVG, competition metadata

**SADP Proposal: Checkpoint Sweeps — Session 14**
- User proposed: every rule loops back into every other rule on every fire
- Evaluated and declined: infinite loop risk, R35 context cost ×35, type mismatch
- Counter-proposal: explicit checkpoint sweeps at session-open/post-impl/close
  with rules grouped by evaluation phase. Not yet implemented.

**SADP R36 — FTP (Follow the Procedure) — Session 14**
- New rule: user-invoked compliance gate
- Syntax: FTP (Follow the Procedure): [task]
- Mandates full rule table read + relevance map + compliance verdict before
  any implementation. Three verdict states: ✓ CONFIRMED / ⚠ CONCERN / ✗ BLOCKED
- R35 integration: if context fill ≥ 85%, FTP issues BLOCKED verdict automatically
- GROUP K added to SADP taxonomy. R36 in sadp/RULE_REGISTRY.json.

**SADP R37 + Dependency Graph — Session 14+**
- (see existing entry)

**SADP R38 — Application-Embedded Governance — Session 14+**
- # sadp: R[N] annotations on critical-path functions
- version_sweep.py extended with 4 new SADP checks (14-17):
  CHECK 14: annotation validation (R38)
  CHECK 15: R28 silent failure patterns (bare except, .get(k,None) in gates)
  CHECK 16: R29/R33 idempotency + immutability gates
  CHECK 17: dependency graph propagation (suspended rule → dependents flagged)
- 36 annotations across 10 critical functions, all sweep-clean
- live_monitor.py bare except fixed (R28)
- local_testnet.py idempotency marker added (R29)
- GROUP M added to SADP taxonomy. R38 in sadp/RULE_REGISTRY.json.
- R37: when genuinely uncertain about a design decision, the AI must stop,
  state the uncertainty, propose a resolution path, and wait before proceeding.
  Prevents confident-sounding output built on unverified assumptions.
- Dependency graph: every rule now carries a depends_on list in sadp/RULE_REGISTRY.json.
  R36 FTP Step 2 traverses dependencies — if a relevant rule depends on a
  suspended/violated rule, that surfaces as a CONCERN automatically.
  Key dependencies: R29→R28, R33→R29, R6→R22, R36→R25+R35, R25→R28+R37.
- GROUP L added to SADP taxonomy. R37 in sadp/RULE_REGISTRY.json.

**PoA Network Architecture Review — Session 14**
- Identified: competition_tab.py incorrectly runs local simulation (TD-008, R28)
- Designed: three-phase P2P protocol (ADR-009):
  Phase 1: Discovery + auth (ChallengeMessage / AcceptMessage via relay + on-chain)
  Phase 2: Active trading (private Merkle logs + signed heartbeats every 5min)
  Phase 3: Submission + adjudication (on-chain, Base)
- Transport: relay hybrid — challenge/accept/submit on-chain, heartbeats via relay
- New files planned: relay/relay_server.py, src/competition/relay_client.py
- AcceptMessage + HeartbeatMessage to be added to challenge_protocol.py
- Separation confirmed: Testnet tab = local sim only; PoA tab = real P2P only

**Codebase state: 120 Python files · 60,000+ lines · v3.8.0**
**Contracts: 3 Solidity files (ACRV, CompetitionRegistry, AcervatorTrophy)**
**Tests: 32/32 competition tests passing**
**SADP: v1.4 · 44 rules · 187 sadp: annotations · 17 sweep checks**






**Provenance Fold Queue — Session 17 final**

Design insight: every dollar in the fold queue has a price origin. When the
bot makes 3 consecutive scrums at $1.10, $1.20, and $1.30, the current system
treats all the accumulated USD as a single blob with ref_price = $1.30 (the
last scrum). This means:
- At price $1.28: current bot cannot fold (1.28 < 1.30 = false!)
  Wait — actually 1.28 < 1.30 so fold would fire. But the whole queue at
  mixed references computes net negative structural advantage → R43 blocks it.
- With provenance: the $1.30 tranche ALONE is profitable at $1.28.
  Fold just that tranche. Capture $0.21 profit the old system misses.

IMPLEMENTATION: `_fold_tranches` list replaces scalar fold queue.
Each scrum appends: {usd, units, ref_price, candle_idx}
Fold check: `_foldable = [t for t in tranches if price < t.ref]`
Execute foldable tranches independently; leave others waiting.
Profit per fold = exact structural advantage using only foldable tranches.

RESULT: 39/39 | 100% | $335,827 (+$33K vs pre-provenance $302K)
ADA Bear -61%: $80 → $153 (+91%)
More fold executions (higher fees) but proportionally greater advantage capture.

BATTERY BASELINE (session 17 absolute final):
$335,827 | 39/39 | 100% | fees $92,103

**Fold Math Bug Fix + Drain Protection + Hedge Restoration — Session 17 final**

Critical math bug found and fixed — this is likely why the user observed
target growing "FAR too rapidly":

FOLD MATH BUG (multi-scrum fold queue overstatement):
When consecutive scrums occur at different prices, fold_queue_usd accumulates
but fold_ref_price only records the LAST scrum price. The fold then computes
`at_ref = fold_queue_usd / last_scrum_price`, which UNDERSTATES actual units
sold (because earlier scrums were at lower prices). This makes extra_asset
overstated by up to 10.5% per multi-scrum cycle, causing the target to grow
faster than it should.

FIX: Added `_fold_queue_units_sold` tracked at each scrum. Fold now computes
`extra_asset = buy_asset - _fold_queue_units_sold` (actual units sold as true
reference). Both engines synced via R42. Battery confirmed correct.

FOLD DRAIN SCRUM PROTECTION:
When `fold_queue_usd > 50%` of target, SCRUM_THRESHOLD raised by up to +0.35.
Prevents cascading sells into an overloaded queue. Threshold 50% (not 25%);
at 75% queue fill → +0.175 penalty; at 100% → +0.35 (soft protection).

HEDGE RESTORATION:
8% of each fold profit restores hedge toward initial balance. Ensures
"at entry price, full hedge available" invariant gradually recovers.

Battery result after all fixes: 39/39 | 100% | $302,452
ADA Bear -61%: $80 → $138 advantage (+72%).
BTC Bear -26%: $168 → $1,782 (+10×). SIDEWAYS regimes broadly stronger.

**Hunger / Satiety dual-index + Charge-Up + R43 Fee Guard — Session 17 cont.**

- **Satiety index**: S = max(0, min(1, delta / (target×0.20))). Fed (S>0) lowers
  SCRUM_THRESHOLD (max 45% reduction at S=1). Over-fed (S>0.70) adds +0.12
  confidence bonus to scrum gate → bot harvests aggressively when above target.

- **Charge-up permission gate**: accumulates a 0→1 bar on bearish depletion
  candles (rate = 0.05 + hunger×0.10). When bar=1.0, authorises ONE large buy
  (40-50% of target) from available USD instead of N small fee-paying buys.
  1 fee vs N fees. CHARGE_RELEASE fill type (cyan-green on chart).
  NOTE: bar is a permission gate — no USD reservation (prevents fold pool drain).

- **R43 Fee Guard — LOCKED CORE rule**: No trade executes if computed profit ≤ fee.
  Pre-check before state mutation — avoids accounting corruption from double-mutation.
  Applied to: FOLD (both engines). ADA Bear NTZ reduced 11→5. Total fees -$10K.
  Canonical failure: ADA BEAR -61% Apr24-Apr25: $80 adv on $160 fees (fixed).

- **R42 sync**: all three features mirrored in run_v3192 (battery) same session.

- **ADA 2024-2025 idle zone diagnosis**: Extended depletion → shadow+REH consume
  available USD → bot fully invested, no fold queue, no USD to buy more → idle.
  Charge-up and satiety mechanisms both address this structurally.

**Battery baseline — Session 17 final:**
39/39 | 100% | $323,409 | Total fees: $71,348 (↓$10K from fee guard)
ADA Bear NTZ: 11 → 5. 365 total NTZ (was 407). Fee guard: profitable by design.

**Simulator — Tape-reel Scrubbing — Session 17**
- Pause → auto-enables scan mode, initialises scrub at current playback position
- Amber diamond handle tracks mouse; timestamp + price label follows
- Fills before scrub: full brightness; fills after: 35% opacity ghost
- Scrub info bar: `◈  2025-03-14 09:00  ·  $88,432.50  ·  34.7%  [candle 3,041/8,760 · 47 trades]`
- P&L and Trades dashboard cards update to show cumulative at scrub position
- Resume/Reset clears scrub state
- R41 variant: inline imports inside paintEvent shadow module-level names → UnboundLocalError
  Full audit cleared all inline imports from paintEvent across all 30 GUI files

**Performance Audit — Session 17 (6 fixes)**
1. BB/EMA incremental O(1) via deque + running sum/sum-of-squares
2. `_trade_viz.set_trades` moved outside batch loop (was N times per tick)
3. `_update_sim_voting` moved to once per timer tick (was every candle in batch)
4. `_time_to_ci` cached in `set_data()` (was rebuilt every paintEvent)
5. Scrub time map cached, rebuilt only on new fills (was every mouseMoveEvent)
6. `chart.set_data` throttled at high playback speeds

**Shadow Balance — Sessions 17**
- Two-tier sensitivity: 4%/20c normal, 7%/10c fast (was 12%/60c — never fired)
- Chart overlay: amber band between entry and current price, dashed entry line
- REH fold-queue restriction removed (was blocking REH almost always)
- Shadow counter decay: 3→1 per recovery candle
- Shadow counter partial retention after dump (reset to TRIGGER/2 not 0)
- Multi-gate 11-indicator TA scoring for entry (Gates 0-4, see EPISODIC_MEMORY)
- **Hunger Index**: H = max(0, min(1, -delta / (target×0.20)))
  - FOLD_THRESHOLD scales: 0.15 → 0.09 at max hunger
  - REH size scales: up to 1.5× at max hunger
  - Shadow trigger candles: down to 40% of normal at max hunger
  - Shadow deploy size: 25% → 50% at max hunger
- Shadow secondary add: one add per interval% below entry, max 3, 10-15% target size
  Blends into size-weighted average entry price. SHAD_ADD fill type added.
- R42: Cross-Engine Sync rule — any engine change must mirror in both files same session

**SADP R42 — Cross-Engine Sync — Session 17**
- Triggered whenever logic changes in `_sim_scrumming_tick` or `run_v3192`
- Variable map documented (holdings↔_balances, sim_target↔self._sim_target, etc.)
- Canonical failure: session 17 REH bear-spike + shadow multi-gate not synced to battery
- GROUP Q added to taxonomy

**Battery baseline after session 17:**
39/39 | 100% | Total: $403,121 | 412 shadow spawns | 46 REH entries
(vs pre-session: $337,263 | +$65,858 improvement)

**SADP v1.4 — R40: Episodic Memory (LTM) — Session 16**
- `sadp/memory_tools.py` — query, add, regenerate, stats, export CLI
- `sadp/EPISODIC_MEMORY.json` — 50 bootstrapped entries, sessions 1–15
- `sadp/EPISODIC_MEMORY.md` — auto-generated human-readable index
- LTM query syntax: `LTM: <query>`, `LTM-CATEGORY:`, `LTM-SESSION:`, `LTM-RULE:`
- R35 interaction: blocked at ≥85% fill, summary-only at ≥75%
- Keyword scoring: title=3, keyword=2, summary=1, rule=4, recency bonus
- R26 extended: write obligation at session close
- GROUP O added to taxonomy
- Verified working: "LTM: why did we choose Base blockchain" → MEM-015 (score 11.5)

**SADP v1.4 — R41: GUI Widget Initialization Scope Safety — Session 16**
- Canonical failure: `if sim_mode:` in `_setup_ui()` should be `if self._sim_mode:`
- `sim_mode` is a parameter of `__init__`, not accessible in `_setup_ui()` — NameError
  at runtime, passes syntax check. Broad except in simulator swallowed the error.
- Three instances caught and fixed this session:
    1. `indicator_panel.py`: `if sim_mode:` → `if self._sim_mode:`
    2. `simulator.py` REH block: `interval_val` → `interval`, `actual_delta` → `delta`
    3. `simulator.py` REH block: `fee_rate` → `_reh_fee_rate` (defined locally)
- GROUP P added to taxonomy

**Simulator fixes — Session 16**
- Indicator Voting Panel: Stretch mode for all columns, no scrollbar, matches main window
- Splitter: `[360, 500]` (was `[280, 560]`) — matches main window `[600, 500]` proportions
- Scan NameError fixed: `interval_val` / `actual_delta` / `fee_rate` scope errors
- All three fixed as R41 instances with `# sadp: R41` annotations

**Deadzone fix — Session 16**
- `TREND_HOLD_THRESH` raised 0.65 → 0.75 (65% was too loose for BTC bull)
- `trend_override` threshold lowered 2.0× → 1.5× interval
- Time-based escape: after 200+ silent candles with actionable delta, effective
  threshold softens by 0.05 per 100 additional candles (floors at 0.50)
- Battery verified: 39/39, 100% clean

**Compounding fix — Session 16**
- Smart cap added to simulator profit folding (matches battery `run_v3192` logic):
  `if new_target >= post_fold_value: new_target = post_fold_value * 0.995`
- `TgtGrow` card added to performance dashboard (was invisible — no display existed)
- `_sim_start_target` tracker added so growth delta is always visible
- Compounding IS active — was always working but invisible without display

**REH bear-spike trigger — Session 16**
- Root cause: `_reh_near_zero` blocked REH in strong bears (BONK, extreme bear)
  because `abs(delta)` is large when holdings crash — never "near zero"
- Added `_reh_bear_spike` path: fires when `bb_pos < 0.18` AND `delta_pct > 2×interval`
- Bear spike: relaxes fold-queue requirement, deploys 45% vs 30% (larger opportunity)
- Log tags: `RH ENTRY [DEAD-ZONE]` vs `RH ENTRY [BEAR-SPIKE]` for observability
- Battery verified: 39/39, 100% clean

**Product Manual — Session 16**
- Leather cover: Pillow-generated leather texture (directional grain, pores, vignette)
  Burned lettering (3-layer: heat halo + char + highlight). Ouroboros brand mark.
  SOLVE ET COAGULA motto arc. Border tooling in blood-red/near-black.
- Parchment pages: aged cream texture with fiber noise, age staining, edge darkening,
  water spots. All 27+ sections have parchment as page background.
- Da Vinci trophy NFTs: SVG color palette swapped to earth tones (umber, sienna, gold),
  sfumato/canvas_texture/craquelure/varnish SVG filters injected, Playwright render,
  Pillow post-processing (warm grade, smooth, canvas noise, vignette).
- Full black/blood-red text palette: all styles updated:
    Body: #1a0000 (near-black)  |  CH: #8B0000  |  SH: #6B0000  |  SSH: #6B0000
    Captions: #2d0000  |  Table body: #1a0000  |  Tables: #6B0000 amber replaced
- Full cyberpunk/Hermetic blend pass (all 27 sections):
    SOLVE ET COAGULA = harvest-fold cycle; Athanor = trading engine;
    Council of eleven = TA indicators; AS ABOVE SO BELOW = Smart Wire;
    Laws of the Art = SADP scar map; Written tradition = HOP file

### Open items

**NEW THIS SESSION (potential tuning):**
- Hunger/satiety constants (0.20 scale, 0.40/0.45 multipliers) — empirical
- Charge bar rate (0.05+H×0.10) and min release size — empirical
- R43 fee guard causes fold queue to age longer; consider fold-abandon at age>150

**CRITICAL (blockers):**
- RSK-001: Provisional patent MUST be filed before open sourcing — PATENT BEFORE GITHUB
- TD-003: Circuit breaker on exchange API (BLOCKS paper trading on live exchange)
- TD-004: Idempotency on trade submission (BLOCKS paper trading on live exchange)
- TD-007: ZK circuit for trustless adjudication (BLOCKS mainnet competition launch)
- TD-008: competition_tab.py runs local simulation (WRONG — R28 violation, v3.9.0 fix)

**HIGH:**
- Deploy ACRV.sol → CompetitionRegistry.sol → AcervatorTrophy.sol to Base Sepolia
- Update base_config.py with deployed contract addresses after Sepolia deploy
- Call setTierSvg() for all 5 tiers on AcervatorTrophy after deployment
- Build real PoA P2P protocol (v3.9.0 — see ADR-009 and TD-008):
  · relay/relay_server.py (FastAPI/WebSocket relay server)
  · src/competition/relay_client.py (WebSocket client, message routing)
  · Add AcceptMessage + HeartbeatMessage to challenge_protocol.py
  · Rebuild competition_tab.py: relay connect → challenge flow → active trading
  · Update CompetitionRegistry.sol: bots activate competition (not owner)
- TD-001: _sim_scrumming_tick CC=365+ refactor (v4.0.0) — R31 violation

**MEDIUM:**
- **SADP Portability v1.3 — COMPLETE** (impl/, CAPABILITY_MATRIX, SPEC-CORE)

**LOW:**
- Plymouth boot splash for AcervatorOS (deferred)
- GitHub Actions CI/CD pipeline
- Trophy gallery integration into competition tab

---

## [RULES — ALL ACTIVE, ALL ENFORCED]

# ═══════════════════════════════════════════════════════════════════════════
# SADP — STRUCTURED AI DEVELOPMENT PROTOCOL
# Version: 1.4  |  Released: 2026-04-18–19
#
# Version history:
#   1.0  R1–R35   Core rules — engine, GUI, testing, docs, session management
#   1.1  R36      FTP (Follow the Procedure) — user-invoked compliance gate
#                 Dependency graph (depends_on field in all rules)
#                 R37 Uncertainty Declaration
#   1.2  R38      SADP Annotations on Critical Paths
#                 Application-embedded governance (# sadp: annotations)
#                 version_sweep.py extended with 4 SADP checks (14–17)
#                 187 annotations backfitted across trading + competition layer
#   1.3  R39      Atomic File Migration
#                 Pre-migration manifest + completeness verification
#                 GROUP N. Canonical failure: sadp/ 4-of-11.
#   1.4  R40      Episodic Memory (LTM)
#                 LTM: query syntax, memory_tools.py, 50 bootstrapped entries
#                 R35 fill% interaction, R26 write obligation extended
#        R41      GUI Widget Initialization Scope Safety
#                 No cross-method scope refs — self.attr not bare var
#                 Both instantiation modes must be verified on _setup_ui() change
#                 GROUP P. Canonical failure: if sim_mode: → NameError
#        R42      Cross-Engine Sync (Simulator ↔ Battery)
#                 Any engine logic change in simulator.py MUST mirror in run_v3192
#                 GROUP Q. Canonical failure: session 17 REH/Shadow not synced
#        R43      Fee Guard — No Trade If Profit ≤ Fee
#                 Pre-check before state mutation. CORE protection class.
#                 GROUP R. Canonical failure: ADA Bear -61% $80 adv on $160 fees
#
# SADP — ADMINISTRATIVE CONTROL LAYER
# Rule administration: LOCK / UNLOCK / SUSPEND / RESTORE / STATUS / LIST / AUDIT
# (SADP = Structured AI Development Protocol — independent of any product branding)
# ═══════════════════════════════════════════════════════════════════════════

The AI recognises RULE commands typed in conversation and executes them
by calling src/core/rule_registry.py. State is persisted in sadp/RULE_REGISTRY.json.

COMMAND SYNTAX:
  RULE LOCK    R<N> [--reason "..."]          Lock a rule (default state)
  RULE UNLOCK  R<N> [--reason "..."]          Unlock for modification
  RULE SUSPEND R<N> --reason "..." [--expires v<X.X.X>]   Temp deactivate
  RULE RESTORE R<N>                           Reactivate suspended/deprecated rule
  RULE STATUS  [R<N>]                         Show all rules or single rule detail
  RULE LIST    [--locked|--unlocked|--suspended|--all]  Filter by state
  RULE AUDIT   [--last N]                     Show last N state changes

LOCK STATES:
  LOCKED      Active and immutable. AI cannot bypass, waive, or modify without
              explicit RULE UNLOCK. Violation = R25 infraction.
  UNLOCKED    Active, normal operation. Can be modified/waived with justification.
  SUSPENDED   Temporarily inactive. Reason mandatory. Noted in every R25 re-read.
  DEPRECATED  Superseded. Retained for history. Not enforced.

PROTECTION CLASSES:
  CORE        R1, R5, R10, R11, R12 — algorithm invariants. Cannot be SUSPENDED
              or DEPRECATED. Only LOCKED or UNLOCKED. Attempting to suspend
              a CORE rule returns an error.
  STANDARD    All other rules. Any state permitted.

AI BEHAVIOUR WHEN RULES ARE LOCKED/SUSPENDED:
  • LOCKED: The AI must refuse any action that would violate the locked rule.
    If the user requests something that would require bypassing it, the AI
    states the lock, names the rule, and requires RULE UNLOCK before proceeding.
  • SUSPENDED: The AI notes the suspension at the start of every R25 re-read.
    The suspended rule is not enforced for the duration of the suspension.
  • On session open: the AI must call RULE STATUS (or read sadp/RULE_REGISTRY.json)
    to detect any suspended or unlocked rules and announce them prominently.

EXAMPLES:
  RULE LOCK R6
  RULE UNLOCK R17 --reason "Debugging layout regression"
  RULE SUSPEND R20 --reason "Single-sim targeted research" --expires v3.7.0
  RULE RESTORE R20
  RULE STATUS
  RULE AUDIT --last 10

# ═══════════════════════════════════════════════════════════════════════════

R1:  _sim_target += profit after EVERY fold (regular + boost).
R2:  Landing Strip v2 import: from ..trading.ta_engine import detect_landing_strip_v2
R3:  Do NOT reset targeting_mode to SEARCH after scrum or fold.
R4:  Trend-hold override when delta >= 2× interval OR band_travel triggered.
R5:  Bearish candle base confidence = 0.15 (not 0.0).
R6:  Simulator has TWO execution paths. Change both or neither.
     Foreground: _sim_tick_inner()   Background: _run_background()
     RAIntSimBat: run_v3192()
R7:  HA candles ONLY. No toggle. UP=cyan(0,210,255), DOWN=purple(180,0,200).
R8:  CENTER in HBoxLayout: addStretch() BEFORE AND AFTER the group.
R9:  _init_live_monitor() must be called AFTER _setup_ui() and _setup_status_bar().
R10: BB Bullseye requires delta_pct >= interval (not just delta > 0).
R11: Hedge Rebalance = SEPARATE upfront reserve. NOT profit-skimming from USD.
R12: Smart Target Increase: cap new_target at holdings × price × 0.995.
R13: NEVER use PERIODS list as positional lookup.
     Use ASSET_PERIODS[symbol][period_idx] directly.
R14: BATTERY_ASSETS = original 13 only. BATTERY_PERIODS = original 3 only.
     Do not expand either without creating a new named constant.
R15: Live data in run_portfolio: fetch_live_ohlcv(symbol, year_str).
R16: Module loading in RAIntSimBat: register in sys.modules BEFORE exec_module.
R17: GUI elements must NOT change size or dimensions without explicit direction.
     setFixedSize / setFixedWidth / setFixedHeight / setMinimumWidth /
     setMaximumWidth / setMinimumHeight / setMaximumHeight / setSizePolicy /
     stretch factors / margins: NONE may be added, modified, or removed
     unless the user explicitly points at that widget and requests the change.
R18: Pre/post dimension check on all GUI work. Before touching any file with
     GUI layout code: record all widget dimensions in the affected area.
     After the change: verify those dimensions are unchanged (except the ask).
R19: TRACE FIRST, FIX SECOND. When the user reports an unexpected change:
     diff the file → layout hierarchy → hypothesis → fix.
     Never attempt a fix before confirming root cause.
R20: FULL BATTERY BY DEFAULT. "Run simulations" or "run research" (with no
     further qualification) = python RAIntSimBat.py (all 39 sims, always).
R21: ALL RESEARCH GOES INTO THE PRODUCT MANUAL.
     Every battery run, new mechanism, strategy comparison, or gap analysis
     must be added as a new numbered section in generate_essay.py and the
     PDF regenerated. generate_essay.py + acervator_product_manual_v3_3_0.pdf
     ARE the record. Nothing significant is documented elsewhere.
R22: When updating RAIntSimBat engine logic, ALWAYS run the full battery
     BEFORE the change and AFTER. Report: win rate, total advantage, avg
     advantage, per-regime breakdown, re-entry count. Document both runs in
     the Product Manual. No engine change ships without this pre/post pair.
R23: Hop# increments ON HOP PROMPT. The moment a new AI delivers the
     HANDSHAKE PROMPT ("So you would like to build a trading bot?..."),
     it must immediately rename this file to ACERVATOR_HOP(N+1).md and
     update all references before doing anything else. The hop counter
     advances at greeting, not at session end.
R24: OFFICIAL DOCUMENTS FOR HUMAN VIEWING → PDF. Any guide, specification,
     report, plan, or register that a human is expected to read as a
     document must be generated as .pdf. Keep .md (or other source format)
     only where the file is referenced by tooling, rendered by GitHub/git,
     or consumed by another part of the project.
     Rule of thumb:
       Human reads it as a document       → .pdf
       GitHub renders it / git tracks it  → .md
       Machine parses / imports it         → .json / .txt / .py
     Affected: docs/ formal documents (SRS, Roadmap, Risk Register, Test Plan,
     PM Framework). Not affected: README.md, CHANGELOG.md, CONTRIBUTING.md,
     ACERVATOR_HOP*.md, ADRs (git-tracked), AI_DEVELOPER_GUIDE.md (AI-consumed).
R25: MICRO-MANAGEMENT LOOP — MANDATORY WORK SAMPLING WITH INLINE QA.
     Every project prompt is scored for complexity. When complexity threshold
     is met, the AI MUST pause and perform a rules re-read + inline QA check
     before continuing.

     COMPLEXITY THRESHOLD (trigger R25 when ANY of these are true):
       • 3 or more files will be modified in one prompt
       • Engine logic in RAIntSimBat/RAIntSimBat.py or simulator.py is touched
       • A new indicator, mechanism, or gate is being added or removed
       • A pre/post battery (R22) is required
       • The prompt spans multiple system layers (GUI + engine + manual)

     R25 PROCEDURE (execute in order, do not skip):
       STEP 1 — RE-READ RULES: Read every rule R1–R42 before writing code.
                Confirm each is respected by the planned approach.
       STEP 2 — DECLARE INTENT: State explicitly what files will be touched,
                what will change, and which rules apply.
       STEP 3 — INLINE QA GATES: After each file change, before moving to the
                next, verify:
                  a) Syntax check (ast.parse for .py)
                  b) Rule compliance spot-check (R6 two paths, R17 no dim
                     changes, R22 pre/post if engine touched)
                  c) No unintended side-effects on adjacent code
       STEP 4 — FINAL SWEEP: After all changes, run full syntax check across
                all modified files and confirm R6 both paths are consistent.

     VERSION BUMP SWEEP (upgrade — every 0.1v increment):
       When the version number increments by 0.1 (e.g., 3.7.0 → 3.7.0),
       a full code optimization and security sweep MUST be run and MUST PASS
       before the release is considered valid.

       Command: python src/core/version_sweep.py --report

       The sweep checks (10 categories):
         1. Syntax         — every .py file parses cleanly
         2. Version        — all version strings match src/__init__.py
         3. Secrets        — no hard-coded API keys, tokens, or key material
         4. Insecure code  — eval(), os.system(), MD5, plain HTTP, shell=True
         5. Debug          — no breakpoint(), pdb, debug prints left in
         6. Unused imports — LOW findings for cleanup backlog
         7. R6 compliance  — both execution paths have matching gates
         8. Requirements   — key imports declared in requirements files
         9. File hygiene   — no .pyc, .DS_Store, .env files committed
        10. TODO/FIXME     — count and promote to Risk Register

       PASS GATE: CRITICAL = 0 AND HIGH = 0
       Results: JSON → RAIntSimBat/reports/sweep_v{version}_{date}.json
                PDF  → docs/pdf/acervator_sweep_v{version}_{date}.pdf  (R24)

       v3.7.0 sweep result: PASSED (0 critical, 0 high, 20 medium, 264 low)
       Medium findings: exec() in intentional wrappers (documented),
         MD5 in non-cryptographic caching, plain HTTP in fallback URLs.
       Low findings: 263 unused imports (cleanup backlog for v3.7.0).

     FAILURE MODE THIS RULE PREVENTS:
       Without R25, complex multi-file prompts accumulate small inconsistencies
       (wrong indices, missing R6 path, stale rule reference) that compound
       into regressions. The Ichimoku off-by-one and the flat-twist regression
       both occurred because changes were made without stopping to verify
       intermediate state. R25 makes the AI stop, look, and confirm at each
       boundary.
R26: DEVELOPMENT CHRONICLE — MANDATORY SESSION CLOSE UPDATE.
     DEVELOPMENT_CHRONICLE.md is the narrative project record. It captures
     decisions, regressions, key insights, and the human context behind the
     work. The CHANGELOG records what changed. The Chronicle records why it
     matters and what happened during development.

     UPDATE TRIGGER: At session close (before packaging the final zip),
     the AI MUST append a Chronicle entry covering the current session.

     REQUIRED ENTRY FORMAT:
       ================================================================================
       SESSION: YYYY-MM-DD  (Session N — brief title)
       VERSIONS: vX.X.X → vX.X.X
       ================================================================================

       WHAT WAS BUILT:
         • [Feature or fix]: one-line description of what changed

       KEY DECISIONS & RATIONALE:
         • Why something was done the way it was (not just what)
         • Alternatives considered and why they were rejected
         • Research findings and what they mean

       REGRESSIONS CAUGHT:
         • Any battery regression, bug, or false assumption discovered and fixed
         • The diagnosis: what caused it, how it was identified

       NEGATIVE RESULTS:
         • Things tried that didn't work and why (equally valuable as successes)

       KEY INSIGHT (session close):
         One sentence capturing the most important thing learned this session.

     CONTENT STANDARD:
       The chronicle is a permanent record. Future developers, patent reviewers,
       and the next AI session will read it. Write for understanding, not just
       for completeness. A regression that was caught and fixed is MORE valuable
       to document than a feature that worked first try — it shows the system
       is self-correcting and the methodology is sound.

     DO NOT SKIP: Even in short sessions. Even if "nothing interesting happened."
     The absence of regressions is itself worth recording.

     FAILURE MODE THIS RULE PREVENTS:
       Without R26, the narrative record of the project falls silent at the point
       where the most important work happens. The chronicle already missed v3.2.7
       through v3.7.0 — the entire indicator suite, USB auth, demo runner, version
       sweep, and R25 — because no rule required it. Those sessions contained the
       most technically sophisticated work of the project and none of it has a
       narrative record. R26 ensures this never happens again.

# ═══════════════════════════════════════════════════════════════════════════
# SADP GOVERNANCE LAYER — Rule Taxonomy R1 through R27
# ═══════════════════════════════════════════════════════════════════════════

  GROUP A — ENGINE & ALGORITHM INTEGRITY
    R1   Target increments after every fold
    R3   No targeting_mode reset after scrum/fold
    R4   Trend-hold override threshold
    R5   Bearish candle base confidence = 0.15
    R6   Two execution paths — change both or neither
    R10  BB Bullseye delta threshold
    R11  Hedge reserve isolation
    R12  Smart Target cap
    R13  ASSET_PERIODS lookup (never positional)
    R14  Battery asset/period constants are fixed
    R15  Live data routing in run_portfolio
    R16  Module loading order in RAIntSimBat

  GROUP B — GUI & DISPLAY
    R7   HA candles only (no toggle)
    R8   HBoxLayout centering with addStretch()
    R9   init_live_monitor() startup sequence
    R17  No GUI dimension changes without approval
    R18  Pre/post dimension check on all GUI work
    R19  Trace first, fix second

  GROUP C — TESTING & VALIDATION
    R20  Full battery default (all 39 sims)
    R22  Pre/post battery on any engine logic change

  GROUP D — DOCUMENTATION & RECORDS
    R21  All research → Product Manual (generate_essay.py)
    R24  Human-facing documents → PDF (R24)
    R26  Development Chronicle → mandatory session-close entry
    R27  Documentation Ecosystem → all formal docs stay current (see below)

  GROUP E — SESSION & RELEASE MANAGEMENT
    R23  Hop file rename on new AI session
    R25  Micro-Management Loop + version bump sweep

  GROUP F — CODE CONSISTENCY
    R27  (also) Downstream variable and key consistency (see below)

# ═══════════════════════════════════════════════════════════════════════════

R27: DOCUMENTATION ECOSYSTEM & CODE CONSISTENCY — KEEP ALL SYSTEMS CURRENT.
     R21, R24, R26 cover the Product Manual, PDF output, and Chronicle.
     R27 covers everything else. It has two parts.

     PART A — FORMAL DOCUMENTATION SYNC
     When any of the following change, the corresponding document MUST be
     updated in the same session. Do not defer to a future session.

       AI_DEVELOPER_GUIDE.md
         UPDATE WHEN: a new rule is added or modified, a new command-line
         tool is added, the development workflow changes.
         TRIGGER: Any Rxx rule change in ACERVATOR_HOP2.md.

       docs/srs/SRS.md (IEEE 29148)
         UPDATE WHEN: a new feature is implemented that adds, changes, or
         removes a stated requirement. Update the relevant FR-xxx / NFR-xxx
         entry and the traceability matrix.
         TRIGGER: New indicators, new mechanisms, new GUI features,
         authentication changes.

       docs/ROADMAP.md
         UPDATE WHEN: a feature in the "Must Have" or "Should Have" list
         ships. Move it to the relevant completed version block.
         TRIGGER: Every version bump where features shipped.

       docs/RISK_REGISTER.md
         UPDATE WHEN: a new technical or business risk is identified, or an
         existing risk's probability/impact changes.
         TRIGGER: Patent filing status, new security findings, new
         dependencies, new deployment modes.

       docs/adr/ (Architecture Decision Records)
         CREATE A NEW ADR WHEN: a significant architectural decision is made
         that future developers will need to understand. Format: Nygard.
         Examples: adding a new indicator category, changing the battery
         engine interface, new authentication mechanism, new deployment path.
         Trigger: Any change that makes the question "why was it done this
         way?" likely to arise in a future session.

       README.md
         UPDATE WHEN: the version number changes, new major features ship,
         setup instructions change, new dependencies added.
         TRIGGER: Every 0.1v version bump.

     PART B — CODE CONSISTENCY CHECKS
     These are deep-nested consistency issues that syntax checks cannot catch.
     The version_sweep.py (R25) now includes check 11 for snapshot keys.
     The following must also be verified manually on any indicator change:

       ta[] SNAPSHOT KEY CONSISTENCY (auto-checked by version_sweep check 11)
         Every key READ via ta.get("key") or ta["key"] in simulator.py
         confidence gates MUST be SET in the snapshot dict in
         _compute_ta_snapshot(). A missing key silently returns None — the
         gate branch never fires and the indicator is effectively disabled.
         This is undetectable at runtime and invisible to syntax checking.
         v3.7.0 found 10 missing Ichimoku alias keys (gates added during
         rewrite without updating snapshot). Silent indicator failure for
         ichi_chikou_abv, ichi_tk_in, ichi_tk_below, ichi_sks_bull/bear, etc.

       INDICATOR PARAMETER CONSISTENCY
         When an indicator has a configurable period or threshold (e.g.,
         MFI period=14, BB period=20, Supertrend multiplier=3.0), the value
         in ta_engine.py MUST match the value hardcoded in the inline gate
         in run_v3192. If they diverge, the battery and live trading evaluate
         different signals. Verify on any indicator parameter change.

       INLINE GATE VARIABLE NAMING
         Inline gate blocks in run_v3192 use short temp variable names
         (_j, _k, _sm, _adx, etc.). These are scoped to their block but
         Python has no formal block scope. Name-check any new gate block
         against adjacent blocks for potential shadowing. The version_sweep
         "unused imports" check does not cover local variable shadowing.

     FAILURE MODE THIS RULE PREVENTS:
       Without R27, formal documentation drifts from implementation. The SRS
       describes a system that no longer exists. The roadmap shows features
       as planned that shipped three versions ago. ADRs are absent for
       decisions that took hours to make and will take hours to rediscover.
       The code has silent indicator failures because gate logic and snapshot
       dict were updated in different sessions with no consistency check.
       R27 makes documentation-as-code a first-class project requirement,
       not an afterthought.

# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP G — FINANCIAL SOFTWARE STANDARDS (R28–R29)
# ═══════════════════════════════════════════════════════════════════════════

R28: FAIL LOUDLY — EXPLICIT FAILURE OVER SILENT DEFAULT.
     SOURCE: "The Pragmatic Programmer" (Hunt & Thomas, 1999) — "Dead programs
     tell no lies." Python Zen: "Errors should never pass silently, unless
     explicitly silenced." Design by Contract (Bertrand Meyer, 1986).

     PRINCIPLE: A function that cannot produce a valid result must raise a
     descriptive exception, not return None and let the failure propagate
     silently. The crash must occur as close to the cause as possible —
     not 200 lines downstream in a gate branch that simply doesn't fire.

     CANONICAL VIOLATION (now fixed): ta.get("ichi_chikou_abv", None).
     The key was missing from the snapshot. The gate received None. The branch
     evaluated to False. The Ichimoku gate silently never fired for the entire
     life of the indicator. Zero runtime evidence. This is the most dangerous
     class of bug: syntactically valid, passes all tests, does nothing.

     RULES:
       1. Functions with a defined return type must raise ValueError or
          RuntimeError if they cannot produce a valid value. Document None
          returns explicitly where "no result" is a valid outcome.
       2. ta.get() calls in confidence gates must use version_sweep check 11
          (snapshot key consistency) — not rely on False defaults.
       3. Any new .get() call on a dict with a None default in a critical
          path (trade execution, confidence calculation) triggers an R25
          inline QA step to verify the key is guaranteed to be present.
       4. Exception messages must include: what was expected, what was
          received, and which function is responsible.

     TECH DEBT: TD-003, TD-004 are downstream consequences of silent failure.

R29: IDEMPOTENCY — FINANCIAL OPERATIONS SAFE TO RETRY.
     SOURCE: Pat Helland (Amazon/Microsoft), "Idempotence is not a Medical
     Condition" (ACM Queue, 2012). REST API design principles. Payment
     processing industry standards. ISO 20022 financial messaging.

     PRINCIPLE: Any function that submits, modifies, or cancels a trade must
     produce the same observable result if called multiple times with the same
     arguments. The second call must either succeed identically or return an
     explicit "already done" status — never create a duplicate order.

     WHY THIS MATTERS: Exchange API calls fail. Networks time out. The bot
     retries. Without idempotency, a timeout-then-retry creates two sell
     orders at the top of a price peak — both fill — and the position is
     immediately wrong. This failure mode is catastrophic and silent until
     the next fold attempt finds insufficient inventory.

     RULES:
       1. Every order submission must include a client_order_id that is
          deterministically derived from trade parameters:
          hash(symbol + side + quantity + price_tier + session_id) % 10**12
       2. On reconnect or exchange re-initialisation, the bot must query
          open orders before placing new ones and reconcile against
          expected state.
       3. The scrumming_bot.tick() function must check for in-flight orders
          before issuing a new one (query first, act second).
       4. REQUIRED STATUS: TD-004 must be resolved before paper trading.

# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP H — CODE QUALITY STANDARDS (R30–R32)
# ═══════════════════════════════════════════════════════════════════════════

R30: SEMANTIC VERSIONING — MAJOR.MINOR.PATCH DISCIPLINE.
     SOURCE: semver.org — Tom Preston-Werner (GitHub co-founder), 2010.
     Widely adopted: npm, pip, cargo, Maven, NuGet.

     PRINCIPLE: Version numbers are a communication contract. Each component
     communicates a specific type of change to anyone consuming the software.

     DEFINITIONS:
       MAJOR (X.0.0): Breaking change. Any of:
         — Battery baseline contract changes (new result keys, removed keys)
         — SADP handoff format changes (HOP file structure)
         — Public API changes that break existing integrations
         — Exchange interface changes incompatible with prior bots
       MINOR (x.Y.0): New backward-compatible feature. Any of:
         — New indicator, new exchange, new GUI feature
         — New SADP rule, new battery test
         — New AcervatorOS component
       PATCH (x.y.Z): Backward-compatible bug fix. Any of:
         — Import placement error (logging_engine __future__ fix = 3.4.1)
         — Spec file rename (= 3.7.0 → 3.4.1 patch)
         — Documentation correction that doesn't add content
         — Single-line bug fixes with no behavioural change

     CURRENT VIOLATION: All version bumps in v3.x history are MINOR.
     Bugfixes and governance changes have been merged as MINOR bumps.
     Apply correct SemVer from v3.7.0 onward. See TD-005.

     AI RULE: Before any version bump, the AI must declare:
       "This is a MAJOR/MINOR/PATCH bump because: [reason]"
     If the reason doesn't match the definition, challenge the classification.

     SESSION-CLOSE EVALUATION (addendum — closes the lag gap):
     At every session close, BEFORE packaging the zip, the AI must evaluate:
       1. List all changes made this session
       2. Classify each as MAJOR / MINOR / PATCH
       3. Apply the highest classification as the version bump
       4. If no changes qualify as MINOR or MAJOR, issue a PATCH bump
     There is no such thing as "no version change" in a session that
     delivered working code. Governance changes, documentation additions,
     and bug fixes all qualify. Every session that packages a zip must
     bump the version. This evaluation is part of R26 session-close protocol.

R31: McCABE COMPLEXITY GATE — CYCLOMATIC COMPLEXITY LIMITS.
     SOURCE: Thomas J. McCabe, "A Complexity Measure" (IEEE Transactions on
     Software Engineering, 1976). NIST SP 500-235. US Air Force guidance
     on software quality. Empirical research: functions with CC > 20 have
     demonstrably higher defect density (Capers Jones, Software Engineering
     Economics).

     PRINCIPLE: Cyclomatic complexity (CC) counts the number of linearly
     independent paths through a function: CC = edges - nodes + 2(connected
     components), approximately = number of branching statements + 1.
     High CC predicts defects, predicts test inadequacy, predicts maintenance
     cost.

     CURRENT STATE:
       _sim_scrumming_tick: CC ≈ 365, 1112 lines  [CRITICAL — TD-001]
       run_v3192:           CC > 500              [CRITICAL — TD-002]
       scrumming_bot.tick:  CC ≈ 121, 416 lines   [HIGH]

     THRESHOLDS:
       CC  1–10   Simple. No action required.
       CC 11–20   Moderate. Acceptable with good tests.
       CC 21–50   Complex. Requires COMPLEXITY: comment and R25 declaration.
       CC 51+     Untestable. Requires architectural review. AI must not add
                  new complexity to an existing function in this range.

     RULES:
       1. New functions must have CC ≤ 20. Exceeding 20 requires R25
          declaration with explicit justification.
       2. Exceeding CC 50 blocks merge until an architectural review is
          documented in TECH_DEBT.md with a target version.
       3. The AI must NEVER add new branches to _sim_scrumming_tick,
          run_v3192, or scrumming_bot.tick without R25 + TD entry.
       4. The version sweep (R25) should report the top 5 most complex
          functions as LOW findings for visibility.

R32: CIRCUIT BREAKER — STOP CALLING FAILING DEPENDENCIES.
     SOURCE: Michael Nygard, "Release It!: Design and Deploy
     Production-Ready Software" (2007). Martin Fowler, CircuitBreaker
     pattern (martinfowler.com, 2014). Hystrix (Netflix OSS), Polly (.NET).

     PRINCIPLE: When a service dependency (exchange API) fails repeatedly,
     continuing to call it causes: rate-limit exhaustion, IP bans, retry
     storms that cascade across all dependent operations, and trades left
     in an indeterminate state. A circuit breaker detects the failure and
     stops calls for a configurable recovery window.

     THREE STATES:
       CLOSED   Normal operation. Calls pass through. Failure count resets
                on success. When failure_count > threshold → OPEN.
       OPEN     Dependency is failing. ALL calls immediately return an error
                without touching the API. After cooldown_seconds → HALF-OPEN.
       HALF-OPEN One test call is allowed. Success → CLOSED. Failure → OPEN.

     CURRENT STATE: No circuit breaker exists. Exchange API failures cause
     immediate retry loops. TD-003.

     RULES:
       1. Before paper trading: every exchange API call in ccxt_connector.py
          must be wrapped in a circuit breaker instance.
       2. Default thresholds: failure_threshold=5, cooldown_seconds=60.
       3. The circuit breaker state must be logged to the trade audit log.
       4. Implementation target: src/exchange/circuit_breaker.py — v3.7.0.
       5. The AI must not implement paper trading (real money, even paper)
          without TD-003 resolved.

# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP I — ARCHITECTURE STANDARDS (R33–R34)
# ═══════════════════════════════════════════════════════════════════════════

R33: IMMUTABLE AUDIT LOG — APPEND-ONLY FINANCIAL RECORDS.
     SOURCE: Sarbanes-Oxley Act (SOX, 2002) audit trail requirements.
     MiFID II Article 25 trade reporting. GDPR Article 30 (records of
     processing). General Ledger accounting principle: debits and credits,
     never erasure. Pat Helland, "Immutability Changes Everything" (2015).

     PRINCIPLE: Every state-changing financial operation must produce a log
     entry that is written once and never modified. The log must contain
     sufficient information to reconstruct what happened, why it happened,
     and what the state was before and after. "If it isn't logged, it
     didn't happen" (financial auditing axiom).

     REQUIRED FIELDS FOR TRADE LOG ENTRIES:
       ts_utc       ISO 8601 UTC timestamp (NOT local time)
       op           Operation type: SCRUM | FOLD | HEDGE | CANCEL | REJECT
       session_id   Current bot session UUID
       order_id     Exchange-provided order ID
       client_id    Deterministic client_order_id (see R29)
       symbol       Trading pair
       side         BUY | SELL
       qty          Quantity (asset units, not dollars)
       price        Executed price
       fee          Fee paid (quote currency)
       before_state Target, held, balance before
       after_state  Target, held, balance after
       reason       Why this trade was triggered (gate conditions met)

     RULES:
       1. The AI must never write code that modifies or deletes an existing
          trade log entry.
       2. Log rotation must be archival (move to .gz) — never truncation.
       3. Log entries must use UTC timestamps. Local time in logs is a bug.
       4. A correlation_id must thread through all operations in a single
          scrum-fold cycle.

R34: SINGLE RESPONSIBILITY PRINCIPLE — ONE REASON TO CHANGE.
     SOURCE: Robert C. Martin (Uncle Bob), "Agile Software Development,
     Principles, Patterns, and Practices" (2002). Originally from Tom
     DeMarco's "Structured Analysis" (1979). The S in SOLID.

     PRINCIPLE: A module, class, or function should have exactly ONE reason
     to change. If you describe a function's purpose using the word "and",
     it has more than one responsibility. Functions with multiple
     responsibilities are the primary defect attractors in large codebases.

     CANONICAL VIOLATION: _sim_scrumming_tick() (1112 lines, CC 365)
     does ALL of the following simultaneously:
       1. Runs simulation logic (scrums, folds, profit folding)
       2. Updates GUI display (chart, performance panel, indicators)
       3. Triggers audio feedback (SFX, trade sounds)
       4. Calculates performance metrics (Sharpe, Sortino, drawdown)
       5. Manages simulation state (tick counter, mode transitions)
       6. Evaluates all 11 indicator confidence gates
       7. Handles the R6 foreground path business logic
     Seven responsibilities. Any change in any one of them requires touching
     all seven. This is the most dangerous function in the codebase.

     RULES:
       1. New functions must have exactly ONE stated purpose, expressed in
          a one-line docstring without the word "and".
       2. If the AI adds a new responsibility to an existing function, it
          must declare this in R25 Step 2 and create a TD entry.
       3. The refactor of _sim_scrumming_tick is documented in TD-001 as
          a v4.0.0 target. Until then: no new responsibilities may be added.
       4. The version sweep should report functions with length > 300 lines
          as MEDIUM findings (add to check 13 — future).

     NOTE: Long functions are not automatically violations. A 300-line
     function with ONE clear responsibility (like generate_qss in
     theme_engine.py — it generates one CSS string) is acceptable.
     The question is not length — it is the number of reasons to change.

# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP J — SESSION MANAGEMENT (R35)
#     R35  Context fill monitoring
#
#   GROUP K — USER-INVOKED COMPLIANCE GATE (R36)
#     R36  FTP (Follow the Procedure) — user-invoked compliance gate
#
#   GROUP L — UNCERTAINTY DECLARATION (R37)
#     R37  Uncertainty Declaration — state unknowns before proceeding
#
#   GROUP M — APPLICATION-EMBEDDED GOVERNANCE (R38)
#     R38  SADP Annotations on Critical Paths — code names its own governance
#
#   GROUP N — ATOMIC FILE MIGRATION (R39)
#     R39  Atomic File Migration — manifest before move, migrate as one unit
#
#   GROUP O — EPISODIC MEMORY AND LONG-TERM RECALL (R40)
#     R40  LTM Episodic Memory — structured session recall, LTM: query syntax
#
#   GROUP P — GUI WIDGET INIT + HISTORICAL REFERENCE VERIFICATION (R41-R42)
#     R41  GUI Widget Init — no cross-method scope refs; self.attr not bare var
#     R42  Historical/Artistic Reference — research first, checklist, declare gaps
#
#   GROUP P (cont.) — TEXT CONTRAST AND READABILITY (R42)
#     R42  Text Contrast — dark bg → light text, light bg → dark text
#          Canonical failure: #1a0000 text on #100000 bg — invisible, no error
#          Global color replacement must be followed by contrast audit
#          Approved: dark table body text = #e8d0b0 (warm parchment cream)
# ═══════════════════════════════════════════════════════════════════════════

R35: CONTEXT FILL MONITORING — TRACK AND REPORT CONVERSATION FILL PERCENT.
     SOURCE: Transformer attention mechanics (Vaswani et al., 2017;
     Liu et al. 2023 "Lost in the Middle"). Empirical observation across
     SADP sessions: rule violations and inconsistencies with earlier
     decisions increase measurably as context fill exceeds ~75%.

     PRINCIPLE: The AI's effective attention to early-conversation context
     degrades as the session grows. This is not a flaw to hide — it is a
     documented property of transformer architecture. The mitigation is
     awareness and proactive session management.

     FILL ESTIMATION:
       fill% = (approximate total conversation chars) / 200,000 × 100
       200,000 chars ≈ ~150K tokens ≈ a well-loaded Claude context window.
       This is an estimate, not an exact count. Report as "~N%".

     REPORTING REQUIREMENTS:
       1. R25 Step 2 (declare intent): always report "~N% context fill"
          as the first line of the intent declaration.
       2. R26 session close: include fill% in the chronicle entry.
       3. At ~75% fill: add an explicit flag:
          "⚠ CONTEXT FILL ~75%+ — RECOMMEND SESSION HANDOFF PREPARATION"
          Update the HOP file before the session reaches 85%.
       4. At ~85% fill: do NOT start new complex multi-file tasks.
          Instead: update HOP file, run version sweep, package zip,
          write chronicle, prepare handoff.

     FORGETFULNESS CALIBRATION:
       The fill% is a proxy for context degradation risk. Known symptoms
       of high fill% / context degradation:
         - Suggesting approaches already tried and rejected this session
         - Rule violations that were explicitly addressed earlier
         - Inconsistency between current code changes and earlier decisions
         - Missing files from R25 intent declarations
       Mitigation at high fill%:
         - Explicitly re-state key decisions before starting new work
         - Run RULE STATUS before any R25-level task
         - Reduce task scope — split into smaller units
         - Prefer session handoff over pushing through complex changes

     AI RULE:
       The AI must report fill% at every R25 Step 2 and every R26 close.
       There is no such thing as "I don't know the fill%" — use the
       estimation formula above. If unsure, round up conservatively.
       Reporting fill% is not optional even in short responses.

# ═══════════════════════════════════════════════════════════════════════════

R36: FTP (FOLLOW THE PROCEDURE) — USER-INVOKED COMPLIANCE GATE.

SYNTAX:
  FTP (Follow the Procedure): [task description]

TRIGGER: When the user prefixes any request with "FTP (Follow the Procedure):",
the AI MUST execute the full FTP procedure before writing any code, making any
file changes, or beginning implementation. No exceptions.

FTP PROCEDURE (execute in order — none of these steps may be skipped):

  STEP 1 — FULL RULE TABLE READ
    Read every active rule R1–R42. For suspended rules, note the suspension.
    This is non-negotiable. "I've read the rules" is not this step.
    The read happens — then the table is built.

  STEP 2 — RELEVANCE MAP (with dependency traversal)
    For each rule, evaluate: directly relevant to this stated task?
    Then traverse the dependency graph: for each RELEVANT rule R, also
    evaluate every rule in R's depends_on list. If a dependency is
    suspended or would be violated, flag it as a CONCERN even if the
    dependency rule itself was not directly triggered by the task.

    Produce a compact table:
      R[N] — RELEVANT: [how it applies to this task]
      R[N] — DEPENDENCY of R[X]: [dependency relationship]
      R[N], R[N] — Not applicable.
    Only rules with genuine relevance or triggered dependencies get
    individual lines. Irrelevant, non-dependent rules may be grouped.

    Example: task touches R29 (idempotency) → R29 depends_on R28 →
    also evaluate whether R28 (fail loudly) is active. If R28 is
    suspended, flag: ⚠ R28 SUSPENDED — R29 idempotency checks may
    not surface failures. This is a CONCERN.

  STEP 3 — CONSTRAINT DECLARATION
    For each relevant rule, state explicitly:
      • What constraint it places on the implementation
      • What the AI will specifically do to comply
      • Any tension with another rule (flag it; do not resolve silently)

  STEP 4 — COMPLIANCE VERDICT
    Before proceeding, issue exactly one of:
      ✓ COMPLIANCE CONFIRMED — no conflicts detected, proceeding
      ⚠ COMPLIANCE CONCERN: [issue] — proceeding with stated caveat
      ✗ COMPLIANCE BLOCKED: [reason] — cannot proceed until [condition met]

    A BLOCKED verdict requires explicit user acknowledgement before the AI
    proceeds. The AI does not self-unblock.

  STEP 5 — PROCEED
    Begin the task. Only after STEP 4 issues a CONFIRMED or CONCERN verdict.

OUTPUT FORMAT:
  The FTP block is a formal compliance record, not conversational preamble.
  Target: under 400 words (excluding rule text reproduced for reference).
  It must not be used as padding, qualification theatre, or delay.
  It must be complete. Abbreviated FTP is not FTP.

RELATIONSHIP TO R25:
  R25 is auto-triggered by the AI when complexity thresholds are met.
  R36 FTP is user-invoked on any task, regardless of complexity.
  When FTP is used on a task that also meets R25 thresholds: run both.
  FTP first (R36), then R25 inline QA gates during implementation.
  FTP does not replace R25.

RELATIONSHIP TO R35:
  If, during STEP 1, the context fill is at or above 85%, the AI must
  issue a COMPLIANCE BLOCKED verdict:
    ✗ COMPLIANCE BLOCKED: Context fill ~[N]% exceeds safe threshold for
      new task execution. Update HOP file and prepare handoff first.
  This prevents FTP from being used as a mechanism to start new work at
  the end of a session when R35 says to close.

WHEN TO USE (guidance for the human):
  FTP is appropriate when:
    • The task touches areas with a history of regression (R6 paths, R28-adjacent)
    • You want explicit assurance before a sensitive change
    • Starting a session and wanting orientation verified before the first task
    • After a gap in development where rule context may have drifted
    • The task seems simple but you want the safety check regardless
    • You have a feeling something could go wrong and want it documented before

AI RULE:
  "I'll keep R[N] in mind" is not compliance. The table must be explicit.
  Claiming to have read the rules is not the same as demonstrating it.
  The FTP output is the demonstration.

FAILURE MODE THIS RULE PREVENTS:
  Without FTP, the human has no direct mechanism to mandate the compliance
  gate on tasks that fall below R25's auto-trigger threshold. Small changes —
  a one-line fix, a config update, a single-file edit — bypass R25 entirely.
  These are exactly where silent rule violations accumulate: changes that
  seem too small to warrant a full re-read, applied by an AI whose earlier
  context has drifted. FTP gives the human a direct override: "I don't trust
  implicit compliance on this one. Show me the work before you touch anything."

EXAMPLE:
  User: FTP (Follow the Procedure): Add a new parameter to _sim_scrumming_tick
        that enables a 3% interval threshold on bearish candles.

  AI Response (before any code):
  ──────────────────────────────────────────────────────────────────────────
  FTP — COMPLIANCE CHECK
  Task: Add parameter to _sim_scrumming_tick for 3% interval on bearish candles
  Context fill: ~72%

  RELEVANCE MAP:
    R1  — RELEVANT: If the new parameter affects fold logic, target increment
          must still fire after every fold.
    R5  — RELEVANT: Bearish candle base confidence = 0.15. The new threshold
          must not change this baseline — it adds a second condition, it does
          not replace R5.
    R6  — RELEVANT: _sim_scrumming_tick is the foreground path. The identical
          gate must be added to _run_background() and run_v3192(). Three files.
    R25 — RELEVANT: 3+ files touched. R25 Step 2 required before implementation.
    R31 — RELEVANT: Adding a branch to _sim_scrumming_tick (CC≈365). Per R31
          rule 3: AI must not add new branches without R25 + TD entry.
    R34 — RELEVANT: New parameter adds a responsibility. Must not expand scope
          beyond the single stated purpose.
    R2, R3, R4, R7–R24, R26–R30, R32–R36 — Not applicable to this change.

  CONSTRAINTS:
    R6:   Change all three execution paths simultaneously. No partial update.
    R31:  TD entry required before implementation. Target version statement needed.
    R25:  This prompt now meets the R25 threshold. R25 procedure applies.

  ✓ COMPLIANCE CONFIRMED — proceeding with R25 Step 2 declaration next.
  ──────────────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP L — UNCERTAINTY DECLARATION (R37)
# ═══════════════════════════════════════════════════════════════════════════

R37: UNCERTAINTY DECLARATION — STATE WHAT YOU DON'T KNOW BEFORE PROCEEDING.

PRINCIPLE: When the AI is genuinely uncertain about a design decision —
not uncertain about syntax or mechanics, but uncertain about whether an
approach is correct — it must say so explicitly before writing any code.
"Proceeding with the best guess" without flagging the uncertainty is a
violation of this rule.

THE DISTINCTION:
  CERTAIN (no R37 trigger):
    "I'll use SHA-256 for the leaf hash." — this is a known-good choice.
    "I'll add a QTimer at 60ms." — this is a known implementation detail.

  UNCERTAIN (R37 triggers):
    "I'm not sure whether the fold should trigger at price < fold_ref
     or price < fold_ref × 0.995 — these produce different cycle counts."
    "I don't know if the relay should use WebSockets or HTTP polling —
     both would work but the trade-offs aren't clear for this use case."
    "I'm uncertain whether this change to the confidence gate will affect
     the 2022 historical battery results."

REQUIRED BEHAVIOUR when uncertainty is detected:
  1. STOP. Do not write the uncertain code.
  2. STATE the uncertainty explicitly:
     "UNCERTAINTY: I don't know whether [X] because [reason]."
  3. PROPOSE a resolution path — exactly one of:
     a) "This can be resolved by: running the battery before and after."
     b) "This can be resolved by: checking [specific source/file/rule]."
     c) "This requires a design decision from you: [question]."
     d) "This is a known unknown — I'll proceed with [choice] and flag
        it as a TD entry for later validation."
  4. WAIT for confirmation before proceeding, unless option (d) applies.

WHAT THIS PREVENTS:
  The AI that doesn't know but doesn't say so. This is the most dangerous
  failure mode in AI-assisted development because it produces confident-
  sounding output that looks correct but embeds an unverified assumption.
  The Ichimoku silent-failure bug (R28 canonical violation) was partly
  this: the AI wasn't certain the snapshot keys were present but didn't
  flag the uncertainty — it proceeded and the gate silently never fired.

SCOPE:
  R37 applies to design decisions, algorithm choices, and strategy-
  affecting logic. It does NOT apply to syntax, standard library usage,
  or well-established patterns where the AI has high confidence.
  Use judgment. When in doubt about whether to flag: flag it.

RELATIONSHIP TO R25 AND R36:
  R25 (Micro-Management Loop): R37 can trigger mid-implementation during
    an R25 inline QA step — if uncertainty is detected at STEP 3, the AI
    must declare it before continuing to the next file.
  R36 (FTP): Uncertainty detected during STEP 1 or STEP 3 must surface
    as a CONCERN in the compliance verdict. A BLOCKED verdict is issued
    if the uncertainty affects whether the implementation is safe to run.
  R37 is a dependency of R25 (listed in R25's depends_on).

FAILURE MODE THIS RULE PREVENTS:
  Without R37, the path of least resistance for the AI is to pick an
  approach, implement it with conviction, and let the battery reveal the
  error three sessions later. The cost of stating uncertainty is a
  one-sentence pause. The cost of not stating it is a silent regression
  that may be in production before it's found.


# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP M — APPLICATION-EMBEDDED GOVERNANCE (R38)
# ═══════════════════════════════════════════════════════════════════════════

R38: SADP ANNOTATIONS ON CRITICAL PATHS — CODE NAMES ITS OWN GOVERNANCE.

PRINCIPLE: Functions that touch the trading engine, fold logic, order
submission, competition layer, or audit log must carry a machine-readable
SADP annotation declaring which rules govern their behaviour. The version
sweep (R25) validates every annotation against the live rule registry
and flags violations as CRITICAL/HIGH findings.

ANNOTATION SYNTAX:
  # sadp: R1 R5 R28     — space-separated rule IDs
  # sadp: R28 R29 R33   — any rules that govern this function's behaviour

PLACEMENT: First non-blank line inside the function body. The annotation
is a comment — zero runtime cost, zero risk to the function.

WHAT THE SWEEP CHECKS (version_sweep.py checks 14–17):
  CHECK 14 — Annotation validation (R38):
    HIGH   — annotation references a SUSPENDED rule
    HIGH   — mandatory function is missing its annotation
    MEDIUM — annotation references an unknown rule ID
    INFO   — all valid annotations (coverage report)
  CHECK 15 — R28 silent failure patterns:
    HIGH   — bare except: in trading/competition modules
    MEDIUM — exception swallowed silently (except Exception: pass/continue)
    MEDIUM — .get(key, None) in a confidence/gate context
  CHECK 16 — R29/R33 gates:
    MEDIUM — submit/award function lacks idempotency marker
    HIGH   — log-write function truncates or overwrites existing entries
  CHECK 17 — Dependency graph propagation:
    MEDIUM — suspended rule undermines a rule that depends on it

MANDATORY ANNOTATIONS (HIGH if missing):
  simulator.py:_sim_scrumming_tick     → R1 R5 R6 R28 R31 R34
  scrumming_bot.py:tick                → R1 R5 R6 R28 R29 R31
  token_ledger.py:award                → R28 R29 R33
  merkle_log.py:append                 → R28 R33
  competition_engine.py:adjudicate     → R28 R29 R33

RATIONALE:
  SADP previously governed how the AI builds the application, but the
  application had no awareness of SADP. R38 closes this loop — the code
  names its own governance constraints, the tooling verifies them at every
  version sweep, and SADP becomes something the application actively carries
  rather than something only the AI session knows about.

EXPANSION RULE:
  When a new function is added to the trading engine, fold logic, order
  submission, competition layer, or audit log: add it to MANDATORY in
  check_sadp_annotations() in version_sweep.py. The next sweep will flag
  missing annotations as HIGH until they are added.

WHAT THIS RULE PREVENTS:
  Without R38, SADP rules exist in the HOP file and the AI's context, but
  are invisible in the codebase itself. A future developer (human or AI)
  reading _sim_scrumming_tick has no indication that R1, R5, R6, and R31
  all have specific implications for that function. The annotation makes
  the governance constraint co-located with the code it governs.


# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP N — ATOMIC FILE MIGRATION (R39)
# ═══════════════════════════════════════════════════════════════════════════

R39: ATOMIC FILE MIGRATION — IDENTIFY ALL ELEMENTS, MOVE AS ONE UNIT.

PRINCIPLE: Before any file restructuring, directory creation, or tool transfer,
the AI must enumerate every file that logically belongs to the unit being moved.
The manifest must be declared explicitly. Migration executes as one complete
operation. No partial moves ship.

TRIGGER: Any of the following:
  • Creating a new directory to house an existing set of related files
  • Moving a module, package, or subsystem to a new location
  • Restructuring a documentation tree
  • Consolidating scattered files into a single directory
  • Any prompt containing: "move", "migrate", "restructure", "reorganise",
    "put X in its own directory", "create a directory for"

REQUIRED PROCEDURE:
  STEP 1 — MANIFEST DECLARATION
    Before touching any files, produce an explicit list of every file that
    belongs to the logical unit being migrated. This requires answering:
      a) What files are the obvious members? (list them)
      b) What files reference or depend on these files? (check imports, paths)
      c) What files are part of the same conceptual system even if not
         directly linked? (e.g. docs, ADRs, tooling, tests)
      d) What files would a new developer expect to find in this directory
         if they were approaching the system cold?
    The manifest is not "files I can think of quickly." It is the complete
    logical membership of the unit.

  STEP 2 — MIGRATE ALL OR STOP
    Execute the migration for every file on the manifest in one session.
    If a file on the manifest cannot be migrated in this session (e.g.
    because doing so would break a dependency chain that requires more work),
    declare it explicitly as a DEFERRED item with a reason, and add a TD entry.
    Do not silently omit it.

  STEP 3 — COMPLETENESS VERIFICATION
    After migration, list the destination directory and confirm every manifest
    item is present. Report the result:
      ✓ All N manifest items present in [destination]
      ⚠ N of M items migrated. Deferred: [file] — [reason]

WHAT THIS RULE PREVENTS:
  The canonical failure: sadp/ directory created with 4 documentation files.
  The implementation (rule_registry.py, version_sweep.py), the continuity
  layer (ACERVATOR_HOP2.md), the ADR, the developer guide, and the chronicle
  were all logically part of the SADP system. None were on a manifest because
  no manifest was produced. The directory looked complete because the files
  that were top-of-mind were there. The files that were not top-of-mind
  were absent. A user opening sadp/ found 4 files instead of 11.
  R39 makes the manifest step non-negotiable.

RELATIONSHIP TO OTHER RULES:
  R27 (Documentation Ecosystem): R39 is a precondition for R27 compliance
    on restructuring tasks — you cannot keep all docs current if you don't
    know which docs belong to the unit being moved.
  R37 (Uncertainty Declaration): if the manifest is uncertain — "I'm not
    sure whether X belongs in this directory" — declare the uncertainty
    before proceeding (R37), then resolve it.
  R36 (FTP): any prompt that triggers R39 also runs FTP. The manifest
    declaration becomes part of the FTP STEP 3 constraint output.

EXAMPLE:
  User: "Put all SADP files in their own directory."

  AI (before creating sadp/ or touching any file):
  ─────────────────────────────────────────────────────────────────
  R39 MANIFEST — SADP system files:
  Documentation:
    sadp/README.md              (new — overview)
    sadp/SPEC.md                (new — R1-R38 extracted from HOP)
    sadp/CHANGELOG.md           (new — version history)
  Administrative layer:
    sadp/RULE_REGISTRY.json     (move from root)
    sadp/rule_registry.py       (copy from src/core/)
    sadp/version_sweep.py       (copy from src/core/ — contains checks 14-17)
  Continuity layer:
    sadp/ACERVATOR_HOP2.md      (copy — the HOP file IS the continuity layer)
  Architecture records:
    sadp/ADR-007-sadp.md        (copy from docs/adr/)
  Developer guidance:
    sadp/AI_DEVELOPER_GUIDE.md  (copy — SADP guidance for incoming AI)
  Records:
    sadp/DEVELOPMENT_CHRONICLE.md  (copy — narrative record)
    sadp/TECH_DEBT.md              (copy — TD register)

  Total: 11 files. Proceeding with full migration.
  ─────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP O — EPISODIC MEMORY AND LONG-TERM RECALL (R40)
# ═══════════════════════════════════════════════════════════════════════════

R40: LTM EPISODIC MEMORY — USE LTM: SYNTAX TO RETRIEVE DEEP PROJECT HISTORY.

LTM QUERY SYNTAX (type at start of prompt):
  LTM: <query>                    — keyword query across all entries
  LTM-CATEGORY: <CAT> <query>     — filter by REGRESSION/DECISION/INVENTION/
                                    RULE_CHANGE/FINDING/DEPENDENCY
  LTM-SESSION: <lo>-<hi> <query>  — filter by session range
  LTM-RULE: <RN> <query>          — filter by rule number
  LTM-ALL:                        — full index (blocked at ≥75% fill)

R35 INTERACTION:
  fill ≥ 85%: BLOCKED — initiate session handoff first
  fill ≥ 75%: summary mode — title + one sentence per entry only
  fill < 75%: full mode — top 5 complete entries + 6-10 as title+summary

WRITE OBLIGATION (R26 extension):
  At session close, add entries for: regressions caught, decisions made
  (with alternatives), inventions, rule changes, significant findings,
  critical dependencies. Run: python sadp/memory_tools.py add

TOOLING:
  python sadp/memory_tools.py query "your query here"
  python sadp/memory_tools.py stats
  python sadp/memory_tools.py regenerate
  python sadp/memory_tools.py add        (interactive wizard)

FILES:
  sadp/EPISODIC_MEMORY.json   50 entries bootstrapped, Sessions 1-15
  sadp/EPISODIC_MEMORY.md     Human-readable index (auto-generated)
  sadp/memory_tools.py        Query engine + CLI

EXAMPLE QUERIES THAT WORK:
  LTM: why did we choose Base blockchain
  LTM-CATEGORY: REGRESSION ichimoku silent failure
  LTM-RULE: R28 snapshot key consistency
  LTM-SESSION: 1-5 accumulation trading invention
  LTM: hedge rebalance design rationale
  LTM: trophy SVG empty strings
  LTM: SADP checkpoint loop rejected


# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP P — GUI WIDGET INITIALIZATION SCOPE SAFETY (R41)
# ═══════════════════════════════════════════════════════════════════════════

R41: GUI WIDGET INITIALIZATION — NO CROSS-METHOD SCOPE REFERENCES.

WHAT THIS RULE PREVENTS:
  The canonical Acervator failure (indicator_panel.py, repeated across sessions):
  A parameter received in __init__(self, sim_mode=False) was stored as
  self._sim_mode, then _setup_ui() was modified to branch on `if sim_mode:`
  rather than `if self._sim_mode:`. Python syntax checking PASSES because
  `sim_mode` is a valid name. The NameError only surfaces at runtime when
  _setup_ui() executes and `sim_mode` is not in its local or global scope.
  The failure is invisible in the compiled .exe until the specific code path
  runs — and it crashes the application with no obvious indication of cause.

  The additional hazard: the sim_mode=True path (simulator) was wrapped in a
  broad except clause that swallowed the NameError, making the simulator appear
  to work while the main window crashed. R28 (Fail Loudly) was being violated
  by the broad except, masking the R41 violation.

THE RULE:
  1. SELF-ATTRIBUTE ONLY: Any branching on widget mode/configuration inside
     _setup_ui() or any helper method called from it MUST use self.attribute,
     never a bare variable name from an enclosing method's scope.
     ✗ WRONG:  if sim_mode:          (NameError at runtime)
     ✓ CORRECT: if self._sim_mode:   (always in scope)

  2. BOTH MODES TESTED: When a widget has multiple instantiation modes
     (sim_mode, read_only, compact, etc.), any change to _setup_ui() or
     __init__() must mentally trace BOTH the True and False paths for every
     mode parameter. If the False path (default, non-sim, main-window) would
     behave differently from the True path under the change, verify it
     explicitly.

  3. NO BROAD EXCEPT AROUND WIDGET INIT: try/except blocks around
     IndicatorVotingPanel(), SimChart(), or any critical GUI widget
     construction must catch specific exceptions and log them — never
     `except Exception: pass` or silent swallowing. A widget that fails
     to construct must raise visibly.

SCOPE TRAP PATTERN (memorise this):
  class MyWidget(QWidget):
      def __init__(self, mode=False):
          self._mode = mode        # stored here
          self._setup_ui()         # called here

      def _setup_ui(self):
          if mode:                 # ← TRAP: mode not in scope here
              ...                  #   NameError at runtime, passes syntax check
          if self._mode:           # ← CORRECT: always in scope
              ...

APPLIES TO:
  All QWidget subclasses in src/gui/ — particularly any widget that accepts
  mode/configuration parameters in __init__ and defers setup to _setup_ui().
  Current affected widgets: IndicatorVotingPanel (sim_mode), SimChart,
  paper_trader_tab, demo_runner.

DEPENDS ON: R6 (both execution paths must be verified), R28 (fail loudly)
GROUP P added to SADP taxonomy.


---

## [KEY FILE LOCATIONS]

```
# SADP GOVERNANCE
sadp/README.md              SADP overview, version, quick reference
sadp/SPEC.md                Full R1-R38 rule specification
sadp/CHANGELOG.md           SADP version history (1.0 / 1.1 / 1.2 / 1.3 / 1.4)
sadp/RULE_REGISTRY.json          Live rule state — 41 rules, depends_on graph
sadp/SPEC-CORE.md           Full R1-R41 specification (portable core, v1.4)
sadp/EPISODIC_MEMORY.json   LTM — 50 entries, sessions 1-15 (R40)
sadp/EPISODIC_MEMORY.md     Human-readable LTM index (auto-generated)
sadp/memory_tools.py        LTM query/add/regenerate CLI
sadp/CAPABILITY_MATRIX.md   Per-provider enforcement capability table
sadp/impl/claude.md         Claude reference implementation
sadp/impl/openai.md         GPT-4/o1 adaptations
sadp/impl/local.md          Local model adaptations

# COMPETITION LAYER (v3.8.0)
src/competition/__init__.py      Package exports
src/competition/bot_identity.py  Ed25519 keypair, trade signing
src/competition/merkle_log.py    Merkle tree trade log + inclusion proofs
src/competition/season_schedule.py  Supply curve, 5 rarity tiers
src/competition/token_ledger.py  Hard-capped ACRV ledger (local)
src/competition/competition_engine.py  Competition lifecycle
src/competition/challenge_protocol.py  Elo rating, challenge mechanics
src/competition/local_testnet.py  In-memory Base chain simulator
src/competition/base_config.py   Chain config: Base mainnet + Sepolia
src/competition/base_connector.py  Web3 bridge (LOCAL/DRY_RUN/TESTNET/MAINNET)
src/competition/trophy_generator.py  5 Hermetic SVG trophies
src/competition/nft_minter.py    Trophy NFT minting integration
src/gui/competition_tab.py       PoA Network tab (⚔)
src/gui/testnet_tab.py           Local Testnet tab (⛓)
contracts/ACRV.sol               ERC-20 token (Base L2)
contracts/CompetitionRegistry.sol  Competition arbiter + Chainlink
contracts/AcervatorTrophy.sol    ERC-721 NFT (on-chain SVG)
contracts/deploy.py              Deploy to Base Sepolia or Mainnet
tests/test_competition.py        32/32 tests

# TRADING PLATFORM
main.py                          Entry point
RAIntSimBat.py                   Root launcher wrapper → RAIntSimBat/RAIntSimBat.py
RAIntSimBat/RAIntSimBat.py       Full simulation engine (50K+ lines total)
RAIntSimBat/reports/             All JSON battery output (79 files)
RAIntSimBat/data/cache/          OHLCV cache (CoinGecko / Yahoo Finance)
generate_essay.py                Product Manual generator
acervator_product_manual_v3_8_0.pdf  The living research record (leather cover, parchment pages)

src/gui/main_window.py           Primary window — QStackedWidget crypto/stock
src/gui/simulator.py             Backtesting simulator (~5,800 lines)
src/gui/paper_trader_tab.py      Paper trading tab
src/gui/paper_exchange.py        Live data + virtual order execution
src/gui/bot_visualizer.py        Bot Swarm (live rows for sim + paper)
src/gui/screen_recorder.py       Rolling-chunk recorder (cv2/ffmpeg/GIF/PNG)
src/trading/ta_engine.py         7-indicator TA engine
src/trading/mr_inspector.py      Mean Reversion Inspector + Boost Fold
src/trading/phantom_balance.py   Multi-TF TradeLock coordination
src/trading/scrumming_bot.py     THE CORE ENGINE

logs/real_market/                Live bot logs + API audit trail
logs/simulator/recordings/       Screen recorder output
logs/simulator/sessions/         Sim story + status logs
logs/paper/reports/              Paper trader session reports

docs/
  PROJECT_MANAGEMENT.md         PM framework overview + document index
  ROADMAP.md                    PMI milestone-based feature roadmap
  RISK_REGISTER.md              PMI PMBOK risk register (live)
  TEST_PLAN.md                  ISO/IEC 25010 quality attributes + coverage
  srs/SRS.md                    IEEE 29148 Software Requirements Spec
  adr/ADR-00*.md                Architecture Decision Records (Nygard format)
```

---

## [RAIntSimBat COMMAND REFERENCE]

```bash
# Standard batteries
python RAIntSimBat.py                                # 39-sim (Apr23-Apr26)
python RAIntSimBat.py RAIntSimBat-BATTERY-HISTORICAL # 39-sim (2020-2022)
python RAIntSimBat.py RAIntSimBat-BATTERY-EXTENDED   # 78-sim (all 6 years)

# Strategy & portfolio comparison
python RAIntSimBat.py RAIntSimBat-COMPARE-FULL
python RAIntSimBat.py RAIntSimBat-COMPARE-PORTFOLIO-ALL-2023

# Sensitivity analysis (all new in v3.7.0)
python RAIntSimBat.py RAIntSimBat-SWEEP-FULL           # interval 0.5%-5%
python RAIntSimBat.py RAIntSimBat-FEE-BREAKEVEN-FULL   # fee 0.01%-1.0%
python RAIntSimBat.py RAIntSimBat-CAPITAL-SCALE-FULL                  # $100-$10,000 retail
python RAIntSimBat.py RAIntSimBat-CAPITAL-SCALE-INSTITUTIONAL         # 156 sims — 4 VIP tiers (Section 19.29)
python RAIntSimBat.py RAIntSimBat-CAPITAL-SCALE-INSTITUTIONAL-BTC-2023 # single sim × 4 tiers
python RAIntSimBat.py RAIntSimBat-CAPITAL-CUSTOM-TARGET-HEDGE-FEE      # arbitrary capital + fee
python RAIntSimBat.py RAIntSimBat-MONTECARLO-FULL      # P10/P50/P90 (N=10)
python RAIntSimBat.py RAIntSimBat-COMPOUND-ALL         # 3-year chain
python RAIntSimBat.py RAIntSimBat-PHANTOM-FULL         # 4h TradeLock

# Single asset
python RAIntSimBat.py RAIntSimBat-BTC-USD-2023
python RAIntSimBat.py RAIntSimBat-NVDA-USD-ALL
```

---

## [BATTERY BASELINE — v3.8.0, April 18, 2026 (Session 16 verified)]

Standard (39 sims):             39/39 wins | Adv range $294K–$403K (stochastic)
Session 17 verified (final):    39/39 | 100% | $302,452 | fees $74,481
v3.9.0 verified:  39/39 | 100% | $364,676 | sweep PASSED (0 CRIT, 0 HIGH)
Historical (2020-2022):         33/39 wins | 6 losses all in 2022 extreme bear
Interval sweep (0.5%–5%):       39/39 at ALL intervals | Optimal 2.5%
Capital scaling (retail):       39/39 at $100–$10K | ~1,961% advantage/capital
Capital scaling (institutional): 156/156 wins across 4 VIP tiers
  $400  (0.10%): adv/capital 1,961%  (baseline)
  $4K   (0.10%): adv/capital 1,961%  (exact linearity — 0.003% diff)
  $20K  (0.08%): adv/capital 2,427%  (+23.8% from VIP1 fee tier)
  $100K (0.05%): adv/capital 3,369%  (+71.8% from VIP3+ fee tier)
Fee break-even:                 Profitable ≤ 0.50% | Breaks even at 0.75%
Monte Carlo (N=10):             100% win rate | P10=$4,939 P50=$7,803 P90=$10,853
Compound 3yr avg:               $174,508 from $400 | DOGE $625K, SOL $551K
Phantom Balance:                Net -0.1% vs base | 39/39 | Safe to deploy
Avg Sharpe:                     4.453 | Min 2.82 | All above "excellent" (2.0)
VolumeGuard verification:       Not triggered at any tested scale. Worst-case
                                $100K scrum ~$5K vs $150K safe limit (AVAX).

---

## [PRODUCT MANUAL SECTION MAP — v3.7.0, 25 sections]

Sections 1-18:   Platform architecture, TA engine, mechanisms
Section 19:      Cross-Market Validation (19.1–19.29)
  19.1-9:        Battery history and validation progression
  19.7:          Strategy benchmark (vs 6 strategies)
  19.8:          Re-Entry Scrum battery
  19.10:         Re-Entry Hedge
  19.11:         Historical battery (2020-2022)
  19.12:         Interval sensitivity sweep
  19.13:         Compound chain simulation
  19.14:         Sharpe/Sortino + drawdown duration
  19.15:         Fee break-even analysis
  19.16:         Capital scaling (retail $100-$10K)
  19.17:         Monte Carlo confidence bands
  19.18:         Phantom Balance comparison
  19.19-19.24:   MACD Taper, Vortex, BB Bullseye, Ichimoku, Volume, CM Slingshot
  19.25-19.28:   ADX/DMI, Supertrend, Z-Score, Kaufman ER
  19.24a:        Development Philosophy — Why Indicators Came Last
  19.29:         Capital Scaling Validation — 156 sims, institutional tiers,
                 VolumeGuard verification, Table 21/22/23
Section 20:      Innovation Assessment (9.9/10)
Section 21:      Contribution Analysis
Section 22:      AcervatorOS — Dedicated Trading Appliance
Section 23:      SADP — Structured AI Development Protocol (R1-R34, Table 20)
Section 24:      Licensing and Intellectual Property
Section 25:      Why These Results Matter
Appendix A:      Version History
Appendix B:      Headless Prompt & Syntax Reference (Table B1-B3,
                 capital scaling commands including INSTITUTIONAL + CUSTOM)

---

## [SESSION OPENING PROTOCOL]

1. User uploads the zip file.
2. User says: "Read ACERVATOR_HOP(N).md and confirm you are oriented."
3. AI delivers the HANDSHAKE PROMPT ("So you would like to build a
   trading bot?...") — THIS ACT IS THE HOP (R23).
4. Immediately after delivering the greeting, AI renames this file to
   ACERVATOR_HOP(N+1).md and updates all references in the repo.
5. AI then confirms orientation:
   - Current version and date
   - Last completed work
   - Active open items
   - What it will tackle first
6. Do NOT touch any code before confirming orientation.
7. Do NOT run the battery before confirming orientation (it takes time).

---

## [HOP NUMBERING PROTOCOL]

This file is named ACERVATOR_HOP2.md because 2 AI-to-AI handoffs have
been completed.

THE HOP COUNTER INCREMENTS ON THE HANDSHAKE PROMPT (R23).
When the incoming AI delivers "So you would like to build a trading bot?"
that IS the hop. It immediately renames this file to ACERVATOR_HOP3.md.

At the END of each session, the outgoing AI must:
1. Update this file with completed work and open items.
2. Ensure the file is already named ACERVATOR_HOP(N+1).md
   (it was renamed at the start of the session per R23).
3. Update all references in README.md and AI_DEVELOPER_GUIDE.md.
4. Include the updated file in the final zip.

Current hop: 3
Next session file: ACERVATOR_HOP4.md  (renamed at session open, not close)

---

---


---

## FULL SUITE RESULTS — v3.9.0 (April 19, 2026)

### Architecture changes this session
- `run_full_battery()` defined as explicit named function (no more module-level auto-run)
- `run_extended_battery()` added (78-sim: 3 recent + 3 historical periods)
- Engine header updated: v3.9.0, feature list current
- Engine version string: "v3.1.92" → "v3.9.0" throughout

### Canonical Battery (39 sims — Apr23-Apr24 / Apr24-Apr25 / Apr25-Apr26)

| Run | Total Advantage | Avg/sim | Fees | Win Rate |
|-----|----------------|---------|------|----------|
| Clean run 1 | $+1,199,624 | $+30,760 | $274,339 | 39/39 100% |
| Clean run 2 | $+1,084,303 | $+27,803 | $274,123 | 39/39 100% |

### Historical Battery (39 sims — 2020/2021/2022)
COVID crash+recovery, ATH bubble, brutal bear market

| Run | Total Advantage | Avg/sim | Win Rate |
|-----|----------------|---------|----------|
| Historical | $+3,160,912 | $+81,049 | 39/39 100% |

Historical advantage higher because 2020/2021 contained extreme bull moves
(COVID recovery, DeFi summer, NVDA AI cycle) and the engine compounds hard
through prolonged trends. 2022 bear — all 9 bear sims: $4,426 total (stable).

### Signal vs No-Signal comparison (canonical battery)
Pre-signal baseline: $791,783 (measured pre-session)
Post-signal median:  $1,141,963 (average of 2 clean runs above)
Improvement:         +44% on canonical battery

### Key observations
- Bear regime: $4,262–$4,427 total across 9 sims — extremely stable, 4% CV
- SIDEWAYS: $55K–$82K total — signal activation helped, especially ER+ADX
- BULL: stochastic variance is high (NVDA 57% CV) — average improvement clear
- Fee ratio: 17-25% of advantage — higher than pre-signal but advantage grew more
- NTZ: 533-567 — slightly higher than pre-signal (601 old), improving

## STRATEGY GAP ANALYSIS — Signal Activation (Session 17 final)

### Signal Inventory (before this work)
104 signals computed per TA snapshot.  38 consumed in trading logic.  66 idle.

### Gaps Identified

TIER 4 — Computed but unwired (zero marginal cost):
  ADX (9 keys): trending → scrum+, ranging → scrum−, parabolic exhaustion → both−
  Z-Score (6): extreme_low → fold+, extreme_high → scrum+, reverting → fold+
  Supertrend (5): flip_bull → fold+, flip_bear → scrum+, downtrend → fold+
  Volume (8 unused): capitulation → fold+, weak_rally → scrum+, cmf_bear → fold+
  Kaufman ER (5): ranging → scrum+, trending+hungry → fold−
  Slingshot (7): snap_bull → fold+, squeeze_bear → fold+

TIER 1 — Critical missing, added this session:
  ATR (Average True Range, 14-period, Wilder smoothing)
    - First absolute volatility measure in engine
    - Dynamic interval: widens scrum threshold when ATR% > interval × 1.5
    - extreme_high flag: de-risks both confidence values by −0.05
    - contracting: fold confidence +0.06 (coiling = likely move incoming)
  RSI (14-period, Wilder smoothing) with divergence detection
    - overbought (>70) on bullish candle: scrum +0.06
    - oversold (<30) on bearish: fold +0.06
    - bullish divergence (price lower low, RSI higher low): fold +0.08
    - bearish divergence (price higher high, RSI lower high): scrum +0.08

TIER 2 — Structural (OHLCV-only, not yet implemented):
  Fair Value Gaps (FVG): imbalance zones where price statistically returns.
    bull FVG = candle[i-1].high < candle[i+1].low. Fill rate: ~40-60% @48h.
  Multi-timeframe regime: aggregate 1h → 4h/daily for directional bias.
  Order block detection: consolidation zone + strong breakout direction.

TIER 3 — Require external data streams (roadmap):
  Funding rate (perpetual futures): over-short/long = squeeze/liquidation signal
  Open Interest change velocity: trend confirmation / exhaustion
  Fear & Greed Index: sentiment extremes correlate with fold opportunities

### Battery Results (6 runs with new signals vs 1 baseline)
Baseline ($791K):    1 run  — pre-signal activation
New signals median:  $2,038,238 (+157% vs baseline)
New signals minimum: $1,350,471 (+71% vs baseline)  
New signals maximum: $2,875,197 (+263% vs baseline)
All runs: 39/39 100% wins

### Key Insight
The engine was already computing the intelligence — it just wasn't using it.
ADX, Z-Score, Supertrend, Volume, ER, Slingshot: all computed every tick,
all ignored. The most direct competitive gap was internal.
ATR is the single most important structural addition: without it, the interval
is static regardless of whether the market is moving 0.5% or 8% per candle.
Every professional system has ATR. Now Acervator does too.

### FVG Fill Rate Validation
Tested across BTC/ETH/SOL/ADA/GLD Apr24-Apr25:
~40-60% of bullish FVGs fill within 48h. This is high enough to trade.
Implementation: next session (Hop 4). FVGs act as fold magnets —
when price is inside or approaching an FVG from above, fold confidence +0.10.


## SESSION 17 — FINAL ADDENDUM (April 19, 2026)
### All work completing Hop 3 — prepares Hop 4

**Battery final baseline: 39/39 | 100% | $791,782 | Sweep PASSED**

---

### R44: Slop Code Prevention (new rule)
No magic numbers in engine logic — named constants only.
Any logic block repeated 2+ times → extract to helper.
No inline dict/list recreated per call that could be class constant.
Defensive guard blocks use a loop, not N separate hasattr() lines.
Functions > 200 lines require TECH_DEBT justification.

Canonical failures fixed:
- `profit_fold` block copy-pasted 4 times → `_apply_profit_fold()` closure
- `type_colors` dict rebuilt in paintEvent per fill → `FILL_TYPE_COLORS` class constant
- 12 separate `hasattr()` guards → compact loop with `setattr`
- `0.001 + 0.0003` magic → `SimulatorTab.FEE_RATE` class constant

CRITICAL LESSON — _apply_profit_fold indentation bug:
The helper was inserted at 8-space indent (same level as `_sim_scrumming_tick`).
Python ended the tick at that point and absorbed the entire 1600-line trading
body into the helper. Result: 0 trades, no console output, simulation idle.
`ast.parse` did not catch this — valid Python, wrong structure.
FIX: helper must be at 12-space indent (nested inside tick), body at 16-space.
RULE EXTENSION: any helper inserted into a nested function must have its
indentation verified against the enclosing function's body indentation level.

---

### R41 bugs found and fixed this session

All fixed via the compact guard loop pattern (R44):
- `_fold_tranches` — provenance list not in `_run_sim` init
- `_charge_bar`, `_charge_n` — charge-up state not in init
- `_shad_add_count` — shadow tier counter not in init
- `_reh_fee_rate` — defined after first usage (L5889 vs L5759)
  FIX: moved to before first usage
- `FILL_TYPE_COLORS` — defined on SimulatorTab, accessed via `self` in SimChart
  FIX: `SimulatorTab.FILL_TYPE_COLORS` (class reference, not instance)
- `FEE_RATE` — defined on SimulatorTab, same cross-class issue
  FIX: `self.FEE_RATE` works because SimulatorTab IS the class
- `_SIM_FEE_RATE` — module-level constant never actually written to file
  FIX: `SimulatorTab.FEE_RATE` class constant instead

RULE EXTENSION (R41 variant): when inserting a new block into a long function,
verify that every variable the block references is defined ABOVE the insertion
point in that function. Python raises UnboundLocalError (not NameError) when
the variable is assigned somewhere in the function but BELOW the usage.

---

### Entry Price Conservation Invariant Fix (CRITICAL MATH)

ROOT CAUSE: `accum_profit = extra_asset × fold_price` violates the invariant
"at entry price, holdings × entry_price ≥ target" whenever folds occur above
the entry price (standard in any bull market).

PROOF (fold above entry, 2× bull scenario):
- Scrum at $2.00, fold at $1.60 (entry_price = $1.00)
- old formula: target grows $40.00
- holdings × entry_price = $225.00
- new_target = $240.00 → INVARIANT VIOLATED (deficit $15.00)

FIX: `target_growth = profit × min(fold_price, entry_price) / fold_price`
     = `extra_asset × min(fold_price, entry_price)`

When fold below entry: ratio = 1.0, no change.
When fold above entry: ratio < 1.0, growth scaled to entry-price value.
Invariant now holds EXACTLY: holdings × entry_price = new_target.

Implementation:
- `_sim_entry_price = ref` stored at run start (ref = first candle close)
- `_apply_profit_fold`: `_new = sim_target + profit * (min(price, _ep) / price)`
- Smart cap excludes shadow/REH assets: `(SIM_balance - shad_qty - reh_qty) × price`
- Battery R42 synced: `entry_price = candles[0].close`

BATTERY EFFECT: $365K → $791K (+116%). Conservative target growth preserves
more delta between scrums → more trades → more structural advantage.

---

### Animation Performance Optimisation

PROFILED PROBLEM (4000 fills @ 60fps):
- 2,760,000 QColor constructions/sec (type_colors rebuilt inside fill loop)
- 120,000 QRadialGradient/sec (glow on every fill every frame)
- 120,000 QFont constructions/sec (QFont created per fill)
- All fills pulsed/glowed regardless of age

FIXES APPLIED:
1. `_fill_color_cache` — pre-built (core, ring_c) per fill, rebuilt only on data change
2. `_type_colors_qc` — pre-built once in `__init__`, referenced in loop
3. `_font_tiny`, `_color_white200` etc — class-level cached QColors/QFont
4. `fm = p.fontMetrics()` hoisted OUTSIDE fill loop
5. Only last 20 fills get glow+pulse — older fills: diamond+label only
6. Viewport cull: `if x < -10 or x > w + 10: continue`
7. Timer: 16ms (60fps) → 33ms (30fps)

ESTIMATED IMPROVEMENT: ~20-40× for heavy simulations

---

### Scrum/Fold Terminology (UI + Manual)

PROBLEM: chart legend listed SCRUM and FOLD as separate categories from BUY and SELL,
implying they were different/neutral operations. Fill label colors were gold (SCRUM)
and cyan (FOLD) — didn't match the pink/green sell/buy diamond colors.

FIXES:
- Legend: "SCRUM (sell)" pink + "FOLD (buy)" green — matches fill diamonds
- `FILL_TYPE_COLORS`: SCRUM/BULLSEYE_SCRUM → sell-pink; FOLD/BULLSEYE_FOLD → buy-green
- Manual Section 3: terminology table added (Table 3.0) as first element
  SCRUM = ↑ SELL | FOLD = ↓ BUY | DISTRIBUTE = ↑ SELL
- Section 3.2: opening line "The SCRUM is always a SELL. The FOLD is always a BUY."
- Cycle diagram subtitles: "SELL excess" / "BUY cheaper" (all-caps)
- Figure 3 caption: "SCRUM (sell), FOLD (buy), DISTRIBUTE"
- Alchemical description: "SCRUM (SOLVE — sell the excess)" etc.

---

### Version & Documentation State

Version: 3.9.0 (bumped from 3.8.0)
Sweep: PASSED (0 critical, 0 high, 27 medium)
Files updated: CHANGELOG, ROADMAP, ADR-010, ADR-011, README, HOP3
Manual: acervator_product_manual_v3_9_0.pdf (Section 28 added)
Memory: 69 entries (sessions 1-17)
Rules: R1–R44 (44 rules)

---

### OPEN ITEMS FOR HOP 4

TUNING (constants not sweep-validated):
- Entry price ratio: `min(price, entry_price) / price` — correct formula,
  constants (exactly 1.0 cap) may need fine-tuning
- Hunger/satiety constants (0.20 depth scale, 0.40/0.45 multipliers)
- Charge bar rate (0.05 + H×0.10) and min release size
- Fold drain threshold (50%) and penalty slope (0.70)

OPEN BUGS / DEBT:
- TD-001: `_sim_scrumming_tick` CC=1600+, refactor deferred to v4.0.0
- TD-003: Circuit breaker on exchange API (BLOCKS paper trading)
- TD-004: Idempotency on trade submission (BLOCKS paper trading)
- TD-008: competition_tab.py runs local simulation (R28 violation)
- RSK-001: Patent MUST be filed before GitHub/public deployment
- Fold-queue abandon at age>150 (R43 causes fold to wait longer; capital lock-up)
- Scrum/Fold terminology: session was closed before full chart label audit

TERMINOLOGY AUDIT (partially complete):
- Chart legend: fixed ✓
- Chart fill label colors: fixed ✓
- Manual: fixed ✓
- Log messages: "SCRUM" log uses "sold" ✓; "FOLD" log doesn't say "bought" explicitly — review
- Trades table in UI: verify Side column shows "sell"/"buy" correctly
- Competition tab simulation: verify trade types labelled correctly



# ═══════════════════════════════════════════════════════════════════════════
# SADP GROUP K — USER-INVOKED COMPLIANCE GATE (R36)