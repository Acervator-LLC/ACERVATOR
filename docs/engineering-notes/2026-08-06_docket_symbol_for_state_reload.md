# DOCKET — `_symbol_for` reloads the entire state file, once per bot, inside a refill loop

**Filed** 2026-08-06 · **Found by** Claude, incidentally, during C05 step 3
**Status** OPEN — deliberately not fixed
**Severity** performance / latency; no correctness impact observed
**Scheduled for** the Bot Swarm tab performance pass, or whichever
cascade next opens `bot_visualizer.py` for real work

---

## 1. What was found

`QuickRoutingMatrix._symbol_for` (`src/gui/bot_visualizer.py:914`) looks
up a bot's display symbol. Its fast path reads a cached widget:

```python
w = self._viz._bot_widgets.get(bot_id)
if w is not None:
    sym = w._bot_data.get("symbol", "") ...
    if sym:
        return str(sym)
```

Its fallback, taken whenever that cache misses **or the cached symbol is
empty**, is:

```python
from ..core.state_manager import StateManager
st = StateManager().load_state()
```

That is a full read and parse of `bot_state.json` — the whole file, all
bots — to retrieve one string.

`_symbol_for` is called once per bot inside `rebuild_scope`'s refill
loop. On the operator's 35-bot swarm, a single `rebuild_scope` with a
cold widget cache is **35 full state-file loads**. `rebuild_scope` runs
on every scope/filter change.

## 2. Why it is being docketed rather than fixed

C05's scope was mass-operation confirmation, named rejections, and
scope-list stability. This is a performance defect in a helper that
C05 only had to *read* in order to understand the scroll behaviour
(it is the call inside the loop that could turn the event loop).

Fixing it means deciding a caching policy — how long a symbol lookup
may be stale, whether `rebuild_scope` should hoist one load out of the
loop, or whether `StateManager` should cache. That is a real design
call, not a drive-by edit, and it belongs to whoever owns the next
pass over this file. Widening C05 to include it is the scope creep the
operator has already called out twice.

## 3. What has NOT been measured

Stated plainly so nobody inherits an unearned conclusion:

- **No timing was taken.** The cost is inferred from the call structure,
  not observed. `load_state()` may be fast enough on the operator's
  state-file size that this never matters.
- **Cache hit rate is unknown.** If `_bot_widgets` is populated in
  practice, the fallback may almost never fire and this is a non-issue.
  If it is cold at construction — which is when `rebuild_scope` first
  runs — it fires for every bot.
- **The empty-symbol path is untested.** A cached widget whose
  `symbol` is `""` falls through to the reload *every time*, and would
  never warm up. Whether that state occurs is unverified.

The first step of any fix is measuring those three, not editing.

## 4. Adjacent observation

Both `try` blocks in `_symbol_for` swallow everything — the first with
`except Exception: pass`, the second returning `"?"`. So a genuinely
broken state file renders as a scope list full of `?` with nothing in
the log. That is the same silence family C05 addressed in the mass
operations, and should be fixed in the same pass as the caching.

## 5. Reference

- `src/gui/bot_visualizer.py:914` — `_symbol_for`
- `src/gui/bot_visualizer.py:879` — `rebuild_scope`, the caller
- Commit `e46cb0b` — C05 step 3, where this surfaced
