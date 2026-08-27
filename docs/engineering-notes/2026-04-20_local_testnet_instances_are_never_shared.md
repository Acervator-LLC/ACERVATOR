# Every `LocalTestnet()` is a private chain, so PoA activity reaches no display

**Found** 2026-04-20 · v3.11.1 · **Status** RESOLVED, one residual noted in §4

Salvaged from a session report that carried this finding inside a
verify-turn narrative. Only the technical content is kept.

## 1. The finding

`LocalTestnet` holds all chain state on the instance: `_chain`
(blocks, transactions, events), `_acrv` (supply and per-wallet
balances), `_registry` (competitions and adjudications). There was no
singleton, no registration, and `persist_path` defaulted to `None`.
Five call sites each constructed their own, so five separate chains
ran and none of them saw another's writes.

## 2. The two observable symptoms

**Every PoA round logged "block #11".** The Nuclear round handler built
a fresh `LocalTestnet()` per round and let it fall out of scope at the
end. `run_demo_competition` mines eleven blocks — open, three
registrations, activate, close, three submissions, adjudicate, mint —
so a chain two seconds old sealed at height 11 every time. Height never
advanced to 22 or 33 because no chain survived a round.

**The TestNet tab showed zeros.** The tab built its own `LocalTestnet()`
at construction and polled it every 3 s. Nothing wrote to that instance,
so every poll read zeros. Its own Run Competition and Stress Test
buttons did populate it, which is why the tab looked live under manual
use and dead under Nuclear.

## 3. What resolved it

`src/gui/shared_testnet.py` — `SharedTestnetBridge.install_on` builds
ONE `LocalTestnet`, attaches it to the MainWindow as `_local_testnet`,
and persists to `~/.acervator/testnet_chain.json` (schema 1, 500 ms
debounce). It is installed at `src/gui/main_window.py:5304`, before tab
construction. Writes are enqueued from any thread and applied on the Qt
main thread; reads are direct.

The two symptom surfaces are both gone independently. `nuclear_live`
was retired in v3.18.3 and its round handler with it
(`src/trading/poa_tournament.py:11`). The TestNet tab is not built:
`src/gui/main_window.py:6021` sets `_testnet_tab = None`, and
`TestnetTab` has no construction site in `src/`, `tests/` or `main.py`.

## 4. Residual — the thread-safety half is convention, not mechanism

`src/competition/local_testnet.py` still carries no lock and does not
import `threading`. Line 224 is a read-modify-write:

```python
self._balances[recipient] = self._balances.get(recipient, 0) + amount_wei
self._total_supply += amount_wei
```

That is safe only while every mutating caller goes through the bridge,
which serialises on `threading.Lock` and on the Qt main thread. One
bypass remains reachable in source: `src/gui/testnet_tab.py:142` falls
back to a private `LocalTestnet()` when no shared instance is passed.
That path is dead while the tab is never constructed.
