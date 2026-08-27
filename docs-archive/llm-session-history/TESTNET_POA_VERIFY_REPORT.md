# TESTNET / POA VERIFY REPORT
**Session 18 · v3.11.1 · 2026-04-20**
**Status:** verify-only turn — no code changes this turn
**Next turn:** polish (single shared-instance refactor + UX)

---

## 1. The Symptom

TestNet tab (screenshot from user): Chain Status shows all zeros —
Block=0, Transactions=0, Events=0, Competitions=0, ACRV Minted=0.
Block Explorer, Transaction Log, Contract Events, Token Holders, and
TestNet Log are all empty.

But Nuclear mode's Console shows PoA activity every ~30 seconds:

```
09:20:20 ⛓ PoA round 1: opening competition on SPY/BUSD (season 1)…
09:20:20 ⛓ PoA: block #11 sealed — winner=0x0x0d6292… ACRV=10
09:20:52 ⛓ PoA round 2: opening competition on SLV/USDT (season 2)…
09:20:52 ⛓ PoA: block #11 sealed — winner=0x0x956843… ACRV=10
09:21:25 ⛓ PoA: block #11 sealed — winner=0x0xe127f6… ACRV=10
09:21:59 ⛓ PoA: block #11 sealed — winner=0x0x27c4f1… ACRV=10
09:22:34 ⛓ PoA: block #11 sealed — winner=0x0xba98cf… ACRV=10
```

Two anomalies screaming at us:
1. Every round says **"block #11"** — not #11, #22, #33…
2. TestNet tab shows zero activity despite 5 rounds completing

---

## 2. Architectural Read — Confirmed by Code Inspection

### 2.1 LocalTestnet is the chain state

`src/competition/local_testnet.py::LocalTestnet` holds:

| Field | Type | What it tracks |
|---|---|---|
| `_chain` | `LocalChain` | Block headers, tx log, event log, block height |
| `_acrv` | `LocalACRV` | Total supply, per-wallet balances, mint history |
| `_registry` | `LocalRegistry` | Competition records, submissions, adjudications |

All three are instance-scoped. When `LocalTestnet()` is constructed,
each starts at zero. There is no global singleton, no persistence file
by default (persist_path defaults to None).

### 2.2 Five places instantiate LocalTestnet

```
src/gui/testnet_tab.py:110                self._testnet = LocalTestnet()
src/core/nuclear_live.py:557                           tn = LocalTestnet()
src/core/nuclear_runner.py:213                    testnet = LocalTestnet()
src/competition/base_connector.py:82           self._local = LocalTestnet()
src/competition/local_testnet.py:20                testnet = LocalTestnet()   # docstring example
```

**Each is a separate chain.** The five instances never share data.
Nothing subscribes to anything.

### 2.3 Nuclear's PoA flow — per-round fresh chain

From `src/core/nuclear_live.py::_run_poa_round` (line 552–584):

```python
from ..competition.local_testnet import LocalTestnet
sym = self.feeds[0].symbol if self.feeds else "BTC/USDT"
...
tn = LocalTestnet()                              # ← NEW chain, every round
result = tn.run_demo_competition(
    n_bots=3, season=self.poa_rounds, symbol=sym)
...
# tn goes out of scope here. State destroyed.
```

`LocalTestnet.run_demo_competition` internally calls:
1. `open_competition_onchain`   (block 1)
2. 3× `register_bot_onchain`     (blocks 2–4)
3. `activate_competition_onchain` (block 5)
4. `close_for_submission_onchain` (block 6)
5. 3× `submit_result_onchain`     (blocks 7–9)
6. `adjudicate_onchain`           (block 10)
7. Final mint                     (block 11)

That's the "block #11" in every round's log line — it's block 11 of a
fresh ephemeral chain that's been running for ~2 seconds, not block 11
of a persistent multi-hour chain.

### 2.4 TestNet tab's flow — isolated chain

From `src/gui/testnet_tab.py::TestnetTab.__init__` (line 108–117):

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self._testnet = LocalTestnet()         # ← TAB-owned instance
    self._comp_count = 0
    self._setup_ui()
    # Auto-refresh every 3s
    self._timer = QTimer(self)
    self._timer.timeout.connect(self._refresh_stats)
    self._timer.start(3000)
```

The tab:
- Creates its own `LocalTestnet()` on tab instantiation (once, at
  startup), which is empty
- Refreshes its display every 3s from `self._testnet.get_competition_stats()`
  — but `self._testnet` has no activity because Nuclear isn't driving
  it, so every refresh reads zeros
- Has its own "Run Competition" + "Stress Test ×10" buttons that, when
  clicked, DO run competitions against `self._testnet` — so the tab
  CAN populate if the user clicks those buttons. It just doesn't
  populate from Nuclear activity.

### 2.5 Why the Chain ID "84532" is a further symptom

The header shows `Chain ID 84532` (Base Sepolia's real chain ID).
That's cosmetic — it's a hardcoded label in the tab header:

```python
self._net_lbl = _lbl("● ACERVATOR LOCAL TESTNET  ·  Chain ID 84532", GREEN, 10)
```

Not a bug per se, but worth noting: this label implies a persistent
chain exists, which is the user expectation the current architecture
isn't meeting.

---

## 3. State Contract — What "Shared Persistent Chain" Means

If we want Nuclear's PoA rounds and the TestNet tab to share ONE
chain, we need to decide which class owns the instance, where it
lives, and how other code finds it.

### 3.1 Proposed owner: main_win

The `MainWindow` (in `src/gui/main_window.py`) is the right owner:
- Outlives tabs
- Outlives Nuclear engine threads
- Already tracks cross-tab singletons (`_market_map`, `_nuclear_thread`)
- Survives tab teardown/recreation

Concretely:

```python
# main_window.py __init__
from src.competition.local_testnet import LocalTestnet
self._local_testnet: LocalTestnet = LocalTestnet()   # ← ONE instance
```

This instance becomes the authoritative chain for the entire app
session.

### 3.2 Consumers

Three places change:

**TestnetTab** (`src/gui/testnet_tab.py`):
- Removes its own `LocalTestnet()` construction
- Takes a reference to `main_win._local_testnet` via constructor injection
  or a lookup method
- Everything else (refresh, run_competition, stress_test) already works
  because they all route through `self._testnet`

**Nuclear engine** (`src/core/nuclear_live.py::_run_poa_round`):
- Receives the shared instance via a new constructor parameter or via
  the existing callback pattern
- Calls `self._shared_testnet.run_demo_competition(...)` instead of
  making its own instance
- Block numbers now monotonically grow: round 1 → block 11, round 2 →
  block 22, round 3 → block 33, etc.

**Demo runner** (`src/gui/demo_runner.py`):
- When constructing `NuclearLiveThread`, pass `main_win._local_testnet`
  as a new kwarg so the engine has access

### 3.3 Wiring for cross-thread safety

Nuclear runs on its own Python thread. The TestNet tab's timer fires
on the Qt main thread. They'll both call methods on the same
`LocalTestnet` instance.

`LocalTestnet` is NOT thread-safe today. Inspection of
`LocalChain.send_tx` / `mine` / `emit` shows:
- `_txs.append(...)` on chain
- `_blocks.append(...)` on chain
- `_events.append(...)` on chain
- `_balances[addr] += amount` on ACRV

Python list.append and dict.__setitem__ are GIL-atomic, but a
read-modify-write pattern like `self._balances[addr] += amount` is
NOT atomic across threads.

**Implication for polish turn:** the shared instance needs a
`threading.Lock` protecting its mutating operations. The lock should
live on `LocalTestnet` itself rather than expecting every caller to
know about it. Propose adding a single `threading.RLock` around
`run_demo_competition`, `_chain.send_tx`, `_chain.mine`, `_chain.emit`,
and the ACRV balance-changing ops. RLock (reentrant) so the outer
`run_demo_competition` call can hold the lock while its internal
sub-operations also acquire it.

### 3.4 Signal for live tab refresh

Currently the tab polls every 3s via QTimer. When Nuclear lands a new
block, the tab won't see it until the next poll. That's fine for v1 —
3s latency is acceptable — but a pub/sub signal would be nicer:

```python
# LocalChain gains a Qt-friendly callback slot
self._block_listeners: list[Callable[[Block], None]] = []

def subscribe(self, callback): ...

# TestNetTab registers a listener that bumps its refresh
main_win._local_testnet._chain.subscribe(
    lambda block: QTimer.singleShot(0, self._refresh_all))
```

Polish turn decision point: poll vs push. Either works. Poll is
simpler, push is prettier.

---

## 4. Proposed Changes for Polish Turn

Not implementing this turn. Listed so you see what I'd actually do:

| File | Change | Why |
|---|---|---|
| `src/gui/main_window.py` | `+ self._local_testnet = LocalTestnet()` in `__init__` | Owner of the singleton |
| `src/gui/testnet_tab.py` | Replace `self._testnet = LocalTestnet()` with injection | Consume shared instance |
| `src/core/nuclear_live.py` | Add `shared_testnet` constructor param; use it in `_run_poa_round` instead of `tn = LocalTestnet()` | Write to shared chain |
| `src/gui/demo_runner.py` | Pass `main_win._local_testnet` when building `NuclearLiveThread` | Wire shared instance through |
| `src/competition/local_testnet.py` | Add `threading.RLock` around mutating operations | Cross-thread safety |
| `tests/test_shared_testnet.py` (NEW) | Verify: two callers write to same chain, block count grows monotonically, TestNet tab reads see Nuclear writes | Regression lock |

Expected observable effects after polish:

- Nuclear Console: `⛓ PoA: block #11 sealed` → `block #22 sealed` → `block #33 sealed` (not always #11)
- TestNet tab Chain Status: populates with real numbers from Nuclear activity — blocks, txs, events, competitions all growing
- Block Explorer populates with a chronological chain
- Token Holders fills with the accumulated winners across all PoA rounds
- ACRV Minted grows by 10 per Nuclear PoA round (matches the `tokens_awarded` figure)
- Remaining ACRV decreases correspondingly
- "Run Competition" button in TestNet tab still works, adds to the same chain
- `~/.acervator/testnet_chain.json` (new, optional) persists state across app launches — stretch goal, can defer

### 4.1 What this does NOT fix

The pattern-level observation (separate subsystems creating separate
state instances) shows up in at least 3 places in the codebase:

- Market Map (fixed in v3.11.0)
- TestNet ↔ Nuclear (to be fixed in polish turn)
- Bot Swarm real/sim/paper sub-tabs (still pending)

It's worth discussing whether the fix for this class of bug deserves
a doctrine — maybe an R60 "Single-Source State" or "Shared Singleton
Registration" rule. Flagging for your consideration; not committing
to it this turn.

---

## 5. What I Want Confirmed Before the Polish Turn

Three questions:

1. **Owner location.** Is `MainWindow._local_testnet` the right place?
   Alternative: a dedicated singleton module
   `src/competition/shared_testnet.py`. MainWindow feels right to me
   because it matches the existing `_market_map`, `_nuclear_thread`
   pattern — but shared-module gives better separation for possible
   stock-mode parity later. Your call.

2. **Thread safety approach.** RLock on LocalTestnet (my preference)
   vs. only-let-one-thread-write pattern (e.g., Nuclear posts events
   to a queue that the main Qt thread drains). RLock is simpler;
   queue is more bulletproof. My read is that the mutation rate
   (1 PoA round every 30s) doesn't justify the queue complexity, but
   I want you to sign off before I lock in the simpler approach.

3. **Persistence.** Do you want `~/.acervator/testnet_chain.json`
   round-trip so the chain survives app restarts? That would let
   users see their PoA history across sessions. Adds ~40 lines.
   Defer to future if you prefer a minimal polish turn.

---

## 6. Assumptions I'm Making (Flag if Wrong)

- The Chain ID 84532 cosmetic label is not something you want changed
  this turn — it's an aesthetic decision, not a bug
- "Stress Test ×10" button should continue running against the shared
  instance (10 extra competitions in rapid succession against the same
  chain). Not a separate isolated burst.
- TestNet LOG panel (empty in screenshot) needs a text-stream feed
  similar to Console. Looking at the code, there's a `_msg()` method
  that writes to `self._log_text` but it's only called from in-tab
  actions — Nuclear PoA activity never reaches it. Polish turn will
  wire Nuclear's PoA events to this panel too.
- No new SADP rule in polish turn — this is a code-correctness fix,
  not a new discipline. The doctrine question (#4.1) is separable.

---

## Ready

When you give me the go-ahead on the three sign-off questions in §5,
I'll execute the polish turn: single refactor pass across 4 files +
1 new test file, cascade to v3.12.0 (minor — new cross-subsystem
capability, shared chain state), SADP stays at 1.14 unless we decide
to add the doctrine rule.
