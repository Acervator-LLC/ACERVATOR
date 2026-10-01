# New User Procedure

A how-to. It takes a new owner from the Releases page to a running fleet, one
screen at a time.

Each page is one step. A step carries one picture, one instruction, and one line
saying what changes.

The first five pictures are the operator's own captures of the Releases page,
cropped to the part each caption concerns. They sit in `supplied/`, and the
producer annotates them and never redraws them.

Every other picture comes from the running program, and every one shows the Qt
build. When a screen changes, the next capture replaces its picture and the page
stays as it is. Two steps carry no picture, because driving them creates bots.
Those two pages say so.

The steps after the fleet starts walk the tab bar from left to right, one page
per tab. They say what a tab is for and what to do there first, and they are not
a reference for every control on it. Live needs no page of its own, because
three earlier steps already reach it.

Three tabs have no page. Accumulation has none because nothing builds it. Status
has none because its screen draws through a web view, which returns one flat
colour to a capture instead of a screen. Console has none because its log pane
and its signal pane cover every row of the tab, leaving nowhere to put a caption
that does not sit on top of the log.

## The order

This table is the order. A page's number is its place in it. A new screen gets
its own numbered page and a row at the point in this table where a reader meets
it. Numbering the pages again is this table's job and nothing else's.

| # | page | the step |
|---|---|---|
| 1 | [Open Releases](01-open-releases.md) | Reach the Releases page. |
| 2 | [Take the newest release](02-take-the-newest-release.md) | Open the one marked Latest. |
| 3 | [Pick one file](03-pick-one-file.md) | Choose by the middle column. |
| 4 | [On Windows](04-on-windows.md) | Extract it and run it. |
| 5 | [On a Mac](05-on-a-mac.md) | Open it and allow it. |
| 6 | [The window opens](06-the-window-opens.md) | Reach the Live page. |
| 7 | [Live has no venue](07-live-has-no-venue.md) | Open the venue form. |
| 8 | [Enter the venue keys](08-enter-the-venue-keys.md) | Store a venue. |
| 9 | [Choose the engine](09-choose-the-engine.md) | Pick the trading engine. |
| 10 | [Name what it trades](10-name-what-it-trades.md) | Pick the venue and the pair. |
| 11 | [How far price must move](11-how-far-price-must-move.md) | Set the opposing trade interval. |
| 12 | [What it watches](12-what-it-watches.md) | Set the chart and the band. |
| 13 | [Set the Target Balance](13-set-the-target-balance.md) | Set the balance the bot trades against. |
| 14 | [The price window](14-the-price-window.md) | Set the ceiling and the floor. |
| 15 | [What a cycle keeps](15-what-a-cycle-keeps.md) | Set the compounding rows. |
| 16 | [The reserve for a dip](16-the-reserve-for-a-dip.md) | Settle the hedge reserve. |
| 17 | [Leave the shadow bot off](17-leave-the-shadow-bot-off.md) | Settle the phantom bots. |
| 18 | [How long a lock holds](18-how-long-a-lock-holds.md) | Settle the lock duration. |
| 19 | [Create the bot](19-create-the-bot.md) | Finish the wizard. |
| 20 | [Make the fleet](20-make-the-fleet.md) | Create more bots from one. |
| 21 | [Start the fleet](21-start-the-fleet.md) | Start the bots. |
| 22 | [The Simulator](22-the-simulator.md) | Replay the fleet against stored history. |
| 23 | [Paper first](23-paper-first.md) | Rehearse on live prices, with no money. |
| 24 | [The chart](24-the-chart.md) | Watch the price a bot works against. |
| 25 | [The market inspector](25-the-market-inspector.md) | Find the next market worth a bot. |
| 26 | [The swarm](26-the-swarm.md) | See the fleet, and the money between its bots. |
| 27 | [What it has traded](27-what-it-has-traded.md) | Check the venue's own fills. |

## Where the pictures sit

Each one sits in `figures/` under the name of the step that shows it.
