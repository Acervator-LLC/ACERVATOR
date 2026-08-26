# Tests

Applies to all tests in this repo.

## Tests assert behavior, never the shape of the source

A test proves what the code **does** — given inputs and state, it exercises the
real unit and asserts the observable outcome. A test must **never** read, parse,
or pattern-match the source of the code under test, and must **never** depend on
where that code physically lives.

**Forbidden, without exception:**

- Line numbers or line positions of source code — no `:1234` anchors, no
  "assert X appears before Y in the file", no `seg.index("a") < seg.index("b")`.
- SHAs, digests, or any hash of a file / of "the codebase state".
- Reading a source file as text and asserting on it — `Path(...).read_text()`,
  `open(...).read()`, then `assert "..." in src`, a regex over the source, or
  `src.splitlines()` counting.
- Reflecting on source via `inspect.getsource` / `inspect.getdoc`, or
  `ast.parse` of a file / of `inspect.getsource(...)`, to assert a function's
  internal shape — its comparisons, its assignments, which names it binds,
  whether it `await`s, how many times something appears.
- Using **comment or docstring text as a landmark** — e.g. locating a region by
  a `# BEGIN ... # END` banner, or asserting a comment/phrase is present. A
  comment is not a contract; a test that depends on one makes the comment
  load-bearing, which it must never be.

These tests are worthless: they pass while the behavior is broken and fail on
every refactor that moves a line or a comment. They give false coverage and
actively obstruct cleanup. **If a test breaks only because code moved, a comment
changed, or a line shifted — the test is the defect. Delete it or rewrite it as
a behavioral test; never repoint its anchors.**

**Allowed** (these read the runtime, not the source text): calling the real
function and asserting its return value / emitted events / mutated state;
`inspect.signature(fn).parameters` to assert the public API/contract;
`dataclasses.fields(...)` for a declared schema; asserting on a value a function
returns or a message it emits at runtime.

If an invariant is only expressible by inspecting source, that is a signal the
code needs a **seam** — extract the logic into one method/function both callers
share, then test that. A shared method makes drift structurally impossible,
which is stronger than any source assertion.

## Only unit and integration tests

Every test is one of two things:

- A **unit test** — exercises a single unit (a function, a method, a class) in
  isolation and asserts its contract. Stub only the outward edges (exchange,
  bus, clock, filesystem); run the **real** code under test.
- An **integration test** — exercises a small, coherent end-to-end flow across a
  few units of one feature, and asserts the outcome the flow is responsible for.

Nothing else. No source-shape tests (above), no "the whole app boots" mega-tests
that assert nothing specific.

## A test describes one thing, and its name says what

- Each test pins **one** behavior. The name states the behavior in plain words
  (`test_a_sell_increments_ytd_scrummed_by_the_fill_usd`), not the mechanism.
- Prefer many small, focused tests over one test with many unrelated assertions.
- An integration test may span a feature's flow, but keep the feature set small —
  it should still be describable in one sentence.

## Make failures legible and controls honest

- Assertion messages name the concrete expectation and, where useful, carry the
  real output (the log lines, the placed order, the emitted event) so a failure
  points at the cause without a debugger.
- A test that asserts "nothing happened" (zero events, no order placed, state
  unchanged) needs a **positive control** proving the instrument would have seen
  the thing if it had happened — otherwise the green means nothing.
- Drive the **real** code path. A stub that reimplements the logic under test, or
  that silently swallows the call, proves nothing. When stubbing a collaborator,
  make it fail loudly if it is misused.

## Determinism

Tests must be deterministic and isolated. No dependence on wall-clock timing,
real network, real exchange, ordering between tests, or shared process-global
state left dirty by another test. Use `tmp_path` / `tempfile` and fakes; never
touch the real runtime tree (see the repo hard rules on paths).

## When code moves, tests follow the behavior — not the lines

Refactors (extracting a mixin, splitting a god-file, renaming) must not break a
well-written test, because a well-written test never knew where the code lived.
If a test breaks during a pure refactor, that test was coupled to source shape —
fix the test to assert behavior, do not restore the old layout to appease it.
