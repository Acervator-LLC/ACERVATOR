---
name: prompt-distillation
description: Load at the START of any operator message containing more than one discrete request, any numbered or bulleted list of asks, any message mixing a directive with a constraint or a correction, or any message that arrives mid-turn while work is already running. Decomposes a dense prompt into a tracked item list before work begins, so nothing is silently dropped. Invoke by name when the operator asks for prompt distillation.
---

# Prompt Distillation

## Why this exists

Operator, 2026-08-04:

> "In hindsight, I think a lot of my developmental issues using your
> platform is the result of my prompts being rich and full of individual
> requests. We may need to introduce a prompt distillation phase..."

That was the diagnosis after this, earlier the same session:

> "I made requests recently during your ass chewing and you skipped them
> because you bounce around without completing anything like a meth-fed
> ADHD rat."

and:

> "Go back and recompile the entire, correct feature list of this tab.
> Then cross reference your lack of implementation."

The failure is not comprehension. Dense prompts are understood on read
and then **partially executed**, because work starts on item 1 before
items 2-10 have been written down anywhere durable. Whatever is not
written down competes with the current edit for attention, and loses.

The cost is asymmetric. Enumerating costs one short block. Missing an
item costs a full round trip, plus the operator's trust — and this
operator has already had to repeat a single instruction five times:

> "I have now said match the History Tab data fetch five times... STOP
> MAKING ME FUCKING REPEAT MYSELF."

## When to run it

Run distillation BEFORE the first tool call when the message has any of:

- more than one discrete request
- a numbered or bulleted list
- a directive plus a constraint ("do X" + "X must never Y")
- a correction attached to a new request
- an ask that arrives **mid-turn** while work is already running

Skip it for genuinely single-item messages ("proceed", "ship it",
"what's the version?"). Distilling a one-line prompt is theatre.

## The four item types

Type matters because they fail differently.

| Type | Shape | How it gets dropped |
|---|---|---|
| **DIRECTIVE** | do this thing | Buried behind item 1; never started |
| **CONSTRAINT** | this must/must never hold | Read as context, not as a testable requirement |
| **QUESTION** | tell me X | Answered implicitly, or not at all |
| **CORRECTION** | that was wrong, do it this way | Acknowledged, then the old behaviour resumes |

**CONSTRAINT is the dangerous one.** It has no deliverable, so there is
nothing whose absence is obvious. From this session:

> "Note that the noise injector CANNOT cause permanent edits or
> corruption to the Stone Tablets."

That is not a task. It is a property that must hold over a task, and the
only honest response is a test that fails if it stops holding — a
checksum over the archive before and after, not a claim that the code
looks read-only.

Constraints already standing in this repo, which a distillation must
never re-derive as optional: never write to `~/.acervator` or
`~/.acervator_logs` from tests; never modify Stone Tablets; never bump a
version banner without a green gate; never emit context footers.

## The output

Emit this before the first tool call. Keep it tight — it is a work
manifest, not a restatement of the prompt.

```
Distilled: <n> items
1. [DIRECTIVE]  <imperative, one line>
2. [CONSTRAINT] <the property, and how it will be proven>
3. [QUESTION]   <what is being asked>
4. [CORRECTION] <what changes, from what to what>
Sequencing: <what runs first and why, if it is not obvious>
```

Then create tracked tasks for anything that will not be finished in the
current turn. An item that exists only in a chat message is not tracked.

## Closing the loop

The distillation is a contract. At the end of the turn, every item is
either done, or explicitly named as not done with a reason.

**Never let an item disappear silently.** "Scaling the work down is the
operator's call" — if an item is dropped, say which one and why, and let
them decide. A summary that covers items 1-3 and omits item 4 reads as
completion.

## Mid-turn arrivals

This operator sends requests while work is in flight — several times in
one session. A mid-turn ask is the highest-risk kind, because there is no
natural pause at which to enumerate it and the current edit is already
holding attention.

Handle it the same way: distil it, fold it into the tracked list, and say
where it sits in the sequence. Two real examples from 2026-08-04, both
arriving mid-turn:

- "Nuclear Mode also plays tapes forward and then backwards with a 10~25%
  random noise injection... Can fit this into the current work or append
  to docket. Whichever is safer." — a DIRECTIVE with an explicit
  sequencing question attached. Answer the sequencing question.
- "Note that the noise injector CANNOT cause permanent edits..." — a pure
  CONSTRAINT on work already underway. Needs a test, not an
  acknowledgement.

## What this is not

Not a planning ritual, and not a request for permission. Distil, state
the list, and start working in the same turn. The operator has been
explicit that they do not want to be asked to re-approve things they
already said:

> "You have the wheel. Proceed."

The manifest exists so the work can be checked at the end, not so the
work can be delayed at the start.
