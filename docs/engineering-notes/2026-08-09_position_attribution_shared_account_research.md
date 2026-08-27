# Position attribution on a shared exchange account

**Date:** 2026-08-09
**Question:** when multiple bots — and the operator by hand — trade one
Coinbase account, how do production systems decide which units belong
to which strategy?
**Occasioned by:** the BICO/IMU incident (2026-08-09, v3.24.51), where
two new bots each bought a second full position on top of one the
operator had placed manually.

---

## The measured situation

| | |
|---|---|
| bots in `bot_state.json` | 37 |
| distinct `target_asset` values | 37 |
| assets targeted by more than one bot | **0** |
| bots with no lots | 0 |
| bots that have never scrummed | 3 |

This matters for one reason. `BotManager.has_sibling_target_bots()` is
the predicate the proposed conditional rule turns on, and on this fleet
it returns False for every bot. "Isolate only when a sibling shares the
asset" therefore does not mean *narrow the rule*; it means **remove
isolation from all 37 bots**.

---

## What the field actually does

Three distinct patterns, all in production use.

### 1. Exchange-level isolation — Coinbase Portfolios

Coinbase Advanced Trade supports multiple **Portfolios** (sub-accounts)
holding separate balances. The API carries `retail_portfolio_id` on Get
Accounts, List Orders, Create Order and Preview Order, so balances and
orders can be scoped to one portfolio. Funds move between portfolios
instantly and free, but a portfolio cannot be funded directly — it must
be filled from another portfolio.

Third-party support is uneven, which is itself evidence of how the
industry treats this:

* **Cryptohopper** — supports Coinbase Portfolios as sub-accounts for
  bot trading, via API keys.
* **3Commas** — supports only the Primary spot and Perpetual accounts;
  "additional portfolios cannot be connected."

This is the only pattern that makes attribution a non-problem: the
exchange itself reports a balance that belongs to exactly one actor.

**HYPOTHESIS.** I could not confirm from primary docs how many
portfolios are permitted, whether an API key can be *hard-scoped* to a
single portfolio (vs passing `retail_portfolio_id` per request), or
whether ccxt's Coinbase driver exposes it. The Coinbase help page
returned HTTP 403 and the CDP FAQ does not cover portfolios. Verify
before relying on it.

### 2. Internal ledger is authoritative — Freqtrade

Freqtrade's FAQ states it plainly:

> "Freqtrade assumes that the trades it opens are managed only through
> the bot."

Its position is what its own trade database says it bought. It fetches
the exchange balance only to check funds before placing an order. There
is **no documented mechanism to adopt a pre-existing or manually-placed
position** — no import, no sync-from-exchange. Users who manually sell
a bot-held position report the bot breaking, and the guidance is not to
do it.

For multiple instances it prescribes separate databases, separate API
ports, separate Telegram bots, and `available_capital` per instance to
partition the pool.

**This is what Acervator already does.** `_main_lots` is the same
concept as Freqtrade's trade DB, and v3.23.43 hardened it to the same
rule.

### 3. Operator-declared allocation cap — Hummingbot

Hummingbot's `balance limit` command sets, per exchange and per asset,
the maximum the bot may use:

> "Sets the amount limit on how much assets Hummingbot can use in an
> exchange or wallet."

The documented effect is that the bot stops placing orders once its
allocation is exhausted **even though more funds exist in the account**,
which "carves out a designated allocation for that bot instance,
leaving the remainder untouched for other bots or manual trading."

This is the piece Acervator does not have, and it is the direct answer
to "how do I stop a bot absorbing coins I want kept out of its reach".
It does not try to infer ownership. The operator declares it.

---

## Assessment of the rule in front of us

**The rule as shipped in v3.24.91:** a bot that has never scrummed
adopts the exchange balance for its asset as its opening position; a bot
with scrum history keeps `_main_lots` authoritative and the exchange
balance may never inflate it.

**Consistent with the field?** Mostly, and it is strictly more capable
than Freqtrade, which has no adoption path at all and simply reports
nothing for a position it did not open. The never-scrummed gate is a
reasonable bound: a bot with no earned history has no ledger worth
defending, so trusting the exchange costs nothing that was earned.

**Failure modes it still has.**

1. **Adoption with an unknown cost basis.** Units the operator bought
   have a real purchase price the bot cannot see. It records current
   price (or `cost_basis_total_exchange` when available). Every later
   P&L number for that bot inherits that approximation.
2. **Two fresh bots on one asset would both adopt.** No sibling check
   fires on ordering; the second bot to boot would claim the same units.
   Not reachable on today's fleet (0 shared assets) and the sibling
   subtraction in the adoption block covers the tracked case, but it is
   not structurally prevented.
3. **Adoption of units the operator wants kept back.** Nothing
   distinguishes "seed for this bot" from "my own holding of the same
   coin". A fresh bot on an asset the operator already holds will take
   all of it.

**Failure mode 3 is the one with no current mitigation, and Hummingbot
solves exactly it.**

---

## Recommendation

**Keep the current rule (option A).** It matches the established
pattern, and the measurement disqualifies the alternative: with zero
shared assets, "isolate only when a sibling exists" removes the guard
fleet-wide and reinstates the class of bug the BICO/IMU fix closed.

**Add the missing safeguard: a per-bot maximum adoptable amount**, in
the shape of Hummingbot's `balance limit`. Adoption then has a ceiling
the operator declares rather than one the bot infers, which closes
failure mode 3 and bounds failure mode 1. The natural default is the
bot's own `target_balance` — a bot asked to hold $25 has no business
adopting $500 of an asset because it happened to be there.

**Consider Coinbase Portfolios as the structural fix** if the fleet ever
grows two bots on one asset, or if you want your manual holdings
provably out of reach. It converts attribution from an inference into an
exchange-enforced fact. Verify the API and ccxt support first — the
specifics above are unconfirmed.

---

## Sources

- Freqtrade FAQ — <https://www.freqtrade.io/en/stable/faq/>
- Freqtrade Configuration — <https://www.freqtrade.io/en/stable/configuration/>
- Freqtrade issue #4355, two strategies on one account —
  <https://github.com/freqtrade/freqtrade/issues/4355>
- Freqtrade issue #8841, bot/exchange balance discrepancy —
  <https://github.com/freqtrade/freqtrade/issues/8841>
- Hummingbot Balance Limit —
  <https://hummingbot.org/client/global-configs/balance-limit/>
- Hummingbot Check Balances — <https://hummingbot.org/client/balance/>
- Coinbase Advanced Trade API changelog (`retail_portfolio_id`) —
  <https://docs.cloud.coinbase.com/advanced-trade/docs/changelog>
- Coinbase Advanced Trade REST API —
  <https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api>
- Cryptohopper, Coinbase portfolios as sub-accounts —
  <https://support.cryptohopper.com/en/articles/9582174-how-to-automate-crypto-trading-with-portfolios-sub-accounts-on-coinbase>
- 3Commas, Coinbase Advanced API keys (portfolio limitation) —
  <https://help.3commas.io/en/articles/8228623-coinbase-advanced-how-to-create-api-keys>
