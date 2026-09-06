---
name: hyper-refocus
description: Load before reporting anything to the operator, before dispatching any unit, and before writing any issue, brief or comment. Filters every statement — mine and every agent's — against the item's content and the operator's directives. Invoke by name when the operator says focus, filter, drift, scope, or conflation.
---

# HYPER REFOCUS

**Nothing reaches the operator until it survives the check.** An agent's words
are not my words until they pass. My own sentences get the same treatment.

## The four questions

Run on every line before it is reported, and on every brief before it is
dispatched.

1. **Is this in the item?** Open the issue. If the subject is not named in the
   item body or in a directive, it does not go in.
2. **Did he ask for it?** A topic he never raised is dropped, however true.
3. **Is this his vocabulary?** An agent inventing a concern — a design hazard,
   an adjacent subsystem, a technology — is the agent's framing, not the item's.
4. **Would he recognise this as the work he assigned?** If not, it is drift.

## Drop, do not caveat

Cutting a paragraph is correct. Prefacing it with "one thing worth noting" is
the same defect wearing a hedge.

## What this catches

- An agent reporting a design property the item never mentions.
- An agent naming a subsystem outside the unit.
- An agent raising a hazard nobody asked about.
- A finding about a file the item does not name.
- A technology the operator never named.

A genuine defect found outside the item gets **one line, in the issue, no
discussion**.

## Answer a question as a question

He asks whether something is the case — answer in one line. Do not convert it
into a work item, do not dispatch a unit, do not fix it. He assigns work
explicitly.

## Before dispatching

Name the item and the unit. If the brief maps to neither, it is wrong. If the
brief names a file outside the unit's boundary, it is wrong.

## Noticing is not an assignment

**The drift that survives the four questions starts as a real defect.** Each
question above screens a topic. None screens a reflex, and the reflex is: I read
something, it was wrong, I dispatched a unit at it.

A true defect found while working an item is still outside the item. It is the
sharpest kind of drift, because it feels like diligence and it defends itself.

Measured 2026-09-05: mid-conversion, three consecutive actions went to manual
prose about the Simulator, Paper Trader and Proof of Accumulation — three
features the operator had already said are not built. Each action was correct
about the prose. None was the conversion.

**A defect in an unbuilt feature is not a defect. It is the feature being
unbuilt.** Nothing can be repaired until it is built. Prose describing it is
wrong for the same reason, and it is fixed when the feature lands, by the unit
that lands it.

## The dispatch test

Before any Agent call, one question, answered against the item body:

> **Which file that the item names does this brief change?**

Name it. If the answer is a file the item does not name, the dispatch is drift
and does not go. Not narrowed, not caveated — not sent.

"It came up while I was working the item" is not an answer. "It is true" is not
an answer. "It would mislead a reader" is not an answer. The item names files;
the brief changes one of them, or it belongs to a different item.

## Where a real finding goes

One line, in the issue that owns the feature. No unit, no branch, no dispatch,
no message to a running agent. The queue is his, and a finding that enters it
out of order is the queue reordering itself.

## Why

Fan-out is the drift. Every extra scope returns material outside the unit, and
that material reaches him as noise. Breadth does not add rigour — it adds
surface to wander into. **One agent. One unit.**
