# New User Procedure

A how-to. It takes a new owner from the Releases page to a running fleet, one
screen at a time.

Each page is one step. A step carries one picture. A step that is a navigation
action carries the instruction for that action. A step that covers a setting names
the control, says what the bot does differently when it moves, says which other
setting it touches, says what a wrong choice costs, and gives the value the live
fleet runs against the value the field opens on.

The first five pictures are the operator's own captures of the Releases page,
cropped to the part each caption concerns. They sit in `supplied/`, and the
producer annotates them and never redraws them.

Every other picture comes from the running program, and every one shows the Qt
build. When a screen changes, the next capture replaces its picture and the page
stays as it is. Every step carries a picture. Two of them photograph the screen
the step names without pressing the control on it, because that press creates
bots or places an order. Those two pages say so.

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
| 17 | [The shadow bot](17-leave-the-shadow-bot-off.md) | Settle the phantom bots. |
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

## The deck

A slide show sits beside these pages:

```
docs/new-user-procedure/New-User-Procedure.pptx
```

It is a view of the pages and not a second source. One slide stands for one row
of the table above. Each slide carries that page's heading, its picture, the
picture's own caption and its bold instruction.

One command writes it:

```
python -m tools.build_vwap_deck --deck new-user
```

`tools/build_vwap_deck.py, in build_procedure` takes the order from the table
above and the four parts from each page. It embeds each figure's own bytes. It
writes the file in place, reads the written file back, and refuses any slide that
differs from its page. A page with no heading, no picture or no instruction stops
the write, and so does a picture the disk does not carry. The message names what
is missing.

A page edit reaches a reader by running that command. A new page needs its row in
the table above, and the next run gives it a slide.

Two runs over unchanged pages do not write the same bytes. Each run stamps its own
time into the archive the slide show is packed in. The slides are the same and
only the bytes differ.

The deck's own second commit recorded the state this replaces:

> The producer is still not in the tree. A guard refuses a new file under
> `tools/`, so the deck was built from a throwaway script and needs rebuilding by
> hand whenever a page is added.

The current reading: the production is in the tree. The guard still refuses a new
file of its own under that folder, so the production joined the module that
already composes this repository's other slide show.

## How many screens and how many decisions

Driven on an empty home, with the home redirected before the first import. Nine
screens stand between a double-click and one running bot.

| # | screen | what the owner does | decisions |
|---|---|---|---|
| 1 | the splash | nothing, or one click to skip it | 1, optional |
| 2 | the window, open on Live | press Add Crypto Exchange | 1 |
| 3 | the venue form | type the key and the secret, press Test and Add | 3 |
| 4 | the venue's own sub-tab | press New Bot | 1 |
| 5 | Trading Mode | pick the engine, press Next | 3 |
| 6 | Select Asset Pair | pick the venue and the pair, press Next | 4 |
| 7 | Trading Parameters | set what the cycle runs on, press Next | 64 |
| 8 | Phantom Bots | settle the shadow reader, press Finish | 15 |
| 9 | the bot list under Live | press Start | 1 |

The four wizard pages carry **82** controls an owner may set. The three pages
before them and the one after carry **6** presses and two fields. Nothing
refuses to advance: every page on the path reports itself complete as it opens,
so an owner who touches none of the 82 reaches Start on the shipped defaults.

The splash closes on its own at 8.5 seconds. `src/gui/main_tabs/splash_screen_surface.py, in paint_ops`
reports 467 drawing calls at the three second mark, eight lines of text, and the
sigil's seven layers at 3,500 triangles.

**No walkthrough appears inside the window.** A machine that has never run
Acervator reads an empty stored name, the startup block writes a line to the log
and opens nothing, and `src/core/instance_guard.py, in InstanceGuard.evaluate`
answers that this machine now owns the directory. These pages are the whole
procedure. Driven on an empty home and on a home holding a saved fleet, the
count of screens the program offers a newcomer of its own accord is nought in
both.

### What these pages describe, and what they do not

The bar carries nine tabs. Six have a page of their own, Live is reached by
steps 6 to 8, and three have none.

| tab | page |
|---|---|
| Sim | step 22 |
| Paper | step 23 |
| Live | steps 6, 7 and 8 |
| Charts | step 24 |
| Inspector | step 25 |
| Swarm | step 26 |
| History | step 27 |
| Status | none |
| Console | none |

The window declares four menus — Exchange, File, Help and Theme — and **none of
the four has a page**. That is the second row of this how-to's own build order
and it is not built.

The program offers seven asset classes, and every one of them accepts a venue:
crypto, stocks, derivatives, forex, commodities, indices and futures perps.
These pages name crypto and nothing else, so the control that picks a class is
on no page.
