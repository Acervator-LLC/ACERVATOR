# Two surface residuals — the unlocked token balance and the private chain

Two pieces of code in the Proof of Accumulation subsystem were safe only while
nothing constructed them. The window builds the first one at start-up. The second
is reached by constructing the class, which is what a new surface does.

## The error

Neither throws. Each is found by reading numbers the program reports about itself.

A token award adds the same amount to the holder's balance and to the total
supply, so the two must agree. Driven from sixteen threads, they do not.

```text
switch interval: 1e-06
supply_summary tier_counts: {'Accumulator': 4800}
mints the program logged: 4800
total_supply() in wei: 4800
balance_of in wei: 3709
```

4,800 awards reached the total and 3,709 reached the balance. 1,091 vanished with
no error and no log line.

The Testnet tab built without the shared chain reports a chain of its own, at a
different block height, and raises nothing.

```text
shared chain block_number: 1
constructed with no bridge
tab._testnet is bridge.testnet: False
tab chain block_number: 0
```

## Reproduction

`main.py` cannot run while the operator is trading. `main.py:812` builds an
instance guard whose `take_ownership` writes into the live `~/.acervator` tree.
The construction path is reached directly instead, the way
`MainWindow._setup_ui` reaches it at `src/gui/main_window.py:277`.

```text
SharedTestnetBridge.install_on(main_win, persist_path=<temp>,
                               quint_ledger_path=<temp>)
  -> LocalTestnet()
  -> LocalACRV(chain, LocalRegistry.ADDRESS)

16 threads x 300 calls to LocalACRV.mint(holder, 1, "comp-race",
"Accumulator", caller="owner"), with sys.setswitchinterval(1e-6)

then TestnetTab(), and TestnetTab(shared_testnet=None, bridge=None)

PYTHONWARNINGS=error python -X dev -X faulthandler <driver>
```

The construction is the program's own and it says so on its own logger.

```text
acervator.shared_testnet SharedTestnetBridge installed (persist=...testnet_chain.json)
bridge.testnet is win._local_testnet: True
acrv class: LocalACRV
```

At the interpreter's default switch interval of 0.005 s the same run lost nothing
in three attempts, and a heavier run of 64,000 awards lost nothing either. The
lost balance is reliable only with the switch interval shortened to one
microsecond; its rate at the default is below what these runs can measure.

Nothing in `src/` constructs the tab today.
`RetiredTabsMixin._install_retired_tab_sentinels` sets `_testnet_tab` to None, so
the class is reached only by constructing it, which the run above does.

## The cause

`LocalACRV.mint` in `src/competition/local_testnet.py` read a balance, added to
it and wrote it back as separate steps, with no lock, and the module imported no
threading at all. A thread suspended between the read and the write stores a
figure computed from a total another thread has already replaced.

```python
self._balances[recipient] = self._balances.get(recipient, 0) + amount_wei
self._total_supply += amount_wei
```

The supply cap check above those lines had the same shape, so two threads could
both read a total under `MAX_SUPPLY_WEI` and both add.

`src/gui/testnet_tab.py` accepted a missing chain and built one.

```python
self._testnet = shared_testnet or LocalTestnet()
```

`SharedTestnetBridge` exists so one chain serves the whole process. A surface
holding a second chain shows block numbers, balances and events, all of them its
own, and agrees with nothing.

## The correction

`LocalACRV` takes a `threading.RLock` in its constructor. `mint` holds it across
the cap check, the balance write, the running total and the award record. Every
reader of those fields takes the same lock, so no reader catches the balance and
the total apart. The event field `totalSupplyAfter` is bound inside the lock
instead of read after it.

```python
        with self._supply_lock:
            if self._total_supply + amount_wei > MAX_SUPPLY_WEI:
                raise OverflowError("ACRV: mint would exceed MAX_SUPPLY")
            self._balances[recipient] = self._balances.get(recipient, 0) + amount_wei
            self._total_supply += amount_wei
```

No arithmetic changed. The expressions are the ones that were there.

In the tab, `shared_testnet` and `bridge` are keyword-only with no default, so
Python refuses a call that omits either, and None for either raises. The no-Qt
stub at the foot of the file takes the same two arguments, so both definitions of
the class carry one contract.

```python
        def __init__(self, parent=None, *, shared_testnet, bridge):
            """Read the chain through ``shared_testnet`` and ``bridge``; neither may be None."""
            super().__init__(parent)
            self.setAccessibleName("Testnet Tab")
            if shared_testnet is None or bridge is None:
                raise ValueError(
```

A missing bridge raises rather than building a private chain, because the issue
rules that way — *"The second needs the bridge to be required rather than
optional"* — and because a private chain is invisible. It renders, it answers,
and it diverges with nothing to read.

## The rerun

Three runs at the one microsecond switch interval, all 4,800 against 4,800.

```text
acrv _supply_lock: <unlocked _thread.RLock object owner=0 count=0 at 0x...>
switch interval: 1e-06
supply_summary tier_counts: {'Accumulator': 4800}
mints the program logged: 4800
total_supply() in wei: 4800
balance_of in wei: 4800
```

The shared path through the tab is unchanged, and both ways of omitting the chain
now stop.

```text
tab._testnet is bridge.testnet: True
tab chain block_number: 1
refused: TypeError: TestnetTab.__init__() missing 2 required keyword-only
arguments: 'shared_testnet' and 'bridge'
refused: ValueError: TestnetTab needs the process-wide chain: pass the
shared_testnet and bridge that SharedTestnetBridge.install_on attached to the
MainWindow. A private LocalTestnet would diverge from every other reader.
```

## Two-sided controls

The before-state is read from git with `git stash`, never rebuilt by hand, so the
bytes are exactly `origin/current`. Driving the same two paths on it returns the
old behaviour.

```text
acrv _supply_lock: None
balance_of in wei: 3709          (total_supply() in wei: 4800)

constructed with no bridge
tab._testnet is bridge.testnet: False
tab chain block_number: 0
```

## What stands

`src/gui/testnet_tab.py:443` still names `LocalTestnet()` in the reset branch for
a missing bridge. A required bridge puts that branch out of reach.

`src/competition/local_testnet.py:721` draws the demo price series from
`random.Random(42)`, which `ruff` reports as `S311` at high severity. It sits at
the same line on `origin/current` and has been in the file since it was added.
Every replacement changes the figures the demo produces.
