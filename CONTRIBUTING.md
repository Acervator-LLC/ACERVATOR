# Contributing to Acervator

This is v1 — built by one person. The battery is 39/39 but one person's perspective has limits. If you find where it fails, that's useful. Document it, fix it, submit it.

## Ground Rules

1. **Honesty over flattery.** If something doesn't work, say so. Failed experiments are as valuable as successes — the research essay documents both.

2. **Gate first.** Any change to the trading engine (`run_v3192` in `src/trading/`) must leave the release gate green. Run `python -m dev_harness.harness.check_release_readiness` before your change, save the `[OK] Release-ready (vX.Y.Z, N tests)` line, make your change, run it again. Put both lines in your PR. A test count that drops without an explanation is a failed run.

3. **Don't break the GUI without fixing it.** GUI changes must not alter widget dimensions outside the changed widget. Check adjacent layout elements before and after.

4. **Essay is the record.** Significant changes — new mechanisms, new battery results, new strategy comparisons — belong in `generate_essay.py` as a new numbered section. The PDF is regenerated automatically.

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

## Submitting a Pull Request

1. Fork the repo, create a branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run every archetype that matches a file you touched, one file per invocation: `python -m dev_harness.harness.coding_archetype PATH` for Python, `python -m dev_harness.harness.docs_archetype PATH` for Markdown. Each must report `passed=true` with no high or critical finding.
4. Put the gate line and the archetype verdicts in your PR description
5. Submit the PR with a clear description of what changed and why

## Running the Tests

```bash
# The whole suite, the way the gate runs it
python -m dev_harness.harness.check_release_readiness

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
