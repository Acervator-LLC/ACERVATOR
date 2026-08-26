"""Simulator subsystem: fleet replay, nuclear mode, and their sim venues.

Moved out of ``src/gui/simulator_tab/`` in issue #128 unit R1. None of these
12 modules imports Qt. They tick real ``ScrummingBot`` instances against a
recorded tape, so they are a data source beside ``src/exchange``, not a widget.
"""
