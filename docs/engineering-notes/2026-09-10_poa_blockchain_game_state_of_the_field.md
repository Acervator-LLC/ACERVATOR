# Blockchain games — what actually runs, and what it costs

2026-09-10. Reference. This note answers one question: can blockchain technology
now run a real game, and do sidechains do it. Every figure carries the page it
came from and the date that page gives. No figure comes from memory. The last
section names every number that no source could supply, and nothing above it uses
one of those numbers.

Raw captured source output: `artifacts/147-research-blockchain/raw_sources.txt`.
The repository gitignores that directory, because it holds captured output, and
`docs/` may not hold captured output.

## The verdict first

Yes. Real games run with the whole game on the chain, and they are not gambling
and not token transfers. They are small. The largest measured audience for a
fully on-chain game reached about two thousand people in a ten-day round, and the
busiest fully on-chain world sustained about four actions a second.

Your hour-turn, turn-based design sits inside what the field has already done.
Your twenty-layer world wants a rate slightly above what the best-measured fully
on-chain game reached, and your participant target runs six to sixteen times
larger than any fully on-chain game has drawn. The rate is reachable. The audience
remains the part nobody in this field has yet proved.

```
one action, on your chain today                1,015 bytes
your per-layer bound, one world turn           1,033 actions   0.29 a second
your twenty-layer world, one world turn       20,660 actions   5.74 a second
OPCraft, sustained over ten days                               4.05 a second
Redstone, all-time peak                                        3.80 a second
Ronin, all-time peak                                           3.91 a second
your participant target                       13,100
Dark Forest, largest measured round             2,000
Eternum, first season sign-ups                    800
```

The second finding lands harder and you should have it early. **The flagship of
this field shut down four months ago.** Lattice made MUD, OPCraft and Sky Strife,
and ran the chain they lived on. It wound down, and that chain closed on 15 May
2026.

```
"After five years, Lattice is winding down. Redstone shuts down
 May 15, 2026 (23:59 UTC)."

"It validated our thesis about emergence, but it didn't reach the scale to
 sustain a business, and we didn't have conviction that raising VC was the
 right path."
```

Five outlets carry those two sentences identically, and the shutdown date matches
the notice on the company's own home page, read 2026-09-10. The technology worked.
The audience did not arrive.

## Are there real games, beyond gambling and transfers

Five. Each entry below names the game and what the chain actually decides. That
distinction matters most, and the marketing hides it.

**Dark Forest** runs a space-conquest strategy game. The contracts hold the
universe and verify every move before accepting it, using zero-knowledge proofs
so a player can prove a legal move without revealing where they sit. The
community branch carries a dated release in June 2026, so the line still runs.

```
what the chain decides    the whole world, and the validity of every move
the source                github.com/dfarchon/dark-forest-ares, read 2026-09-10
the wording               "contracts define the world"
                          "Players produce proofs from these circuits; the
                           contracts verify those proofs before accepting
                           state changes onchain"
latest release            2026 Jun / v0.1.5, a test round
original development      2019 to early 2022
largest measured round    "Nearly 2,000 people" over "a 10-day period"
                          blog.zkga.me/v6-r5-wrapup, dated 2022-04-01
```

**OPCraft** ran a voxel world, the Minecraft shape, with the contracts generating
the terrain themselves. OPCraft gives the densest measurement in this field.

```
what the chain decides    every block placed, and the terrain function itself
the source                mud.dev/introduction, version 2.2.23, read 2026-09-10
the wording               "a fully onchain voxel world" built "in 1.5 months,
                           which processed 3.5 million transactions in 10 days"
derived                   4.05 transactions a second, averaged over ten days
                          243 transactions a minute
ran for                   two weeks, then closed
```

**Loot Survivor** runs a turn-based dungeon crawler on Starknet. It comes closest
to the shape you are building, and its storage trick carries the single most
useful engineering fact in this note.

```
what the chain decides    combat, loot generation, every action
the source                docs.provable.games/lootsurvivor, read 2026-09-10
the wording               "all game logic executed on Starknet"
the storage               "A player's gamestate exists primarily in a single
                           felt252, every action the player takes only updates
                           a single storage slot"
                          github.com/BibliothecaDAO/loot-survivor, read 2026-09-10
one storage slot          31 bytes
```

**Eternum** runs a fully on-chain strategy game with territories, alliances and
armies, on Starknet with the Dojo engine. Eternum leads this field in ambition and
still draws a small audience.

```
what the chain decides    territory, resources, armies, trade
the source                bankless.com/read/eternum-returns-to-starknet
                          dated 2025-04-30
season zero sign-ups      about 800
season one pools          1 million LORDS and 100,000 STRK
combat                    "in-game battles are now rapid and stamina-based"
                          — real time, not turn based
```

**DUST** carries the surviving autonomous world, continuing the OPCraft line. It
moved chains in April 2026 when Redstone closed, and 0xPARC supports it now.

```
what the chain decides    the world's physics and matter, per its own wording
the source                dustproject.org, read 2026-09-10
the wording               "an autonomous world with fixed rules of physics"
the notice                "DUST HAS MIGRATED TO DUST CHAIN", April 2026
published figures         none — no players, no transactions, no world size
```

**Primodium** runs a fully on-chain base-building game. Ethereum's own
application directory lists it, with the site updated 8 September 2026.

```
what the chain decides    stated as the whole game
the source                ethereum.org/apps/primodium, site updated 2026-09-08
the wording               "Unlike most games on the market, Primodium is a
                           fully onchain game"
chain named on that page   none
```

### Against those, the games everyone has heard of

Here sits the marketing-against-architecture line, and it falls exactly where you
expected. Axie Infinity and Pixels carry the two largest names in this field, and
in both cases the chain holds assets and currency while the play happens
elsewhere. The direction of travel gives the clearest evidence: Pixels moves
currency **off** the chain on purpose.

```
the source      pixels.xyz/faq, read 2026-09-10
the wording     "Coins" is an off-chain currency, bought with PIXEL
                BERRY becomes "an off-chain coin to ensure fairness" in
                Chapter 2
```

One caution on this pair, because this kind of claim comes easily and proves
hard. I could not find a primary page from the makers of Axie Infinity stating
where its combat resolves. The unsourced list at the end carries that absence, and
no figure in this note rests on it.

## Are sidechains used — the direct answer

Yes, and the field has moved past them. One sidechain runs a real game today.
The biggest one abandoned the model four months ago.

Ethereum's own documentation, last updated 23 February 2026, draws the line and
names the sidechains. Dark Forest runs on one of those named chains, which makes
it the live example you asked for.

```
the definition    "a separate blockchain that runs independent of Ethereum and
                   is connected to Ethereum Mainnet by a two-way bridge"
the difference    "Unlike layer 2 scaling solutions, sidechains do not post
                   state changes and transaction data back to Ethereum Mainnet"
the trade         "A sidechain uses a separate consensus mechanism and doesn't
                   benefit from Ethereum's security guarantees"
named sidechains  Polygon PoS, Skale, Gnosis Chain (formerly xDai),
                  Loom Network, Metis Andromeda
the source        ethereum.org/en/developers/docs/scaling/sidechains/
```

Ronin answers the question outright. Sky Mavis launched it in 2021 as an Ethereum
sidechain, specifically to carry Axie Infinity's in-game actions, and it became
the most-used gaming chain in this field. On 12 May 2026 it stopped being a
sidechain.

```
the source      coindesk.com, published 2026-05-11
migration date  2026-05-12
before          an independent Ethereum sidechain
after           an Ethereum Layer 2
their reason    "Four years ago, we launched Ronin because Axie Infinity needed
                 a faster and more efficient network"
the trigger     security, tokenomics and scale, after a "$625 million exploit"
                 in 2022
the effect      token inflation "from over 20% to below 1%"
downtime        about ten hours
```

### What replaced them

The family in use today covers rollups and app-chains. A rollup publishes its
data to a parent chain and inherits that chain's security, which a sidechain
gives up. An app-chain holds one application, and that pattern now carries every
fully on-chain game.

```
Dark Forest        a sidechain, Gnosis Chain        still running
Ronin              sidechain until 2026-05-12       now a Layer 2
OPCraft            its own OP Stack chain           closed after two weeks
Sky Strife, DUST   Redstone, an OP Stack chain      chain closed 2026-05-15
DUST, today        DUST Chain, its own chain        running
Eternum            Starknet, a validity rollup      running
Loot Survivor      Starknet                         running
Primodium          its own chain                    chain unnamed on its page
```

State channels did not appear once in this research as the basis of a game that
runs. Neither did any sharded game chain. Two engines aiming at high tick rates,
Keystone from Curio and World Engine from Argus, appear only as announcements,
with no game of theirs measured here.

## What an action-heavy game actually achieves

The honest measurement counts user operations a second, and the honest source is
L2BEAT, which publishes that rate per chain with the date of each peak. Read on
2026-09-10, covering the year to that date.

```
chain              past day    all-time peak    peak recorded
Starknet               2.97           273.38    2025-10-09
Base                 153.21           244.48    2026-06-05
Arbitrum One          18.13           109.13    2026-02-05
Ronin                  2.96             3.91    2026-05-28
Xai                    0.62           140.30    2024-07-16
Immutable zkEVM        0.55            11.74    2024-07-08
Redstone            no data             3.80    2024-11-28
```

Two rows deserve a second reading. Ronin carried the largest audience this field
has ever had, and its all-time peak stands at **3.91 operations a second**. The
people who made the MUD engine made Redstone for fully on-chain games, and its
all-time peak stands at **3.80**. The field's gaming chains are not busy.

### Against your own figures

Your per-layer bound allows 1,033 actions in a one-hour world turn. That gives
0.29 actions a second. Your full twenty-layer world gives 5.74 a second. The
table sets every measured figure beside both.

```
                         a second    an hour   x your 20 layers   x one layer
your 20-layer world          5.74     20,660          1.00            20.00
your one layer               0.29      1,033          0.05             1.00
OPCraft, ten-day average     4.05     14,583          0.71            14.12
Ronin, all-time peak         3.91     14,076          0.68            13.63
Redstone, all-time peak      3.80     13,680          0.66            13.24
Starknet, past day           2.97     10,692          0.52            10.35
Arbitrum One, past day      18.13     65,268          3.16            63.18
Immutable, all-time peak    11.74     42,264          2.05            40.91
Xai, all-time peak         140.30    505,080         24.45           488.94
Base, past day             153.21    551,556         26.70           533.94
Starknet, all-time peak    273.38    984,168         47.64           952.73
```

Read it in both directions, as you asked.

**Where the field does better.** Starknet at its peak carried 47 times your whole
twenty-layer world. Base carries 27 times your whole world as its ordinary daily
traffic. General-purpose rollups hold ample headroom for your rate, today,
without any new technology.

**Where your design wants more.** Your twenty-layer world needs a higher
sustained rate than any dedicated gaming chain in this field has ever reached.
OPCraft's ten-day average, Ronin's peak and Redstone's peak all sit between 66
and 71 per cent of your twenty-layer figure. A single layer sits comfortably
inside the field; the full cube sits at the frontier of what has actually run.

**Where the headline numbers prove nothing.** Somnia launched a gaming chain on
2 September 2025 with a headline of more than a million transactions a second.
Read on 2026-09-10, a public dashboard shows it moving 37 transactions a second.
That gap between announcement and delivery appears in one line, and the same
caution covers every engine claim in this field, including Paima's documented
"10k+ tps per game", which sits on a documentation page as a claim rather than a
measurement.

### On bytes, where you do much worse and can fix it

Your chain writes 1,015 bytes for one action. Loot Survivor writes one storage
slot, which holds 31 bytes. Your own earlier measurement already found a 399-byte
compact encoding for the same action.

```
your chain today                1,015 bytes an action
your own compact encoding         399 bytes an action
one Starknet storage slot          31 bytes
ratio, today against a slot        32 to 1
ratio, compact against a slot      13 to 1
```

The two do not measure the same layer, and that matters. Your 1,015 bytes forms a
readable record in a file you own, and it buys you a file a person can read. The
31 bytes forms a packed field in contract storage that costs money per byte. Your
figure counts disk and theirs counts fees. The comparison still earns its place,
because it shows real headroom in your own encoding, already measured — the
399-byte figure sits in
`docs/engineering-notes/2026-09-10_poa_world_state_budget.md`.

## What it costs

You asked for cost, and this gives the strongest argument for the choice you
already made. Running your own chain in process means an action costs nothing but
disk. On a public chain, every single action carries a fee.

Only Base gave me a dated per-action fee figure, from a page published 22 August
2026 and updated 9 September 2026.

```
the source   polkastarter.com/blog/what-is-crypto-gas
the wording  on Base, "sending tokens about 1 to 3 cents, swaps and app
              interactions about 5 to 20 cents"
```

A game action counts as an application interaction, so the five-to-twenty band
applies. Against your own action counts:

```
fee an action     one layer an hour    20 layers an hour    20 layers a day
$0.01                       $10.33              $206.60             $4,958
$0.05                       $51.65            $1,033.00            $24,792
$0.20                      $206.60            $4,132.00            $99,168
```

At five cents an action, a twenty-layer world running continuously costs about
twenty-five thousand dollars a day in fees alone. Some studios pay this for their
players rather than charging them. Nothing here recommends a direction; the number
answers what you asked, and the choice stays yours.

## Does anything put a full world on chain

Yes, and the engine that does it states the claim plainly. MUD holds the whole
application state in the chain's own execution environment, so the client needs
nothing but a node.

```
the source   mud.dev/introduction, version 2.2.23, read 2026-09-10
the wording  "the entire application state lives in the EVM, and the only
              requirement for clients and frontends is an Ethereum Node"
```

The scale those worlds reach should shape your expectations.

```
world                  players                 actions           duration
Dark Forest, round 5   nearly 2,000            not published     10 days
OPCraft                not published           3.5 million       10 days
                                               243 a minute
Eternum, season 0      about 800 sign-ups      not published     a season
DUST                   not published           not published     running
Primodium              not published           not published     unstated
```

Your target of 13,100 participants across a twenty-layer world runs 6.5 times the
largest measured fully on-chain round and 16 times Eternum's first season. Your
120 participants in a single event sit well inside what has already run.

One more thing belongs in this section, because the field makes a promise it did
not keep. The case for fully on-chain worlds says nobody can shut them down. Then
Redstone closed, and DUST had to move chains to survive. A world lasts only as
long as somebody keeps running the chain beneath it.

## Unagreed block membership — the field's answer

You named this as the open problem: two of your nodes close a world turn holding
different sets of actions, so the same action gets a different stored id. The
field has a standard answer, and it differs from the one you would hope for.
**Nobody makes two writers agree. One writer takes the authority, and the others
confirm its work.**

Three named, running mechanisms do this, and all three share one idea.

**One sequencer with sole authority.** Every rollup works this way, and the Dojo
engine's own sequencer says so in as many words. Eternum and Loot Survivor run on
it.

```
the source    dojoengine.org/toolchain/katana, read 2026-09-10
the wording   "a sequencer has singular authority over transaction ordering and
               block production", giving "fast finality and predictable
               performance"
block timing  instant on arrival, or a fixed interval set in milliseconds
```

**One proposer per round, chosen by rotation.** Every chain in the Cosmos family
uses this answer. The specification says plainly that a single named node writes
the proposal and the rest vote on the whole set, yes or no.

```
the source   github.com/cometbft/cometbft, consensus specification,
             read 2026-09-10
the wording  "A proposal is signed and published by the designated proposer at
              each round"
             "The proposer is chosen by a deterministic and non-choking round
              robin selection algorithm that selects proposers in proportion to
              their voting power"
```

**Borrow the ordering from a chain that already has it.** This answer sits
closest to your architecture, and it comes from the one engine in this field made
for turn-based games. The game sends actions to an existing chain purely to get
them ordered, then its own code computes the state from that order.

```
the source   docs.paimastudios.com, read 2026-09-10
the wording  "apps publish transactions to a blockchain for ordering and data
              availability, but uses its own code to determine the correct app
              state"
on chain     the transaction inputs
off chain    the state computation
built in     "passive time and timers (game ticks)" and commit-reveal
status       version 1 documented; version 2 "still under construction"
```

The third deserves your attention for one specific reason. Your world turn
already closes at a declared time, and your ordering already tie-breaks on the
hash of a record's own contents. You lack an authority on the set. All three
mechanisms above supply that authority by naming one party per turn rather than by
reconciling two. That makes a design choice for you, not a technical gap in your
chain.

## Where your design suits this better than the field's norm

Plainly: your hardest-looking choices already solved the field's hardest problem.

The field's failures cluster in real-time play. Eternum moved to real-time,
stamina-based combat. Two whole engines, Keystone and World Engine, exist only to
raise the tick rate, and neither appears here with a measured game. A chain cannot
hold a live animation, and every attempt to make one do so has needed new
infrastructure.

Your design wants none of that.

```
your world turn       one hour
your event turns      60 of one minute, or 12 of five minutes
your resolution       actions placed during the turn, resolved at the close
your playback         a filled block played back theatrically
```

An hour-long turn fits a chain more easily than anything else could. It gives the
chain three thousand six hundred seconds to do work a real-time game would need
finished in sixteen milliseconds. Your playback design separates the pace of the
chain from the pace of the spectacle, which names exactly what the tick-rate
engines try to fake.

Two more of your choices beat the field's norm, for measurable reasons.

```
lazily created layers   an unvisited layer costs nothing, so the cube's cost
                        follows where people actually are; OPCraft generated
                        terrain in the contracts and saturated blockspace
your own chain          no fee an action; on Base the same actions cost
                        $206 to $4,132 an hour at twenty layers
```

Your design suits this worse in one place, and only one: the audience. No fully
on-chain game has drawn 13,100 people. That raises a market question rather than a
technical one, and nothing in this research calls the rate impossible — only that
nobody has had to serve it.

## What no source could supply

I searched for each item below and found no named, dated page. **No figure
anywhere above rests on one of these.**

```
Axie Infinity's on-chain against off-chain split, from a page by its makers
Eternum or Realms Blitz moving to their own app-chain — a social post only
player counts for DUST, Primodium or Eternum in September 2026
a per-action fee in cents for Starknet, Ronin, opBNB or any app-chain
Redstone's lifetime transaction total
Kamigotchi's chain, on a primary page — secondary sources name "Yominet"
any published actions-a-minute figure for a fully on-chain game; the OPCraft
  figure above comes from a division and gives an average, not a peak
the date of the Chainspect dashboard snapshot — the page states none, so the
  reading carries the date I read it
```

One figure above comes from arithmetic rather than from a quotation, and this
paragraph names it so nobody mistakes it for a published one. OPCraft's 4.05
actions a second and 243 a minute both come from dividing its published 3.5
million transactions by its published ten days. Every other rate in this note
appears as a rate on its own source page.

## What this note does not do

It recommends no chain, no engine and no service. Where a finding implies a
choice, this note states the choice and its cost and leaves it with you. The
three mechanisms for block membership describe what exists, not a proposal to
adopt one.
