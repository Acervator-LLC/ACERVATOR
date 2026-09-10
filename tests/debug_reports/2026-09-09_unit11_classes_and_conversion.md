# 2026-09-09 — Proof of Accumulation: the classes and the RPG conversion

Issue #147, unit 11. Files changed: `src/competition/rpg_classes.py`,
`src/competition/rpg_metrics.py`, `src/competition/__init__.py`,
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js`,
`src/gui/web/proof_of_accumulation_tab.css` and
[docs/manual/08-tabs/proof-of-accumulation.md](../../docs/manual/08-tabs/proof-of-accumulation.md).
No test file was written.

Unit 4 built the three zones and unit 15 filled the wallet. This unit adds the
seven classes and the conversion from a bot's trading profile into RPG metrics.
The conversion reads and never writes. No figure a bot trades on changes.

Three runs drove the change, all under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`. The conversion ran against the live fleet load and
against the readings the running platform wrote to its own trade, gate and voting
logs. The panel was built the way the main window builds it, through
`ProofOfAccumulationReactPanel`, and every on-screen value was read back with the
page's own `runJavaScript`. `main.py` was never launched: it takes an instance
lock in the operator's live tree while he is trading.

---

## 1 — The refusal path named a class that no longer existed

### 1.1 the error

```
mypy:name-defined line 145: Name "UnknownClass" is not defined
pyright:reportUndefinedVariable line 145: "UnknownClass" is not defined
```

### 1.2 reproduction

`python -m dev_harness.harness.coding_archetype src/competition/rpg_classes.py`
after the exception class was renamed to carry the `Error` suffix the same
archetype asked for.

### 1.3 the cause

The rename touched the class statement and not the `raise` inside `pick_class`.
Any caller handing that function a name outside the seven would have hit a
`NameError` instead of a refusal.

### 1.4 the correction

The raise names the renamed class, and the message is a local variable rather
than an f-string inside the raise.

```python
    if class_named(class_name) is None:
        refusal = (
            f"{class_name!r} is not a PoA class; "
            f"the seven are {', '.join(CLASS_NAMES)}"
        )
        raise UnknownClassError(refusal)
```

### 1.5 the rerun

`coding_archetype` on that file reports `passed=True`, exit 0, with no high or
critical finding.

---

## 2 — The numeric guards admitted a boolean

### 2.1 the error

```
numeric_guard NG001 rpg_metrics.py:73 [high]: isinstance guard on 'value' in
'_number' admits subclasses, so bool and any float subclass pass it, and 'value'
is then coerced with float().

numeric_guard NG001 proof_of_accumulation_tab_surface.py:285 [high]: isinstance
guard on 'maximum' in 'health_text'.
```

### 2.2 reproduction

`python -m dev_harness.harness.coding_archetype` on each of the two files.

### 2.3 the cause

`isinstance(value, (int, float))` is true for `True`, because `bool` subclasses
`int`. A field holding `True` would have converted to a health pool of one
dollar.

### 2.4 the correction

`_number` tests the exact type and branches, so no coercion runs on a boolean.
`health_text` asks only whether the metric is present, because `read_metrics`
drops a metric whose field was absent.

```python
    value = _read(holder, name)
    if type(value) is int:
        return float(value)
    if type(value) is float:
        return value
    return None
```

### 2.5 the rerun

Both files report `passed=True` with no high or critical finding.

---

## 3 — The grade axes came back empty on a real trade

### 3.1 the error

No traceback. Driving the conversion with a real fill produced `accuracy=None`,
`efficacy_timing=None` and `grade_numeric=0.5`.

### 3.2 reproduction

One live fill read out of `~/.acervator_logs/trade/trade.log` was handed to
`grade_trade` with a price series built from `gate.log`.

### 3.3 the cause

A gate record carries no price field, so the series was empty and every axis of
the grade had no input. `grade_trade` documents 0.5 as its answer when no axis
can be scored, so the figure was a default and not a measurement.

### 3.4 the correction

The price series comes from the fills of the same market in `trade.log`, which is
where the platform records the prices it traded at.

```python
    prices = [
        row["price"] for row in fills if row.get("symbol") == fill["symbol"]
    ]
```

### 3.5 the rerun

The same fill on KAT/USD now grades `A+`, with accuracy 1.0, execution
-1915.16 bps, timing 1.0 and an overall of 1.0.

---

## 4 — The manual block repeated a heading

### 4.1 the error

```
structure DOC005 line 1555 [high]: Duplicate heading text 'what is not built'
(also appears at line 1396).
```

### 4.2 reproduction

`python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/proof-of-accumulation.md`
after the dated block landed.

### 4.3 the cause

Unit 8's block already ends in a section of that name. Two sections with one name
break the contents listing.

### 4.4 the correction

The heading names this unit's subject.

```
### What the classes and the conversion do not reach
```

### 4.5 the rerun

The page reports `passed=True`, exit 0. Every heading in the file is unique, and
no finding falls on a line this unit added.

---

## 5 — The read-back script crashed on a gate label

### 5.1 the error

```
UnicodeEncodeError: 'charmap' codec can't encode character '≤' in position 30
```

### 5.2 reproduction

Printing the `blocked` metric, whose first label is `delta≤0`, to a console on
the Windows ANSI codepage.

### 5.3 the cause

The gate writes its blocker labels with mathematical symbols. The default console
encoding cannot represent them. The conversion itself carries the labels through
untouched.

### 5.4 the correction

The run reconfigures its own output stream before printing.

```python
sys.stdout.reconfigure(encoding="utf-8")
```

### 5.5 the rerun

All twenty-seven metrics print, including the three gate labels, and the run
exits 0.

---

## What the runs reported

One live bot on KAT/USD, with every reading the platform itself wrote.

```
max_health_usd        209.20253838691363   scrumming_state.target_balance
base_health_usd       200.0                scrumming_state.anchor_target_balance
levelled_health_usd     9.202538           compounding_snapshot.accrued_growth_usd
level_gain_cap_usd      2.0                compounding_snapshot.cycle_growth_budget_usd
level_gain_cap_pct      1.0                config.max_target_growth_pct
current_health_usd    199.28537772239835   max_health_usd + scrum_fixture.delta
wound_pct             None                 GateContext.delta_pct
damage_usd            676.8840471879465    stats.ytd_scrummed_usd
damage_hit_usd        None                 trade.filled.usd on a SELL
healing_usd           953.6880203823049    stats.ytd_folded_usd
healing_hit_usd        10.111345000000014  trade.filled.usd on a BUY
heal_pending_count     11                  tranche_snapshot.fold_count
heal_pending_usd       29.720012           tranche_snapshot.fold_total_usd
accuracy                1.0                TradeGrade.execution_score
accuracy_bps        -1915.16               TradeGrade.execution_bps
efficacy_timing         1.0                TradeGrade.timing_score
efficacy_outcome      None                 TradeGrade.outcome_score
efficacy_strategic    None                 TradeGrade.strategic_score
grade_numeric           1.0                TradeGrade.overall_numeric
grade_letter            A+                 TradeGrade.overall
crit_confidence         0.0005             VotingSummary.consensus_confidence
fumble_adjusted         0                  stats.verify_adjusted
fumble_canceled         0                  stats.verify_canceled
fumble_errors           0                  stats.consecutive_errors
pool_usd                0.0                stats.standing_surplus_usd
cash_usd             1762.9698204938495    stats.cash_balance_usd
blocked               3 labels             scrum_blockers and fold_blockers

read 23 of 27
```

Four metrics carried nothing and each absence has a reason. `GateContext`
computes `delta_pct` and the gate emitter does not carry it. The last fill was a
BUY, so the SELL half of the cycle is empty. The outcome axis needs a per-unit
realised figure and the strategic axis needs a rolling sell-to-buy reading;
no emitter carries either.

## Breaking each source

The same bot, with one part of its record removed each time. Nothing else was
touched and the figures above were re-read after every cut.

```
whole record and gate reading   16 metrics held
scrumming_state removed         13   lost base, current and max health
stats removed                    9   lost damage, healing, 3 fumbles, pool, cash
config removed                  15   lost the percent gain cap
gate reading removed            10   lost blocked, current health, both heals
                                     pending, both compounding figures
```

## Constructed and reached

`src.core.desktop_bridge.build_registry` registers the surface under
`proof_of_accumulation_tab.state`, and `dispatch` answers fourteen declared
fields, three of them new.

```
fields: accessible_name built chain classes heading issue issue_text method
        metric_sources participants party state_text wallet zones
```

The panel drew both chains. Every value below came off the rendered page.

```
chain live      page_ready True   40 slots, 38 held, 7 classes, 0 faults
                04e1cafc | none | $54.19
                092428b2 | none | $101.98
                168b78e3 | none | $67.30
                party placeholder: absent

chain testnet   page_ready True   40 slots,  0 held, 7 classes, 0 faults
                party placeholder: "No participant is listed."
```

The seven classes drew in both runs, with the role each one holds.

```
Lead Ward | Tank
Tin Bulwark | Tank
Iron Edge | Damage
Solar Lance | Damage
Quicksilver Draught | pure healer
Copper Conduit | support healer
Silver Mirror | pure support
```

## Demo mode

The demo chain is the same code path with a different chain name. The panel takes
its chain at construction, the surface reads it out of the bridge parameters, and
`chain_file` puts the chain in the file's name. No flag exists.

```
chain live      bot_state.json           exists   38 participants
chain testnet   bot_state_testnet.json   absent    0 participants
```

## What has no caller

`pick_class` and `ClassProgress` have no caller. A participant picks a class for
an event, and unit 12 builds the modes, the Elite flag and the turn. That unit
adds the caller.
