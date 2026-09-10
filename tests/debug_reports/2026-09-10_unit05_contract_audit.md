# Unit 5 — the contract audit, and the three runs that threw

Reference. Three commands failed during the audit pass. Each one is recorded with
the command that produced it, the cause, what changed, and what the same command
prints now. No Solidity changed in this unit.

## The error

**Error 1. semgrep crashed writing its own output file.** The scan finished and
reported 98 findings; the crash came after, in the file write.

```
semgrep --config r/solidity --metrics off --output ..\semgrep_contracts.txt contracts

'charmap' codec can't encode characters in position 44-63: character maps to <undefined>
Traceback (most recent call last):
  File "...\site-packages\semgrep\commands\scan.py", line 1193, in scan
    output_handler.output(
  File "...\site-packages\semgrep\output.py", line 619, in _save_output
    fout.write(output)
  File "...\Lib\encodings\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode characters in position 44-63
exit 2
```

**Error 2. slither's exit code came back as 127, the code for a command that does
not exist.** slither had run and printed 18 results on the same invocation.

```
slither . --exclude-dependencies        (Git Bash)
INFO:Slither:. analyzed (32 contracts with 102 detectors), 18 result(s) found
SLITHER_EXIT=127
```

**Error 3. mythril would not install.** The failure is the last package in the
resolution.

```
python -m pip install mythril==0.24.8        (Python 3.12.10)

Building wheel for pyethash (pyproject.toml): finished with status 'error'
  error: Microsoft Visual C++ 14.0 or greater is required. Get it with
  "Microsoft C++ Build Tools": https://visualstudio.microsoft.com/visual-cpp-build-tools/
ERROR: Failed building wheel for pyethash
error: failed-wheel-build-for-install
exit 1
```

## Reproduction

**Error 1.** Run semgrep with `--output` over `contracts` on this machine, under
Python 3.14.4, with no encoding variable set. The crash is deterministic.

**Error 2.** Run slither from Git Bash and read `$?`. Run the same command from
PowerShell and read `$LASTEXITCODE`. The two numbers differ.

**Error 3.** Build a Python 3.12 environment and install mythril at its latest
published version.

```
py -3.12 -m venv <dir>
<dir>/Scripts/python.exe -m pip install mythril==0.24.8
```

## The cause

**Error 1.** `semgrep/output.py:619` opens the output file with the interpreter's
default encoding, which is cp1252 on Windows. semgrep echoes each matched source
line into its report, and two contracts carry characters cp1252 cannot represent.
Positions 44 to 63 are inside the echoed line, not inside semgrep's own text.

```
contracts/CompetitionRegistry.sol:239   unicode"Registry: need ≥ 2 participants"
contracts/AcervatorTrophy.sol:229       unicode' Acervator Trophy — '
```

**Error 2.** slither returns -1 when it has findings. Git Bash folds a negative
native exit code into the 8-bit range and reports 127. The shell produced the
number, not the tool.

**Error 3.** mythril depends on py-evm, which depends on pyethash, which publishes
no wheel at all. pip must build it from source, and the source needs a Microsoft
C++ toolchain this machine does not have. No mythril release avoids the
dependency.

```
mythril 0.24.8 -> py-evm 0.7.0a1 -> pyethash 0.1.27

pip download pyethash==0.1.27 --no-deps    pyethash-0.1.27.tar.gz, source only
pip index versions mythril                 latest is 0.24.8
docker --version                           command not found
vswhere.exe                                not present
```

## The correction

**Error 1.** Set `PYTHONUTF8=1` for the semgrep runs, so the interpreter opens
files as UTF-8. Nothing in the repository changed and semgrep was not modified.

**Error 2.** Read the exit code through PowerShell, captured on the same statement
as the call so no later command can overwrite it.

```powershell
$out = & slither . --exclude-dependencies --json artifacts/solidity_audit/slither_all.json
$code = $LASTEXITCODE
```

**Error 3.** None, and nothing was substituted. The audit records mythril as not
run and itself as incomplete on symbolic execution. Two routes unblock it, and
both need the operator to decide.

```
install Microsoft C++ Build Tools on this machine
install Docker and use the maintainers' own mythril/myth image
```

## The rerun

**Error 1.** Both semgrep runs complete and write their files.

```
PYTHONUTF8=1
semgrep --config r/solidity --metrics off --output ... contracts   exit 0
  Ran 50 rules on 4 files: 98 findings.
semgrep --severity INFO --output ...                              exit 0
  Ran 17 rules on 4 files: 98 findings.
```

**Error 2.** Both numbers are now slither's own, and the pair is what proves the
High band can report.

```
SLITHER_EXIT=-1   full run, 18 results
SLITHER_EXIT=0    High band only, 0 results
```

Every band run and every calibration run after this was read the same way.

**Error 3.** The install failed identically at the same package.

```
pip install mythril==0.24.8     exit 1    ERROR: Failed building wheel for pyethash
```

## What the audit pass left behind

No Solidity changed, and the diff is the proof.

```
git diff --stat contracts/      no output, no change
```

The files added are a report, a manual section, this page, and one calibration
pair for the forge invariant runner.

```
docs/audits/2026-09-10_contract_audit_ethtrust_levels.md
docs/manual/08-tabs/proof-of-accumulation.md             152 insertions
tests/debug_reports/2026-09-10_unit05_contract_audit.md
harness_fixtures/solidity_analyzers/known_bad_forge.sol
harness_fixtures/solidity_analyzers/known_good_forge.sol
```

## The calibration pair, and what it proves

The forge pair differs by one statement. The bad half credits the held bucket and
leaves the wallet bucket standing, so the books stop balancing on the first
spend.

```
known_bad_forge.sol    exit 1   [FAIL: buckets do not equal totalEverMinted]
                                runs: 1, calls: 1, reverts: 0
known_good_forge.sol   exit 0   [PASS] runs: 256, calls: 16384, reverts: 12529
```

The shipped invariants were run, not rewritten. They belong to an earlier unit.

```
forge test    exit 0
QuintessenceConservationTest invariants  runs: 256, calls: 16384, reverts: 8661
TrophyTierCapsTest invariants            runs: 256, calls: 16384, reverts: 9588
10 tests passed, 0 failed
```
