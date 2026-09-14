---
name: screen-conversion
description: The six steps for converting one screen to the second build variant. Load before writing any host. The abstraction must be complete or the new screen silently draws nothing.
---

# Converting a screen

**A converted screen that draws is not a converted screen.** Every failure on
this project has the same shape: the picture is right and no data reaches it.

Operator, 2026-09-13, after the fourth such screen: *"RESEARCH THE CORRECT, FULL
WORK FLOW OF HOW TO DO THIS AND IMPLEMENT THE STEPS."*

## What this is, by its established name

`src/gui/variant_surface.py` is **Branch by Abstraction** (Paul Hammant): an
abstraction over the implementation being replaced, two implementations behind
it, and a toggle choosing. The pattern's own precondition is the one that keeps
getting skipped:

> **The abstraction must cover everything the client uses.**

A client call that the abstraction omits does not fail. It reaches the old
implementation, or nothing, and the screen comes up blank while every check is
green. Combine with Michael Feathers on **seams** — the place where behaviour
can be substituted — and the seam here is the widget's public surface plus the
pushes made into it.

## The published sources this follows

Nothing here is invented. Each step is a named, documented practice:

| step | practice | source |
|---|---|---|
| the toggle over two implementations | **Branch by Abstraction** | Paul Hammant — https://martinfowler.com/bliki/BranchByAbstraction.html |
| replacing a screen at a time behind it | **Strangler Fig** | Martin Fowler — https://martinfowler.com/bliki/StranglerFigApplication.html |
| finding where behaviour can be substituted | **Seams** | Michael Feathers, *Working Effectively with Legacy Code*, ch. 4 |
| recording what the old thing does first | **Characterization tests** | Feathers, same, ch. 13 |
| the client's calls as the contract | **Consumer-driven contracts** | Ian Robinson — https://martinfowler.com/articles/consumerDrivenContracts.html |
| comparing rendered output | **Approval / golden master** | Llewellyn Falco — https://approvaltests.com/ |

The precondition that keeps being skipped is Hammant's own, stated in his
article: the abstraction has to cover what the clients use. Everything this
skill adds to the published method is the order of the steps and the counts a
report carries.

## The six steps, in order

### 1. Characterize the seam

List every attribute, method and signal the rest of the application touches on
the widget being replaced. Search every call site, not the class body: the class
may declare members nobody calls, and callers may reach members through
`getattr`.

Write the list down. **It is the contract.** A member on the list and not on the
new host is a defect the moment the toggle flips.

### 2. Enumerate the feeds

Separately, list every place the application **pushes into** the widget: a
refresh loop, a timer tick, a signal connection, a direct call after a fill.
Each one carries data that must arrive at the new screen at the same moment.

A screen has more feeds than it has controls, and the feeds are what is
invisible in a picture.

### 3. Implement the whole contract

The host answers every member of the list from step 1 — stand-in objects where
the client drives a child widget, so one set of calls drives either side.

**Not the members a screenshot exercises.** The ones a screenshot exercises are
the ones that were never the problem.

### 4. Route every feed

Every push from step 2 reaches the new host under the second variant, at the
same moment it reaches the old one under the first. Where the application
pushes to the old widget by name, the push goes through the abstraction instead.

### 5. Drive each member and read it back at the page

Member by member, feed by feed: call it, then read the value **off the running
page** — not off the host, not off a cache. Report the count: members driven,
members answering.

This is the step that catches a host that accepts a value and drops it.

### 6. Compare the two renders, last

Only after step 5. Two pictures agreeing proves nothing about whether either is
right; two pictures differing proves nothing about which is correct. The render
is for layout, colour and density — never for whether the screen works.

## What a report must carry

```
contract members            N
members answered            N of N
feeds enumerated            N
feeds routed                N of N
members driven and read back N of N
```

Anything less than N of N is an unfinished screen, and saying otherwise is the
lie this skill exists to stop.

## Falsification

This skill is wrong if a screen passes all six steps and still comes up blank or
unfed in the running application. Then a seventh source of data exists that
steps 1 and 2 do not reach, and finding it is the work.
