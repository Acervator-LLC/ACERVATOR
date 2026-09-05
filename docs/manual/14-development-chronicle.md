# The Development Chronicle

Explanation. This is the engineering history of Acervator, told in the first
person by the assistant that typed most of the code. Git records a second author
on a change by writing a co-author line at the foot of the commit message, and
688 of the 798 commits on this branch carry mine. That first sentence is
checkable, like every other claim here. Each one names a commit, an issue
number, a tag or a file, and a reader who does not trust me can go and look.

One fact shapes the rest. The platform is four months old. Its git history is
nineteen days long. Almost all of the invention happened where no version
control was watching, so this repository is not the record of the work. It is
the record of what happened once the work became checkable, and the gap between
those two things is most of the story.

```
11 April 2026      the oldest session in the archived record
22 May 2026        the last session record in it
9 June 2026        the last version entry in it, at v3.23.1
4 August 2026      a second archived record picks up
18 August 2026     the first commit: 650 files, 470 Python, 315,743 lines
5 September 2026   the branch tip: 798 commits, 206 issues
```

## April and May: 127 sessions, and not one diff

The oldest record here is one the repository inherited rather than produced. It
is a session-by-session summary of the build, 18,814 lines long, and it sits at
[DEVELOPMENT_CHRONICLE.md](../../docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md).
A session is one sitting at the keyboard. A session record is a paragraph
written afterwards saying what that sitting did.

It holds 127 of them. The first, dated 11 April, conceives the strategy, designs
a voting engine of seven indicators and builds a desktop window, all in one go.
The second connects the Coinbase exchange and spends most of its length fighting
key authentication. By the fifth day the platform has its name.

What the file does not contain, anywhere, is a diff — the line-by-line record of
what a change actually altered. Without one, a summary cannot be checked against
the thing it summarises. For two months that file was the entire written history
of the product.

It cannot even be checked against itself. Its own header says seventeen sessions
covering 11 to 15 April. Count the session markers in the body and there are
127, running to 22 May. The header is wrong by a factor of seven about the file
it is attached to, which is a fair warning about everything underneath it. It
also directs the reader to the full transcripts, at a path that exists on no
machine anyone here can reach.

```
sessions recorded   127, dated 11 April to 22 May 2026
versions carried    v1.0 to v3.23.1
lines               18,814
commits covering    0
```

## June: the record thins out and then stops

After 22 May the session records stop and the file changes shape. It carries on
in a second form — fourteen dated version entries — and the last of those is
9 June 2026, at v3.23.1. That is where the archive ends.

Then eight weeks of nothing. Between 9 June and 4 August this repository holds
no commit, no session record and no version entry. The platform was being
worked on. Nothing here can say what happened to it.

## 4 to 25 August: the changelog nobody noticed had gone

The second archived record starts on 4 August, at
[CHANGELOG-narrative-2026-08-04-to-2026-08-25.md](../../docs-archive/llm-session-history/CHANGELOG-narrative-2026-08-04-to-2026-08-25.md).
It holds 77 version headings and carries the number from 3.24.19 to 3.27.0 in
twenty-one days, which is close to four releases a day.

Its opening paragraph is the interesting part. The changelog that came before it
had been moved into an archive folder during the 3.23 releases and never
replaced where the release procedure expected to find it. The whole 3.24 series
therefore shipped with the changelog step of that procedure silently skipped,
and nobody noticed until somebody went looking for the file. A step that
produces no artefact when it is missed is a step that will be missed.

```
narrative log     4 to 25 August 2026, 77 version headings
version span      3.24.19 to 3.27.0
gap before it     9 June to 4 August 2026, nothing tracked
```

## 18 August: the upload

Git history begins with two commits. They carry the same subject, the same date
and the same 650 files, and they have no ancestor in common. The tree arrived as
a snapshot, twice.

Three hundred and fifteen thousand lines landed in a single act. No diff, no
review, no test run anybody could point at afterwards. Four months of invention
became a starting state, and every belief the code held about itself came along
with it, unexamined.

An issue filed four days later says so in its title. Issue 66, on 22 August:
"Git history is an upload log, not development history".

```
6e4f46b   18 Aug 2026   initial upload   650 files, 470 Python, +315,743
be6aa04   18 Aug 2026   initial upload   the second root, sharing no ancestor
```

## 19 to 22 August: reading it for the first time

The first week was mostly reading. Fifty-eight issues went up between 19 and
22 August, and the shape of the code came out fast.

Two files carried most of the platform. The trading brain ran to 15,220 lines,
and one method inside it — the routine that runs once per price update — was
4,508 of them on its own. That is issue 71. The main window ran to 8,243 lines
with fourteen screen classes nested inside it, which is issue 72. A method that
long cannot be held in a head, and nothing had ever forced anybody to try.

Two pieces of tidying landed in the same days. Four backup copies of source
files had been committed alongside the originals, and went out at 12,479 lines.
The review tooling moved out of the folders the shipped application imports
from, so no running module could reach it.

Then a smaller finding, which set the tone for everything after it. Before a bot
sells, it asks a shared registry how much of the asset it is allowed to claim,
so two bots holding the same coin cannot both sell it. A check afterwards was
meant to confirm the registry granted what was asked for. It read like this:

```python
actual=round(float(_qty), 10),
expected=round(float(_qty), 10),
```

It compared the request with the request. It was true on every call, on every
bot, on every price update, from the day it shipped. That is issue 21, and it
named the pattern this chronicle keeps walking into. A check that cannot fail is
not a weak check. It is a decoration.

## 23 to 25 August: gates that could not say no

Acervator does not predict price. It sells the excess above a dollar target —
a scrum — and buys back a larger quantity on the dip, which is a fold. Whether
either fires is decided by a chain of gates. A gate is one yes-or-no test, and
every gate in the chain must say yes.

Several of those gates read a confidence figure, a number between zero and one
produced by a panel of indicators voting on direction. One gate refuses to trade
below a confidence of 0.25. On one branch of the code a bonus of 0.30 was added
to the confidence first, and only then compared against the floor.

```
    confidence + 0.30 >= 0.25      which is      confidence >= -0.05
```

Confidence cannot go below zero, so no reading existed that could fail. That is
issue 102. Two further bonuses turned out to have exactly the same shape, filed
as issue 104. None of the three was found by looking for them; all three fell
out of an instrument being set up for a different question, which is the honest
version of how most of these came to light.

The repair matters as much as the finding. The obvious fix is to subtract the
bonus from the floor instead of adding it to the reading, and that lands at or
below zero and is the same tautology again. What shipped divides the floor by
the bonus, so the arm now refuses anything under 0.192, and a confidence of
exactly zero is still refused however large the favour becomes.

The same week produced three more of the same family. A moving average was
starting from twenty-five invented values, so its signal line was wrong whenever
the price history was short (issue 99). A voter that had declined to vote still
had its full weight counted in the divisor of the consensus, quietly dragging
the result toward the middle (issue 100). And a cap on how far the dollar target
may grow was computed at four separate places, each from the original starting
figure, so it never compounded (issue 106).

The seventh was on screen while somebody was writing the others up. The panel
showing the minimum price at which a buy-back becomes worthwhile left the
exchange's trading fee out of the sum, so six rows were showing green that
should not have been. That is issue 97.

## 24 August: nine months of green over a dead Simulator

The Simulator replays recorded market data through the bots so a strategy can be
tried without money. For about nine months it produced no started bot and no
trade at all. The test suite was green for every one of those months.

The reason is worth the space. No test in the suite asserted that a replay fires
a trade. The trade counter was only ever checked as equal to zero, on a
freshly-made progress object. A Simulator with nothing running and a Simulator
working perfectly therefore produced identical test results, and the suite
reported the dead one as a pass.

A separate instrument made the same mistake by itself. It reported one hundred
bots worked out of one hundred entered, on a replay in which not one bot had
started. After the repair the same instrument reports two.

```
before   worked=100 of entered=100, worked_pct=100.0
after    worked=2, throttled=98
```

That is issue 109, and its lesson is one sentence I now apply everywhere. A
negative assertion fails green. "No error was logged", "the counter stayed at
zero" and "the alarm stayed silent" are all satisfied by a subject that is dead.

## 25 August: joining two histories, and a scrub that swung too hard

Two lines of development with no ancestor in common had to become one branch.
The tag `pre-rejoin-backup` marks the commit the join started from, and ten
commits carry it through to the release that closed it. It was awkward in a
specific way. An automatic formatter had run on one side and moved code that the
other side's tests pointed at, so every conflict had to be sorted into a real
edit or a reflow before it could be resolved.

The same day, a sweep went through the tree removing machine paths and personal
details. It deleted 23,010 lines across 26 files. A restore commit put most of
it back, and its message carries the measurement that justified the reversal:
the sweep had deleted 18,814 lines in order to remove what measured as two email
addresses and no machine paths at all.

That is the whole argument for measuring before swinging, and it happened on a
day when everybody involved believed they were being careful.

```
39cb519   25 Aug 2026   the tag the join started from
566a5a1   25 Aug 2026   the formatter over the divergence point, 480 files
d935ddc   25 Aug 2026   scrub machine paths and user info, -23,010
032ba3c   25 Aug 2026   restore the record the scrub had deleted whole
```

## 26 to 27 August: the demolition

The largest single deletion in this history is the documentation folder, and the
operator wrote its commit message himself.

```
c932a06   26 Aug 2026   remove everything from the docs folder   -59,156

    Everything in the docs folder was some sort of hallucinated pseudo git
    history. It had no value, just noise. The current state of the
    application should be used to build docs
```

That sentence is the standard this manual is written against, and this part in
particular. A page that reconstructs a history nobody can check is worse than a
blank page, because it looks like evidence.

One more removal followed the same logic. A homegrown system for tracking
changes, which recorded by hand what git already recorded by itself, went out at
33,372 lines.

Then the two big files came apart. The trading brain lost its state saving, its
order execution, its fold bookkeeping and its reconciliation with the exchange,
each into a module of its own. The long method was cut into thirteen phases,
named for what each one does, and is now a third of its old length. The main
window gave up its fourteen nested screen classes, and its settings dialog
became one module per tab.

```
src/trading/scrumming_bot.py   15,220 lines on 18 Aug   5,010 today
    its price-update method     4,508 lines on 18 Aug   1,636 today, in 13 parts
src/gui/main_window.py          8,243 lines on 18 Aug   3,548 today
```

## 27 to 28 August: the version number that went backwards

The version had been a literal typed into more than one file, and the files
disagreed with each other. Issue 70 counted four sources that did not match, and
one of them named the wrong project.

The repair replaced the literal with something that works it out. A source
checkout answers from the nearest git tag. A packaged build carries no
repository, so the build stamps the value into the package and the reader picks
it up from there. Anything not sitting exactly on a tag, with no local edits,
adds a suffix after a plus sign — so a built copy can never quietly claim to be
a release.

The visible consequence was that the version went backwards. The narrative log
had been typed up to 3.27.0 by hand. The first real tag is v0.1.0, three days
later.

```
ef105f5   27 Aug 2026   derive the version from git and bake it into the build
v0.1.0    28 Aug 2026
v0.2.0     3 Sep 2026
```

## 29 August onward: converting the interface by measurement

Acervator is moving its desktop interface from the Qt toolkit it was built on to
React. That is issue 128. Sixty-seven commits carry its number and they touch
276 files.

The method is what makes progress checkable rather than claimed. Each screen
first gets a plain Python object holding everything the screen displays, with no
toolkit imported at all. A React module then reads that object and draws it. A
test can drive the object without opening a window, and can compare the two
halves without taking a screenshot.

Progress comes off a tool rather than out of a report, and the tool carries its
own control: three names known to be converted must come back as paired, and
they do.

```
renderer modules the page loads : 75
bridge methods a module speaks  : 67
src/gui .py importing PySide6   : 69
  paired, a React module serves it : 63
  not a screen, Qt plumbing        : 5
  UNPAIRED, the work that is left  : 1
```

The conversion also worked as a defect finder, because rewriting a screen forces
somebody to read what it actually does. One commit repaired nine faults found
while converting the wizard that creates a bot. Another repaired four found in
the driver that pulses a widget's opacity. Nobody went looking for either set.

## 1 to 5 September: reading every comment in the tree

Issue 319 asks one narrow question. Does every comment in this tree state
something true? Eighty-nine commits carry its number, they touch 431 files, and
they delete more than two lines for every line they add.

The yield was not tidier prose. Reading a comment against the code beneath it
forces a comparison that nothing else forces, and the comparison kept failing on
the code rather than on the comment.

```
aa74c8f   TradeJournal.verify recomputes the hash chain, it did not
2f99732   Wilder RS divides by avg_loss, not avg_loss plus an epsilon
ba50496   remove every committed machine path
```

The first was a trade journal that could not report tampering. Each entry is
supposed to be sealed by a fingerprint of the one before it, so an altered entry
breaks the chain. The verifier recalculated the whole chain from the entries in
front of it, which means it agreed with whatever it was given.

The second was a very small number added to a divisor to avoid dividing by zero.
On an asset priced in thousands it is invisible. On the assets several of these
bots actually trade, some of them priced in millionths of a dollar, it is large
enough to move the indicator. The same shape was later found across the whole
indicator family, as issue 399.

One commit in the sweep deleted 2,256 lines across 120 files and inserted none.
Proving a change like that is safe means parsing each file before and after,
stripping every free-standing string at every depth, and comparing the syntax
trees. The program comes out identical or the change does not land.

## The suppression markers, and why one green says nothing about another

A suppression marker is a comment telling a code checker to ignore a line. They
lie in three ways, and this tree had all three.

The first is the formatter. When it wraps a long line into a bracketed form, the
trailing comment travels down to the closing bracket, and the checker attributes
the finding to a different line. The marker survives every text search and
silences nothing. Run one checker twice over the same file, once honouring
markers and once ignoring them, and the gap shows. That is issue 243.

The second is a rule switched off somewhere else. Issue 402 counted markers for
an import-order rule that the project configuration already ignores everywhere,
so they suppress nothing where they sit and nobody can tell by reading them.
Re-counted today there are 346, and 329 of those are in the test folder.

The third is the reverse, and it is the one worth watching. Issue 325 records a
marker that had never fired sitting above a silently discarded error. The
comment sweep shortened the prose on that line, which let the formatter pull the
statement back onto one line, which put the marker exactly where the checker
looks. It started working and silenced a real finding on the way past. Nobody
edited a line of running code to cause that.

The file that produced the original measurement now reads differently, and the
difference is the point. Two markers used to be dead; today all fourteen bind.

```
ruff --isolated --select S110 src/gui/main_window.py                  ->   0 errors
ruff --isolated --select S110 --ignore-noqa src/gui/main_window.py    ->  14 errors
```

The rule that came out of this is short. Delete the marker, run the checker
again, compare the findings. Nothing else proves one is doing anything.

## 4 September: pointing the instruments at themselves

This was the least comfortable day in the history and the most productive.

The release gate is the check everything else defers to — nothing may claim to
be ready until it prints its approval. It proves each reviewer works by scoring
a file known to be good and a file known to be bad before trusting any verdict.
Turning that rule on the gate itself found that all three of its known-good
paths name a folder this tree does not hold. The real fixtures live somewhere
else entirely.

```
the gate looks for   docs/audits/2026-07-24_.../fixtures/known_good.py
they actually live   harness_fixtures/coding_archetype/known_good.py
```

The gate cannot report ready at all. That is issue 416, and it is open.

Two neighbours failed the same way. One review rule had a known-bad file that
passes, so nothing could make that rule fail (issue 401). A version sweep
carried five checks reading paths that have never existed in any commit, so
those five could not fail either (issue 403).

Then the tests. Issue 411 counts 222 of 525 test files asserting on the text of
the source rather than on what the code does. Those tests pass while the
behaviour is broken and fail on any tidy-up that moves a line, which makes them
worse than absent, because a coverage figure counts them. Twenty-eight commits
have so far rewritten them to drive the real object and read the answer.

## Two defects worth the whole audit

The first is a single setting read at nine places that do not agree on what to
do when it is missing. Four fall back to zero and five fall back to one. The two
values are not near each other; they name opposite policies. Zero freezes the
dollar target where it started. One grows it by a percent of that figure every
cycle, and the label the operator reads says exactly that.

One of the nine manages both at once. An absent setting gives it one policy, and
a stored zero gives it the other.

```
src/trading/container/restore.py       1.0
src/trading/scrumming/execution.py     0.0  and  1.0
src/trading/scrumming/snapshots.py     0.0
src/trading/scrumming/tick_phases.py   1.0  and  1.0
src/trading/scrumming_bot.py           0.0, 1.0 or 0.0, 1.0
```

That is issue 409. Nothing in the tree held the nine reads together, so they
drifted one edit at a time and each edit looked reasonable on its own.

The second is a guard that stands aside at the moment it matters. Before a sell,
the code asks the shared registry how much of the asset this bot may claim, and
refuses the order if it wants more. When no registry has been attached the
lookup raises an error, and the handler catches it and lets the sell through.

Every place in the code that builds a bot was then listed. Only the two
Simulator ones attach a registry. The path that rebuilds the live fleet on
startup attaches none. The guard therefore runs where the money is fake and
stands aside where the money is real. That is issue 427, and the next guard in
the same function takes the opposite stance on the same kind of failure.

## Where the work stands, 5 September 2026

The report, in one place. Nineteen days of history, over which the tree nearly
doubled in file count while its two largest files each lost more than half their
length.

```
commits (excluding merges)   798          18 Aug to 5 Sep 2026
insertions                   1,503,977
deletions                    394,117
tracked files                650 -> 1,186
Python files                 470 ->   974
test modules                 239 ->   556
issues                       206 filed, 59 closed, 147 open
pull requests                234 merged
version tags                 v0.1.0, v0.2.0
```

Two rows there need reading carefully. The closures are not spread out: 49 of
the 59 landed on 1 September alone. And the merged pull request count is not a
quality signal here, because the automatic checking meant to gate those merges
stopped running. Issue 152 records that the workflow was advisory and nothing
enforced it, and the lanes now run from a script on the machine instead.

The instruments cost real time and I would rather say so than imply the
discipline is free. The code review that runs on every file write takes twelve
seconds on the largest trading module — measured, not estimated. The comment
audit has consumed eighty-nine commits and is still open. Five reviewers exist,
and four of them carry the known-good and known-bad pair that makes a verdict
mean anything.

## Two repairs this repository cannot show you

Both of these are real, both are visible in the tree today, and neither has a
commit here, because both landed before 18 August. They are the clearest example
of what this part keeps saying.

One configuration class served two kinds of bot, and the two kinds read two of
its fields in opposite senses. For one, the base currency is what the bot spends
and the target asset is a single ticker. For the other, the base currency is
what the bot accumulates and the target asset is a pool marker. The same field
name meant opposite things, so a bot could take a configuration that looked
perfectly coherent and behave as the other kind entirely. A screenshot found it:
a bot drawing the wrong symbols beside the wrong balance.

The repair was structural rather than local. One factory function builds every
configuration, it holds a separate list of legal fields per kind, and every site
that builds a bot was moved onto it. It is `make_bot_config`, in the container
config module. It refuses a field belonging to the other kind before it builds
anything, and re-raises whatever the shape check then reports on the finished
object.

```python
    if not isinstance(mode, BotMode):
        raise TypeError(
            f"make_bot_config(): mode must be BotMode enum, got "
            f"{type(mode).__name__}={mode!r}"
        )

    kwargs = _sanitize_deprecated_kwargs(kwargs)

    foreign: list = []
    if mode == BotMode.EXTRACTOR:
        for key in kwargs:
            if key in _BOT_CONFIG_SCRUMMING_ONLY_FIELDS:
                foreign.append(key)
    elif mode == BotMode.SCRUMMING:
        for key in kwargs:
            if key in _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS:
                foreign.append(key)
```

The second is a pair of gates that judge the market regime — one reading how
directional recent movement has been, the other how far the price sits from its
own average. Both shipped in consecutive releases and neither did anything,
because both read a value the price-update routine never filled in. Both saw a
zero, and both treat zero as "not measured yet" and pass. Two lines connected
them, and both are in the live chains today.

An earlier draft of this page went on to say that a test followed which
enumerates every gate class, every chain and every voter, and asserts each one
is reached. No such test exists. Nothing in this repository so much as names
either of those two gates. I wrote that sentence, it survived a review, and it
described a piece of software that would have been rather useful if anybody had
written it. It stands here as what should have followed the fix, which is a
different and much less flattering claim.

## What the record cannot show

Some things named in the earlier records leave no trace here at all. The query
is the same every time: list every path any commit on any branch ever added,
deleted or renamed, and look for the name.

The query returns 1,626 distinct paths. It returns one for the main trading
module, so it works. For these it returns nothing.

```
RAIntSimBat, a batch simulation runner        0 paths
Spectre, in any Python file in any commit     0 paths
the builders of the fourteen original PDFs    0 paths
```

The best of these is a whole subsystem. A protocol called SADP was documented in
the project configuration, in the front-page README and in the contributing
guide; two tools imported a module from it; and the README explained how to run
its test battery by invoking a script. No commit ever added the folder. No
commit ever added the script. Both tools raised an import error every time they
were run, which is the least ambiguous review any of this has ever received. The
tree today holds a test whose job is to stop those references coming back, at
[test_no_dead_sadp_references.py](../../tests/test_no_dead_sadp_references.py).

The last row of the block above is not a phantom, which makes it sharper. The
fourteen original manual documents exist, 479 pages of them, and something built
them. No commit here ever added that something. The same shape has a live issue
against this manual: the 39 charts in Part 9 are embedded as images with no
producer in the tree, so a clean checkout cannot rebuild them. That is issue
431, and it is open against me rather than against anybody else.

A matching case sits inside the code. The protocol section of the operator's
original manual described 77 rules, counted in
[manual-original-parts-audit.md](../audits/manual-original-parts-audit.md). The
rule registry in the tree defines 35, and of the identifiers that appear in
both, not one describes the same rule.

## A note on the two archived records

Both files quoted at the top of this part are kept, and neither is evidence for
how the software behaves. They are records of conversations, written without
diffs, and they cannot be checked against the code, against each other, or in
the older one's case against itself. Where one of them and the current code
disagree, the code is what is true and the record is what somebody believed on
the day. They are worth keeping for what they show about the shape of the work,
and for nothing else.

That is the argument of this part in one line. A thing can be entirely real and
still leave nothing a reader can check, and the only way to tell those two cases
apart is to go and look.
