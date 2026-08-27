# Traps that pass a naive test

Reference. Every entry here is a defect this codebase actually shipped,
where the **obvious fix and the obvious test both look right and both
are wrong**. They are collected because they keep recurring: five of the
eight cascades shipped on 2026-08-07 hit one.

The common shape: an instrument that reports success while measuring
nothing. A test that cannot fail is worse than no test, because it
converts an open question into a settled one.

Each entry names where it is guarded in code, so this document and the
source cannot drift apart silently.

---

## 1. Bound methods compare unequal by identity

```python
obj.handler is obj.handler   # False
obj.handler == obj.handler   # True
```

CPython builds a fresh bound-method object on every attribute access.
Any registry that stores callbacks and later removes them by `is` will
match **nothing** while looking entirely correct.

**Shipped as:** `EventBus` had no `unsubscribe` at all (C17). An
identity-based implementation would have left every subscription
attached and the sim-to-live bus leak intact, behind a green test.

**Guarded at:** `src/core/event_bus.py` — comment on `_Subscriber.callback`,
and `unsubscribe` uses `!=`. Pinned by
`tests/test_event_bus_unsubscribe.py::test_it_works_on_bound_methods`,
which asserts the language behaviour itself so the premise cannot rot.

---

## 2. Reading a `defaultdict` mutates it

`d[k]` on a `defaultdict` **creates** `k`. An accessor that inspects
such a structure — a count, a report, a health check — changes what it
is measuring, and before/after comparisons drift on key churn alone.

**Shipped as:** near-miss in C17. The subscriber-count accessor written
the obvious way would have made the exit gate's before/after fingerprint
non-deterministic.

**Guarded at:** `src/core/event_bus.py` — comment on the `_subscribers`
declaration; `subscriber_count` and `subscription_fingerprint` use
`.get()`. Pinned by
`test_counting_an_unknown_topic_does_not_create_it`.

---

## 3. `subprocess.run(text=True)` decodes with the LOCALE codec

No `encoding=` means cp1252 on this machine. One non-cp1252 byte in a
tool's output raises `UnicodeDecodeError`, `stdout` comes back `None`,
and the layer silently produces nothing.

**Shipped as:** `docs_archetype` read proselint this way. proselint's
curly-quote message *contains curly quotes*, so the prose layer returned
**zero findings for every document it ever checked**. The defect message
it existed to report is what killed it.

**Guarded at:** all 10 subprocess sites across the three archetypes now
pass `encoding="utf-8", errors="replace"`. Pinned structurally by
`tests/test_archetype_subprocess_encoding.py`, which sweeps every
`subprocess.run` in `tools/harness/`.

---

## 4. `logging.FileHandler` with no `encoding` drops records

Same root cause, opposite direction — encoding rather than decoding.
Python's logging swallows the `UnicodeEncodeError` into
`--- Logging error ---` and **discards the record**.

**Shipped as:** the system logger. The operator's 2026-08-07 08:18 boot
produced 15,616 lines, 825 error blocks, and **3 surviving records**.
Found by trying to *read* the log to diagnose something else.

**Guarded at:** `src/core/logging_engine.py`. Pinned by
`tests/test_system_log_encoding.py`, with a positive control proving a
bare handler really does drop the arrow on this machine — so the test
cannot pass vacuously where the locale codec is already UTF-8.

---

## 5. Source-text search matches the comment explaining the removal

Asserting a thing is *absent* by searching source text fails the moment
someone documents why it was removed — because the comment names it.

**Shipped as:** hit 5+ times across this series. Most recently in C09,
where a substring count read 3 for 2 real calls.

**Guard:** assert over the **AST** — `ast.Call` nodes, assigned
attribute names, `ast.Name` ids — never `in source`. Used throughout
`tests/test_bot_swarm_list.py`, `test_suite_integrity.py`,
`test_bus_injection_isolation.py`.

---

## 6. Qt object lifetime is not Python lifetime

A `QDialog` can be destroyed C++-side while its Python wrapper survives.
A `weakref` on the wrapper therefore proves nothing about whether the
widget leaked.

**Shipped as:** C28's `WA_DeleteOnClose` omission. A weakref-based
assertion would have passed against the *unfixed* code.

**Guarded at:** `tests/test_sim_visuals_expand_reentrancy.py` checks
`shiboken6.isValid`, falling back to a wrapper weakref only when
shiboken is unavailable.

Related: `repaint()` does **not** fire `paintEvent` offscreen;
`render(QPixmap)` does. Any test asserting on paint side effects must
use `render`.

---

## 7. A defaulted parameter means the caller can silently skip the fix

Adding an injectable seam does nothing if no production caller injects.
The capability tests all pass; the defect survives.

**Shipped as:** C35's dismissal store — the pane could persist, and
nothing in production handed it anywhere to persist to. Caught only by a
pin asserting the **call site**, not the capability.

**Guard:** for every injection, pin the wiring at each hop with an AST
call-check. See
`tests/test_topology_dismiss_persistence.py::test_the_owner_actually_wires_a_store`
and `test_bus_injection_isolation.py::TestTheNuclearControllerInjects`.

---

## 8. A blanket `except` makes an absence test vacuous

If a function catches everything and returns `None`, then
`assert result is None` passes for *any* reason — including reasons
unrelated to the behaviour under test.

**Shipped as:** C15. A new pin passed against **unfixed** code because
the dummy exchange failed construction for an unrelated reason.

**Guard:** pin the *reason*, not just the outcome — assert the
operator-visible message, and assert structurally that the guard
precedes the `try`. See
`tests/test_sim_capital_registry_fail_closed.py`.

---

## 9. Verifying isolation by touching the thing you are isolating from

**Shipped as:** C15's first `_assert_capital_isolation` compared each
bot's registry against `get_registry()` — which *resolves, and can
construct*, the live singleton from a sim path. The guard broke the rule
it was written to enforce. `tests/test_singleton_isolation.py` failed
it.

**Guard:** verify a **property** that does not require the live object
(`autosave` is off), not identity against it.
