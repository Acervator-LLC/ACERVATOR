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
| 16 | [Leave the shadow bot off](16-leave-the-shadow-bot-off.md) | Settle the phantom bots. |
| 17 | [Create the bot](17-create-the-bot.md) | Finish the wizard. |
| 18 | [Make the fleet](18-make-the-fleet.md) | Create more bots from one. |
| 19 | [Start the fleet](19-start-the-fleet.md) | Start the bots. |

## Where the pictures sit

Each one sits in `figures/` under the name of the step that shows it.
