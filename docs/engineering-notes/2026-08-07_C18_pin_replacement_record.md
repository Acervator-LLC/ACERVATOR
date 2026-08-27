# C18 — record of a pin replacement, written before the edit

Required by M7. Operator acknowledgement recorded 2026-08-07: **replace
with a behavioural pin**.

Third such replacement in this series (after C09 and C16), and the
second where the pin's *requirement* is right and its *implementation*
is a proxy that contradicts it.

## The pin being replaced

`tests/test_sim_reservation_isolation.py` —
`test_sim_bots_are_constructed_with_phantoms_enabled`

```python
"""``enable_phantoms=False`` removed the subsystem from sim
entirely. Phantom balance is per-bot in-memory state, so it needs no
external isolation — it was simply switched off, which is the same
feature-subtraction the directive rejects."""
src = inspect.getsource(frc._instantiate_bot)
assert "enable_phantoms=True" in src, \
    "sim bots must carry phantom balance like live bots"
```

## The requirement is right; the implementation contradicts it

The requirement — **do not remove the phantom subsystem from sim** — is
correct and is preserved. Switching a feature off is not simulating it.

The implementation asserts the literal string `enable_phantoms=True`.
That has two consequences, and the second is self-defeating:

1. **It is a proxy, and a weak one.** It checks a substring, not
   behaviour. It would stay green if phantoms were constructed and then
   never ticked — which is exactly the state the wall-clock cadence
   defect produced, and which this cascade also fixes. A phantom that
   exists and never runs satisfies this pin completely.

2. **It contradicts its own failure message.** The message reads "sim
   bots must carry phantom balance **like live bots**". Live bots do not
   have phantoms enabled: `phantoms_enabled` is False on **35 of 35**
   recorded bots, verified read-only from
   `~/.acervator/bot_state.json`. Hardcoding `True` makes the sim
   *unlike* live, which is the opposite of what the message asks for,
   and makes every parity claim about SCRUM/FOLD decisions
   non-comparable to the live fleet.

The cascade plan states the inverse of what the code does — it claims a
replay may construct *zero* phantoms. The controller hardcodes them
*on*. The plan's premise for this finding is backwards.

## What replaces it

`test_the_phantom_subsystem_stays_reachable_in_sim` — asserts the
requirement behaviourally:

- with the per-run toggle forced on, phantoms **are** constructed;
- and `tick_for_cursor` **advances** one, so the subsystem is exercised
  rather than merely instantiated.

Strictly stronger than the string check:

- it fails if phantoms are removed (the original defect);
- it also fails if phantoms exist but never tick, which the original
  could not see;
- it does not require the sim to run a configuration no live bot uses.

## What is NOT being relaxed

The default remains faithful to live (off), per the operator decision of
2026-08-07, with an explicit toggle so C17 and C46's phantom changes can
be verified by a run in which `_tick` actually executes. The toggle can
only force phantoms **on**, never off — an override that could disable
would be a second route to a phantom-less replay that looks configured.

## Failing-first

The replacement is observed RED against a baseline with the toggle
unimplemented, before the C18 edit is kept.
