---
mode: story
---

# The Development Chronicle

This is how Acervator got built. It runs from 10 April 2026 to 8 September 2026.

None of it is written from memory. Memory is the first thing this project
stopped trusting. Every date below sits on an artefact — a commit, an issue, a
file, a comment somebody dated. Where no artefact exists, the entry says so and
stops there.

```
docs/audits/2026-09-08_development_map.md
    125 entries    120 artefact-recorded, 3 inferred, 2 gaps
    152 days       61 of them carry no usable record
    largest blank  27 June to 23 July
```

Sixty-one blank days out of a hundred and fifty-two is a poor record, and I am
not going to dress it up. Those days are blank in the paperwork, not in the
work. Read the gaps as gaps.

## How this chronicle was built

Seven sources carry the story, and each one has a reach and a limit. Nothing
before 18 August is in the commit history. Four months arrived as a single
import, so the first third of this chronicle is reconstructed rather than
replayed.

```
version numbers written into code comments      20 April to today
the pre-git build archive                       10 to 24 April
the archived session chronicle                  11 April to 9 June
six handoff files at the repository root        18 April to 3 September
dated audit units inside the first commit       24 July to 15 August
the narrative changelog                         4 to 25 August
git log and the runtime directory               18 August to today
```

One source was tried and thrown out. File dates in my own working copy put five
package roots on 23 April. A fresh checkout of the same commit gives those files
today's date, because checkout writes them. That is a fact about one disk. It is
not a fact about this project, so nothing here rests on it.

## 2026-04-11 — five days inside a chat window

We started in a chat window. Not an editor, not a terminal — a chat window with
no access to the file system. Every session began by uploading a zip of the
whole codebase, because the session could not read a file on its own.

Seventeen conversations, five days, about 27 MB of transcript. Out the far end
came 74 Python files and roughly 34,000 lines. Day one produced a grid bot, then
the accumulation engine, then a seven-indicator voting panel, the Phantom
Balance, a window and a build script. That is not a normal first day and I know
it.

```
docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md
    lines 13 to 26     session one
    lines 304 to 308   ~27 MB, 74 files, ~34,000 lines
```

## 2026-04-12 — scrum and fold were the wrong way round

Our whole method is one cycle. Sell the excess above a dollar target, buy back
more of the asset on the dip. Do that enough times and you end up holding more
than you started with.

On day two we found the two halves inverted. Our engine was selling where it
should have bought. Its own record calls this the most consequential defect in
the project, and I agree with that. Get the direction wrong and every other
thing you build is a faster way to lose.

```
archive chronicle lines 90 to 101   scrum and fold inverted, corrected
src/trading/otd_math.py             where the fold arithmetic lives today
```

## 2026-04-15 — the name

For the first four days this was not called Acervator. Sixteen builds stored on
11 April carry an earlier product name. Last build under the old name is stamped
14 April at 22:03. First build stamped Acervator reads 15 April at 01:35.

Acervator is Latin for one who heaps up. That is the whole product in one word.
Our code folder kept the old name for another two days. That only bothers the
person who renamed it.

```
build archive folder listing   old name through 14 April 22:03
build archive folder listing   Acervator from 15 April 01:35
src/core/event_bus.py          the name on the copyright line of every source file
```

## 2026-04-16 — the handoff, invented on the fly

Here is the problem a chat window gives you. Every session starts with nothing.
No memory of the last one, no vocabulary, no idea which decisions are settled.
You re-explain the entire product, and then you watch it re-litigate a thing you
closed a week ago.

We wrote a file. One markdown document at the root of the project, carrying
the vocabulary, the invariants and the standing rules forward into the next
session. Read it first, then work. That is the whole protocol, and it was
invented in an afternoon because the alternative was losing a day a week.

```
build archive package stored 16 April 14:59
    a 38,903-byte protocol document, a template, two readme files
ACERVATOR_HOP2.md    the earliest handoff still in the tree
tools/hop_check.py   what measures handoff drift today
```

That same release introduced numbered rules. Whenever a class of silent defect
got fixed, we wrote a rule, and no rule was ever deleted. By the next day there
were twenty-seven of them in six groups, because an ungrouped list of rules is a
load nobody can hold in their head.

That habit did not survive contact. On 18 June I ruled that no part of the
protocol built around those rules was valid or working. Two modules totalling
2,586 lines had been built to serve it. Nothing imports either one today.

```
src/core/rule_registry.py     every rule locked by default
src/core/version_sweep.py     built for the protocol, imported by nothing
```

## 2026-04-19 — the version went backwards and nobody wrote it down

In twelve hours the engine version reads 3.14.0, then 3.19.0, 3.21.0, 3.24.0 and
3.25.0. At 20:15 the same day it reads 3.9.0.

Why it went back is **not recorded**. No artefact states it. Both handoffs
written that day and the next carry 3.9.0, so the lower number is the one the
project kept, and that inference is the whole of the evidence. This entry is
inferred and I am marking it inferred.

```
six archived builds, version read from each build's own entry point
ACERVATOR_HOP3.md and ACERVATOR_HOP4.md    both at 3.9.0
```

## 2026-04-20 — ten reviewers, four of whom would not give it money

Ten named reviewers went over the trading logic. Six called it work in progress.
Four said plainly they would not trust capital to it.

They were right. Live decisions at that point used Bollinger Bands alone, at a
fixed two per cent delta, across fifteen bots. Twelve indicators vote on a trade
today, and none of that existed yet. That review proposed seven rules
of its own and not one of the numbers survived; the first was claimed by an
unrelated rule the following day.

```
docs-archive/llm-session-history/ACERVATOR_DEPT_LEAD_REVIEW_v3_12_0.md
    lines 13 to 26     the ten verdicts
    lines 364 to 368   Bollinger Bands alone, fifteen bots
```

## 2026-04-26 — three weeks I cannot account for

From 29 April to 18 May there are two dated points and nothing else. Our session
chronicle jumps the span. Handoff jumps it too. Build archive stopped on
24 April. Sixteen of those twenty days are **unrecorded**.

What I can say is that three whole minor version series passed through that
window. That makes it the fastest-moving stretch in the record and the worst
documented, which is not a coincidence.

Two things are dated inside it, both from directives quoted in the running code.
Venue is the authority on position health, and nothing recomputes locally what
the exchange already reports. Our grid bot was deleted somewhere in here, and no
commit ever added it, so a comment about a removed table is the only proof it
existed.

```
src/exchange/position_health.py    the venue is the authority
src/exchange/timeframes.py         timeframes follow what each venue offers
```

## 2026-05-20 — four hundred gigabytes

Our log directory grew to about 400 GB and crashed the machine.

Cause was ordinary and the shape of it is worth keeping. Per-run file rotation
had been added weeks earlier, capping each run at 400 MB. Nobody capped the
number of runs. Every crash and restart wrote a fresh post-mortem bundle of a
few hundred megabytes, and they accumulated for weeks until the disk went.

Three retention limits were written the same day. Bundle count, bundle age, and
a size warning printed at startup so the next one is visible before it is fatal.

```
acervator_watchdog.py
    POSTMORTEM_KEEP_LATEST     most recent 20 bundles kept
    POSTMORTEM_MAX_AGE_DAYS    anything older than 30 days dropped
    POSTMORTEM_SIZE_WARN_BYTES 5 GB, reported on startup
src/core/log_paths.py          the one labelled root every log writes under today
```

That same day carried twenty entries. A declarative gate chain replaced the
checks that had been scattered through the engine, and twenty-four standing test
failures closed. Our Extractor skeleton and its four-state machine landed in the
same stretch.

```
src/trading/extractor_bot.py   the four-state machine, still where it started
```

## 2026-06-05 — an address I never had

A session needed the project's source repository address. Instead of asking, it
built one out of my email handle and shipped it.

That invented address landed in 25 files and in a package published to PyPI —
the public index Python installers download from. Publishing is one way, so the
wrong address could not be withdrawn; the only remedy was a version bump and a
fresh upload. One good lesson came out of it. Do not infer an identifier. Ask,
leave it blank, or fail loudly.

```
docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md
    lines 18585 to 18587    fabricated address, 25 files, one published wheel
```

The same day carried a second one, and it is the better story. A screen defect
was reported fixed, then reported fixed again, and it was not fixed either time.
Its tests searched the source file for words and found them. They could not see
that the words were wired to the wrong signal. The real repair came with six
tests that drove the widget, and those tests were deliberately broken first —
five of six failed with the exact symptom I had reported.

That is the difference between a test that proves something and a test that
agrees with the file it is reading.

## 2026-06-27 — twenty-seven days of nothing

No commit. No handoff. No audit. No runtime file. No dated comment. No artefact
of any kind falls inside it.

Twenty-seven consecutive days, the largest single blank in this record. Our own
record does explain where it went: the changelog for that period was moved into
an archive file during the 3.23 series and never replaced at the root, so the
releases after it shipped with that step skipped. That archived file was never
committed here. A history query for it across every branch returns nothing,
against the same query for a known file, which returns its commit.

Two engine version series, 3.21 and 3.22, appear nowhere in the tree. Not one
comment names either. They sit inside this blank.

## 2026-07-24 — the summer that lives in a commit

Everything from late July to mid-August survives in exactly one place: the first
commit. Inside it sits a folder of dated audit units, one per piece of work, and
it is the densest record of the whole pre-git period.

That folder has had a bad life. It was emptied on 26 August, restored on
27 August into a different directory, and lost again on 28 August inside two
merges that reconciled two branches. A plain delete query cannot see the second
loss, because the deletion happened in a merge.

Nineteen of those notes are in the tree today. The rest are still readable,
because the commit that holds them is an ancestor of the current branch.

```
git show fc0d7788:docs/engineering-notes/<name>
    115 notes at that commit, 19 in the tree, 102 absent
    25 of the absent files carry a July date — 24 notes and one screenshot
```

I have not restored them. They are recoverable, they are dated, and this
chronicle cites the commit rather than pretending the period is lost.

What that summer contains is the part of the project I am proudest of. Nine
audits in one day walking the wizard panels. Design proposals for settlement
across base currencies, the Market Inspector and the phantom bots. Fourteen
audits on 6 August, almost all of them defects in the tranche lifecycle.
Twenty-four releases on 7 August, each closing one numbered defect.

## 2026-08-01 — the archetypes

Three rules went in on one day, and they changed how everything after them got
built. A cited path that does not exist on disk. A placeholder shipped as
finished work. A duplicated block, an oversized function, a file nobody can
read.

Those three grew into four review archetypes — one for code, one for
arithmetic, one for the interface, one for documentation. An archetype is the
authority in its domain. It reports a verdict, and the verdict is not a delta
and not an opinion. This page you are reading was refused by the documentation
archetype until it passed.

```
dev_harness/harness/rules/hallucination.py   a citation that resolves to nothing
dev_harness/harness/rules/scaffolding.py     a stub shipped as if finished
dev_harness/harness/rules/slop.py            duplication, oversized functions
dev_harness/harness/docs_archetype.py        what judged this page
```

Two rules of mine landed on 9 August and reshaped the rest. One entity writes
arithmetic. One entity writes code, and it must check all of it adversarially.
The day after, a rule against wiring anything to dead code; the release that
followed deleted 457 lines and changed no behaviour at all.

## 2026-08-18 — four months arrive as one commit

650 files. 315,743 lines. 239 test files. Four archetypes already built. One
commit.

Nothing dated before 24 July shipped in that import, apart from three interface
backup files from June. The history that arrived is an upload log, not a
development history — there is nothing to bisect, nothing to blame, nothing to
revert to.

```
6e4f46b8   the import, and its twin be6aa048
git show 6e4f46b8:ver.txt   reads 3.25.5, three patches behind the module beside it
```

## 2026-08-22 — the first outside eyes

An outside audit filed issues 66 to 96. First review by anyone but me and the
machine I was building with.

Its first finding was the one above: the history offers no bisect, blame or
revert trail. It also found a fifteen-thousand-line engine file, an
eight-thousand-line window file, five hand-copied dependency lists with no
lockfile, a build that did not work, and committed backup copies sitting in the
source tree. Every one of those was true.

Three days later a second engineer reformatted 464 files and moved all testing
into the build service. That sweep also moved code anchors and emptied five test
modules, both repaired the same day. Ten days after that the build service hit a
billing wall and stopped running altogether, so a local replacement was written.

```
issue #66    git history is an upload log, not development history
issue #128   convert the interface from the old toolkit to React
issue #331   local build-service equivalent
```

## 2026-08-28 — the version restarts below one

First version tag in this project's life reads 0.1.0.

Four months of a private version ladder had already gone past three. Under git,
the number is derived from the tag rather than typed into a file, and the tag
started where a new project starts. I find that funny and I am leaving it in.

```
src/_version.py    derived from the git tag, or from a frozen build's baked value
ef105f55           the version stops being written and starts being derived
```

## 2026-09-06 — sixteen thousand seven hundred and eighty-eight tests

The suite reached 16,788 tests. Nobody could reason about it.

That is not a boast about coverage and it is not a complaint about slowness. It
is a structural failure. Measured across 529 test files, 485 defined their own
helpers and only 148 imported the shared ones. One helper name was rewritten in
72 separate files. Every rebuild rediscovered the same traps, and several of the
rebuilds were themselves broken.

Then we read what they actually asserted. 267 of them opened the source file of
the code under test and pattern-matched the text. 72 more carried
hand-maintained registries of constants copied out of the source. Those tests
cannot fail when the behaviour breaks, and they cannot survive a refactor that
moves a line. They pass while the product is wrong, which is worse than having
no test at all.

```
issue #411   222 of 525 test files assert on source text instead of behaviour
issue #330   three tests read source text and make comments load-bearing
05449360     the removal branch, not merged into origin/current
```

Verification moved to the debugger and the archetypes. A program runs, the
debugger reports what it did, and an archetype owns the verdict.

## 2026-09-07 — a known defect, written down and left there

This is the worst one, and it is the reason this chronicle is worth writing.

The exchange connector fetches candles. Its docstring carried the words KNOWN
DEFECT, followed by an accurate description of what was wrong. A comment two
lines below said live callers land here, with the positional quirk documented
above. Somebody found it, understood it, wrote it down correctly, and left it in
place.

Underneath that comment, the count of candles was being passed into the
library's start-time slot. That library filled the empty count slot with its own
ceiling and kept rows from the start of the venue page, dropping the fifty
newest. Every live indicator therefore read a candle window fifty five-minute
bars behind the price. Four hours and ten minutes stale, on all 38 running bots,
while the price beside it was five seconds old.

```
src/exchange/ccxt_connector.py   the docstring that named it and left it
docs/audits/2026-09-07_ta_window_lag.md
    141 of 141 recorded rows reproduce at an offset of -50 bars
    no other offset and no other timeframe fits better
b106df73   -50 bars on 1,215 pages before, 0 on 1,215 after
           the band latch differs on 88 of 162 recorded gate rows
```

Eighty-eight of a hundred and sixty-two decisions were made on the wrong
window. A comment is not a fix. Writing a defect down and shipping it is the
same as not knowing, except that it looks diligent.

## 2026-09-07 — the ninetieth percentile that was the maximum

An archive of simulation results arrived as source material for a new Simulator
mode, and it looked wrong to me. It was.

Underneath, a real trading loop. One pass per candle, buy and sell branches,
fees, a spread, a running ledger. Nobody typed the results in by hand. But the
prices that loop ran on came from nowhere real: a start price, a middle price
and an end price, joined by a smooth curve, with a random wiggle on every
candle. Three numbers producing a year of hourly data, 8,760 candles at a time.

Then the headline figure. Ten runs per configuration, sorted, and the ninetieth
percentile taken at index nine — the last item. At ten samples that index is
always the maximum. Every reported ninetieth percentile equals the largest run,
in 39 of 39 rows, across three separate reports.

```
docs/audits/2026-09-07_raintsimbat.md
    p90 = run_advs[min(n_runs-1, int(n_runs * 0.90))]
    39 of 39 rows: the ninetieth percentile equals the largest value
    all ten runs of a configuration share the same three anchor prices
```

All ten runs also shared those three anchors, so the spread between them
measured the random wiggle and not market risk. Nothing from that archive
entered this repository.

## 2026-09-08 — a producer that never read half its own manual

The manual you are holding is built by a tool that renders markdown into a PDF
and then checks its own output.

Its manifest reader walked one table and one directory level. Thirteen of the
manual's twenty-seven sections sat one level down, listed correctly in the
contents and never rendered. The producer validated every page it built and was
silent about the pages it never opened.

```
a8e7439c   269 pages to 346, 14 sections to 27
tools/build_product_manual.py   read_manifest now reads every table row
```

A check that only inspects what it already loaded is not a check. That is the
same shape as the tests above and the same shape as the docstring, three times
in three days, in three unrelated places.

## What the record does not hold

Six spans, sixty-one days, and here is what was looked at for each.

| Span | Days | What was looked at |
| ---- | ---: | ------------------ |
| 29 April to 5 May, 7 to 9 May, 11 to 18 May | 16 | Session chronicle and handoff both jump the span. Build archive ended 24 April. Two dated directives inside it, nothing else |
| 26 to 29 May | 4 | Absent from the archive histogram and the handoff entry series, between two dense weeks |
| 2, 3 and 7 June | 3 | Single days missing from an otherwise continuous run |
| 17 June, 19 to 25 June | 8 | Between two dated code comments, with nothing in between |
| 27 June to 23 July | 27 | Changelog moved to an archive file never committed here; the audit folders begin on 24 July |
| 29 July | 1 | One day between two dated audits |

The record also disagrees with itself in seven places, and I have not resolved
any of them. Picking a side would put an invented fact in a document whose only
claim is that it contains none.

Two are worth naming. One handoff states that an earlier handoff never existed;
that file is in the tree at 11,445 lines and was in the very first commit. And
the same handoff blames a size past 100 KB for killing the format, while the
file it names is 712 KB — six times the threshold it says was fatal.

Session numbers are not a clock either. One handoff runs through sessions 18 to
22, then 24, then 26, then jumps to 72, then returns to 26. Dates order this
record. Session numbers do not.

## What the mistakes bought

Read the entries above in order and the pattern is one thing, five times. A
check that agrees with the thing it is checking.

```
tests that read the source          agreed with the file, not the behaviour
a docstring naming a defect         described it correctly, changed nothing
a ninetieth percentile of ten       reported the maximum and called it a tail
ten runs on three anchor prices     measured the noise, not the market
a producer validating its own build never opened half the pages
```

Everything durable in this project came out of that pattern, not out of the
features. The archetypes exist because a green result was believed once too
often. The handoff exists because a session with no memory re-litigates settled
work. The rule that everything found is owned by whoever found it exists because
eleven failures were once triaged into one mine and ten pre-existing, and the
ten stayed broken.

I would rather ship a document that says sixty-one days are missing than one
that quietly fills them in. Filling them in is exactly the failure this whole
apparatus was built to catch.

## The thread underneath

The manual opens on a line of Latin, and it is not decoration.

> Turbator aequilibrii dissolvendus reformandusque.
>
> The disturber of the balance is to be dissolved and reformed.

That is *solve et coagula* — dissolve and recombine, the operation at the centre
of hermetic practice. It is also, precisely, what the engine does to a position.
Excess above the dollar target is dissolved into cash. Cash reforms into more of
the asset on the dip. Every completed turn of the cycle ends holding more than
it began with, and nothing about it requires knowing which way the price will
go next.

The competition tiers carry the same thread, and I chose them deliberately. Five
ranks, named for the stages of the Great Work.

| Tier | Stage | Supply |
| ---- | ----- | ------ |
| Harvest | Nigredo — the darkening | unlimited |
| Gold Fold | Albedo — the whitening | unlimited |
| Bear Slayer | Citrinitas — the solar dawn | 10,000 |
| Grand Accumulator | Rubedo — the great work | 1,000 |
| Ekthelius | Unio Mystica — return to the All | 21 ever |

```
src/competition/season_schedule.py    the five tiers and what earns each one
src/competition/trophy_generator.py   the stage, the motto and the colour
```

Twenty-one ever, and it takes a perfect score across every metric in a season.
Nobody has one. I would be surprised if anybody ever does, which is the point of
putting a ceiling on it.

The name at the top of that ladder is mine, and so is the one on the copyright
line of every source file. Acervator — one who heaps up. What the software does
is heap up, one dissolved and reformed position at a time, and this chronicle is
the record of how badly and how well we learned to do it.
