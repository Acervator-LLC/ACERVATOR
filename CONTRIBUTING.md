# Contributing to Acervator

This is v1 — built by one person. The battery is 39/39 but one person's perspective has limits. If you find where it fails, that's useful. Document it, fix it, submit it.

## Ground Rules

1. **Honesty over flattery.** If something doesn't work, say so. Failed experiments are as valuable as successes — the research essay documents both.

2. **Battery first.** Any change to `RAIntSimBat.py` or the trading engine (`run_v3192`) requires a pre/post battery comparison. Run `python RAIntSimBat.py` before your change, save the output, make your change, run it again. Include both results in your PR.

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
3. Run the battery if you touched engine code: `python RAIntSimBat.py`
4. Include battery results in your PR description if applicable
5. Submit the PR with a clear description of what changed and why

## Running the Tests

```bash
# Full simulation battery (required for engine changes)
python RAIntSimBat.py

# Strategy comparison
python RAIntSimBat.py RAIntSimBat-COMPARE-FULL

# Single asset validation
python RAIntSimBat.py RAIntSimBat-BTC-USD-2023
```

## Questions

Open an issue. Be specific about what you're seeing and what you expected.

---

*"The next version of Acervator will be built by everyone."*
