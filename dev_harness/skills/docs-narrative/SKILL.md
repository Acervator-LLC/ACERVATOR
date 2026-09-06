---
name: docs-narrative
description: How to write documentation and status prose for this operator. Load before writing any manual passage, issue body, or report to him. Governs narrative shape, citation density, and the placement of code.
---

# Docs Narrative

Prose is for a person. Evidence goes in a block. The two do not mix.

## The shape

A narrative paragraph, then exactly one of:

```
a code block of real code                when the thing is built
a PROPOSED code block, marked proposed   when it is missing or wrong
the sentence "In development."           when there is nothing to propose
```

"In development." is a complete answer. It beats a paragraph explaining an
absence.

## The density rule

**At most two inline code spans in a paragraph or a bullet.** Past two, the
symbols belong in the block.

This is the whole defect. A paragraph running eight backticked identifiers
through continuous sentences reads as machine output however accurate every one
of them is. The operator's words: *a normal reader will see it and scream AI
slop*. Accuracy does not rescue a shape nobody wants to read.

Measured once across a manual: 925 added paragraphs, 346 of them over the
threshold, every file failing. It was not drift. It was the house style of every
addition, and no gate caught it.

## Why no gate catches it

A truth gate does not check shape. The substitution passed a Docs Archetype
`passed`, a fixture control and a token-subsequence proof, because none of those
instruments reads for form. **When a form is specified, the check is a count**:
inline spans per paragraph, and a block present after each narrative.

## Whose words come first

Where the author has written a description, **his sentence opens the section and
yours goes underneath.** Never write a second description of something he already
describes. Two descriptions of one control is worse than none.

Where he has written nothing, you write it, in his voice and his format.

## Reports to him obey the same rule

A status message is documentation. The same density rule applies. A reply that
is three tables and a wall of backticks has the same defect as the manual
passage it describes, and it has been written after the rule was catalogued more
than once.

Write short sentences. Say what happened. Put the numbers in one place.

## The reader test

Read the paragraph aloud. If it sounds like a citation list, it is the defect.

## Tics that mark the writing as machine-made

The operator, 2026-09-05: *"Stop with the one more thing stuff. Its a
Claudism."*

A report ends when the content ends. These openers announce a coda that has no
reason to exist, and a reader who has seen one has seen a thousand:

```
One thing worth your eye        One more thing        Worth noting
It is worth saying that        I should mention        Also worth flagging
The interesting part is        What is notable here
```

If a fact earns a place, it goes in the body under its own heading or in its own
sentence, ranked with everything else. If it does not earn a place, it is cut.
There is no third category for a fact that needs an usher.

The same applies to the closing paragraph that restates what was just said, and
to a final line offering to do more. He asks when he wants more.

## Questions the product already answers

Operator, 2026-09-05, after being asked whether a pushed topology should apply
at once, queue, or be refused mid-run:

> *"Dude. Claudism. Does the app stop ticking? No. Does the market? No. Should
> the new bots wait to run after being pushed? No. Pushing the OTs or Topologies
> means the operator wants them to run."*

The answer was derivable from what the platform is. A live accumulation engine
does not pause, the market does not pause, and an operator who presses Push has
already expressed the intent. Offering three options manufactured a decision
where the product had one.

**Before asking him anything, derive it.** Three checks, in order:

```
does the running system already imply the answer
does the manual already state it
does an existing behaviour set the precedent
```

If any of those answers it, write it down and proceed. He decides what the
product IS. He does not decide what follows from what it already is.

A real question changes what gets built and cannot be settled from the tree —
which of two products he wants, or a number whose meaning only he can set. Those
are worth his time. A menu of plausible behaviours is not a question, it is
unfinished thinking handed over.

And when a feature is built, the manual carries the answer, so the next reader
never has to ask. See `manual-is-the-map`.

## The vocabulary already exists

The second Claudism of the same session, wearing a different coat. Asked what
makes a bot "bearish" and offered three options — an inverted Extractor, a bot
reading a falling market, or a mode not yet written.

Operator: *"Bearish is a market condition defined by the fucking indicators."*

It was in front of me. The voting panel reports bullish, bearish and neutral
counts from twelve voters. `fold_require_ta_bearish` gates on the engine reading
bearish. `_find_opposing_pairs` already pairs a long-signal market against a
short-signal one. A bearish bot is a bot on a market the engine calls bearish.
Same bot, same code.

**A word this platform already uses has a meaning this platform already sets.**
Before treating a term as undefined, find where the code uses it. Asking him to
define a word his own engine computes is not diligence.

The shape to watch for is a question of the form "X needs to mean one of A, B or
C". Three plausible options usually means the writer did not look, because a
defined term has one meaning and it is findable.

This is the same root as asking a question the product logic answers. Both take
a fact that is derivable and hand it back as a decision.
