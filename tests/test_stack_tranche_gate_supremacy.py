"""v3.23.44 — a Stack tranche never supersedes a trading gate.

OPERATOR DIRECTIVE, 2026-08-11, verbatim:

    "Its also important to verify that tranches do not supersede any
     trading gates. They are only are 'used' when a valid trading
     condition occurs."

    "A price threshold being passed activates the tranche which allows it
     to be spent when the trading condition manifests."

WHY THIS FILE HAS NO TESTS
==========================
This file used to pin the SECOND stage's *position in the source of*
``ScrummingBot.tick`` -- by parsing the AST of the shipped file and
asserting the spend call sat under a gate-chain verdict, with planted
source mutations as controls. That is a stateful check of the source
text/structure, not of behaviour: it verified where a call is WRITTEN,
not that the gate actually refuses a spend at run time, and it tripped on
any reformat of ``tick``. It was removed as an antipattern.

WHERE THE BEHAVIOUR IS COVERED
------------------------------
``tests/test_stack_mode_execution.py`` pins what each stage DOES,
functionally: that stage one is reachable on a refused tick and places
nothing, and that stage two places the order only under an authorised
gate-chain verdict. That is the property the operator directive asks for,
tested by running the code rather than reading it.

FOLLOW-UP (flagged, not silently dropped)
-----------------------------------------
If a dedicated functional test for the "no ungated spend" invariant is
wanted beyond what test_stack_mode_execution.py already exercises, it
should drive a stubbed bot through the tick spend-path and assert no
order is placed when the gate refuses -- not re-parse the source.
"""
