# The touch-set gate that refused everywhere, and the Solidity analyzer with no declaration

Reference. Two units doing other work reported these two tools as broken. This
unit acted on both reports instead of recording them again.

## Defect one: the touch-set gate

### The gate error

The report said the gate cannot run in a worktree and exits 0 while refusing.
The first half holds. The second does not: the gate refused, and it returned 2.

```
python -m dev_harness.touchset baseline dev_harness/touchset.py --pin <file>
  REFUSED: no routing rule at <worktree>\...\archetype_gate.py
  This module reuses the gate's routing rather than copying it,
  so with no rule to reuse it measures nothing. Nothing written.
EXIT=2
```

PowerShell captured that exit code on the same line as the command, so no other
process could set it.

### Reproducing the reported zero

Piping the output into another program returns that program's status, not the
gate's.

```
python -m dev_harness.touchset baseline <file> --pin <file> 2>&1 | sed 's/^/  /'
  REFUSED: no routing rule at ...
EXIT=0
```

That reproduces the reported reading exactly, including the two-space indent in
the original report. The zero belongs to `sed`.

### The gate cause

`GATE_RELPATH` named the hook file inside the `.claude/hooks/` directory. The
harness moved its hooks to `dev_harness/hooks/` and nobody updated the constant.
`.gitignore:103` excludes the old directory, so no worktree and no fresh clone
can carry it, and the operator's own tree does not carry it either.

```
git ls-files .claude
  .claude/.gitignore
  .claude/rules/code-comments.md
  .claude/rules/documentation.md
  .claude/rules/tests.md

git ls-files dev_harness/hooks/archetype_gate.py
  dev_harness/hooks/archetype_gate.py
```

`load_gate` therefore raised `RoutingUnavailable` on every invocation in every
tree. The gate refused 100 per cent of runs and measured nothing for anybody.

The harness had already found this. Its hallucination rule reported the dead path
three times on the unmodified file, at medium, where `passed` cannot see it.

```
python -m dev_harness.harness.coding_archetype dev_harness/touchset.py
  passed=True   findings=40   low=32 medium=8
  hallucination   3 findings on the old hooks path
  hallucination   2 findings on the deleted island tool
```

### The gate correction

`GATE_RELPATH` now names the tracked file. The routing rule itself does not move,
and a measurement says so rather than an assumption: the tracked file and the
installed user-level hook hold identical bytes.

```
diff <user hooks>/archetype_gate.py dev_harness/hooks/archetype_gate.py
DIFF_EXIT=0
```

Every command now ends through one function, so the printed exit code and the
returned exit code share one value and cannot drift.

```python
def _say_verdict(code: int, headline: str, *detail: str) -> int:
    label = "OK" if code == 0 else "REFUSED"
    _say(f"{label} (exit {code}): {headline}")
    for line in detail:
        _say(line)
    return code
```

Four further dead citations in the same file are gone. Two docstrings compared
this module to the deleted island tool. Two strings named the module under its
old package.

This unit changed nothing the gate checks. It relaxed no rule, moved no
threshold, added no suppression, and left the set of paths the routing covers
exactly as it was.

### Refuse or degrade

The gate refuses. A missing routing rule means the run cannot start, so it exits
2 and writes no pin. The alternative is a private copy of the routing table
inside this module, which would drift from the hook and would grade files under
an authority this module does not hold.

The refusal is now loud on both surfaces. The status says 2 and the text says 2,
so a caller that loses the status still reads the verdict.

### The gate rerun

The refusal path, driven by running the same file in a tree that holds no routing
rule.

```
REFUSED (exit 2): no routing rule at <tree>\dev_harness\hooks\archetype_gate.py
This module reuses the routing rule rather than copying it, so
with no rule to reuse it measures nothing. Nothing written.
EXIT=2
```

The same refusal read through the pipe that produced the false report. The status
is still the pipe's, and the text now carries the truth.

```
  REFUSED (exit 2): no routing rule at ...
EXIT=0
```

A genuine pass, in the worktree, measuring a real file end to end.

```
Touch set: 1 file(s) under <worktree>
Routing rule: dev_harness/hooks/archetype_gate.py:_pick_archetypes

  dev_harness/touchset.py
      line endings LF   forbidden directives 0 (tokenize-comment-pragmas)
      dev_harness.harness.coding_archetype: passed=True   high=0
      dev_harness.harness.ta_archetype: passed=True   high=0

OK (exit 0): pin written to <scratch>\TBG_pass_pin.json
EXIT=0
```

The second subcommand, against that pin.

```
OK (exit 0): 1 file(s) match the pin, and no file the pin never saw
    carries a suppression, a red verdict or a foreign line ending.
EXIT=0
```

## Defect two: the Solidity analyzer

### The analyzer error

`slither` sat only inside a scratch virtual environment and was absent from PATH.
A cleanup of that directory removes Solidity static analysis, and nothing
announces the loss.

### Where it resided

In a temporary directory, on the interpreter version this repository pins.

```
C:\Users\...\Temp\claude\solaudit-venv\Scripts\slither.exe
slither_analyzer-0.11.6.dist-info      Requires-Python: >=3.10
pyvenv.cfg                             version = 3.14.4

which slither        no slither on PATH
```

### The analyzer cause

No committed declaration named it. `pyproject.toml` is the one dependency source
in this repository, and the analyzer appeared in none of its extras, so nothing
could reinstall it and nothing could report it absent.

### The analyzer correction

The `dev` extra now declares it, beside the six analyzers the coding archetype
spawns, with its consumer and its measured version named in the comment above.

```toml
"slither-analyzer>=0.11.6",
```

Every other analyzer in that extra uses the same lower-bound form. The fixtures
measured 0.11.6. `foundry.toml` already pins the compiler it needs, solc 0.8.36,
and the analyzer brings `solc-select`, which fetches that compiler with no hand
build.

```
solc-select install 0.8.36
solc-select use 0.8.36
```

The repository's own dependency tool reads the declaration and reports on it. It
named the gap before the install and names the version after it.

```
python -m tools.deps check --extras dev --extras-only
  MISSING slither-analyzer   (slither-analyzer>=0.11.6)
  ...
  ok      slither-analyzer   0.11.6
```

Installing from that declaration put the program on PATH, where the other
analyzers live.

```
python -m pip install "slither-analyzer>=0.11.6"
Get-Command slither     ...\Python314\Scripts\slither.exe
slither --version       0.11.6
```

The install added 26 packages and upgraded none. It moved one package down,
`websockets` 17.1 to 15.0.1, which the web3 bound forces. Nothing requires that
package and no file in the tree imports it.

```
python -m pip show websockets
  Required-by:            (empty)

grep -rn "import websockets" --include=*.py .
  (no matches)
```

### The analyzer rerun

One more fact came first. Inside this repository `crytic-compile` detects the
Foundry project from `foundry.toml` and runs `forge`, which sits in
`~/.foundry/bin` and is absent from PATH.

```
crytic_compile/platform/foundry.py:225 in config
FileNotFoundError: [WinError 2] The system cannot find the file specified
```

With that directory on PATH, the fixture pair discriminates. The bad half names
the weakness the fixture carries, and the good half stays silent. Both numbers
match what the Solidity audit recorded.

```
known_bad_slither.sol    exit -1   31 detectors, 1 result   reentrancy-eth
known_good_slither.sol   exit  0   31 detectors, 0 results
```

The command, in full.

```
$env:PATH = "$env:USERPROFILE\.foundry\bin;$env:PATH"
slither <fixture>.sol --exclude-informational --exclude-optimization
                      --exclude-low --exclude-medium
```

## What the lanes reported

```
python -m tools.local_ci --lane black  --all     VERDICT: PASSED
python -m tools.local_ci --lane flake8 --all     VERDICT: PASSED
```

## One finding left open, with its measurement

Both lane path lists cover `src`, `tests`, `tools` and the root scripts. Neither
covers `dev_harness`, so neither lane read either file this unit changed. Both
files went through the two programs directly, and both are clean.

```
python -m black  --check dev_harness/touchset.py     exit 0
python -m flake8          dev_harness/touchset.py    exit 0
```

Widening the lanes belongs to another unit, because `dev_harness` does not pass
black today.

```
python -m black --check dev_harness
  12 files would be reformatted, 37 files would be left unchanged
```
