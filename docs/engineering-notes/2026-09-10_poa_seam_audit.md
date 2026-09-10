# PoA — the seam audit of what is already built

Reference. A seam is a join that does not carry. This audit reads the Proof of
Accumulation machinery for four shapes of it, before a unit falls into one.

```
built but uncalled        a public entry nothing outside its own module calls
reads what nobody writes  a field or a source that is always absent
writes what nobody reads  state produced and never consumed
agrees with nobody        the same figure held in two modules
```

The subjects are the twenty-three modules of the competition package, the shared
bridge, and the Proof of Accumulation tab surface.

```
src/competition/                               10,717 lines, 23 modules
src/gui/shared_testnet.py
src/gui/main_tabs/proof_of_accumulation_tab_surface.py
```

No behaviour changed. Nothing under `src/` was edited.

## The count

Twenty-eight seams. Ten figures are held in more than one module and all ten
agree today; those are listed separately and counted as none of the twenty-eight.

| shape | seams |
| ----- | ----- |
| built but uncalled | 18 |
| reads what nobody writes | 3 |
| writes what nobody reads | 5 |
| agrees with nobody | 2 |

The two counted under the fourth shape are copies inside one module where one
copy is the declaration and the other is a literal nothing checks against it.

## The instrument, and the proof it can tell the two apart

The tool is `vulture`, already in the toolbox and already run by the coding
archetype. It was proved on four symbols this issue had itself recorded as
uncalled, three of which a later unit wired.

```
python -m vulture --min-confidence 60 src/ main.py acervator_watchdog.py tools/ contracts/ dev_harness/

reported     node_link.py:329 unused method 'start_listening'   still has no caller
not reported eligible_pool     capture_bounds.py:369 calls it
not reported open_window        capture_bounds.py:370 calls it
not reported verdict_for        market_rotation.py:358 calls it
```

One symbol fires and three stay quiet, on the same run, and the three are quiet
because code now calls them. That is the two-sided proof.

**The repository's own setting hides every uncalled function.** An unused function
carries 60% confidence and `pyproject.toml` sets a floor of 70, so the plain
command returns nothing at all.

```
python -m vulture src/competition/ src/gui/shared_testnet.py
    exit 0, zero lines                         pyproject min_confidence = 70
python -m vulture --min-confidence 60 ...
    exit 3, 81 rows for these files            the archetype's own setting
```

**Its verdict moves with the scope it is given.** Narrowing the run to the
package plus the bridge reported nine symbols as unused that a wider run clears,
because their only callers sit in `contracts/deploy.py`.

**And it matches a bare name, so a name used anywhere clears it everywhere.**
Two seams below were invisible to it for that reason and were found with
`git grep`.

```
attach_to_bus      logging_engine.py defines one and main.py calls it,
                   so the socket's own method is never reported
capture_bounds     a parameter of that name in three files clears the
                   bridge property of the same name
```

Every zero-caller claim in the table below was confirmed a second way, with
`git grep -o <name> | wc -l` over the index.

## The table, ordered by what blocks a test today

**Ten of the twenty-eight block something he can press today.** They are rows one
to ten, and the last column is the authority. Rows one, two, five and six are one
seam seen from four sides: the bridge builds the right objects over the persisted
chain at launch and the tab reads none of them.

| # | what it is | shape | evidence | owner | blocks a test today |
| - | ---------- | ----- | -------- | ----- | ------------------- |
| 1 | `MarketRotation._post_commitment` writes its commitment transaction to `self._testnet.chain`; `chain_rotation` builds that rotation over a fresh `LocalTestnet()` that is discarded when the control returns | writes what nobody reads | `market_rotation.py:525-527`, surface `:1304-1308`; `LocalTestnet.__init__` builds a new `LocalChain()` and the program prints `block_number 0` | the unit that points the surface at the installed bridge | **yes** — press Drop and the real chain records nothing |
| 2 | `chain_season` reads `current_season` off a fresh `LocalTestnet()`, never off the loaded chain | reads what nobody writes | surface `:1311-1313`; `LocalRegistry.__init__` sets `_current_season = 1` at `local_testnet.py:594` and no statement writes it again | same as 1 | **yes** — the Season panel reads 1 whatever the chain holds |
| 3 | `CertificationSocket.attach_to_bus` has no caller, so no fill ever reaches `certify` | built but uncalled | `certification_socket.py:474`; `install_certification_socket` at `shared_testnet.py:491-523` does not call it; two occurrences in the index, the def and one docstring | the fill-to-activation unit | **yes** — a real trade can never distil |
| 4 | `_on_trade_filled` reads `exchange_id` and `season`; the emit contract declares neither | reads what nobody writes | `certification_socket.py:535,602` against `emit_contracts.py:73-88`, whose optional set ends at `fee_usd` and `fee_refusal` | the fill-to-activation unit | **yes** — every fill names no activation |
| 5 | Eight of the ten objects `install_on` attaches occur only inside the file that made them | writes what nobody reads | `git grep -l` on `_quint_ledger`, `_market_rotation`, `_capture_bounds`, `_certification_socket`, `_node_link`, `_action_spend`, `_event_redistribution`, `_poa_world` returns `src/gui/shared_testnet.py` alone | the unit that points the surface at the installed bridge | **yes** — the installed world, link and socket exist only to be logged |
| 6 | Six bridge read accessors have no caller | built but uncalled | `shared_testnet.py:301,370,402,434,469,526` | same as 5 | **yes** — the same seam from the read side |
| 7 | `ActionSpend` keeps charges and offers in instance memory, and the surface builds a new one per press | writes what nobody reads | `action_spend.py:661-662`; `PoaRecordStore.save` at `:544` persists records and skills only; surface `:1430` | the Elite spend unit | **yes** — a charge that spans turns cannot survive a press |
| 8 | Ten `ActionSpend` methods have no caller: the affordability check, the three-step charge, the three-step underwrite, and three readouts | built but uncalled | `action_spend.py:194,375,681,699,728,740,762,787,794,813` | the Elite spend unit | **yes** — no control reaches the charge or the underwrite |
| 9 | `PoaNodeLink.start_listening` has no caller; the link listens on nothing | built but uncalled | `node_link.py:329` | the tab surface unit | **yes** — two nodes cannot be linked |
| 10 | `stop_listening`, `sync_all` and `verify_request` have no caller | built but uncalled | `node_link.py:352,435,195` | the tab surface unit | yes, with 9 |
| 11 | `EventMode.party_min`, `party_max` and `guild_required` are emitted and read by nothing | writes what nobody reads | `poa_modes.py:81-83,400-402`; `ModeRow` in `proof_of_accumulation_tab.js` renders code, label, variant, turn and ranks | the modes unit | no |
| 12 | Two of four modes set `guild_required` true and nothing enforces it | reads what nobody writes | `poa_modes.py` MODES table, rows two and four | the guild unit | no |
| 13 | `world_grid.py` is 999 lines and sixteen of its public methods have no caller; the tab surface imports nothing from it | built but uncalled | `world_grid.py:136,409,435,502,508,548,617,626,658,737,744,783,790,819,839,846`; thirteen of the sixteen are one occurrence in the whole index | the world unit | no |
| 14 | Seven `QuintessenceLedger` methods have no caller: respawn, both embeds, both releases, two balances | built but uncalled | `quintessence_ledger.py:287,300,312,340,370,389,393` | the Vessel and pleroma unit | no |
| 15 | `CaptureBounds.activation_for`, `close_activation` and `may_award` have no caller | built but uncalled | `capture_bounds.py:406,410,445` | the activation unit | no |
| 16 | `require_participation`, `lifetime_certified_fee_usd`, `ratchet_certified_fee_usd` and `detach_from_bus` have no caller | built but uncalled | `certification_socket.py:398,408,433,488` | the fill-to-activation unit | no |
| 17 | `EventRedistribution.record_certified_fill` has no caller | built but uncalled | `event_redistribution.py:325` | the fill-to-activation unit | no |
| 18 | `MarketRotation.eligibility_of` and `membership_proof` have no caller | built but uncalled | `market_rotation.py:421,588` | the rotation unit | no |
| 19 | `MerkleTradeLog.verify_inclusion` has no caller | built but uncalled | `merkle_log.py:190` | the rotation unit | no |
| 20 | `ClassProgress.experience` is declared with a default of zero and nothing ever writes it | writes what nobody reads | `rpg_classes.py:112`; the only other occurrence is the axis name string at `rpg_metrics.py:48` | the levelling unit | no |
| 21 | `RarityTier.qualifies` has no caller, and `classify_tier` repeats all five percentiles as literals instead of reading `rank_pct_max` | agrees with nobody | `season_schedule.py:58` against `:121-137` | the tier unit | no |
| 22 | `RarityTier.condition` is set on all five tiers and read by nothing; `cumulative_supply` has no caller | built but uncalled | `season_schedule.py:54,39` | the tier unit | no |
| 23 | `WALLET_SECTIONS` is read by nothing; `wallet` builds the same three sections as a literal list | agrees with nobody | surface `:233` is its only occurrence in the index, against `:922-926` | the wallet unit | no |
| 24 | `DECLARED_FIELDS` is read by nothing, and the payload builder repeats all twenty-eight names | built but uncalled | surface `:557`, read nowhere; `view_model` at `:1801` | the tab surface unit | no |
| 25 | `challenge_protocol.py` is 229 lines with no importer outside the package | built but uncalled | only `src/competition/__init__.py` names it; `record_result`, `challenge_hash` and the `declined` field have no reader | the tournament unit | no |
| 26 | `trophy_generator.py` is 295 lines and no Python file in the index names it | built but uncalled | `generate_trophy` at `:231` and the five tier generators have no caller; `setTierSvg` has none either, as `contracts/deploy.py:256` already records | the trophy art unit | no |
| 27 | `ACRV_ABI` and `REGISTRY_ABI` are read by nothing | built but uncalled | `base_config.py:77,179`; the file's only importer is `contracts/deploy.py`, which reads the two network configs and neither ABI | the deployment unit | no |
| 28 | `LocalTestnet.cap_reached`, `get_total_supply`, `get_remaining_supply` and `tx_url` have no caller | built but uncalled | `local_testnet.py:551,895,898,931` | the chain unit | no |

## The figures held in more than one module

Ten. **Every copy agrees today, and no check pins a single one of them.**
`tests/contracts/` carries six Foundry suites and none compares a Solidity figure
against its Python twin.

| the figure | where it is held | agree |
| ---------- | ---------------- | ----- |
| the season budget curve | `season_schedule.py:25-36` and `CompetitionRegistry.sol:327-339`, both dividing once | yes |
| the four trophy ceilings | `season_schedule.py` `max_ever` and `AcervatorTrophy.sol:63-66`, plus bare literals at `local_testnet.py:744,922,923` | yes, across three copies of 21 and two of 1,000 |
| the five loot weights | `loot_drop.py:LOOT_TIERS` in per cent and `tests/contracts/AcervatorLoot.t.sol:223-227` in per mille | yes, after scaling |
| the bleed curve | `quintessence_ledger.py:15-16` and `Quintessence.sol:64-66` | yes at every level |
| the Quintessence cap | `quintessence_ledger.py:13` and `Quintessence.sol:58` | yes |
| the transfer skill bounds | `quintessence_ledger.py:17-18` and `Quintessence.sol:60-61` | yes |
| one Quintessence in base units | `event_redistribution.py:38`, `Quintessence.sol:54`, `local_testnet.py:48`, `Quintessence.sol:56` | yes, under four names |
| the ACRV cap | `season_schedule.py:16` and `ACRV.sol:47` | yes |
| the largest party | surface `:159` and the `poa_modes.py` MODES table | yes |
| the season floor and first pool | `season_schedule.py:18,22` and `CompetitionRegistry.sol:122-123` | yes |

Two of the ten carry a third copy, and the third copy is the exposed one.

```
local_testnet.py:744   if self._ekthelius_minted >= 21
local_testnet.py:922   "remaining_ekthelius": 21 - self._registry._ekthelius_minted
local_testnet.py:923   "remaining_grand_acc": 1000 - self._registry._grand_acc_minted
```

The contract states these as named constants and a Foundry suite pins them. The
Python copies are bare numbers inside one method and nothing pins them at all.

The five loot weights have a sharper gap. `contracts/deploy.py` deploys five
contracts and the loot contract is not among them, so the weights its constructor
requires have no source outside a test file.

```
deployed   ACRV, CompetitionRegistry, AcervatorTrophy, Quintessence, Governance
absent     AcervatorLoot
```

## What was collected rather than found

Four seams were already recorded in this issue's unit reports and are carried
here with their evidence re-measured, not rediscovered.

```
start_listening           unit 16 named it; still uncalled
the fill names no activation   the activation unit named it; the emit contract confirms it
the emission figure       the pool unit named it; it is his to set
block membership          the ordering unit named it; it is his to choose
```

Three more that those reports named are now closed, and the audit says so rather
than repeating them.

```
eligible_pool   wired, capture_bounds.py:369
open_window     wired, capture_bounds.py:370
verdict_for     wired, market_rotation.py:358
```

The remaining twenty-four were found here.

## Awaiting his decision, and not defects

These are product questions. Each is recorded in the issue already.

```
the emission figure       how much Quintessence a market's pool holds in a window
block membership          appoint a writer, or another of the three named ways
the age rule's absence    refuse, admit, or add a second age source
the external review       whether a firm reads the contracts before genesis
what a first version is   the machinery provable, or something he can play
```

## The honest placeholders, deliberately not reported as seams

Each of these says on screen that the thing is not built. That is the correct
answer and reporting it would bury the real findings.

```
the map subtab      MAP_ABSENT_TEXT at surface:530
the gear subtab     GEAR_ABSENT_TEXT at surface:550
the season control  SEASON_ADVANCE_TEXT at surface:474
the guild term      NO_GUILD_NOTE at surface:205
```

The season text is honest about the counter and does not cover seams one and two,
which are about which chain object the surface reads.

## The denominator

Twenty-three modules. Twenty-one are reached from outside the package; two are
not.

```
reached       21 modules
not reached   challenge_protocol.py  229 lines
              trophy_generator.py    295 lines
script only   base_config.py         346 lines, contracts/deploy.py alone
```

## What no named tool could answer

Whether the Solidity half of the season budget curve returns the same number as
the Python half, driven rather than read. The Python side was run and printed its
values. The contracts have never compiled, because no toolchain resolves their
imports, so `forge` cannot execute `seasonBudgetTokens` to compare. The two
algorithms were read against each other and they match in structure; that is a
reading, not a measurement, and it is stated as one.

## Raw output

Gitignored, under `artifacts/`.

```
U42_vulture_narrow.txt     the plain command, zero rows at the repository floor
U42_vulture_narrow60.txt   the package and the bridge
U42_vulture_whole60.txt    src, main, watchdog, tools
U42_vulture_all60.txt      the widest scope, including contracts
U42_const_competition.txt  every numeric module constant in the package
```
