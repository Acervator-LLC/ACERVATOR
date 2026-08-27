# Suppression Audit

Audit. Every `noqa`, `nosec` and `type: ignore` in the live tree, classified
by measurement. This document classifies directives and proposes units. It
changes no code, removes no directive, and bumps no version.

Date: 2026-08-13. Tree: `acervator_session25_CLOSE_hop5_v3_15_27`,
branch `cascade/c43-release-gate-integrity`. Read-only throughout.

The authoritative number is **709 directives in 217 files: 622
LOAD-BEARING, 58 REDUNDANT, 29 DEAD, 0 unmeasured**. Eleven of the
load-bearing ones hide a finding that describes a real defect.

Why this audit exists, in the operator's words:

> Treat every existing noqa/nosec as UNVERIFIED. A `# nosec B310` glossed a
> real `file:///` hole for the life of the file. Never add one to clear a
> finding.

---

## 1. The instrument and its controls

### 1.1 What counts as a directive

A comment token whose first pragma segment starts with one of eleven
spellings: `noqa`, `ruff: noqa`, `nosec`, `nosemgrep`, `type: ignore`,
`pyright: ignore`, `pylint: disable`, `pylint: skip-file`, `flake8: noqa`,
`mypy: disable-error-code`, `mypy: ignore-errors`. Only four occur:
650 `noqa`, 34 `ruff: noqa`, 18 `type: ignore`, 7 `nosec`.

Matching runs on comment tokens, so the same text inside a docstring or a
string literal does not count. The rule is the one `tools/touchset.py`
already uses, so the counts here and the gate's counts are comparable.

### 1.2 Which rules are enabled

**The repository has no lint configuration.** `pyproject.toml` declares
`build-system`, `project`, `setuptools`, `pytest`, `coverage`, `mutmut` and
`vulture`, and nothing else. The tree holds no `ruff.toml`, `setup.cfg`,
`.flake8`, `mypy.ini`, `.pylintrc`, `pyrightconfig.json` or `bandit.yaml`,
in the repository or in any parent directory.

The invocation therefore decides what "enabled" means, and the invocation
that binds is the archetype gate's. Anchor text, `tools/harness/coding_archetype.py:469`:

```
cmd = [sys.executable, "-m", "ruff", "check", "--output-format=json",
       "--no-cache", "--select=ALL"]
```

For a test file the gate appends an ignore list. Anchor text,
`coding_archetype.py:453`:

```
_TEST_FILE_EXEMPT = ("S101", "S105", "S106", "PLR2004", "SLF001")
```

Every measurement below mirrors that invocation, including the test split.
Ruff 0.16.0 resolves 810 rules under `--select=ALL` with no config file.

**The brief's premise is falsified.** The brief expected a large DEAD class
on the theory that `BLE001` is not enabled here. `BLE001` is enabled and
does fire: stripping it produces `Do not catch blind exception: Exception`
at every one of the 334 sites that name it. Ruff has two distinct verdicts,
and they are not the same finding:

| ruff says | meaning | bucket |
|---|---|---|
| silence | the directive suppressed a real finding | LOAD-BEARING |
| `RUF100 Unused noqa (unused: X)` | rule enabled, does not fire here | REDUNDANT |
| `RUF100 Unused noqa (non-enabled: X)` | rule not in the selected set | DEAD |
| `RUF102 Invalid rule code` | ruff has no such rule | DEAD |

The incident that prompted this audit was `(unused: BLE001)`. That is
REDUNDANT, not DEAD.

### 1.3 Method

Per directive: copy the file, neutralise that one directive, run the owning
analyzer on both copies, diff the finding sets. The difference is what the
directive hides.

Three properties of the method are load-bearing, and each was learned by
getting it wrong first.

**Neutralisation preserves the line length.** The pragma is overwritten with
padding, not deleted. A line that exceeds the 88-character limit only
because of its trailing pragma would otherwise drop under the limit in the
variant, `E501` would not fire, and a load-bearing directive would be
recorded as suppressing nothing. Padding goes to the left of the comment,
because padding on the right leaves trailing whitespace and `W291` then
appears in the added set as a finding the directive never hid.

**Findings compare by line and rule code, never by message.** Ruff messages
quote the file name, so a text comparison between two differently named
copies never matches and every directive reports LOAD-BEARING.

**A file-level directive is diffed over the whole file.** `# ruff: noqa: X`
on line 1 suppresses across every line. Comparing only line 1 reports every
file header as suppressing nothing. This synthesis made that error on its
first pass, disagreed with a probe, and found the fault in its own
instrument.

### 1.4 Two-sided control

Three controls, each taking a real directive whose live verdict is known and
mutating the code beneath it so the rule's own precondition changes. A
verdict that flips only when the code changes is a measurement.

```
OK  a_redundant_to_loadbearing: got=LOAD_BEARING expected=LOAD_BEARING
      base=(none)          var=BLE001            added=BLE001
      logger.exception -> logger.warning removes ruff's BLE001 exemption
OK  b_loadbearing_to_redundant: got=REDUNDANT    expected=REDUNDANT
      base=RUF100          var=(none)            added=(none)
      except Exception -> except ValueError leaves nothing blind to catch
OK  c_dead_is_producible:       got=DEAD         expected=DEAD
      base=BLE001,RUF102   var=BLE001            added=(none)
      the directive names a rule code ruff does not define
```

Case (a) proves the method is not stuck on REDUNDANT. Case (b) proves it is
not stuck on LOAD-BEARING. Case (c) exists because this run reported DEAD
for no directive outside `tests/`, and a zero is a claim about the
instrument until the bucket is shown reachable.

Two further instruments were controlled, because each returned a zero
somewhere:

**mypy.** A control module carries two ignores: one over a real assignment
error, one over a call that type-checks. Mypy named only the second:
`control_pair.py:18: error: Unused "type: ignore" comment [unused-ignore]`,
and stayed silent on line 17. The reading separates a live ignore from a
dead one, in the same invocation that produced the measurement.

**bandit.** A control module carries `PASSWORD_A = "hunter2"` bare and
`password_b = "hunter2"  # nosec B105`. Honouring nosec reports line 3 only;
`--ignore-nosec` reports both. The difference set is non-empty, so an empty
difference on a real file is a statement about that file.

**The enumerator.** Planted `# noqa: F401` in five variants of one module:
baseline 0, on a code line 1, inside a docstring 0, inside a string literal
0, and inside the prose `# we did NOT add a noqa here, the finding is real`
0. The last is the discriminator. Without comment-token anchoring, writing
down a refusal to suppress would inflate the audit that reads it.

### 1.5 Coverage

Four measurements, no overlap, summing to the enumerated total.

| instrument | directives | scope |
|---|---|---|
| probe, scrumming_bot | 42 | `src/trading/scrumming_bot.py` |
| probe, main_window | 74 | `src/gui/main_window.py` |
| probe, rest | 432 | `tests/`, `tools/`, `simulator_tab/`, five named files |
| this synthesis | 161 | everything the three probes did not reach |
| **total** | **709** | |

The 161 breaks down as 138 ruff-owned, 17 `type: ignore`, 6 `nosec`. All
138 variants passed an integrity check: each differs from its baseline in
exactly one line, at the expected line, with no line-count or line-ending
drift.

---

## 2. The bucket table

### 2.1 Whole tree

| bucket | count | share |
|---|---|---|
| LOAD-BEARING, benign | 611 | 86.2% |
| **LOAD-BEARING, hiding something** | **11** | **1.6%** |
| REDUNDANT | 58 | 8.2% |
| DEAD | 29 | 4.1% |
| **total** | **709** | |

By area:

| area | total | dead | redundant | load-bearing |
|---|---|---|---|---|
| `tests/` | 260 | 29 | 12 | 219 |
| `src/gui/` | 184 | 0 | 18 | 166 |
| `src/gui/simulator_tab/` | 126 | 0 | 8 | 118 |
| `src/trading/` | 76 | 0 | 6 | 70 |
| `tools/` | 24 | 0 | 8 | 16 |
| `src/core/` | 19 | 0 | 2 | 17 |
| `src/exchange/` | 12 | 0 | 2 | 10 |
| `src/stocks/` | 8 | 0 | 2 | 6 |

By the rule code that actually reappeared when the directive was removed:

| code | count | what it says |
|---|---|---|
| `BLE001` | 334 | blind `except Exception` |
| `E402` | 221 | import not at top of file |
| `S110` | 78 | `try`/`except`/`pass` |
| `S101`, `SLF001` | 57 | assert used, private member access |
| `SIM105` | 15 | use `contextlib.suppress` |
| everything else | 33 | `N802`, `S311`, `F401`, `S603`, `S607`, `A002`, `E501`, `S112`, `S310`, `B104`, `B105`, `B006`, `D401`, `F821`, `F841`, `E721`, `PLC0415` |

`BLE001` and `E402` are 78% of the tree. Neither describes a defect on its
own. `E402` is the `sys.path` preamble in test files and the PySide6 import
guard. `BLE001` is this codebase's stated posture for surfaces that must not
die. **The boring result is the result, and it is stated plainly: 611 of 709
directives suppress a real finding that is not a defect.**

### 2.2 Per file

Every file carrying three or more directives. The remaining 187 files carry
one or two each.

| total | dead | redun | load | file |
|---|---|---|---|---|
| 74 | 0 | 5 | 69 | `src/gui/main_window.py` |
| 42 | 0 | 2 | 40 | `src/trading/scrumming_bot.py` |
| 40 | 0 | 3 | 37 | `src/gui/simulator_tab/fleet/fleet_replay_panel.py` |
| 23 | 0 | 2 | 21 | `src/gui/bot_visualizer.py` |
| 21 | 0 | 1 | 20 | `src/gui/simulator_tab/fleet/fleet_replay_controller.py` |
| 19 | 0 | 2 | 17 | `src/gui/simulator_tab/nuclear_fleet_controller.py` |
| 18 | 0 | 1 | 17 | `src/gui/simulator_tab/simulator_tab.py` |
| 13 | 0 | 3 | 10 | `src/gui/bot_live_settings.py` |
| 11 | 0 | 0 | 11 | `src/gui/indicator_panel.py` |
| 11 | 0 | 0 | 11 | `src/gui/simulator_tab/nuclear_mode_panel.py` |
| 11 | 0 | 2 | 9 | `tests/test_extractor_requires_parent.py` |
| 10 | 0 | 4 | 6 | `tools/harness/ta_archetype.py` |
| 8 | 0 | 2 | 6 | `src/gui/market_inspector.py` |
| 7 | 0 | 0 | 7 | `src/core/state_manager.py` |
| 7 | 0 | 2 | 5 | `src/stocks/tradingview_bridge.py` |
| 7 | 0 | 1 | 6 | `src/trading/bot_container.py` |
| 6 | 0 | 0 | 6 | `src/gui/bot_wizard.py` |
| 6 | 0 | 0 | 6 | `src/gui/crypto_news_ticker.py` |
| 6 | 0 | 0 | 6 | `src/gui/simulator_tab/nuclear_controller.py` |
| 5 | 0 | 0 | 5 | `src/gui/history_tab.py` |
| 5 | 0 | 0 | 5 | `src/gui/market_inspector_fetcher.py` |
| 4 | 0 | 0 | 4 | `src/exchange/tablet_backend.py` |
| 4 | 0 | 1 | 3 | `src/gui/history_helpers.py` |
| 4 | 0 | 0 | 4 | `src/gui/native_chart.py` |
| 4 | 0 | 0 | 4 | `src/gui/screen_recorder.py` |
| 4 | 0 | 0 | 4 | `src/gui/settings_dialog.py` |
| 4 | 0 | 0 | 4 | `src/gui/simulator_tab/fleet/simulator_bot_state.py` |
| 4 | 0 | 0 | 4 | `src/trading/stone_tablets/fetcher.py` |
| 4 | 1 | 0 | 3 | `tests/conftest.py` |
| 4 | 0 | 2 | 2 | `tests/test_build_sim_smart_wires.py` |
| 3 | 0 | 0 | 3 | 22 further files |

An independent third instrument agrees on the four files it was run over.
`python -m tools.touchset baseline` reports 74, 23, 6 and 40 forbidden
directives for `main_window.py`, `bot_visualizer.py`,
`crypto_news_ticker.py` and `fleet_replay_panel.py`. Those are this audit's
counts exactly.

---

## 3. Load-bearing and hiding something

Eleven directives suppress a finding whose own message describes a real
defect. They are ranked by blast radius: money path, then live-order path,
then state path, then display, then gate tooling.

One ordering choice is stated rather than hidden. H4 is a state-READ path
whose consequence is a display, and H7 is a state-WRITE. H4 is ranked above
H7 because its consequence is larger, not because its band is higher.

### H1 — the bot delete path swallows the only stop. MONEY, LIVE-ORDER.

`src/gui/main_window.py:7176-7181`. The quoted text is the anchor, not the
line number.

```
                if confirm == QMessageBox.Yes:
                    try:  # noqa: SIM105
                        self._schedule_async(bot.stop())
                    except Exception:  # noqa: S110
                        pass
                    self._bot_manager.unregister(bot_id)
```

Suppressed finding, measured: `S110 try-except-pass detected, consider
logging the exception`. `S110` is HIGH in the archetype's severity map.

**The defect.** `bot.stop()` is the only stop on this path.
`BotContainer.unregister` does not stop anything. Read on live, it releases
the capital reservation, pops the bot with `bot = self._bots.pop(bot_id,
None)`, removes the scan symbol, detaches smart wires, and emits
`bot.unregistered`. It never calls `stop()` and never cancels a task. The
cancel lives in `stop()`, anchor text `src/trading/bot_container.py:1371`:

```
    async def stop(self) -> None:
        """Gracefully stop the bot and cancel remaining orders."""
        self._stop_event.set()
```

**The failure.** If the scheduling call raises, the bot is never told to
stop, and it is popped from the registry anyway. Its asyncio task keeps
running against the exchange with real money. The manager no longer holds a
reference, and the user interface enumerates bots from the manager, so
nothing can stop it. The operator meanwhile receives three confirmations:
`f"Bot {bot_id} deleted."`, a `"Bot {bot_id} DELETED"` notification, and a
state-change sound.

**Reachable**, with two separate answers.

The handler itself is narrow. `_schedule_async` calls
`asyncio.run_coroutine_threadsafe(coro, self._async_loop)`, which raises
`RuntimeError: Event loop is closed` on a closed loop. `bot.stop` is
`async def`, so calling it builds a coroutine object without running the
body, and the TypeError path is not live. The trigger is the shutdown
window.

The silence it normalises is every delete. In the loop-alive path the
returned Future is never read. In the fallback path the `pool.submit` Future
is never read either. A failure inside `bot.stop()` is discarded in both.
The `try`/`except`/`pass` makes the delete path look guarded while guarding
only the scheduling call.

**The file argues against itself.** The sibling branch does it correctly,
37 lines up, anchor text `src/gui/main_window.py:7141`:

```
                    except Exception as exc:
```

followed by `self._status_log.log(f"Failed to stop bot {bot_id}: {exc}",
"error")`. This is an omission, not a considered decision.

### H2 — the wire verifier answers "registered" when it does not know. MONEY.

`src/gui/main_window.py:5717-5721`:

```
            try:
                return tgt_id in (mgr.get_outgoing_wires(src_id) or {})
            except Exception as exc:  # noqa: BLE001
                logger.warning("C06c: wire read-back failed: %s", exc)
                return True
```

Suppressed finding, measured: `BLE001 Do not catch blind exception:
Exception`.

**The defect.** This function is the verifier. Its caller counts what the
engine accepted rather than what the user interface emitted, because the bus
handler discards a refusal and "N wires drawn" could otherwise report a full
success for a topology the engine took none of. On any exception the
verifier returns `True`, which means accepted. The blind catch treats an
`AttributeError` from a renamed manager interface exactly like a transient
failure, and reinstates the false success the check was built to stop.

**The failure.** `wires_drawn` inflates, and the operator is told wires are
routing profit that no engine holds.

**Reachable.** Yes, from `_adopt_topology_proposal`, which calls
`self._wire_is_registered(src_id, tgt_id)`.

**Stated in mitigation.** It logs at WARNING, and the docstring reasons
about the unknown-is-True choice. That reasoning covers the branch where the
manager is absent, because a missing engine is not evidence of rejection. It
does not cover the branch where the engine is present and its read-back
raised, and that is this line.

### H3 — disconnect reports success it did not achieve. LIVE-ORDER.

`src/gui/main_window.py:3009-3017`:

```
        def _do_disconnect(self):
            if self._connector:
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(asyncio.run, self._connector.disconnect())
                except Exception:  # noqa: S110
                    pass
                self._connector = None
```

Suppressed finding, measured: `S110`.

**The defect, in two layers.** The submitted Future's exception is never
retrieved, so a failing `disconnect()` cannot even reach this handler; it is
discarded when the executor shuts down. Whatever the handler can see is
swallowed by `pass`. Then `self._connector = None` runs unconditionally, and
four lines later the label reads `"Disconnected"` and the log records
`"DISCONNECTED", "Connection closed"`.

**The failure.** The operator is told the exchange connection is closed
while the session may still be open, and the only reference to it has been
dropped, so nothing can close it afterwards. A leaked session, plus a status
display that asserts the opposite.

**Reachable.** Yes, by a button: `self._disconnect_btn.clicked.connect(
self._do_disconnect)`.

### H4 — wire hydration fails per route with no record anywhere. STATE-READ.

`src/gui/bot_visualizer.py:2926-2932`:

```
                    try:
                        bus.emit("wire.created",
                                 source_id=str(bid), target_id=dst,
                                 pct=pct)
                        n += 1
                    except Exception:  # noqa: S112
                        continue
```

and its caller, `src/gui/bot_visualizer.py:1460-1463`:

```
            try:  # noqa: SIM105
                self._hydrate_smart_wire_routes_from_disk()
            except Exception:  # noqa: S110
                pass
```

Suppressed findings, measured: `S112 try-except-continue detected, consider
logging the exception` at 2931, and `S110` at 1462.

**The defect.** `_hydrate_smart_wire_routes_from_disk` reads the bot state
file, walks each bot's `smart_wire_routes`, and replays each as a
`wire.created` event so the canvas paints it. Its docstring says it "Returns
count of events emitted". **The caller discards the return value.** A
failed route increments nothing, logs nothing, emits nothing, and the count
that would have shown the gap is thrown away. The outer handler then
swallows a total failure of the whole hydration the same way.

**The failure.** The wire overlay shows fewer wires than the state file
holds, and no record of the difference exists anywhere. The wires carry
routed fold profit, so the picture the operator reads to check the money
topology can silently disagree with the file that defines it.

**Reachable.** Yes. The call sits in `BotVisualizationTab.__init__`, so it
runs on every construction of the tab.

**The repository already names this failure class.** Anchor text,
`src/trading/smart_wire.py:490`:

```
        # import_wires does NO existence check against _bot_refs: it
```

and four lines later, "Reporting the return value as though it were the
ACTIVE count is the '40 wires, $0.00 routed' failure." That is the same
shape, written down by the same codebase.

### H5 — a journal write is dropped in silence. STATE-WRITE.

`src/gui/main_window.py:6537`, `except Exception:  # noqa: S110` in
`_on_ai_feedback`. The guarded body builds a `TradeRecord` and calls
`self._journal.record(rec)`. Suppressed finding, measured: `S110`.

**The defect and its bound.** A journal write is a state write, so the band
is correct. The record is an `AI_FEEDBACK` note with `price=0, quantity=0,
usd_value=0`, not a trade. A silent drop loses a note. Ranked here on band,
not on consequence.

### H6 — bot error records are dropped on a malformed event. OBSERVABILITY.

`src/gui/main_window.py:5673`,
`except Exception:  # R28-OK: telemetry capture must never raise  # noqa: S110`
in `_on_bot_error_for_log`. Suppressed finding, measured: `S110`.

**The defect.** The guarded body parses an event and appends to
`self._error_log_buffer`. It calls `int(...)` on a field taken from the
event, which raises `ValueError` on a non-numeric value. A malformed event
therefore drops the whole bot-error record, and the operator's error log
under-reports. The justification is sound as far as it goes, because
telemetry must not raise. "Must not raise" and "must not record" are
different requirements, and `S110` asks for exactly the log that separates
them.

**Reachable** on a malformed `bot.error` event.

### H7 — the thread-violation diagnostic writes nothing when it cannot write. OBSERVABILITY.

`src/gui/main_window.py:5138`, `except Exception:  # noqa: S110` in
`_on_api_event`. Suppressed finding, measured: `S110`.

**The defect.** The guarded body writes a `thread_violation_<date>.log`
recording that `_on_api_event` was called off the GUI thread and was refused
to avoid a Qt fatal error. The refusal still happens. Only the evidence is
lost. Given the open asyncio-on-GUI-thread arc, that record is the arc's
only field instrument.

**Reachable** on any write failure, such as a permission error or a full
disk.

### H8 — a fleet load reports success it did not deliver. DISPLAY.

`src/gui/simulator_tab/fleet/fleet_replay_panel.py:486-489`:

```
            try:
                self.fleetLoaded.emit(list(self._configs))
            except Exception:  # noqa: S110 - signal best-effort
                pass
```

Suppressed finding, measured: `S110`.

**The defect.** `fleetLoaded` has one consumer,
`self.fleet_replay.fleetLoaded.connect(self._on_fleet_loaded)`. A direct
connection propagates a slot's exception back to the Python `emit()` caller,
so this handler is the last catch for the method whose own docstring says
"Everything the fleet drives, from one signal." The handler is a bare
`pass`: no log, no status text, no telemetry. Immediately before it, the
status label has already been set to a success sentence naming the bot
count, the symbol count and the total target.

**The failure.** The bot table, the chart picker and the active-bot dropdown
stay empty or stale while the panel reports success.

**Reachable, and narrow.** The slot defends and logs its own risky regions.
The unwrapped escape iterates the configs and calls `.get` on each element,
so an element that is neither `None` nor a mapping raises `AttributeError`
and lands here.

**The standard exists elsewhere.** `src/trading/bot_container.py:3439`
records the same situation and explains why, then logs a warning.

### H9 — a suppression asserts a control the code does not perform. DISPLAY.

`src/gui/crypto_news_ticker.py:182`:

```
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - RSS feed fetch, https-only allowlist
```

Suppressed finding, measured: `S310` plus `E501`.

**The defect.** This call site performs no allowlist check. The repository has
one. `src/core/safe_url.py:61` defines
`DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})`
and exposes `safe_urlopen`, and **eight other call sites in seven modules
route through it**: `notifications.py:317`, `sms_engine.py:131`,
`chart_data.py:230`, `market_data.py:116`, `crypto_assets.py:369`,
`ccxt_connector.py:416`, `main_window.py:3221` and `main_window.py:3319`.
`crypto_news_ticker.py` imports the raw `urlopen` and asserts the control in
a comment instead. This is the operator's named precedent class exactly.

**Blast radius today is bounded, and this report will not overstate it.**
`NEWS_SOURCES` is a hard-coded tuple of ten `https://` literals, and the one
caller is `fetch_all()` with no argument, so no other scheme can reach the
call today. The defect is that the guard is written in a comment instead of
in code, and the checker that would notice the day `NEWS_SOURCES` becomes
settings-backed is switched off at that line.

**Reachable** through `fetch_all()` on a worker thread.

### H10 — the gate resolves two of its six analyzers through PATH. GATE TOOLING.

`tools/harness/coding_archetype.py:30`, `# ruff: noqa: S603, S607`.
Stripping it produces `S603` at five lines and `S607 Starting a process with
a partial executable path` at two. Anchor text,
`tools/harness/coding_archetype.py:560`:

```
            ["pyright", "--outputjson", str(target)],
```

and `coding_archetype.py:671`:

```
            ["semgrep", "scan", "--config=p/python", "--config=p/security-audit",
```

**The defect.** The `S603` findings are benign, because that argument vector
is literals plus a `Path`. The `S607` pair is not. Four of the six runners
in this file spawn `[sys.executable, "-m", ...]`, an absolute interpreter
path. These two spawn a bare program name and let the operating system
search PATH at exec time. The file already contains the safe form and
deviates from it twice, and the blanket file-level directive is what stops
anyone noticing.

**The failure.** On Windows, PATH plus PATHEXT resolution will execute a
`pyright.cmd`, `pyright.bat` or `semgrep.exe` planted anywhere earlier on
PATH, under the developer's own token, every time the gate runs. It also
makes both runners silently sensitive to PATH ordering.

**Reachable** on every write to a Python file, because the gate appends
`tools.harness.coding_archetype` unconditionally for that suffix.

### H11 — the resolved absolute path is computed and thrown away. GATE TOOLING.

`tools/harness/docs_archetype.py:23`, `# ruff: noqa: S603, S607`. Stripping
it produces `S603` at two lines and `S607` at one. Anchor text,
`tools/harness/docs_archetype.py:395`:

```
        vale_bin = shutil.which("vale")
        if vale_bin is None:
            raise FileNotFoundError("vale not on PATH")
```

and `docs_archetype.py:401`:

```
                ["vale", "--output=JSON", str(f)],
```

**The defect, sharper than H10.** `shutil.which` returns the absolute path
into `vale_bin`. A search of the whole file finds exactly two references:
the assignment and the `is None` test. Line 401 discards it and makes the
operating system search PATH a second time.

**The failure.** A time-of-check-to-time-of-use gap. `which` proves one
binary exists; `subprocess.run` may spawn a different one. A wrong `vale`
scoring documentation would report findings the operator would read as the
docs gate's verdict.

**Reachable** on every gated Markdown write.

**Standing.** H10 and H11 are reported, not fixed. Only archetypes edit
archetypes.

### 3.1 What this audit looked for and did not find

No suppression in `src/trading/scrumming_bot.py` hides a defect. All 42 were
read against the code. The file has already been through the cleanup this
audit hunts, and it says so in its own comments: `scrumming_bot.py:5915`
reads `# v3.24.10 - was 'except Exception: pass', which meant a`, and
`scrumming_bot.py:8541` reads `# v3.24.18 - was 'except Exception: pass',
which meant one`. Not one of its 38 blind catches is a silent swallow:
30 log, 2 return a structured refusal, 6 assign a conservative fallback and
log.

No suppression anywhere hides an arithmetic defect, a credential path or an
injection path. `main_window.py` carries no `nosec`, no `S603`, no `S607`
and no `S311`.

Two `nosec B104` directives in `src/stocks/tradingview_bridge.py` sit on the
real binds at lines 183 and 298 and suppress nothing, because bandit cannot
see through a variable. Their comments claim "operator-configurable;
defaults to 127.0.0.1". That claim rests on a directive with no effect. It
is REDUNDANT rather than hiding, and it is listed here so it is not lost.

### 3.2 Three accidental directives, none of them intended by its author

- `src/gui/simulator_tab/nuclear_candle_source.py:294` reads
  `# noqa justification: S311 flags non-cryptographic RNG. This`. The
  character after `noqa` is a space, not a colon, so ruff parses a BLANKET
  noqa that would silence every rule on that line. Ruff's own words:
  `Unused blanket noqa directive`. Inert today, because the line holds only
  prose. A landmine if code ever moves onto it.
- `src/core/version_sweep.py:361` quotes `# nosec` inside a sentence.
  Bandit scans the whole line, so bandit reads it as a directive.
- `src/gui/screen_recorder.py:59` and `:76` carry a bare `# noqa` with no
  code. Measured, each hides `F401` and `PLC0415`. A bare noqa also silences
  every rule that may ever fire on that line.

`src/core/version_sweep.py:365` compounds the second one. It is itself a
suppression recogniser: `if '# nosec' in line or '# version-sweep:' in
line.lower(): continue`. That is a raw substring test with no comment
parsing, so any line containing the text anywhere, including inside a string
literal, is skipped as operator-blessed. It is a third suppression surface,
and it is the most permissive of the three.

### 3.3 Two directives whose comment states something untrue

Both name `BotConfig` as retained for type hints. Neither file uses it.

- `src/gui/live_bot_window.py:47` —
  `from ..trading.bot_container import BotConfig, BotMode, make_bot_config  # noqa: F401`
  with the comment "BotConfig retained for type hints only". `BotConfig`
  appears in this file only in the module docstring and on the import line.
- `src/gui/simulator_tab/nuclear_controller.py:35` — the same comment, the
  same untrue claim.

The suppressed finding is accurate and an unused import causes no failure,
so both are benign. They are the operator's named pattern in its harmless
form: a directive whose comment asserts a control the code does not perform.

---

## 4. Cold read: where the probes disagreed

Four disagreements. All four were re-measured for this report, and three of
them have one root cause.

**A composite directive is not one verdict.** Ruff's unused-directive report
answers per rule CODE. A strip-and-diff answers per DIRECTIVE. Where one
named code is live and another is not, the two methods disagree without
either being careless. The directive-level answer is the correct one for a
bucket table, because a directive is what gets removed.

### D1 — `scrumming_bot.py`: 41 or 42

Both. The file has 41 lines carrying a directive and 42 directives, because
one line carries two. Anchor text, `src/trading/scrumming_bot.py:3945`:

```
        if confirmation_token != "SELF-DESTRUCT":  # noqa: S105  # nosec B105
```

A line-based grep returns 41. A directive-based count returns 42. **Neither
probe was wrong.** This audit counts directives, so 42, and the merge
carries an explicit collision guard that fails rather than collapsing the
two rows.

### D2 — `main_window.py`: 68 or 69 load-bearing

Probe 1 said 68 from `RUF100` alone. Probe 3 said 69 from strip-and-diff.
Re-measured here:

```
LOAD_BEARING mw_whole      scope=line  added=BLE001 x1
REDUNDANT    mw_s110_only  scope=line  added=(none)
```

Anchor text, `src/gui/main_window.py:2617`:

```
            except Exception:  # noqa: BLE001,S110 - countdown best-effort
```

Removing the whole directive adds `BLE001`, so the directive is
LOAD-BEARING. Removing only `S110` adds nothing, so that half is inert; the
handler body is `return`, not `pass`. **Probe 1 was wrong at directive
granularity**, and it was wrong for a defensible reason: it scored a
composite by its dead half. The correct count is 69.

### D3 — DEAD: 31 or 29

Probe 1 said 31. Probe 4 said 29. Re-measured here, over the whole file
because these are file-level directives:

```
LOAD_BEARING tapes_whole      scope=file  added=S311 x2
LOAD_BEARING tapes_s311_only  scope=file  added=S311 x2
REDUNDANT    tapes_s101_only  scope=file  added=(none)
LOAD_BEARING identity_whole   scope=file  added=S311 x1
```

The `tests/` directory holds 31 file-level headers. Twenty-nine name only
`S101` and `SLF001`, both of which the gate disables for test files, so
those 29 are DEAD. Two also name `S311`, which the gate does not disable,
and `S311` is the half doing the work. **Probe 4 was right at directive
granularity, 29.** Probe 1's 31 counted the two composites by their dead
`S101` half.

Anchor text, `tests/test_nuclear_tablet_tapes.py:1`:

```
# ruff: noqa: S101, SLF001, S311
```

**This synthesis got D3 wrong on its first pass and reported REDUNDANT for
both composites.** The fault was in this instrument, not in the probe: a
file-level directive was compared only at its own line. The finding is
recorded because a corrected disagreement is more useful than a quiet one.

### D4 — `tests/test_api_load_monitor.py:51`

Probe 1 listed it among six dead `type: ignore` comments. Probe 4 called it
LOAD-BEARING. Re-measured here with a real strip-and-diff:

```
contested_b.py:51: error: Unused "type: ignore" comment, use narrower
    [method-assign] instead of [assignment] code  [unused-ignore]
contested_v.py:51: error: Cannot assign to a method  [method-assign]
```

Stripping the directive ADDS `method-assign`, so the directive suppresses a
real finding. **Probe 4 was right. Probe 1 was wrong**, and the reason
generalises:

**Mypy's `unused-ignore` is not a reliable REDUNDANT oracle.** When the
named code is a PARENT of the code that actually fired, mypy still honours
the ignore and simultaneously advises a narrower code. Reading that message
as "dead" mislabels a live directive. Only the strip-and-diff separates the
two. Applying it to all 17 unmeasured `type: ignore` directives gives 9
LOAD-BEARING and 8 REDUNDANT.

### D5 — 709 against 439 against 165

Not a disagreement. Scope.

- 165 is `tools.touchset` over the 32 files promoted this session.
- 439 is one probe's named subset, 252 files.
- 709 is `src/`, `tests/` and `tools/` entire, 393 files scanned, 217
  carrying at least one directive.

Per-file counts agree exactly wherever two instruments covered the same
file.

---

## 5. The dead list

Removing a dead directive strictly reduces findings and cannot change
behaviour. **Twenty-nine directives, one per file, all on line 1, all in
`tests/`.** Each names only rule codes the gate disables for test files, so
each suppresses nothing. Ruff says so in its own words:
`Unused noqa directive (non-enabled: S101, SLF001)`.

Nothing in this list has been removed. It is written down so one unit can
clear it in one pass.

| # | file | directive |
|---|---|---|
| 1 | `tests/conftest.py` | `# ruff: noqa: S101, SLF001` |
| 2 | `tests/test_archetype_gate_calibration.py` | `# ruff: noqa: S101, SLF001` |
| 3 | `tests/test_candle_addressing.py` | `# ruff: noqa: S101` |
| 4 | `tests/test_docs_archetype_calibration.py` | `# ruff: noqa: S101, SLF001` |
| 5 | `tests/test_emit_contracts.py` | `# ruff: noqa: S101, SLF001` |
| 6 | `tests/test_feature_telemetry.py` | `# ruff: noqa: S101, SLF001` |
| 7 | `tests/test_fleet_replay_controller.py` | `# ruff: noqa: S101, SLF001` |
| 8 | `tests/test_gate_coverage.py` | `# ruff: noqa: S101` |
| 9 | `tests/test_gate_coverage_streaming.py` | `# ruff: noqa: S101, SLF001` |
| 10 | `tests/test_gate_healer.py` | `# ruff: noqa: S101` |
| 11 | `tests/test_live_log_reader_since.py` | `# ruff: noqa: S101, SLF001` |
| 12 | `tests/test_nuclear_fleet_controller.py` | `# ruff: noqa: S101, SLF001` |
| 13 | `tests/test_nuclear_scout_isolation.py` | `# ruff: noqa: S101, SLF001` |
| 14 | `tests/test_parity_harness.py` | `# ruff: noqa: S101` |
| 15 | `tests/test_rate_spike_protector.py` | `# ruff: noqa: S101, SLF001` |
| 16 | `tests/test_registry_lazy_bodies.py` | `# ruff: noqa: S101, SLF001` |
| 17 | `tests/test_replay_yield_budget.py` | `# ruff: noqa: S101, SLF001` |
| 18 | `tests/test_scrumming_get_balance_no_self_recursion.py` | `# ruff: noqa: SLF001, S101` |
| 19 | `tests/test_sim_exchange_open_index.py` | `# ruff: noqa: S101, SLF001` |
| 20 | `tests/test_sim_reservation_isolation.py` | `# ruff: noqa: S101, SLF001` |
| 21 | `tests/test_sim_run_log.py` | `# ruff: noqa: S101, SLF001` |
| 22 | `tests/test_sim_validation_guard.py` | `# ruff: noqa: S101, SLF001` |
| 23 | `tests/test_sim_visual_decoupling.py` | `# ruff: noqa: S101, SLF001` |
| 24 | `tests/test_start_all_progress_events.py` | `# ruff: noqa: S101, SLF001` |
| 25 | `tests/test_stone_tablets_availability.py` | `# ruff: noqa: S101` |
| 26 | `tests/test_stone_tablets_fetcher.py` | `# ruff: noqa: SLF001, S101` |
| 27 | `tests/test_stone_tablets_registry.py` | `# ruff: noqa: SLF001, S101` |
| 28 | `tests/test_topology_stress.py` | `# ruff: noqa: S101, SLF001` |
| 29 | `tests/test_wire_credits_bounded.py` | `# ruff: noqa: S101, SLF001` |

**Two more, as an edit rather than a deletion.** These two headers carry a
dead half and a live half. Measured above: the `S311` half suppresses two
findings in the first file and one in the second. The `S101` and `SLF001`
halves suppress nothing.

| file | now | after |
|---|---|---|
| `tests/test_nuclear_tablet_tapes.py:1` | `# ruff: noqa: S101, SLF001, S311` | `# ruff: noqa: S311` |
| `tests/test_ta_suffix_bit_identity.py:1` | `# ruff: noqa: S101, SLF001, S311` | `# ruff: noqa: S311` |

**A second, larger free win, named but not counted as DEAD.** The 58
REDUNDANT directives also reduce findings on removal, because ruff currently
reports each as `RUF100 Unused noqa directive`. They differ from the dead
ones in that the rule IS enabled, so a later code change could make them
live again. They are a separate unit and a separate decision.

---

## 6. Unit plan

Sized per `unit-decomposition`. One verb each, neighbours named, input table
closed before the first edit. Every unit is a proposal. None is built here.

**File ownership.** `src/trading/scrumming_bot.py` is contended; another job
holds it on an island. **No unit below touches it**, and its two REDUNDANT
`E721` directives are deliberately left out of U6 for that reason.
`src/gui/main_window.py` carries three units, so those three run in sequence
on one island rather than in parallel.

**Clean ground, measured on the unmodified tree before any work order.**
`python -m tools.touchset baseline` over the four proposed source files:

| file | coding | gui | ground |
|---|---|---|---|
| `src/gui/main_window.py` | passed | passed | GREEN |
| `src/gui/simulator_tab/fleet/fleet_replay_panel.py` | passed | passed | GREEN |
| `src/gui/bot_visualizer.py` | FAILED, 9 high | FAILED, 5 high | RED |
| `src/gui/crypto_news_ticker.py` | FAILED, 4 high | FAILED, 2 high | RED |

Two of the four are already red. A unit cannot be greener than the file it
lands in, so the red is its own unit and it goes first.

### Island A — `src/gui/main_window.py`. Green ground. Three units, sequenced.

**A1. RECORDS the bot-delete stop failure.** Fixes H1.
Closed input table: the raises reachable from `_schedule_async(bot.stop())`.
`bot.stop` is `async def`, so calling it builds a coroutine and runs no
body. The set is `{RuntimeError from a closed loop, any raise from
asyncio.run_coroutine_threadsafe, no TypeError}`. Test: drive the delete
with a closed loop and assert one error-level status line naming the bot.
Not this unit: whether `unregister` should stop the bot.

**A2. RECORDS the disconnect failure and stops asserting a state it did not
reach.** Fixes H3. Two verbs, so it is two units if the status text changes;
scoped here to the record only. Closed input table: `{import failure,
executor failure, submit failure, disconnect() raising inside the worker}`.
Test: force the fourth case and assert a status line. Not this unit: the
`"Disconnected"` label, which is A2b.

**A3. ANSWERS unknown as unknown in the wire verifier.** Fixes H2. Closed
input table: `{manager absent, read-back returns a mapping, read-back
returns None, read-back raises}`. The last row is the one that changes.
Test: force the raise and assert the wire is not counted as drawn. Not this
unit: what `_adopt_topology_proposal` does with a lower count.

**A4, A5, A6.** H5, H6 and H7, each one verb, each RECORDS. They can be
deprioritised independently of A1 to A3 and of each other.

### Island B — `src/gui/bot_visualizer.py`. RED ground.

**B0. CLEARS the pre-existing red.** 9 coding highs and 5 gui highs on the
unmodified tree. This is its own unit and it goes first. Baseline recorded,
never compared against zero.

**B1. COUNTS and RECORDS wire-hydration failures.** Fixes H4. Closed input
table: per route, `{emit succeeds, emit raises}`; per call,
`{state file missing, state file unreadable, bus unavailable, hydration
raises}`. Test: force one route to raise and assert both the returned count
and one log line. Not this unit: how the canvas paints, and whether the
route should be repaired.

### Island C — `src/gui/crypto_news_ticker.py`. RED ground.

**C0. CLEARS the pre-existing red.** 4 coding highs, 2 gui highs. Goes
first.

**C1. ROUTES the feed fetch through `safe_urlopen`.** Fixes H9. Closed input
table: the ten `NEWS_SOURCES` URLs, all `https`, plus the rejected schemes
`{file, ftp, data, an unknown custom scheme}` against `safe_url`'s
`DEFAULT_ALLOWED_SCHEMES`. Test: pass a `file://` source and assert a
refusal rather than a read. Not this unit: the per-feed `BLE001` handler,
which is correct.

### Island D — `src/gui/simulator_tab/fleet/fleet_replay_panel.py`. Green ground.

**D1. RECORDS the `fleetLoaded` slot failure.** Fixes H8. Closed input
table: `{slot returns, slot raises AttributeError on a non-mapping config,
slot raises anything else}`. Test: hand the panel a config list holding one
non-mapping element and assert a log line plus a status that does not claim
success. Not this unit: the slot's own defences, and the status sentence.

### Island E — `tests/`. Structural only.

**E1. REMOVES the 29 dead file headers and trims the 2 composites.** Closed
input table: exactly the 31 files listed in section 5. Expected effect,
which is the test: the ruff finding set is unchanged except that `RUF100`
disappears from line 1 of the 29, and the two trimmed headers keep
suppressing their `S311` findings. Any other change fails the unit. No
behavioural change, so this unit can ship alone.

### Island F — the 58 REDUNDANT directives. Structural only.

**F1. REMOVES the measured-inert directives, excluding the contended file.**
56 directives across 30 files. Closed input table: the 56 rows, each with a
live `RUF100` naming it. Expected effect: 56 `RUF100` findings disappear and
nothing else changes. Split further by file if the touch set is too wide to
gate in one pass. **`src/trading/scrumming_bot.py`'s two `E721` directives
are excluded** because that file belongs to another island.

### Not units — the harness

H10 and H11 sit in `tools/harness/`. Only archetypes edit archetypes, so
they are reported and left alone. Both become proposed rules below.

---

## 7. Proposed rules

Three. None is built here.

**R1. The gate refuses a NEW `RUF100` or `RUF102`.** Both codes are already
inside `--select=ALL`, and both map a suppression to its own verdict for
free. This rule would have caught the `# noqa: BLE001` incident at the
moment it landed, and would have stopped eight `S110` halves being
copy-pasted forward inside one file. Compared against a pinned baseline, not
against zero, because 58 pre-existing REDUNDANT directives are not one
unit's to clear.

**R2. The gate runs mypy with `--warn-unused-ignores`.** Anchor text,
`tools/harness/coding_archetype.py:518`:

```
        proc = subprocess.run(
            [sys.executable, "-m", "mypy", str(target),
```

The flag list that follows does not include it, so a `type: ignore` that
suppresses nothing is invisible to the gate. Eight were found here. **The
rule must carry D4's caveat**: `unused-ignore` alone mislabels a directive
whose named code is a parent of the code that fired, so the rule should
report rather than block until a strip-and-diff confirms.

**R3. A blanket directive is refused.** A `# noqa` with no rule code
silences every rule on its line for ever, including rules that do not exist
yet. Three exist today: two in `screen_recorder.py`, and one created by
accident in `nuclear_candle_source.py` because a space was typed where a
colon belonged.

---

## 8. Limits

**The benign judgement has no positive control.** The bucket assignment is a
measurement, and it is controlled three ways. The split of 622 load-bearing
directives into 611 benign and 11 hiding is a JUDGEMENT about code. No
planted defect proves a reading of 611 handlers is right. A second reader
could move a directive across that line, and the honest form of the result
is: the measurement found 622 load-bearing directives, and reading them
found 11 defects.

**REDUNDANT is a property of today's code.** Every REDUNDANT verdict says
the rule is enabled and does not fire at that site now. A later edit can
make it fire. That is why the dead list and the redundant list are separate
units with separate risk.

**DEAD is a property of the gate's invocation, not of the code.** The 29
dead headers are dead because `_TEST_FILE_EXEMPT` disables `S101` and
`SLF001` for test files. A control demonstrated the same header revealing 43
`S101` findings when the file is scored outside a `tests` path. If the gate
ever stops exempting those codes, the 29 come back to life.

**Mypy ran with `--follow-imports=silent`, as the gate does.** A blanket
`type: ignore` on an import-fallback line was measured under that resolution
and no other. The verdict is "redundant under the gate's invocation", which
is the invocation that matters, and not "redundant under every possible mypy
configuration".

**The counter over-counts prose by one.** `src/core/version_sweep.py:361`
quotes `# nosec` inside a sentence, and the anchoring rule counts it. That is
an over-count against the author's intent but not against effect, because
bandit scans the whole line and reads it as a directive too.
`tools/touchset.py` shares the algorithm and shares the behaviour.

---

## 9. Falsification

This audit is wrong if any of the following holds.

- A directive ruff reports through `RUF100` is bucketed LOAD-BEARING, or a
  directive whose removal adds a finding is bucketed REDUNDANT.
- The buckets do not sum to 709, or any directive is left unmeasured.
- A variant differs from its baseline anywhere except the one neutralised
  segment.
- The two-sided control fails to produce both answers from the same method.
- A directive of a spelling this audit names goes unmeasured by the analyzer
  that owns it.
- One of the eleven hiding findings is driven on the real path and does not
  produce the failure described.
