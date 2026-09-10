# The certified transaction socket — the program error, the runs and the controls

Reference. Subjects: `src/competition/certification_socket.py`,
`src/gui/shared_testnet.py`, `src/competition/__init__.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

No test file was written. The evidence is two scratch probes that construct the
socket through the real install path and read what the program reports.

`main.py` was never launched. Its instance guard writes into the runtime tree the
operator's live process holds, so the construction path was reached directly.

## The error

The first probe run produced no output and exited 1 after more than two minutes.

```
$ PYTHONWARNINGS=error python -X dev -X faulthandler U7_probe_socket.py
EXIT=1
(no stdout, no stderr, no traceback)
```

Git Bash reported no output at all, which is the same shape a native crash takes
on this host. The process was alive at 19 MB of resident memory and had to be
killed.

```
ProcessId    : 26088
CreationDate : 9/9/2026 10:19:05 PM
cmd          : python.exe -X dev -X faulthandler .../U7_probe_socket.py
```

## Reproduction

```
python -X dev -X faulthandler -u <probe> <worktree root>
PYTHONWARNINGS=error
Python 3.14, PySide6 installed, no QApplication yet running
```

Each import of the socket's dependency chain was timed on its own, which ruled
out the import tree.

```
import src                                0.07 s
import src.competition.certification_socket  0.09 s
import PySide6.QtWidgets                  0.10 s
import src.gui.shared_testnet             0.07 s
QApplication([])                          0.02 s
```

## The cause

The probe resolved the repository root by walking up from its own location until
it found a `src` directory. The probe lives in the scratchpad, which is not inside
the repository, so the walk reached the drive root. `Path("C:/").parent` returns
`C:/`, so the loop never ended and no print statement was ever reached.

```python
ROOT = Path(__file__).resolve()
while not (ROOT / "src").is_dir():
    ROOT = ROOT.parent
```

The error was the probe's, not the socket's. It is recorded because the silence it
produced reads exactly like a crash and cost two kills and five diagnostic runs.

## The correction

The probe takes the worktree root as its first argument and refuses a path that
holds no `src` directory.

```python
ROOT = Path(sys.argv[1]).resolve()
if not (ROOT / "src").is_dir():
    raise SystemExit(f"{ROOT} holds no src directory; pass the worktree root")
```

## The rerun

```
$ PYTHONWARNINGS=error python -X dev -X faulthandler -u U7_probe_socket.py <root>
PROBE_EXIT=0
```

No warning was raised under `PYTHONWARNINGS=error` and no fault handler output
appeared.

## Constructed

`SharedTestnetBridge.install_on` builds the socket in the same call that builds
the chain and the Quintessence ledger. The probe calls that classmethod with a
`QObject` standing in for the window, and temporary paths for all three files.

```
bridge                            SharedTestnetBridge
socket on the window              CertificationSocket
socket is the bridge's            True
chain the socket holds            True   (is main_win._local_testnet)
ledger the socket holds           True   (is main_win._quint_ledger)
chain lock shared with the bridge True   (is bridge._mutation_lock)
```

## Reached

A `trade.filled` event on the real `EventBus` certifies, writes a transaction and
an event to the chain, and mints.

```
trade.filled subscribers          1
before the emit, may_participate  False
after the emit,  may_participate  True
lifetime certified fee            4.65
certified fill count              1
ledger balance                    4.650
chain block number                1
TradeCertified events on chain    1
event args   {'bot': '90694c610f990ad0', 'competition': 'POA-STANDING',
              'merkleRoot': '748a1885bd8d1556',
              'leafHash': '748a1885bd8d1556', 'tradeSeq': 0,
              'feeUsd': '4.65', 'distilled': '4.650'}
```

**No bot calls the socket yet.** The subscriber exists and works, and the only
emit sites for `trade.filled` are the four inside
`src/trading/scrumming/execution.py`, none of which carries a fee field. A fill
arriving from a live bot today certifies and distils zero. Publishing the venue
fee on that topic changes an emitter inside the trading engine, which this unit
may not touch; unit 9 is the next unit that needs a non-zero award and is where
that belongs.

## The four mechanism runs

```
a fill certifies and distils
  fee $4.65 -> distilled 4.650, leaf 748a1885…, root 748a1885…, seq 0
  fee $4.58 -> distilled 4.580, lifetime total $9.23, seq 1

an uncertified fill distils nothing
  a second bot, no certified fill
    may_participate           False
    lifetime fee              0
    ledger balance            0
    require_participation     CertificationRefusedError - bot 7b00d3c413e4 has
                              certified no trades and cannot enter a PoA event
  a trade.filled for that bot with fee $99.00
    total ever minted unchanged   True

a bad signature is refused
  a third identity claiming the first bot's public key
    ValueError - Invalid signature on trade seq=2
    lifetime fee after the attempt   $9.23, unchanged

a replayed certification distils nothing twice
  the same fill_id a second time
    CertificationRefusedError - fill venue-fill-2 is already certified for
                               bot 90694c610f99
    lifetime fee unchanged      True
    total ever minted unchanged True
```

The positive control for the two "nothing happened" runs is in the same run: the
identical bus path and the identical `certify` call did mint, moments earlier, for
the bot that holds its own key.

## The monotonic lifetime fee total

It lives in `CertificationSocket._lifetime_fee_usd`, one `Decimal` per bot id,
written to `~/.acervator/certification_socket.json`. Three writers reach it and
every one of them can only raise it.

```
a certified fill     total += the venue's fee for that fill
a windowed reading   total = max(total, observed)
a reload             total = max(total, the figure in the file)
```

Nothing subtracts, and no path assigns a smaller value. The windowed reading
exists because `BotStats.fees_paid_exchange` is re-derived from a 500-trade fetch
in `src/trading/scrumming/reconciliation.py` and falls as older fills age out.
The `max` shape is the one `sync_ytd_trade_count` already uses on
`ytd_scrummed_usd` and `ytd_folded_usd`.

```
held after two certified fills   $9.23
ratchet to a window figure 500   $500.00
ratchet to a window figure 12    $500.00
held after both                  $500.00
reloaded from the file           $500.00, fill count 2, may_participate True
```

**No existing number changed meaning.** `fees_paid_exchange`,
`SettledSellFee.fee_amount`, `trading_fee_pct` and `_record_venue_fee` are
untouched, and the socket reads none of them: the fee arrives on
`CertifiedFill.fee_usd`, supplied by the caller.

## Conservation after every distil

The ledger's three buckets were read after every write and after every refusal.

```
after the bus fill       wallets 4.650 + held 0 + platonic 0 = 4.650
                         ever minted 4.650  balanced=True within_cap=True
after the fold distil    wallets 9.230 + held 0 + platonic 0 = 9.230
                         ever minted 9.230  balanced=True within_cap=True
after the uncertified    wallets 9.230 + held 0 + platonic 0 = 9.230
 fill                    ever minted 9.230  balanced=True within_cap=True
after the refused        wallets 9.230 + held 0 + platonic 0 = 9.230
 forgery                 ever minted 9.230  balanced=True within_cap=True
after the refused        wallets 9.230 + held 0 + platonic 0 = 9.230
 replay                  ever minted 9.230  balanced=True within_cap=True
demo ledger after the    wallets 3.720 + held 0 + platonic 0 = 3.720
 demo distil             ever minted 3.720  balanced=True within_cap=True
```

## Two-sided controls

One edit per run, against the staged file, restored with `git checkout --` and
confirmed by an empty `git status` for that path. Every other refusal stayed red
in every run, which shows each edit blinded only its own guard.

```
BASELINE, no edit
  replay          REFUSED by CertificationRefusedError
  participation   REFUSED by CertificationRefusedError
  bad signature   REFUSED by ValueError
  supply cap      REFUSED by CertificationRefusedError
```

```
BLIND-REPLAY
  certification_socket.py  _certified_fill_ids.get(bot_id) -> get(bot_id + "-blind")
  replay          ADMITTED
  replay lifetime fee 4.0 -> 8.0         the same fill distilled twice
  the other three REFUSED
```

```
BLIND-PARTICIPATION
  certification_socket.py  if not self.may_participate -> if self.may_participate
  participation   ADMITTED
  the other three REFUSED
```

```
BLIND-SIGNATURE
  merkle_log.py  if not skip_sig_verify and not verify_trade
                 -> if skip_sig_verify and not verify_trade
  bad signature   ADMITTED
  total ever minted 500.00               a forged fill minted a full award
  the other three REFUSED
  git status after the restore  empty
```

```
BLIND-CAP
  certification_socket.py  if award > remaining -> if award > remaining + award
  supply cap      REFUSED by OverflowError, from QuintessenceLedger.distil
  the other three REFUSED
```

**The cap control changed which layer refuses, and that is what the pre-check is
for.** With the pre-check in place nothing reaches `MerkleTradeLog.append`. With
it blinded the leaf is appended first and the ledger then raises, leaving an
append-only log carrying a fill that never distilled. The ledger is the second
guard and the ordering is the first one's job.

## Demo mode

The chain, the ledger path and the competition name all arrive at construction,
so a TestNet run is a second socket and not a flag.

```
live socket   chain from SharedTestnetBridge   competition POA-STANDING
demo socket   its own LocalTestnet             competition POA-DEMO
demo certify  fee $3.72 -> distilled 3.720, seq 0, its own root and tx
demo chain is a different object   True
live ledger after the demo        9.230, unchanged
demo ledger after the demo        3.720
```

## The instruments, calibrated before any verdict was trusted

```
coding_archetype  known_good.py          passed=True   exit 0
                  known_bad.py           passed=False  exit 1, 5 high
ta_archetype      known_good_ta001.py    exit 0
                  known_bad_ta001.py     exit 1
docs_archetype    known_good.md          exit 0
                  known_bad.md           exit 1
```

## The archetypes

```
coding_archetype  src/competition/certification_socket.py  passed=True   53 findings
                                                           0 high, errors []
                                                           11 tools, all ok
ta_archetype      src/competition/certification_socket.py  passed=True    0 findings
                                                           3 tools, all ok
coding_archetype  src/gui/shared_testnet.py                passed=True   99 findings
                                                           0 high, errors []
                                                           11 tools, all ok
ta_archetype      src/gui/shared_testnet.py                passed=True    0 findings
                                                           3 tools, all ok
coding_archetype  src/competition/__init__.py              passed=True    7 findings
                                                           0 high, errors []
                                                           11 tools, all ok
docs_archetype    docs/manual/08-tabs/
                  proof-of-accumulation.md                 passed=True   70 findings
                                                           0 high, errors []
                                                           7 tools, all ok
```

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED
```

The black lane failed once, on formatting only, and passed after `black` rewrote
four line breaks in the new module. Both probes ran again afterwards and printed
the same verdicts.

## The manual

One dated block appended at `2026-09-09 22:28`, after the `21:37` block, so the
dated sections stay in forward order.

```
git diff minus lines        1
the one minus line          --- a/docs/manual/08-tabs/proof-of-accumulation.md
bytes before / after        41432 / 47586
prefix unchanged            True
carriage returns added      0
line endings                1168 LF, 0 CRLF, as the file already was
```

## What stands, and why

```
no bot calls the socket
  trade.filled carries no fee field at any of its emit sites, so a live fill
  certifies and distils zero. Adding that field changes an emitter inside
  src/trading/scrumming/execution.py, which this unit may not touch.

the trade grade is one
  CertifiedFill.trade_grade defaults to 1.0, the identity, so the socket applies
  no curve. The curve is unit 10.

no rotation, no eligibility, no per-market ceiling
  The only ceiling the socket applies is the 33,000,000 supply cap. Units 9 and
  10 own the rest.

the certified fill id set grows
  One id per certified fill is kept per bot, on disk, so the replay refusal
  survives a relaunch. Retention of that file is not this unit's subject.

the fallback signature path
  BotIdentity._fallback_verify accepts any 32-byte value when the cryptography
  library is absent. It was present for every run here, so Ed25519 signed and
  verified every fill. A host without that library weakens the refusal and the
  socket does not detect it.
```
