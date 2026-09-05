# The Development Chronicle

Explanation. This is the engineering history of Acervator, written in the first
person by the assistant that typed most of the code. That claim is checkable
like everything else here: 680 of the 790 commits on this branch carry a Claude
co-author trailer. The chronicle runs from the first working bot in April 2026
to the tree as it stands on 5 September 2026, and every episode below names a
commit, an issue, a tag or a file, so a reader can check it against the
repository instead of taking it on trust.

One fact shapes the rest. The platform is four months old and its git history is
nineteen days long. Almost all of the invention happened where no version
control was watching. The repository is not the record of the work. It is the
record of what happened once the work became checkable, and the difference
between those two things is most of this story.

```
11 April 2026      first session in the archived chronicle
9 June 2026        last session in it, at v3.23.3
4 August 2026      the narrative version log picks up, at 3.24.83
18 August 2026     first commit: 650 files, 470 Python, 315,743 lines
5 September 2026   branch tip: 790 non-merge commits, 205 issues
```

## April to June: 127 sessions and no diffs

The oldest record the repository holds is one it inherited rather than produced.
It is a session-by-session summary of the build, 18,814 lines long, and it sits
in the tree at
[DEVELOPMENT_CHRONICLE.md](../../docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md).

It counts 127 sessions between 11 April and 9 June 2026 and carries the version
from v1.0 to v3.23.3. The first session conceives the strategy, designs a
seven-indicator voting engine and builds a desktop window, all in one sitting.
The second connects Coinbase and spends most of its length on key
authentication. By the fifth day the platform has its name.

What the file does not contain is a single diff. Every entry is a summary of a
conversation. Nothing in it can be checked against anything else in it, and for
two months that was the entire written history of the product.

```
sessions            127, from 11 April to 9 June 2026
versions            v1.0 to v3.23.3
lines               18,814
commits covering    0
```

## June to August: a version log that skipped itself

The next record starts on 4 August 2026 and is also tracked, at
[CHANGELOG-narrative-2026-08-04-to-2026-08-25.md](../../docs-archive/llm-session-history/CHANGELOG-narrative-2026-08-04-to-2026-08-25.md).
It holds 121 version headings and carries the number from 3.24.83 to 3.27.0 in
twenty-one days. That is roughly six releases a day.

Its own opening paragraph is the interesting part. The changelog that preceded
it had been moved into an archive folder during the 3.23 series and never
replaced at the repository root. The whole 3.24 series therefore shipped with
the changelog step of the documented release sequence silently skipped, and
nobody noticed until somebody went looking for the file. A step that produces
no artefact when it is missed is a process step that will be missed.

Between 9 June and 4 August there is nothing. No commits, no sessions, no
version entries. Roughly eight weeks of the platform's life left no record in
this tree at all.

```
narrative log     4 to 25 August 2026, 121 version headings
version span      3.24.83 to 3.27.0
gap before it     9 June to 4 August 2026, no tracked record
```

## 18 August: the upload

Git history begins with two commits. They carry the same subject, the same date
and the same 650 files, and they have no common ancestor with each other. The
tree arrived as a snapshot, twice.

Three hundred and fifteen thousand lines landed in a single act. No diff, no
review, no test run that anyone could point to afterwards. Four months of
invention became a starting state, and every belief the code held about itself
came with it, unexamined.

An issue filed four days later says so in its title. Issue 66, 22 August: "Git
history is an upload log, not development history".

```
6e4f46b   18 Aug 2026   initial upload   650 files, 470 Python, +315,743
be6aa04   18 Aug 2026   initial upload   the second root, no shared ancestor
```

## 19 to 22 August: reading it for the first time

The first week was mostly reading. Fifty-eight issues went up between 19 and
22 August, and the shape of the codebase came out fast.

Two files carried most of the platform. The trading brain ran to 15,220 lines
with a single method of 4,508 lines inside it, filed as issue 71. The main
window ran to 8,243 lines with fourteen widget classes nested inside it, filed
as issue 72. A method that long cannot be reasoned about, and nothing had ever
forced anybody to try.

Then a smaller finding that set the tone for everything after. A postcondition
check inside the bot compared a value to itself:

```python
actual=round(float(_qty), 10),
expected=round(float(_qty), 10),
```

It claimed to assert that a capital reservation granted the quantity requested.
It compared the request to the request. Its result was true on every call, on
every bot, on every tick, from the day it shipped. That is issue 21, and it
named the pattern the rest of this chronicle keeps running into: a check that
cannot fail is not a weak check, it is a decoration.

## 23 to 25 August: three gates that could not refuse

An audit of the voting engine went looking for how often a confidence gate
changed a decision. It found that one of them never could.

The Bollinger-priority arm adds 0.30 to effective confidence. The technical
analysis confidence floor is 0.25. On that arm the test becomes a comparison
against a negative number, and confidence is bounded at zero and one, so no
reading exists that the floor can refuse.

```
    conf + 0.30 >= 0.25      which is      conf >= -0.05
```

That is issue 102. Two more boosts turned out to have the same shape, filed as
issue 104. None of the three was found by looking for it. All three fell out of
an instrument being calibrated for a different question, which is the honest
version of how most of these were found.

The same week produced three more of the same family: a moving average that
back-filled twenty-five invented values so the signal line was wrong on a short
tape (issue 99), an abstaining voter whose full weight still counted in the
consensus denominator (issue 100), and a growth cap computed from the anchor at
four separate sites so it never compounded (issue 106). A seventh, issue 97,
was visible on screen: a rebuy price that omitted the trading fee, showing six
false greens on the operator's monitor while somebody wrote it up.

## 24 August: the nine-month green

The Simulator produced no initialised bot and no trade for roughly nine months.
The test suite was green for all of them.

The reason is worth the space. No test in the suite asserted that a replay fires
a trade. The trade counter was only ever asserted equal to zero, on a fresh
progress object. A Simulator with nothing running and a Simulator working
perfectly therefore produced identical test results, and the suite reported the
dead one as a pass.

A separate instrument made the same mistake independently. It reported one
hundred bots worked out of one hundred entered, on a replay in which not one bot
had initialised. After the repair the same instrument reports two.

```
before   worked=100 of entered=100, worked_pct=100.0
after    worked=2, throttled=98
```

That is issue 109. Its lesson is a sentence I now apply everywhere: a negative
assertion fails green. "No error was logged", "the counter stayed at zero" and
"the tripwire stayed silent" are all satisfied by a subject that is dead.

## 25 August: the rejoin, and a scrub that swung too hard

Two histories with no common ancestor had to become one branch. The tag
`pre-rejoin-backup` marks where that started, and ten commits carry the join.
It was messy in a specific way: a formatter had run on one side and moved code
that the other side's tests anchored to, so the merge had to tell a real edit
apart from a reflow.

The same day, a scrub went through the tree removing machine paths and personal
information. It deleted 23,010 lines across 26 files. A restore commit put a
large part of that back, and its message carries the measurement that justified
the reversal: the scrub had deleted 18,814 lines in order to remove what
measured as two email addresses and zero machine paths.

That is the whole argument for measuring before you swing, and it happened on a
day when everyone involved believed they were being careful.

```
39cb519   25 Aug 2026   pre-rejoin-backup, the tag before the join
566a5a1   25 Aug 2026   black over the divergence point, 480 files
d935ddc   25 Aug 2026   scrub machine paths and user info, -23,010
032ba3c   25 Aug 2026   restore the chronicle the scrub deleted whole
```

## 26 to 27 August: the demolition

The largest single deletion in the history is the documentation folder, and the
operator wrote its commit message himself.

```
c932a06   26 Aug 2026   remove everything from the docs folder   -59,156

    Everything in the docs folder was some sort of hallucinated pseudo git
    history. It had no value, just noise. The current state of the
    application should be used to build docs
```

That sentence is the standard this manual is written against, and this part in
particular. A page that reconstructs a history nobody can check is worse than an
empty page, because it looks like evidence.

Three more removals followed the same logic, two of them earlier in the same
week. Four committed backup copies of source files went out at 12,479 lines. The
review harness moved off the product import path entirely, so no shipped module
could reach it. A homegrown tracking system that duplicated what git already did
went out at 33,372 lines.

Then the god files came apart. The trading brain lost its state serialiser, its
execution, fold and reconciliation engines, and finally had its long method
decomposed into thirteen phase methods. The main window had its fourteen nested
widget classes lifted out, and its settings dialog split into one module per
tab.

```
src/trading/scrumming_bot.py   15,220 lines on 18 Aug   5,010 today
src/gui/main_window.py          8,243 lines on 18 Aug   3,548 today
```

## 27 to 28 August: the version number that went backwards

The version had been a literal typed into more than one file, and the files
disagreed. Issue 70 counted four sources that did not match, and one of them had
the wrong project name in it.

The repair replaced the literal with a resolver. A source checkout answers from
the nearest git tag. A frozen bundle carries no repository, so the build stamps
a value into the package and the resolver reads that instead. Anything that is
not sitting exactly on a tag, unmodified, reports a local segment after a plus
sign, so a built copy can never quietly claim to be a release.

The visible consequence was that the version went backwards. The narrative log
had reached 3.27.0 by hand. The first real tag is v0.1.0, three days later.

```
ef105f5   27 Aug 2026   derive the version from git and bake it into the build
v0.1.0    28 Aug 2026
v0.2.0     3 Sep 2026
```

## The suppressions, and why one green says nothing about another

A lint suppression is a comment that tells a checker to ignore a line. They lie
in three ways, and this tree had all three.

The first is a formatter. When it wraps a long line into a parenthesised form,
the trailing comment travels to the closing bracket, and the checker attributes
the finding to a different line. The marker survives every text search and
silences nothing. Run one checker twice on the same file, once honouring markers
and once ignoring them, and the gap shows:

```
ruff --isolated --select S110 <file>                  ->   2 errors
ruff --isolated --select S110 --ignore-noqa <file>    ->  14 errors
```

Twelve of those markers bind. Two are dead, and the two dead ones are exactly
the findings that make the file fail its review. That is issue 243.

The second is a rule that is switched off somewhere else. Issue 402 counts 339
markers for an import-order rule that the project configuration ignores
globally, so they suppress nothing where they sit and nobody can tell by looking.

The third is the reverse, and it is the dangerous one. Issue 325 records a
marker that had never fired, sitting above a bare catch-and-discard. When the
rule set changed, the marker started working, and it silenced a real finding on
the way past.

The rule that came out of this is short. Delete the marker, run the checker
again, compare the findings. Nothing else proves one. Commit `791c4dc` is a
marker that did not survive that test: it sat on a closing bracket, the checker
reported the opening line, and it had never suppressed anything.

## 29 August to 5 September: converting the interface, by measurement

Acervator is moving its desktop interface from the Qt widget toolkit to React,
filed as issue 128. Sixty-six commits carry that number and they touch 274
files.

The method is what makes it checkable. Each screen first gets a plain Python
object that describes what the screen shows, with no toolkit imported. A React
module then reads that description. A test can drive the description without
opening a window, and compare the two halves without a screenshot.

Progress comes off a tool rather than out of a claim, and the tool carries its
own control: three names known to be converted must report as paired, and they
do.

```
renderer modules the page loads : 75
bridge methods a module speaks  : 67
src/gui .py importing PySide6   : 69
  paired, a React module serves it : 63
  not a screen, Qt plumbing        : 5
  UNPAIRED, the work that is left  : 1
```

The conversion also worked as a defect finder, because rewriting a screen forces
somebody to read what it actually does. One commit repaired nine defects found
while converting the bot creation wizard. Another repaired four found in the
opacity driver. Nobody went looking for either set.

## 3 to 5 September: reading every comment in the tree

Issue 319 asks a narrow question: does every comment in the tree state something
true? Eighty-seven commits carry its number, they touch 429 files, and they
delete about two and a half lines for every line they add.

Its yield was not tidier prose. Reading a comment against the code beneath it
forces a comparison that nothing else forces, and the comparison kept failing on
the code rather than the comment.

```
aa74c8f   TradeJournal.verify recomputes the hash chain, it did not
2f99732   Wilder RS divides by avg_loss, not avg_loss plus an epsilon
ba50496   remove every committed machine path
```

The first was a journal verifier that could not report tampering, because it
recomputed the chain it was supposed to be checking. The second was a small
constant added to a denominator to avoid dividing by zero. At a four-figure
price it is invisible. At the prices several of these bots actually trade it is
large enough to move the indicator, and the same shape was later found across
the whole indicator family as issue 399.

One commit in the sweep deleted 2,256 lines across 120 files and inserted none.
To prove a change like that, parse each file before and after, strip every bare
string at every depth, and compare the syntax trees. The program comes out
identical or the change does not land.

## 4 September: pointing the instruments at themselves

This was the least comfortable day in the history and the most productive.

The release gate is the check that everything else defers to. Nothing may claim
to be ready until it prints its approval. Applying the fixture rule to the gate
itself — score a known-good body and a known-bad body before trusting any
verdict — found that all three of its known-good constants name a directory the
tree does not hold. The fixtures live somewhere else entirely.

```
harness_fixtures/coding_archetype/known_good.py
harness_fixtures/gui_archetype/known_good_widget.py
harness_fixtures/docs_archetype/known_good.md
```

The gate cannot report ready at all. That is issue 416, and it is open.

Two neighbours failed the same way. One archetype rule had a known-bad fixture
that exits zero, so the rule had no two-sided control and nothing could make it
fail (issue 401). A version sweep carried five checks reading paths that never
existed in any commit, so those five could not fail either (issue 403).

Then the tests. Issue 411 counts 222 of 525 test files asserting on the text of
the source rather than on behaviour. Those tests pass while the behaviour is
broken and fail on any refactor that moves a line, which makes them worse than
absent, because a coverage count includes them. Twenty-seven commits have so far
converted them to drive the real object and read the result.

## Two defects worth the whole audit

The first is a single configuration key read at nine places that do not agree on
what to do when it is missing. Three fall back to zero, six fall back to one.
The two values are not near each other; they name opposite policies. Zero
freezes the target at its anchor. One grows it by a percent of anchor per cycle,
and the operator-facing label says exactly that.

One site writes both at once, so an absent key gives one policy and a stored
zero gives the other.

```
src/trading/scrumming/execution.py     0.0  and  1.0
src/trading/scrumming/snapshots.py     0.0
src/trading/scrumming/tick_phases.py   1.0  and  1.0
src/trading/scrumming_bot.py           0.0, 1.0, 1.0, 1.0
```

That is issue 409. Nothing in the tree held the nine reads together, so they
drifted one edit at a time and each one looked reasonable on its own.

The second is a guard that stands down at the moment it matters. Before a sell,
the execution path asks the capital registry how much of the asset this bot may
actually claim, and refuses the order if the amount exceeds it. When no registry
is attached, the lookup raises, and the handler catches the exception and lets
the sell proceed.

Every construction site that builds a bot was then listed. Only the two
Simulator sites pass a registry. The path that rebuilds the live fleet passes
none. The guard therefore runs where the money is fake and fails open where the
money is real. That is issue 427.

## Where the work stands, 5 September 2026

The report, in one place. Nineteen days of history, and the tree roughly doubled
in file count while its two largest files each lost more than half their length.

```
commits (non-merge)     790          18 Aug to 5 Sep 2026
insertions              1,501,127
deletions               392,852
tracked files           650 -> 1,184
Python files            470 ->   972
test modules            239 ->   554
issues                  205 filed, 59 closed, 146 open
pull requests           234 merged
version tags            v0.1.0, v0.2.0
```

Two rows in that table need reading carefully. The closures are not spread
evenly: 49 of the 59 landed on 1 September alone. And the merged pull request
count is not a quality signal here, because the continuous integration meant to
gate them stopped running. Issue 152 records that the workflow was advisory and
nothing enforced it, and the lanes now run from a local script instead.

The instruments cost real time and I would rather say so than imply the
discipline is free. The code review that runs on every file write takes twelve
seconds on the largest trading module. The comment audit has consumed
eighty-seven commits and is still open. Five review archetypes exist; four of
them carry the known-good and known-bad fixture pair that makes their verdicts
mean anything.

## Two repairs the repository cannot show you

Both of these are real, both are visible in the tree today, and neither has a
commit here, because both landed before 18 August. They are the clearest example
of what this part keeps saying.

One configuration class served two bot modes, and the two modes read two of its
fields in opposite senses. For one mode the base currency is what the bot spends
and the target asset is a single ticker. For the other the base currency is what
the bot accumulates and the target asset is a pool marker. The same field name
meant opposite things, so a bot could take a configuration that looked coherent
and behave as the other mode entirely. A screenshot found it: a bot rendering
the wrong symbols beside the wrong balance.

The repair was structural rather than local: a typed factory with one field
manifest per mode, every construction site moved onto it, and direct
construction banned by a test.

```python
def make_bot_config(mode, **kwargs) -> BotConfig:
    if not isinstance(mode, BotMode):
        raise TypeError(...)
    kwargs = _sanitize_deprecated_kwargs(kwargs)
    foreign: list = []
    if mode == BotMode.EXTRACTOR:
        for key in kwargs:
            if key in _BOT_CONFIG_SCRUMMING_ONLY_FIELDS:
                foreign.append(key)
```

The second is a coverage test. Two regime gates had shipped in consecutive
releases and neither did anything, because both read a field from the tick
context that the tick never filled. Both saw a zero sentinel and passed every
time. The wiring fix was one line. The part worth keeping was the test that
followed it, which enumerates every gate class, every chain construction site
and every voter, and asserts each one is reached. It lives at
[test_gate_coverage.py](../../tests/test_gate_coverage.py).

## What the record cannot show

Some things named in the earlier records have no trace here at all. The query is
the same in every case: list every path any commit on any branch ever added,
deleted or renamed, and look for the name.

The query returns 1,626 distinct paths, and it returns one for the main trading
module, so it works. For these it returns nothing.

```
RAIntSimBat, a batch simulation runner        0 paths
a protocol tree named sadp                    0 paths
Spectre, in any Python file in any commit     0 paths
the fourteen manual builder scripts           0 paths
```

The last row is the sharpest, because it is not a phantom. The fourteen original
manual documents exist, 479 pages of them, and something built them. No commit
here ever added that something. The same shape has a live issue against this
manual: the 39 charts in Part 9 are embedded as images with no producer in the
tree, so a clean checkout cannot rebuild them. That is issue 431.

A matching case sits inside the code. The protocol section of the original
manual described 77 rules, counted in
[manual-original-parts-audit.md](../audits/manual-original-parts-audit.md). The
rule registry in the tree defines 35, and of the identifiers that appear in
both, not one describes the same rule.

That is the argument of this part in one line. A thing can be entirely real and
still leave nothing a reader can check, and the only way to tell the two cases
apart is to look.
