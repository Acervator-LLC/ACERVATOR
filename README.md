# ⬡ Acervator

**Accumulation Trading Platform** — an open-source algorithmic trading system that harvests market volatility rather than predicting price direction.

> *"Stop predicting. Start accumulating."*

Built by Anthony L. Brown (Ekthelius the Accumulator). Released to humanity.

**Current version:** `__version__` in [`src/__init__.py`](src/__init__.py) is the one source; this README does not restate it, so it cannot go stale (issue #70).

---

## What It Does

Most retail traders lose because they try to predict which way a chart will move. Acervator does the opposite: it treats every price oscillation as fuel. When your holdings rise above a dollar target, it sells the excess. When price dips below the sell reference, it buys back more than it sold. The structural guarantee — every completed cycle ends with more asset than it began with — holds regardless of market direction.

This is the **Scrum/Fold cycle**:

```
Price rises → SCRUM (sell excess above target → fold queue fills)
Price dips  → FOLD  (buy back with queued USD at lower price → net accumulation)
Repeat      → Target grows via compound profit folding
```

No prediction required. The volatility that destroys emotional traders is the engine.

---

## Battery Results (measured at v3.13.7)

Tested across **738 simulations** spanning 27 portfolio configurations, capital levels from $400 through $100K, six two-year historical periods (including 2020 COVID crash, 2021 ATH bubble, and 2022 brutal bear), and VIP-0 through VIP-3 fee tiers. Identical parameters throughout. No per-asset optimization.

| Metric | Result |
|--------|--------|
| Win rate | **715/738 (96.9%)** |
| Total advantage vs buy-and-hold | **+$78.0B** |
| Canonical 39-sim battery | 39/39 (100%) — baseline preserved |
| Historical 2020–2022 (39 sims) | 39/39 (100%) — $+3.16M total advantage |
| Capital scaling 156-sim | 156/156 (100%) — superlinear at $100K |
| Bear regime stability | $4,262–$4,427 total / 9 sims / 4% CV |
| Profitable fee ceiling | up to 0.50% roundtrip |

The 23 non-wins are concentrated in extreme single-asset bear conditions (2022-class drawdowns of 64–94%) at small capital levels. Losses in those cases are marginal ($10–$157 on $400 deployments). Strategy does not claim to win in catastrophic single-asset collapses.

**vs 6 competing strategies** (canonical 39-sim battery):

| Strategy | Acervator wins |
|----------|----------------|
| Passive Hold | 39/39 (100%) |
| DCA Weekly | 39/39 (100%) |
| DCA Daily | 39/39 (100%) |
| Grid Trading | 39/39 (100%) |
| SMA 50/200 Cross | 37/39 (94.9%) |
| RSI Mean-Reversion | 35/39 (89.7%) |

The per-simulation tables behind these figures were published in a product-manual PDF that is not in this repository. Nothing in the tree reproduces them, so treat the table above as the summary of record and read `CHANGELOG.md` and `docs/audits/` for how each number was reached.

---

## Core Mechanisms

- **Scrum/Fold Cycle** — harvest excess above target, buy back cheaper
- **Profit Folding** — each fold permanently raises the target, compounding growth
- **Hunger/Satiety Dual Index** — delta-driven aggression scalar
- **Provenance Fold Queue** — per-tranche independent fold execution
- **BB Midline Gate** — scrum only above midline, fold only below (trend alignment)
- **Bollinger Band Bullseye** — rapid-fire execution when price touches BB exactly
- **Band Travel Detection** — triggers harvest when price has moved ≥N% of BB width since last trade
- **Landing Strip Detection** — Heikin-Ashi consolidation at BB extremes as high-confidence reversal signals
- **Hedge Rebalance** — separate reserve buys during delta depletion in bear conditions
- **Re-Entry Scrum / Re-Entry Hedge** — recovery mechanisms for post-crash dead zones
- **Boost Fold** — MR-Inspector-triggered aggressive fold when z-score extreme detected
- **Fair Value Gap magnets** — FVG-aware fold placement / scrum amplification
- **Multi-timeframe regime bias** — 4h phantom signal informs 1h execution
- **7-Indicator TA Consensus** — BB, Vortex, MACD, Stochastic RSI, Ichimoku, Volume, Slingshot

---

## Nuclear Mode — Continuous Stress Demo

Nuclear Mode lives under `src/gui/simulator_tab/` (`nuclear_controller.py`, `nuclear_fleet_controller.py`, `nuclear_mode_panel.py`, `nuclear_sim_exchange.py`, `nuclear_candle_source.py`) with its verification helpers in `src/trading/nuclear_verification.py`. It runs the platform in a self-exercising burn-in mode: each bot is assigned a random asset, base currency, and 2-year historical period from the battery, and executes real Scrum/Fold ticks visibly through the GUI. Its job is to confirm the engine, Smart Wire, MR Inspector, PoA TestNet, and TokenLedger all function under realistic load for extended periods without operator intervention.

**Speed oscillator (v3.13.7):** tick rate and per-tick workload co-oscillate on a 120-second cycle — 45s cosine ramp up, 30s sustain at 4× base (0.2s tick, 4× candles/tick → 16× combined throughput), 45s cosine ramp down, repeat. A 5Hz `SystemLoadMR` sampler runs on a background daemon; CPU ≥ 60% triggers a COOLING regime that caps the multiplier at 1.5× until three consecutive CALM samples restore normal cycling. Workload is deterministic (fractional accumulator preserved across ticks) so expected throughput matches the multiplier exactly.

---

## Development Harness

Acervator is built with an AI co-developer under a harness that refuses work rather than trusting it. The harness lives in `dev_harness/`; the rules the operator gives the agent live in `.claude/skills/`.

| Component | Description |
|-----------|-------------|
| **Archetypes** | `dev_harness/harness/coding_archetype.py`, `docs_archetype.py`, `gui_archetype.py`, `ta_archetype.py` and `watchdog_archetype.py`. Each one reads a single file and returns `passed` with its findings. `passed=false` is invalid work, and fewer findings than last time is not a pass. |
| **Rules** | `dev_harness/harness/rules/` — hallucination, numeric-guard, scaffolding and slop detectors that run inside the archetypes. |
| **Release gate** | `python -m dev_harness.harness.check_release_readiness` runs the suite and prints `[OK] Release-ready (vX.Y.Z, N tests)`. No version banner and no CHANGELOG entry moves before that line appears. |
| **Emitter registry** | `python -m tools.emitter_registry_check` — every runtime pin in `src/` must have a row, and every row must have a pin. A claim with no emitter behind it is not evidence. |

An earlier governance harness, SADP, was retired. Documents under `docs/audits/`, `docs/harness_archive/` and `CHANGELOG.md` still describe it. They are historical records and were true when written.

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/ekthelius/ACERVATOR---THE-ACCUMULATION-TRADING-PLATFORM.git
cd ACERVATOR---THE-ACCUMULATION-TRADING-PLATFORM

# Core (required). The dependency list lives in pyproject.toml
# ([project] dependencies). A requirements.txt is not in the tree.
pip install -e .

python main.py
```

**Optional extras.** Issue #94 moved these into
`[project.optional-dependencies]` in `pyproject.toml`, so each one is
named in that file and nowhere else:

```bash
pip install -e ".[report]"    # PDF sweep report (reportlab)
pip install -e ".[video]"     # screen recorder (opencv-python, Pillow)
pip install -e ".[charts]"    # chart and PDF tokens (matplotlib)
pip install -e ".[monitor]"   # live monitor HTTP client (httpx)
pip install -e ".[display]"   # AcervatorOS mini panels (Raspberry Pi)
pip install -e ".[build]"     # PyInstaller host
pip install -e ".[dev]"       # ruff, mypy, bandit, vulture, pytest, stubs
```

Issue #94 also removed a hand-copied "minimum install" list that used to
stand here, one of the nine it found. Every package it named is a core
dependency, so `pip install -e .` above already installs all of them.
`psutil` is one: Nuclear Mode uses it for `SystemLoadMR` CPU sampling,
and without it `_make_oscillator` caps the load multiplier instead of
reporting zero load (R28 FL / R61 CBF compliance).

**Video recording options (best to worst):**
```bash
pip install -e ".[video]"      # direct MP4 via opencv-python, no temp files
# OR install system ffmpeg     # 30s rolling MP4 chunks, auto-purge
# OR the Pillow in that extra   # animated GIF fallback
```

**Where the package names live.** `pyproject.toml` is the only place.
`build_windows.ps1`, `build_mac.sh`, `BUILD.py`, `os/install.sh` and
`os/update.sh` each call `python -m tools.deps requirements <consumer>`
and install what it prints. `requirements/` holds the resolved
transitive set that `python -m tools.deps lock` produced, one file per
platform and interpreter.

---

## Project Structure

```
acervator/
├── main.py                                   # Entry point
├── acervator_watchdog.py                     # Out-of-process crash watchdog
├── BUILD.py                                  # PyInstaller build driver
├── pyproject.toml                            # Dependencies, pytest, coverage
├── CHANGELOG.md · CONTRIBUTING.md · DISCLAIMER.md · LICENSE
│
├── contracts/                                # Solidity + deploy script
│   ├── ACRV.sol · AcervatorTrophy.sol
│   ├── CompetitionRegistry.sol
│   └── deploy.py
│
├── dev_harness/                              # The development harness
│   ├── harness/                              # Archetypes + release gate
│   │   ├── coding_archetype.py · docs_archetype.py
│   │   ├── gui_archetype.py · ta_archetype.py
│   │   ├── watchdog_archetype.py
│   │   ├── check_release_readiness.py
│   │   └── rules/                            # hallucination · numeric_guard
│   │                                         # scaffolding · slop
│   ├── agents/
│   └── touchset.py
│
├── docs/
│   ├── audits/                               # Session audits (historical)
│   ├── harness_archive/                      # Retired-harness records
│   ├── EMITTER_IDENTIFICATION.md
│   ├── ITEM_10_EMITTER_NETWORK.md
│   └── TOUCHSET.md
│
├── src/
│   ├── core/                                 # Cross-cutting services
│   │   ├── system_load_oscillator.py         # Speed oscillator (v3.13.7)
│   │   ├── state_manager.py · event_bus.py
│   │   ├── sound_engine.py · sms_engine.py
│   │   ├── logging_engine.py · log_paths.py
│   │   ├── encryption.py · settings.py · usb_auth.py
│   │   ├── execution_discipline.py · trade_historian.py
│   │   ├── emit_contracts.py                 # Emitter registry
│   │   ├── rule_registry.py                  # Rule state and admin commands
│   │   └── version_sweep.py
│   ├── trading/                              # The bot brain
│   │   ├── scrumming_bot.py                  # Core Scrum/Fold engine
│   │   ├── ta_engine.py                      # 7-indicator TA + Landing Strip
│   │   ├── phantom_balance.py                # Multi-TF coordination (TradeLock)
│   │   ├── mr_inspector.py · smart_wire.py
│   │   ├── volume_guard.py · reconciliation.py
│   │   ├── buy_safety.py · capital_reservation.py
│   │   ├── extractor_bot.py · bot_container.py
│   │   ├── nuclear_verification.py
│   │   ├── stone_tablets/                    # Historical candle store
│   │   └── risk_manager.py · analytics_engine.py
│   ├── competition/                          # Proof of Accumulation package
│   │   ├── bot_identity.py · merkle_log.py
│   │   ├── competition_engine.py · challenge_protocol.py
│   │   ├── token_ledger.py · trophy_generator.py
│   │   ├── season_schedule.py · base_config.py
│   │   └── local_testnet.py                  # In-process blockchain for testing
│   ├── exchange/                             # Crypto exchange integrations
│   │   ├── base.py · ccxt_connector.py
│   │   ├── market_data.py · data_pool.py
│   │   ├── circuit_breaker.py · idempotency.py
│   │   └── crypto_assets.py · tablet_backend.py
│   ├── stocks/                               # Equity broker integrations
│   │   ├── broker_base.py · alpaca_connector.py
│   │   ├── stock_bot.py · stock_accumulation_bot.py
│   │   └── tradingview_bridge.py · market_hours.py
│   └── gui/                                  # PySide6 UI
│       ├── main_window.py · stock_main_window.py
│       ├── simulator_tab/                    # Simulator + Nuclear Mode
│       │   ├── simulator_tab.py
│       │   ├── nuclear_controller.py
│       │   ├── nuclear_fleet_controller.py
│       │   ├── nuclear_mode_panel.py
│       │   └── nuclear_sim_exchange.py
│       ├── testnet_tab.py · competition_tab.py
│       ├── bot_visualizer.py · bot_wizard.py
│       ├── market_inspector.py · indicator_panel.py
│       ├── history_tab.py · journal_tab.py
│       └── screen_recorder.py · audio_suite.py
│
├── tests/                                    # 7382 tests
└── tools/                                    # Repo utilities
    ├── emitter_registry_check.py
    ├── build_release_zip.py
    └── gate.py · queue_state.py · migrate_harness.py
```

**Runtime files are not in the tree.** State lives under `~/.acervator/`
(`bot_state.json`, credentials, reservation state) and logs under
`~/.acervator_logs/` (`activity/`, `console/`, `trade/`). Nothing writes a
`logs/` directory into the source tree.

---

## Philosophy

Most trading tools are built for people who already have money and access. Acervator was built for everyone else.

The strategy requires no prediction skill, no market timing, no insider information. It requires capital (the canonical battery runs at $400/sim), patience, and a systematic approach. The accumulation guarantee — that every completed Scrum/Fold cycle results in more asset than was sold — is structural, not statistical.

The inventor does not experience this as something he built. It arrived. It belongs to the people it was built for.

---

## Proof of Accumulation — Competition Layer

Acervator v3.8.0 introduced an on-chain competition system where bots compete publicly and winners earn **ACRV tokens** on Base (Coinbase L2). The system evolved through v3.9–v3.13: Ed25519 bot identity, append-only Merkle trade logs, Elo ratings, tournament brackets, in-platform LocalTestnet.

### How It Works

Every Acervator bot has a cryptographic identity (Ed25519 keypair). During a competition, every trade is signed and appended to a Merkle tree. At the end, the bot submits only the Merkle root — a 32-byte hash that commits to the entire trade history without revealing any trade details. Strategy stays private. The proof is public. Winners are awarded ACRV and an NFT trophy.

### ACRV Token Economics

| Property | Value |
|----------|-------|
| Hard cap | 10,000,000 ACRV (immutable on-chain) |
| Chain | Base (Coinbase L2) — chain ID 8453 |
| Standard | ERC-20 |
| Minting | CompetitionRegistry contract only |
| Burning | Never |

### Trophy Tiers

Five rarity tiers following the Corpus Hermeticum alchemical path:

| Tier | Stage | ACRV | Max Supply | Condition |
|------|-------|------|------------|-----------|
| 🌾 Harvest | NIGREDO | 10 | Unlimited | Top 50% of field |
| 🪙 Gold Fold | ALBEDO | 50 | Unlimited | Top 10% of field |
| 🐻 Bear Slayer | CITRINITAS | 100 | 10,000 | Top 25% in bear market |
| ⚡ Grand Accumulator | RUBEDO | 500 | 1,000 | Top 1% × 3 seasons |
| ∞ Ekthelius | UNIO MYSTICA | 10,000 | **21 ever** | Perfect score |

Trophy NFTs are fully on-chain SVG (no IPFS). They exist as long as Base exists.

### In-Platform Testnet

The full competition lifecycle — register, trade, submit, adjudicate, award tokens, mint NFT — runs entirely in-process with no network, no private key, and no ETH. Open the "⛓ Testnet" tab in the platform to run live competitions and see the block explorer.

```python
from src.competition.local_testnet import LocalTestnet
testnet = LocalTestnet()
result  = testnet.run_demo_competition(n_bots=3, season=1)
print(result['results_table'])
```

### Contracts (Base Sepolia — deploy before mainnet)

```bash
npm install @openzeppelin/contracts @chainlink/contracts
export ACERVATOR_PRIVATE_KEY=0x...
python contracts/deploy.py --network sepolia
```

---

## Contributing

Built by one person. The battery is 96.9% but the edge cases one person finds are limited by one person's perspective.

If you find a market condition where it fails — document it, open an issue, submit a fix. The next version of Acervator will be built by everyone.

Please read `CONTRIBUTING.md` before submitting pull requests.

---

## Disclaimer

This software is for educational and research purposes. Simulation results — including the 738-sim / 96.9% / +$78.0B figures above — do not guarantee live trading performance. You are solely responsible for any trading decisions made using this software. See `DISCLAIMER.md`.

---

## License

Apache License 2.0 — see `LICENSE` for full terms.

Copyright 2025–2026 Anthony L. Brown (Ekthelius the Accumulator)
