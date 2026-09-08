---
mode: story
---

# How I Built Acervator

Explanation. This is my own record of the work, in date order.

## 2026-04-11 — the first sitting

The platform began as a grid bot, an approach that was discarded within the same
sitting once its dependence on directional prediction became apparent to the
author. The design that replaced it was substantially simpler in its intent: the
excess above a stated dollar target is sold, and a larger quantity is bought back
whenever the price subsequently falls below that reference. The consequence of
that arrangement is that every completed cycle terminates with a larger holding
than it started with. The whole of the first implementation was completed in a
single sitting, and a summary of that day survives in
docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md.

## 2026-04-12 — a long fight with keys

The second sitting was given over almost entirely to connecting the platform to
the Coinbase exchange, and key authentication consumed the greater part of that
day before a live balance was rendered on screen. The record for that day is
thin, and no artefact survives from it, so the date should be treated as an
approximation rather than as an established fact.

## 2026-08-18 — the first commit

The platform was developed for approximately four months without any version
control whatsoever, and on this day a total of 650 files were placed under git
in a single operation. The consequence of that change is that every subsequent
alteration carries a diff, which allows a reader to verify each claim
independently. The cost of the preceding gap is set out at issue #66.

## 2026-09-03 — the wall

The build minutes available to the project were exhausted, and every run
attempted since that date has terminated within two seconds on a billing
condition rather than on any defect in the code itself. The merge gate was
switched off so that development could continue, and the resulting ledger is
recorded at issue #370.
