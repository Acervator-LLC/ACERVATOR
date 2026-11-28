# Proof of Accumulation

Now: no Proof of Accumulation code is in the tree. The bar draws a PoA tab and a
Quint tab between Swarm and History, and no click, key or drag opens either one.

`src/gui/main_tabs/main_window_surface.py, in INACTIVE_TABS` — the two tabs

```python
POA_TAB = "PoA"
QUINT_TAB = "Quint"

#: The tabs the bar draws and no click, key or drag opens, side by side in this order.
INACTIVE_TABS = (POA_TAB, QUINT_TAB)
```

Reference. The design is an on-chain competition layer where bots compete
anonymously and the winners take a token on Base, which is Coinbase's layer two.
Every instance holds a cryptographic identity, signs each trade into an
append-only log, and publishes only a commitment to that log. The strategy stays
private and the proof is public.

This is currently proposed as a concept but will likely require the building of a supporting blockchain team for proper / full implementation. This system is designed to enable users of Acervator to compete against each anonymously via our own Proof of Accumulation blockchain. The idea is to convert trades executed into videogame metrics such as damage to a coliseum style monster or a fellow trader in a 1v1 face off. This further positions the platform as a surgical tool that can be finely tuned and customized to produce intense competition scenarios between entire groups of traders. This, of course, opens the door for actual tokenized Trading Guilds who may require their members to have a certain number of PoA tokens under their belt to join. There will be much more to follow on this as I do intend to scaffold it out for internal testing.

## Quintessence

> "Everything is Quint and we can invent our version of gas using an alchemical
> term for 'flow' or 'move' or 'fuel'"

## The event modes and the turn

> "Please rename events to match Hermetic tests or similar..."

## The world grid

> "Also, terrain grids do not need to overlap perfectly with the world grid. These
> grids are varied in size and shape while be linked together at their own
> borders."

## Movement, and the world turn's pool

> "Just need to be able to say that character A traversed x% of a given square in
> a given turn and this will make it relatively easy to simulate varied terrain
> within one or across multiple squares. Should be simple enough to make this
> dynamic and per character or army or group with encumberance playing a role."

> "Its a function of Strength (max weight) and Constitution (turn point penalty
> while carrying)."

> "Just need to be able to say that character A traversed x% of a given square in
> a given turn... Should be simple enough to make this dynamic and per character
> or army or group with encumberance playing a role."

## Dungeons and the second clock

> "PoA - Dungeons - World Map - Another example of needed inference. What happens
> after a player enters a dungeon? These are the sorts of design questions I want
> you to ask while proceeding. Who. What Where. When. Why. How."

## The skill ladder and the transfer skill

> "All skills have levels that grow through use. Skills should be intelligently
> designed with growth curves similar to Eve Online."

> "Quint is transferable between players via a specific skill isolated to common
> Guild members, takes significant time to complete based on amount and skill
> level, and has a negative effect of 'bleeding' quint back into the 'platonic'
> where it can be respawned and redistributed to other PoA participants."

## The PvP vote

> "There will be PvP Worlds and Events. A world entering PvP mode is determined by an
> active Player Vote and that can put forth once every 24hrs. The voting window
> persists for 15m or three 5m candles. Only while in PvP mode or participating in PvP
> events can one player destroy another's Vessels. This will allow players to have
> specific Vessels they are willing to fight to the death with..."

> "51% or higher. Proper Democracy over here..."

> "Three successive pro-PVP votes over 72hrs will lock the World in PvP mode for an entire
> week starting from the third vote."

## Guilds and the treasury

> "only those holding PoA tokens can form a guild... guild membership locks and
> stakes PoA tokens, by guild rank... a guild may hold any number of members"

> "A guild holds a Quintessence treasury, filled two ways and spent one way.
> Filled by the transfer skill, from a member, paying the bleed. Filled by the
> guild's own event awards. Spent on action costs for guild members, inside an
> event. Never paid out to a member's personal wallet."

## The two meters, and the reset

> "A block fill and real time turn completion meter next to each other."

> "PoA - Demo Mode - ... Must be able to reset the testnet."
