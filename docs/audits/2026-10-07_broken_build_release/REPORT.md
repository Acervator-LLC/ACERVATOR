# A released build filed every Coinbase bot under the wrong sector

A build was released whose Live tab showed no bots under Crypto. The operator
opened it, found the tab empty, and returned to the last build he knew worked.
Seven tabs carried the same fault. It reached him because three verification
stages all passed, and none of them had ever opened the Live tab with bots in
it.

This record states the mechanism, answers the six questions, and adds the four
catalogue rows the event earns.

## What the program answered

The Live tab asks one function which sector a market belongs to. That function
takes the set of sectors a venue serves, removes derivatives, sorts what is
left, and returns the first name.

```python
rest = sorted(served - {DERIVATIVES})
return rest[0] if rest else DERIVATIVES
```

Sorting puts `commodities` before `crypto`. So the answer is correct only while
the venue serves exactly one sector besides derivatives.

Driven over four commits, with a dollar spot pair as the symbol:

| Build | Commit | Sectors the venue serves | A spot pair answers |
| ----- | ------ | -----------------------: | ------------------- |
| 2194 | `e3dcc15f` | 1 | `crypto` |
| 2198 | `0d0454bd` | 3 | `commodities` |
| 2204 | `07e4fa18` | 6 | `commodities` |
| 2234 | `ca61770a` | 6 | `commodities` |
| 2235 | `ca642b7d` | 6 | `crypto` |

Build 2194 is the last build the operator reported as working, and it is the
last commit before the fault appeared. His reading and the measurement agree to
the commit.

Control: a venue serving no sector answers an empty string, so the function
discriminates rather than returning a constant.

## The fault landed in a commit that did not touch the function

`0d0454bd` added Stocks and Commodities to the sectors the venue serves. It
changed a table of data. The selection code was untouched, and had been correct
the day before.

A reviewer reading that commit saw a venue gain two rows. Nothing in the diff
named a sort, a tie-break, or a first element. The defect was written earlier
and was dormant, waiting for a second candidate to exist.

## W5H

**Who** — `bot_class` in `src/gui/main_tabs/class_filter_surface.py:104` decides
which sector a bot is filed under. It answers the sector a bot declares, and
falls through to `market_class` at the same file's line 88 when the bot declares
none. No saved bot declared one, so every bot took the fallback.

**What** — a bot trading a dollar spot pair was filed under Commodities. The
Crypto layer then held nothing, and the tab drew its empty note.

**Where** — seven tabs filter by sector, and all seven read the same function:
Live, Charts, Inspector, Swarm, History, Sim and Paper. Two tabs are exempt by
the operator's own rule, Status and Console.

**When** — on every tab draw, from build 2198 through build 2234. Three days.

**Why** — the manual's Trading tab page states that a bot appears under the
sector it trades. The program contradicted that sentence for three days.

**How** — the operator selects Crypto on the Live tab, the tab asks for the bots
of that sector, the filter compares each bot's answered sector against Crypto,
every comparison fails, and the tab reports nothing to show.

## Why three stages passed

This is the part that matters, because the mechanism above is one line and this
is the reason it shipped.

**Continuous integration passed.** The test suite exercises the filter against
venue product lists — which venues appear under which sector. Those tests were
correct and stayed green, because a venue serving six sectors genuinely does
appear under six sectors. The filter's other job is to decide which sector one
market belongs to, and that is the job that broke.

**The archetypes passed.** They read code for known defect shapes. A sort
followed by a first-element read is ordinary Python and is not one of them.

**A screen was rendered at 700 by 900 and read back.** It was rendered with no
bots. An empty Live tab and a Live tab emptied by a filter draw the same way.

So the fault was invisible to each stage for the same reason: **the filter was
proven against the catalogue it reads and never against the records it hides.**

```
proven            which venues appear under a sector
never proven      which sector one bot is filed under
what broke        the second one
```

## The referee's share

The fix is one line and was merged the hour it was reported. The failure is not
the line. Five changes were merged and two builds were released on the day the
tab was already empty, and nothing in that sequence opened the tab with a fleet
in it. A build was handed over as ready on the strength of three green stages,
none of which could see the screen the operator opens first.

## Catalogue rows this event adds

Four rows go into `dev_harness/skills/ocir/SKILL.md` as C143 through C146. They
are stated there in full; this is the index.

| Row | The shape |
| --- | --------- |
| C143 | a tie-break that is correct while the set holds one candidate |
| C144 | a docstring naming the concrete case the code gets wrong |
| C145 | a filter proven against its catalogue, never against what it hides |
| C146 | a build number read as an ordering between two branches |

## What is fixed and what is open

Fixed and released: the sector a bot is filed under, from build 2235.

Open, and tracked as rows on issue #1203: the React variant has had no Paper
tab and no Simulator tab since 2026-10-04, from a constant deleted in
`e3dcc15f` and still read by two view-model builders; the derivatives branch in
the selection function is unreachable for every venue measured; and the New Bot
target asset list is empty on five of six sectors because no recorded symbol
carries a sector yet.
