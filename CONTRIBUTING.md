# Contributing to Acervator

This is v1 — built by one person. The battery is 39/39 but one person's perspective has limits. If you find where it fails, that's useful. Document it, fix it, submit it.

## Ground Rules

1. **Honesty over flattery.** If something doesn't work, say so. Failed experiments are as valuable as successes.

2. **Tests first.** Any change to the trading engine or exchange logic ships with tests. Add or update tests under `tests/`, and make the full suite green (`pytest`) before you open a PR. CI runs the same suite; a red suite blocks the merge.

3. **Don't break the GUI without fixing it.** GUI changes must not alter widget dimensions outside the changed widget. Check adjacent layout elements before and after.

4. **Nothing is written to the repo by a test.** Tests verify behaviour in memory and route any file output to a temp dir (`tmp_path`/`tempfile`). Never write into the working tree, `~/.acervator`, or `~/.acervator_logs` from a test — `tests/conftest.py` guards this.

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
3. Run `black`, `flake8`, and `pytest` locally — all green
4. Submit the PR with a clear description of what changed and why
5. CI (lint + tests) must pass before the PR can merge

## Questions

Open an issue. Be specific about what you're seeing and what you expected.

---

*"The next version of Acervator will be built by everyone."*
