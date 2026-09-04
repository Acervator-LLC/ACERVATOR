# Proof of Accumulation

Reference. `src/competition/` is the Proof of Accumulation package. The
engine runs with no screen in front of it, and both the Competition and
Local Testnet tabs stay shelved, which makes this an initial
implementation rather than a repair.

## Identity

`BotIdentity` in `src/competition/bot_identity.py` gives each instance an
Ed25519 keypair. The private key signs every trade in the log; the public
key is the identity another party verifies against. Strategy parameters
are never signed and never published, so authorship is provable while the
method stays private.

## The trade log

`MerkleTradeLog` in `src/competition/merkle_log.py` appends each signed
trade to a Merkle tree. Leaves are the SHA-256 of a trade's canonical
bytes, `merkle_root` returns the commitment, `merkle_proof` builds an
inclusion proof for one trade and `verify_proof` checks it. A third party
can confirm a trade sits in the log without receiving the log.

## The competition lifecycle

`CompetitionEngine` in `src/competition/competition_engine.py` runs four
phases: registration, where a bot commits capital and a config hash;
active, where each trade appends to its Merkle log; submission, where
trading closes and each bot submits a root and a `PerformanceSubmission`;
and adjudication, where the arbiter verifies, ranks and awards. A
competition runs either locally across instances on one machine and one
price feed, or between two machines exchanging signed submissions.

## Tournaments

`TournamentEngine` in `src/trading/poa_tournament.py` builds the game
shapes: `build_duel`, `build_melee` and `build_gauntlet` each return a
`Tournament` from a `TournamentConfig`, and `run` plays it over a candle
provider to an `Outcome`. `DynamicEventScheduler` places market shocks,
puzzle events and regime flips from the config's seed, so the same seed
replays the same tournament. `LocalACRVAdapter` settles the award and
each tournament persists as JSON.

## The token

`TokenLedger` in `src/competition/token_ledger.py` is append-only.
`TOTAL_SUPPLY_CAP` in `src/competition/season_schedule.py` sets the hard
cap at ten million ACRV, and the ledger refuses an award that would pass
it. Awards are idempotent: settling the same result twice writes one
`AwardRecord`. Balances are replayed from the log, and no operation edits
a balance.

`RARITY_TIERS` in the schedule file names five tiers, awarded on rank
within the field: Harvest, Gold Fold, Bear Slayer, Grand Accumulator and
Ekthelius. Season rewards fall each season, so later tokens are harder to
earn.

## Head to head

`challenge_protocol.py` carries the Elo ladder. A challenger sends a
signed challenge, the target accepts or declines, both trade the agreed
asset for the agreed duration, the shared engine adjudicates, and
`ELO_K_FACTOR` at 32 moves both ratings while the stake flows from loser
to winner.

## Trophies

`src/competition/trophy_generator.py` renders one SVG per tier through
`generate_trophy`, and `generate_preview_html` lays the set out on one
page. `harvest_svg` letters `SOLVE · ET · COAGULA` around the trophy's
ring, which is the epigraph's own instruction in its usual form.

## The chain

`local_testnet.py` simulates the whole Base environment in memory, with
no wallet, no ETH and no network. `LocalChain` produces blocks,
`LocalACRV` holds the ERC-20 balances and mint history, `LocalRegistry`
holds competitions, submissions and adjudications, and `LocalTestnet`
binds them together with a mock oracle and transaction receipts.

`base_config.py` carries the real targets for the day it deploys: Base
mainnet at chain id 8453 and Base Sepolia at 84532, with the contract
addresses and ABIs beside them.

## The two shelved tabs

`src/gui/competition_tab.py` and `src/gui/testnet_tab.py` both exist.
`RetiredTabsMixin._install_retired_tab_sentinels` in
`src/gui/main_tabs/retired_tabs.py` assigns `None` to `_competition_tab`
and `_testnet_tab`, and the window builds neither.
`competition_tab_surface` and `testnet_tab_surface` stay registered in
`build_registry` in `src/core/desktop_bridge.py`, so the view models
answer even with no Qt tab in front of them.

Back to [the subsystem index](README.md).
