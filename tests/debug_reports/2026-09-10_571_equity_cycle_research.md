# `docs/engineering-notes/2026-09-10_equity_cycle_viability.md`

Reference. This unit changed no product file, no contract and no test. It ran web
searches and web fetches, read the accumulation engine and the equity package,
and wrote one engineering note plus two captured raw-source files.

No pytest ran. No pytest file names a symbol this unit changed, because this unit
changed no symbol. Both CI lanes would skip with no Python changed and report
`PASSED — 0 lane(s) ran`, which records that no lane ran rather than a pass.

## Where each file went, and why

```
docs/engineering-notes/              the note. CLAUDE.md gives docs/ the role of
2026-09-10_equity_cycle_             human-written documentation only, and this
viability.md                         note is a human-written research finding
                                     carrying no captured output

artifacts/571-equity-research/       the captured regulatory sources, verbatim,
raw_regulatory.txt                   with every URL and source date

artifacts/571-equity-research/       the captured market-structure sources,
raw_market_structure.txt             verbatim, with every URL and source date

tests/debug_reports/                 this file, matching every sibling in that
2026-09-10_571_equity_cycle_         directory
research.md
```

CLAUDE.md forbids captured output in `docs/`, `src/` and `tests/`. `.gitignore`
line 112 covers `artifacts/`, confirmed in the worktree:

```
git check-ignore -v artifacts/571-equity-research/raw_regulatory.txt
  .gitignore:112:artifacts/   artifacts/571-equity-research/raw_regulatory.txt
```

The name check ran before the write, listing `tests/debug_reports/` and filtering
it. The directory holds 125 files, and a filter for equity, stocks, 571 and cycle
matched none of them.

## The shared reproduction

Every regulatory and market figure in the note came from a `WebSearch` or a
`WebFetch` on 2026-09-10. The two raw-source files list each URL, the verbatim
sentence read, and the date the page itself gives. Re-running the fetches
reproduces the readings, with three exceptions that publish live numbers:

```
cboe.com/tradable_products/vix/     VIX spot, read at 17.72 on 2026-09-10
gurufocus.com S&P 500 yield         live, re-read gives a new number
multpl.com S&P 500 yield            live, re-read gives a new number
```

Four pages refused a fetch and the note says so rather than citing them:

```
investor.gov freeriding glossary                     HTTP 403
investor.gov fractional-share bulletin               HTTP 403
ecfr.gov 12 CFR 220.8                                302 to an unblock page
mdpi.com 18(3):132 full text                         HTTP 403, abstract used
```

The Regulation T text came from `law.cornell.edu/cfr/text/12/220.8` instead, and
the note names that source.

The arithmetic in the note came from one pass over the declared constants in this
repository and the fee rates quoted above. Every input and output sits in
`artifacts/571-equity-research/raw_regulatory.txt` under `ARITHMETIC`:

```
src/trading/container/config.py:66    target_balance           $200.00
src/trading/container/config.py:69    scrumming_interval_pct      1.0 %
src/trading/container/config.py:163   trading_fee_pct             0.6 %
src/stocks/stock_accumulation_bot.py:55   target_balance       $200.00
src/stocks/stock_accumulation_bot.py:59   interval_pct            2.0 %
SEC Section 31    $20.60 per $1,000,000 of sale value
FINRA TAF         $0.000166 per share sold
```

## The instrument, proved before the verdict

```
docs_archetype  harness_fixtures/docs_archetype/known_good.md
                EXIT=0   passed=True

docs_archetype  harness_fixtures/docs_archetype/known_bad.md
                EXIT=1   passed=False   1 critical/high finding
```

Both exit codes came back on the same line as the command that produced them, so
no pipe reported another command's status. Both runs listed all seven tools as
`ok` under `tool_availability`.

## The verdict on the note

```
docs_archetype  docs/engineering-notes/2026-09-10_equity_cycle_viability.md
                EXIT=0   passed=True   0 findings
                why_not_green=[]   unavailable_required=[]
                scanned=True   unhandled=False
                tool_availability: proselint ok, vale ok, structure ok,
                  story ok, updates ok, scaffolding ok, hallucination ok
```

Read out of the JSON `passed` field, not off the exit code.

The first run reported `passed=False` with 21 findings:

```
high     1   vale write-good.So, a sentence opening with "So "
medium  18   vale passive voice and wordy forms
low      2   proselint straight quotes, and a missing Diataxis mode signal
```

Only the one high finding gated. A prose rewrite cleared all 21. No rule changed.

## The hallucination rule

The note cites these paths inside the repository, and every one resolves in the
worktree:

```
src/trading/container/config.py
src/trading/scrumming/execution.py
src/trading/scrumming_bot.py
src/stocks/stock_accumulation_bot.py
src/stocks/alpaca_connector.py
src/stocks/broker_base.py
src/stocks/market_hours.py
src/gui/stock_main_window.py
artifacts/571-equity-research/
```

A second read confirmed every cited line number after the note landed. One
correction followed: the holiday table sits at line 28, and an earlier draft said
27.

Every other citation in the note points at a public web page with its own date,
and the two raw-source files carry the verbatim wording each one supplied.

## Two premises in the brief that the measurement refuted

```
1  The brief listed notional, extended_hours and fractionable among the order
   fields the existing connector assumes. It assumes none of them.

   grep -c "notional|fractionable|429|retry|sleep|corporate|split|dividend"
     src/stocks/alpaca_connector.py   0
     src/stocks/broker_base.py        0

   The connector sends symbol, qty, side, type, time_in_force, and a limit or
   stop price. Alpaca's API does carry the other fields, so the API is the wider
   surface and the connector uses less of it.

2  The issue records the two layers as already independent, on a search for
   "from src.trading" returning nothing in src/stocks/.

   the absolute form the issue searched   0 matches
   the relative form                      3 matches
     src/stocks/stock_accumulation_bot.py:28-30
       ..trading.ta_engine, ..trading.mr_inspector, ..trading.smart_wire

   The absence was a fact about the search pattern.
```

## Two defects found and not repaired

Both sit in `src/stocks/market_hours.py`, which nothing in the program reaches.
No entry point imports the package, and no test file cites it.

```
src/stocks/market_hours.py:216   et_offset = -5
  Eastern Daylight Time is UTC-4. The offset is computed once at construction
  and never refreshed.

src/stocks/market_hours.py:28    US_MARKET_HOLIDAYS_2025_2026
  the table ends at 2026-12-25.
```

A repair needs the file to execute first, and the owning item carries them.

## What the operator sees differently

Nothing on screen. This unit answers whether the accumulation cycle survives an
equity market, and writes the answer down.
