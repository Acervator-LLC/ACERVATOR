---
name: truth-check
description: Run before any claim reaches the operator. Names what he cares about, names what was actually observed, and refuses to report the proxy as the thing.
---

# Truth check

**Every false report in this project had the same shape. I observed a proxy and
reported the thing.**

Not one was an invented fact. Each was a true measurement of something adjacent
to what he asked about, presented as an answer to what he asked about.

## The three questions, before any claim leaves

```
1  What does he care about?          state it in his words, from the item
2  What did I actually observe?      the command, the file, the number
3  Are those the same thing?         if not, report what I observed
```

Question 3 is the whole skill. When the answer is no, the claim is rewritten to
say what was measured and what it does not cover.

## The proxies that were reported as things

Every row measured in this project. Each read as success.

| reported | actually observed | the gap |
|---|---|---|
| "the React build" | an executable named `-react` | no runtime code reads the variant; both builds draw identical Qt |
| "63 of 64 converted" | a bridge method and a manifest entry | the manifest belongs to a shell that never ran |
| "the tab is converted" | a parity test comparing two descriptions | neither description has to be on screen |
| "the guard passes" | the guard printed a note | it stood down whenever the app was running |
| "the manual is in the tree" | a file on a branch | he was on a different branch |
| "no tokens missing" | a check whose sentinel sat in the file it measured | the control could not fire |
| "the emitters are healthy" | a spool of what did emit | it cannot show what stopped emitting |

## The tells

A claim is a proxy when it rests on any of these:

```
a NAME          a file, a flag, a variant, a label
a REGISTRY      a manifest, a declaration, a config entry
a COMPARISON    two descriptions agreeing with each other
a COUNT         of code written, rather than code reached
a GREEN         from an instrument whose red was never seen
```

None of those is behaviour. Behaviour is: the program ran and this happened.

## What passes

- **A runtime observation.** The object was constructed. The panel drew. The
  record was written. Name how it was seen.
- **A two-sided proof.** Red before, green after, both quoted.
- **An honest negative.** "I could not observe this, and here is the limit of my
  method" is a true report and outranks a green from a proxy.

## The sentence that must appear

For any claim of completion, one line, in his terms:

> **What does the operator see differently because of this?**

"Nothing yet" is a correct answer. It is only dangerous unsaid. This is OCIR R9,
and it went unasked through 39 units and 71 files.

## Where this bites hardest

**A label the work itself created.** The `-react` executable is the sharpest
case: the build flag named the file, and the file was then read as evidence that
the flag changed behaviour. The proof and the claim were the same artefact.

**A count of the wrong unit.** Files written, tests passing, modules paired —
all true, none of them the item. Count what the item names.

**A green nobody has watched fail.** See `two-sided-control` and OCIR C1 to C6.

## Falsification

This skill is wrong if a claim passing all three questions still misled him.
When that happens, add the row to the proxy table with its measurement.
