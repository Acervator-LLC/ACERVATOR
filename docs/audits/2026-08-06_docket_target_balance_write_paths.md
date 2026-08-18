# DOCKET — who is allowed to write Target Balance, and what a "cycle" is

**Filed** 2026-08-06 · **Prompted by** operator
**Status** OPEN — one violation identified, currently DORMANT
**Grade** `M-4a` → **P1** (money path, rare because gated off, silent)

---

## 1. The operator's stated invariant

> "I also argued with the other Claude instances about the compounding
> mechanism being the ONLY means beyond a user edit that will ever be
> allowed to modify this value."

And the hypothesis that prompted the check:

> "I postulated during one of the troubleshooting attempts that the
> Target Balance setting was preventing compounding growth due to it
> being a hard cap and critically important value for the strategy."

## 2. Every writer, enumerated from the AST

Fifteen assignments to `target_balance` / `_target_balance` /
`_anchor_target_balance` across `src/`.

| Site | Verdict |
|---|---|
| `scrumming_bot.py:1289-1301` `set_target_balance_live` | **user edit** — permitted |
| `scrumming_bot.py:1429` `_apply_fold_target_growth` | **compounding** — permitted |
| `scrumming_bot.py:336` `__init__` | construction from config, not a mutation |
| `scrumming_bot.py:3570, 3611` `import_scrumming_state` | restore/read-back, not a mutation |
| `scrumming_bot.py:10029` `_execute_detonation` | resets target to anchor — deliberate, operator-initiated harvest with a documented "lock in gains = full reset" semantic |
| `bot_wizard.py:737` | a `QDoubleSpinBox` that happens to be named `_target_balance`; unrelated |
| `phantom_balance.py:144` | a phantom's own target field; different object |
| **`scrumming_bot.py:1873-1877`** `apply_wire_income` | **VIOLATION** |

**The invariant holds for fourteen of fifteen.**

## 3. The violation

`apply_wire_income`, inside the `if _stack_eligible:` branch:

```python
self._target_balance = float(self._target_balance) + u
self._anchor_target_balance = float(self._anchor_target_balance) + u
try:
    self.config.target_balance = self._target_balance
except Exception:
    pass
```

Three separate problems against the stated rule:

1. **It bypasses the compounding mechanism entirely.** It does not route
   through `_apply_fold_target_growth`, so there is no growth cap, no
   `_fold_cycle_cap_consumed` accounting, and no standing-surplus
   handling. `max_target_growth_pct` does not bound it.
2. **It moves the ANCHOR too.** Compounding raises the target above a
   fixed anchor; this raises the baseline itself, permanently.
3. **It rewrites `config.target_balance`** — the operator's persisted
   setting, and the value the Settings spinbox displays. The operator's
   own configured number changes underneath them.

## 4. It is DORMANT, and that is the only reason this is not P0

Gated on `_stack_eligible`, which requires Stack Mode. Verified against
the live state file (read-only): **`stack_mode` is enabled on 0 of 35
bots.**

So the invariant currently holds in practice and is broken in code.
Enabling Stack Mode on any bot starts uncapped rewrites of that bot's
configured target balance immediately. This interacts with C40a, which
proposes reviving Stack Mode — **that revival must not ship before this
write path is resolved.**

## 5. What a "market cycle" actually is

Operator's question:

> "compounding is also only allowed to happen once per market cycle and
> I am not sure if a 'cycle' (buy-sell-buy or sell-buy-sell depending on
> whether or not the bot is the initiator of a position…)"

`_fold_cycle_cap_consumed` is reset at **two** sites, not one:

| Site | Trigger |
|---|---|
| `:7263` | **A SCRUM fires.** Comment: *"Target Delta has swung positive… the fold cycle has naturally ended. Next fold burst gets a fresh cap budget."* |
| `:6141` | **An asymmetric BB-extreme reset.** Gated on `_reset_fired` and `_target_grow_last_side`; fires when price reaches the band extreme OPPOSITE the one where growth last occurred. |

(A third site, `:3625`, is the restore path reading the persisted value —
not a reset.)

**So a cycle ends on a sell, OR on price touching the opposite Bollinger
extreme, whichever comes first.** It is a hybrid of trade event and price
geometry, not a pure buy-sell-buy sequence.

On the initiator-versus-inherited distinction: a fresh bot starts the
counter at 0, so its first fold burst gets a full budget with no
preceding sell, and the same is true for a bot taking over an older
position. The distinction does not change the budget. It only means the
FIRST cycle is delimited solely by whichever of the two reset events
happens first.

## 6. What this does NOT establish

- **Whether the two-trigger reset is correct.** It is described here, not
  judged. Whether a BB-extreme touch SHOULD grant a fresh growth budget
  is a strategy question for the operator.
- **Whether `_execute_detonation`'s reset-to-anchor is in scope of the
  rule.** It is operator-initiated, which arguably makes it a user
  action, but it is a third code path that moves the value and the
  operator may want it named explicitly in the invariant.
- **Whether the Stack Mode write is intentional design.** It may have
  been deliberate when written. It is reported as a violation of the
  rule the operator stated in 2026-08-06, not as a proven mistake.
- **No fix is proposed.** The path is dormant; changing it is Phase 3
  work and interacts with C40a.

## 7. Reference

- `src/trading/scrumming_bot.py:1873-1877` — the violation
- `src/trading/scrumming_bot.py:1429` — the permitted compounding write
- `src/trading/scrumming_bot.py:1289-1301` — the permitted user edit
- `src/trading/scrumming_bot.py:6141`, `:7263` — the two cycle resets
- C40a in `2026-08-05_remediation_methodology.md` — the Stack Mode revival this blocks
