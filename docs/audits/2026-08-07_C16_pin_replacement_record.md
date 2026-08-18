# C16 — record of a pin replacement, written before the edit

Required by M7:

> **Never modify a test to make it pass.** When a green pin encodes the
> defect, record in writing that the pin encodes the defect, replace it
> with one encoding the requirement, and get operator acknowledgement
> *first*.

Operator acknowledgement recorded 2026-08-07: **replace with a
behavioural pin**.

## The pin being replaced

`tests/test_sim_reservation_isolation.py` —
`test_ensure_reservation_has_no_sim_mode_skip`

```python
src = inspect.getsource(ScrummingBot._ensure_capital_reservation)
body = src.split('"""', 2)[-1]
code = "\n".join(ln for ln in body.split("\n")
                 if not ln.strip().startswith("#"))
assert "_sim_mode" not in code, (
    "sim-mode skip reintroduced in _ensure_capital_reservation; "
    "isolation must come from the injected registry instead")
```

## This one does NOT encode the defect — it encodes a proxy

An important distinction from the C09 replacement, where the pin
asserted the defect *was correct*. This pin's **requirement is right**:

> "Its presence meant a sim bot never reserved at all, which is the
>  behaviour the 2026-08-05 directive reverses."

Sim bots must reserve. That is correct and stays.

What is wrong is the **implementation**. It checks that the string
`_sim_mode` is absent from non-comment source, as a stand-in for "sim
bots still reserve". Two consequences:

1. **It is over-broad.** It fails any use of `_sim_mode` in that method,
   including one that does not skip. C16 declines to assert
   `total_holdings` on the *first* sim reserve — the bot still reserves,
   against the injected private registry, exactly as intended. The
   requirement is honoured; the proxy is tripped.

2. **It is weak where it matters.** It never verifies that a sim bot
   obtains a reservation. If sim reservations broke for any *other*
   reason — a renamed registry method, a changed qty formula, an
   exception swallowed upstream — this pin stays green. It is guarding
   the spelling, not the behaviour.

The second point is why replacement is the right call rather than
working around the first. The current test would have passed throughout
the entire period SN-5 describes, in which sim reservations failed on
every bot on every tick.

## What replaces it

`test_a_sim_bot_actually_obtains_a_reservation` — constructs a sim bot
with an injected private registry and asserts a reservation token exists
for it afterwards.

Strictly stronger:

- It covers the original requirement (no skip: a skip produces no
  token, so the new pin fails).
- It also covers every other way sim reservation can break, which the
  string check could not see.
- It asserts against the **injected** registry, so it cannot be
  satisfied by a reservation landing on the live one.

The original test's name and docstring intent are carried into the
replacement so the history is not lost.

## What is NOT being relaxed

`test_bot_accepts_an_injected_registry` and
`test_crr_prefers_the_injected_registry` in the same file are untouched.
The isolation requirement — that sim reserves against its own registry
— is unchanged and now behaviourally enforced rather than inferred from
source text.

## Failing-first

The replacement is observed RED against the pre-C16 baseline (where sim
reservations fail the over-commit check every tick) before the C16 edit
is kept. A pin never observed failing has not been verified.
