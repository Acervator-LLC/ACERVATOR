# ⬡ Acervator

**Accumulation Trading Platform** — an open-source algorithmic trading system that harvests market volatility rather than predicting price direction.

> *"Stop predicting. Start accumulating."*

> 🛠️ **Looking for SADP?** The AI development governance harness that this project was built on top of is now packaged for separable adoption.
> → [`WHY_SADP.md`](WHY_SADP.md) — what SADP is, comparison to other harnesses, how to adopt it
> → [`sadp/SKILL.md`](sadp/SKILL.md) — Anthropic-Agent-Skills-compatible packaging
> → [`tools/sadp_init.py`](tools/sadp_init.py) — scaffolder for adopting SADP in a fresh project
>
> SADP is Apache 2.0. The Acervator trading inventions are NOT inside that grant — see [`NOTICE`](NOTICE) for the boundary.

Built by Anthony L. Brown (Ekthelius the Accumulator). Released to humanity.

**Current version:** 3.15.94 · **SADP:** 1.92 · **Rules:** R1–R76 (R59 reserved) · **Last battery:** 39-simulation historical battery (2020 COVID + 2021 ATH + 2022 bear), 38/39 wins (97.4%), R55 verify-clean 100%. See `sadp/RAIntSimBat/reports/` for current sweep data.

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

## Battery Results (v3.13.7)

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

The 23 non-wins are concentrated in extreme single-asset bear conditions (2022-class drawdowns of 64–94%) at small capital levels. Losses in those cases are marginal ($10–$157 on $400 deployments). Strategy does not claim to win in catastrophic single-asset collapses; see `docs/RISK_REGISTER.md` RSK-006.

**vs 6 competing strategies** (canonical 39-sim battery):

| Strategy | Acervator wins |
|----------|----------------|
| Passive Hold | 39/39 (100%) |
| DCA Weekly | 39/39 (100%) |
| DCA Daily | 39/39 (100%) |
| Grid Trading | 39/39 (100%) |
| SMA 50/200 Cross | 37/39 (94.9%) |
| RSI Mean-Reversion | 35/39 (89.7%) |

Full methodology and every simulation's numbers: `acervator_product_manual_v3_13_7.pdf`.

---

## Core Mechanisms

- **Scrum/Fold Cycle** — harvest excess above target, buy back cheaper
- **Profit Folding** — each fold permanently raises the target, compounding growth
- **Hunger/Satiety Dual Index** — delta-driven aggression scalar (see ADR-011)
- **Provenance Fold Queue** — per-tranche independent fold execution (see ADR-010)
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

`src/core/nuclear_live.py` runs the platform in a self-exercising burn-in mode: each bot is assigned a random asset, base currency, and 2-year historical period from the battery, and executes real Scrum/Fold ticks visibly through the GUI. Its job is to confirm the engine, Smart Wire, MR Inspector, PoA TestNet, and TokenLedger all function under realistic load for extended periods without operator intervention.

**Speed oscillator (v3.13.7):** tick rate and per-tick workload co-oscillate on a 120-second cycle — 45s cosine ramp up, 30s sustain at 4× base (0.2s tick, 4× candles/tick → 16× combined throughput), 45s cosine ramp down, repeat. A 5Hz `SystemLoadMR` sampler runs on a background daemon; CPU ≥ 60% triggers a COOLING regime that caps the multiplier at 1.5× until three consecutive CALM samples restore normal cycling. Workload is deterministic (fractional accumulator preserved across ticks) so expected throughput matches the multiplier exactly.

---

## Structured AI Development Protocol (SADP)

Acervator was built using the **Structured AI Development Protocol (SADP)** — a formal methodology for building complex software with an AI co-developer across an indefinite number of sessions. SADP is an independent invention, separate from the trading platform, applicable to any AI-assisted project.

**Current SADP state:** version 1.18, rules R1–R62 (R59 reserved), 154 memory entries, 43 HOP addenda across 4 HOP generations.

| Component | Description |
|-----------|-------------|
| **Continuity Layer (GHP)** | Structured session handoff. `sadp/ACERVATOR_HOP4.md` + `sadp/NEXT_SESSION_ORDERS.md`. Each new session runs `python3 sadp/hop_open.py [--query \| --proceed]` — six deterministic steps (read SADP / Chronicle / PM / orders / checklist audit / verdict) gated by exit code. |
| **Governance Layer (R1–R62)** | 62 behavioral rules grouped A–JJ. Each rule encodes a specific failure mode observed in earlier sessions. Includes rules sourced from named SE standards (McCabe 1976, Martin 2002, Nygard 2007, Helland 2012). Recent additions: **R60 QD** (queue discipline, older pre-empts newer), **R61 CBF** (callback boundary fail-loudly — see ADR-012), **R62 FRG** (freshness gate, structural drift detection). |
| **Administrative Control Layer** | `RULE LOCK / UNLOCK / SUSPEND / RESTORE / STATUS / LIST / AUDIT` command syntax. CORE protection on algorithm invariants. Full audit trail via `sadp/EDIT_LOG.jsonl` and `sadp/EPISODIC_MEMORY.json`. |
| **Structural Enforcement** | `sadp/CHECKLIST.json` — 14 declarative file-relationship invariants (mtime_gte, byte_identical, version_match, custom). `sadp/checklist.py` runs them; cascade-blocking failures gate hop open and cascade close. `sadp/ARTIFACTS.json` + `sadp/cleanup_outputs.py` manage `/mnt/user-data/outputs/` lifecycle with regen-on-demand. |

Key docs: [`sadp/SPEC-CORE.md`](sadp/SPEC-CORE.md) · [`sadp/ACERVATOR_HOP4.md`](sadp/ACERVATOR_HOP4.md) · [`sadp/NEXT_SESSION_ORDERS.md`](sadp/NEXT_SESSION_ORDERS.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · `acervator_product_manual_v3_13_7.pdf` Part III.

---

## Installation

**Requirements:** Python 3.11+

```bash
git clone https://github.com/yourusername/acervator.git
cd acervator

# Core (required)
pip install -r requirements.txt

# Optional: video recording, PDF reports, stock trading
pip install -r requirements-optional.txt

python main.py
```

**Minimum install:**
```bash
pip install PySide6 ccxt cryptography keyring numpy psutil
```

`psutil` is required for Nuclear Mode's `SystemLoadMR` CPU sampling. Without it, Nuclear Mode refuses to start rather than silently reporting zero load (R28 FL / R61 CBF compliance).

**Video recording options (best to worst):**
```bash
pip install opencv-python      # direct MP4, no temp files
# OR install system ffmpeg    # 30s rolling MP4 chunks, auto-purge
# OR pip install Pillow       # animated GIF fallback
```
---

## Project Structure

```
acervator/
├── main.py                                   # Entry point
├── RAIntSimBat.py                            # Launcher → sadp/RAIntSimBat/
├── acervator_product_manual_v3_13_7.pdf      # Full research documentation (43 pages)
│
├── sadp/RAIntSimBat/                         # Simulation battery (under SADP)
│   ├── RAIntSimBat.py                        # Engine
│   ├── reports/                              # JSON output + MASTER_SUMMARY PDFs
│   └── data/cache/                           # OHLCV data cache (CoinGecko / Yahoo)
│
├── sadp/                                     # Structured AI Development Protocol
│   ├── SPEC-CORE.md                          # Rule specifications (R1–R62)
│   ├── RULE_REGISTRY.json                    # Rule state machine
│   ├── EPISODIC_MEMORY.json                  # 154 memory entries
│   ├── EDIT_LOG.jsonl                        # Every file touch with rationale
│   ├── ACERVATOR_HOP4.md                     # Session handoff (43 addenda)
│   ├── NEXT_SESSION_ORDERS.md                # Next-session orders
│   ├── hop_open.py                           # Deterministic 6-step hop-open
│   ├── freshness.py                          # R62 FRG drift detection
│   ├── CHECKLIST.json / checklist.py         # 14 declarative invariants
│   ├── ARTIFACTS.json / cleanup_outputs.py   # Outputs lifecycle manager
│   └── hop_updater.py                        # HOP header regenerator
│
├── docs/
│   ├── adr/                                  # Architecture Decision Records (ADR-001…012)
│   ├── srs/SRS.md                            # Software Requirements Specification
│   ├── AUDITS.md · TEST_PLAN.md              # Test suite overviews
│   ├── ROADMAP.md · RISK_REGISTER.md         # Project management
│   ├── PROJECT_MANAGEMENT.md
│   └── tools/build_product_manual.py         # PDF generator for Product Manual
│
├── logs/
│   ├── real_market/                          # Live bot trade logs + API audit
│   ├── simulator/
│   │   ├── recordings/                       # Screen recorder output (MP4/GIF)
│   │   └── sessions/                         # Per-session story + status logs
│   └── paper/reports/                        # Paper trader session reports
│
├── src/
│   ├── core/                                 # Cross-cutting services
│   │   ├── nuclear_live.py                   # Nuclear Mode engine
│   │   ├── system_load_oscillator.py         # Speed oscillator (v3.13.7)
│   │   ├── nuclear_runner.py · mini_display.py
│   │   ├── state_manager.py · event_bus.py
│   │   ├── sound_engine.py · sms_engine.py
│   │   ├── logging_engine.py · encryption.py · settings.py
│   │   ├── execution_discipline.py · trade_historian.py
│   │   ├── rule_registry.py                  # SADP admin control layer
│   │   └── version_sweep.py                  # Release gate
│   ├── trading/                              # The bot brain
│   │   ├── scrumming_bot.py                  # Core Scrum/Fold engine
│   │   ├── ta_engine.py                      # 7-indicator TA + Landing Strip
│   │   ├── phantom_balance.py                # Multi-TF coordination (TradeLock)
│   │   ├── mr_inspector.py · smart_wire.py
│   │   ├── volume_guard.py · reconciliation.py
│   │   └── risk_manager.py · analytics_engine.py
│   ├── competition/                          # Proof of Accumulation package
│   │   ├── bot_identity.py · merkle_log.py
│   │   ├── competition_engine.py · challenge_protocol.py
│   │   ├── token_ledger.py · nft_minter.py
│   │   ├── trophy_generator.py · season_schedule.py
│   │   ├── base_config.py · base_connector.py
│   │   └── local_testnet.py                  # In-process blockchain for testing
│   ├── exchange/                             # Crypto exchange integrations
│   │   ├── base.py · ccxt_connector.py
│   │   ├── paper_exchange.py · market_data.py
│   │   └── crypto_assets.py · data_pool.py
│   ├── stocks/                               # Equity broker integrations
│   │   ├── broker_base.py · alpaca_connector.py
│   │   ├── stock_bot.py · stock_accumulation_bot.py
│   │   └── tradingview_bridge.py · market_hours.py
│   └── gui/                                  # PySide6 UI
│       ├── main_window.py · simulator.py
│       ├── paper_trader_tab.py · paper_exchange.py
│       ├── testnet_tab.py · competition_tab.py
│       ├── bot_visualizer.py · bot_wizard.py
│       ├── market_map.py · indicator_panel.py
│       ├── screen_recorder.py · audio_suite.py
│       └── ...
```

---

## Running the Battery

```bash
# Full canonical 39-simulation battery
python RAIntSimBat.py

# Extended 78-sim battery (3 recent periods + 3 historical)
python RAIntSimBat.py RAIntSimBat-EXTENDED

# Strategy comparison (vs 6 competitors, all 39 sims)
python RAIntSimBat.py RAIntSimBat-COMPARE-FULL

# Capital scaling battery ($400 / $4K / $20K / $100K × VIP tiers)
python RAIntSimBat.py RAIntSimBat-CAPITAL-SCALING

# Single asset, all years
python RAIntSimBat.py RAIntSimBat-BTC-USD-ALL

# Help / full command reference
python RAIntSimBat.py --help
```

Headless prompts and syntax reference: `HEADLESS_SYNTAX_GUIDE.md`.

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
