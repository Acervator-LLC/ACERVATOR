---
name: w5h
description: Who, What, Where, When, Why, How. Load before accepting any design directive as understood, and before dispatching a unit to build one. Six questions that find the gap before a unit falls into it. Invoke by name when the operator says W5H, deep inference, or asks what design gaps remain.
---

# W5H — Who, What, Where, When, Why, How

**A directive you can restate is not a directive you can build.**

Operator, 2026-09-10, naming this skill:

> "What happens after a player enters a dungeon? These are the sorts of design
>  questions I want you to ask while proceeding. Who. What Where. When. Why.
>  How."

And the rule it serves:

> "Its all about identifying the gaps BEFORE we fall in them."

## Why this exists

A long design arc produced, measured in one day: **10,717 lines of machinery and
nothing a player would recognise as a game.** Nine content gaps were found only
when the operator asked. Four seams — a missing fee, absent controls, an absent
guild roster, an unset emission figure — were each found by a unit doing
something else.

**Every one of them is a W5H question nobody asked.** Not a hard question. An
unasked one.

## THE SIX QUESTIONS, EACH WITH THE FAILURE IT CATCHES

Ask all six of any directive before building it. **Each one below has already
caught a real defect in this project**, which is why there are six rather than a
tidy three.

### WHO acts, and who is affected?

```
catches   an action with no actor, and an actor with no permission
measured  a payout could be pressed by anyone before any participant had a
          score. It stamped the event settled FOR EVER, paid nobody, and
          permanently denied every participant who later earned a share
```

Also ask: **who is told?** A thing that completes while nobody is looking needs
a reader, or it completes invisibly.

### WHAT changes, and what does it carry?

```
catches   a record that lacks the field its consumer needs
measured  Quintessence distils from a certified fee, and a fill carried NO FEE.
          1,709 real trades read zero. Every earning mechanism was built and
          nothing could earn
```

Also ask: **what does this read that nothing writes, and what does it write that
nothing reads?** Those two questions are the whole of the seam audit, asked while
the code is still in your head.

### WHERE does it live, and where is it seen?

```
catches   a mechanism with no surface, and a surface with no source
measured  FIVE separate units each reported that their mechanism worked and
          nothing on a screen could start it — no control for a transfer, a
          spend, a payout, a drop, or a season
```

A mechanism nobody can reach is indistinguishable from one that does not exist.

### WHEN does it happen, and what if it does not?

```
catches   a missing clock, a missing timeout, and an unhandled absence
measured  a turn's rules were built and each refusal had to be driven
          separately — a missed window losing its actions, a midturn entrant
          getting no fresh timer, a pool expiring unspent
```

Also ask: **which clock?** This design has two — a one-hour world turn and a
one-to-five-minute event turn — and a feature that does not name its clock has
not been designed.

### WHY would anyone do it, and why would they abuse it?

```
catches   a feature nobody wants, and a feature everybody exploits
measured  the greedy extraction strategy drives world alignment into
          Destruction, and the cataclysms that follow are the bill. That was a
          CONSEQUENCE of an existing rule, found by asking why rather than by
          building anything
```

The abuse half is the valuable one. **Ask what the cheapest way to win is**, and
whether the design survives it.

### HOW is it reached, and how does it fail?

```
catches   dead code, and a happy path with no unhappy one
measured  start_listening had no caller anywhere. eligible_pool and open_window
          had none. pick_class had none until a later unit wired it
```

Also ask: **how is it proved?** A directive whose success cannot be observed
cannot be reported honestly.

## THE SEVENTH QUESTION, WHICH IS NOT A W

**HOW MUCH?** Every design figure is either measured, decided by the operator, or
invented — and the third is a defect.

```
measured  the figure came from running something and reading what it said
decided   the operator named it, and it is quoted
invented  a number sits in code that nobody chose
```

Measured, 2026-09-10: an activation refuses because **no emission figure exists**,
and the unit correctly declined to default one. A number nobody chose becomes the
answer, and nobody ever revisits it.

## WHEN A QUESTION HAS NO ANSWER, THAT IS THE DELIVERABLE

**Do not fill a gap to look complete.** The answer "nothing provides this, and
unit N would" is worth more than an invented mechanism, because the first is
actionable and the second has to be unpicked.

```
right   "no control starts a transfer; unit 15 owns it"
wrong   a control that appears to work and writes nothing
```

**A placeholder must look like one.** A screen saying "nothing builds armour,
weapons, accessories, consumables" is a correct answer to WHERE. An empty frame
is a lie.

## HOW TO USE IT WITHOUT DROWNING IN IT

**Six questions per directive, answered in a line each.** Not an essay. Most
answers are a sentence and four of the six are usually already settled by
something built.

```
cheap     asking all six of a directive, once, before dispatch
expensive a unit that builds the wrong thing because WHERE was never asked
```

**The questions go in the brief**, so the unit inherits the answers rather than
re-deriving them — and where an answer is unknown, the brief says so and tells
the unit to stop on it rather than invent.

**Run it on the operator's words, not on your restatement.** A paraphrase has
already lost the ambiguity that W5H exists to find.

## It also reads backwards, over what is already built

The six questions work as an audit of finished work, and the four seam shapes
fall straight out of them:

```
built but uncalled        HOW is it reached
reads what nobody writes  WHAT does it carry
writes what nobody reads  WHO is told
agrees with nobody        HOW MUCH, asked twice in two modules
```

That last one is the most dangerous. Measured, 2026-09-10: **a season budget
curve existed in two modules and the copies disagreed by one** — 361,249 against
361,250 — on a figure that an immutable contract and the platform must agree on
for ever.

## Falsification

This skill is wrong if six questions asked of a directive surface nothing a
builder did not already know, across ten directives. Then it is ceremony and it
should be cut to the ones that earn their place.

It is also wrong if it becomes a document rather than six lines. The measured
failure it exists to prevent was an unasked question, not an under-documented
one.

Related: `ocir`, `reachability-first`, `found-it-own-it`, `widest-true-reading`.
