# Contributing to Acervator

This is v1 — built by one person. The battery is 39/39 but one person's perspective has limits. If you find where it fails, that's useful. Document it, fix it, submit it.

## Ground Rules

1. **Honesty over flattery.** If something doesn't work, say so. Failed experiments are as valuable as successes.

2. **Gate first, then tests.** Any change to the trading engine or exchange logic ships with tests, and must leave the release gate green. Run `python -m dev_harness.harness.check_release_readiness` before your change, save the `[OK] Release-ready (vX.Y.Z, N tests)` line, make your change, run it again. Put both lines in your PR. A test count that drops without an explanation is a failed run. CI runs the same suite; a red suite blocks the merge.

3. **Don't break the GUI without fixing it.** GUI changes must not alter widget dimensions outside the changed widget. Check adjacent layout elements before and after.

4. **Nothing is written to the repo by a test.** Tests verify behaviour in memory and route any file output to a temp dir (`tmp_path`/`tempfile`). Never write into the working tree, `~/.acervator`, or `~/.acervator_logs` from a test — `tests/conftest.py` guards this.

5. **The changelog is the record.** Significant changes — new mechanisms, new battery results, new strategy comparisons — go in `CHANGELOG.md`, with the supporting measurement written up under `docs/audits/`.

## What We're Looking For

- **Edge cases the battery doesn't cover** — new assets, new market regimes, extreme conditions
- **Dead zones** — market conditions where the gating logic paralizes the bot inappropriately
- **Performance improvements** — with pre/post battery evidence
- **Exchange connectors** — the paper trader supports CoinGecko, Kraken, Bybit. More sources welcome.
- **Documentation** — translations, clearer explanations, better examples

## What We're Not Looking For

- Prediction-based features. The whole point is that we don't predict.
- Features that require the user to be right about market direction.
- Complexity that can't be explained in plain language.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"        # runtime deps + pytest, black, flake8
```

## Running the tests

```bash
# Full suite. Qt widgets are built in the suite, so run headless:
QT_QPA_PLATFORM=offscreen pytest -q            # Windows: set QT_QPA_PLATFORM=offscreen

# A single file or test:
pytest tests/test_exchange_registry.py -q
```

## Formatting and linting

Formatting is `black` and linting is `flake8`; CI enforces both. Run them
before you push:

```bash
black src tests tools *.py        # format in place
flake8 src tests tools *.py       # lint
```

`black --check` and `flake8` also run as the CI `lint` job, so a PR that is
not formatted, or that trips a lint rule, will fail there.

## Submitting a Pull Request

1. Fork the repo, create a branch: `git checkout -b feature/your-feature-name`
2. Make your changes, with tests
3. Run `black`, `flake8` and `pytest` locally — all three green. CI runs the same three and blocks the merge on any of them.
4. Run every archetype that matches a file you touched, one file per invocation: `python -m dev_harness.harness.coding_archetype PATH` for Python, `python -m dev_harness.harness.docs_archetype PATH` for Markdown. Each must report `passed=true` with no high or critical finding.
5. Put the gate line and the archetype verdicts in your PR description
6. Submit the PR with a clear description of what changed and why
7. CI (lint + tests) must pass before the PR can merge

## Running the Tests

```bash
# The whole suite, the way the gate runs it
python -m dev_harness.harness.check_release_readiness

# What CI runs: formatting, lint, then the fast lane
black --check src tests tools *.py
flake8 src tests tools *.py
pytest -n auto -m "not slow and not archetype" -q

# One test file while you work
python -m pytest tests/test_your_file.py -q

# One file through its archetype (one file per invocation)
python -m dev_harness.harness.coding_archetype src/your_file.py

# Every runtime pin still has a registry row
python -m tools.emitter_registry_check
```

Do not run pytest with a friendlier invocation than the gate uses. A pass the gate cannot reproduce is not a pass.

## Questions

Open an issue. Be specific about what you're seeing and what you expected.

---

*"The next version of Acervator will be built by everyone."*
