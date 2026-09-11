# PoA name clearance — similar content, and concept fidelity

**Mode: Reference.** This page enumerates every proper name the Proof of
Accumulation package declares, checks each against existing uses, and checks
whether the project's use of a borrowed term matches what the term means in its
own source. It writes no code and renames nothing.

The names come out of the modules, not out of a list. Every set below comes off
the running package.

```
src/competition/loot_drop.py            five loot tier names and five short forms
src/competition/materials.py            QUALITY_GRADES = TIER_NAMES, the same tuple
src/competition/rpg_classes.py          seven classes, their planets and metals
src/competition/quintessence_ledger.py  the currency and the four buckets
src/competition/poa_modes.py            four event modes and the Impetus pool
src/competition/monster_table.py        twenty-one designs, twenty-three entities
src/competition/map_glyphs.py           three mark families
src/competition/trophy_generator.py     five trophy tiers, phases and mottoes
```

---

## The test is similar content, not any use anywhere

The operator narrowed this himself, and the narrower test is the one that binds.
His words:

```
"Well, do not be TOO strict. Mainly saying to not use stuff that is repeated
 in the similar content. Cauda Pavonis is probably fine."
```

Similar content means a fantasy or role-playing game, an occult work, a bestiary,
or a loot and rarity scale. A goth metal band is not similar content. A fantasy
game using the name for an item is. **A reader of this page must not apply the
stricter rule by mistake.**

He also named the intent, and it carries a second test the first one does not
reach.

```
"Just want to make sure we are not stepping on any toes or stretching concepts
 too far..."
```

Two questions follow from that, and they are independent.

```
stepping on toes     is this name already used in similar content
stretching a concept  does the project's use match what the term means in its source
```

---

## What proved the search could report

A zero from a search nobody has watched find something is worth nothing. Three
searches act as the control here, each surfacing a real use of an exact term in a
game.

```
"Vorpal Sword"        returned the Dungeons and Dragons magic item, legendary,
                      attunement required, the decapitation roll
"Quicksilver Draught" returned the Warhammer Age of Sigmar item carried by
                      Stormcast Eternals heroes
"Solar Lance"         returned the Baldur's Gate 3 superweapon in the Githyanki
                      Creche storyline
```

The instrument finds a fantasy-game use of an exact phrase. Every clear verdict
below rests on that.

---

## The composed names, and the four that land in fantasy games

This project composed its seven class names, and `rpg_classes.CLASSES` declares
them with a planet and a metal each. A collision here costs the most, because the
phrase originates here and a reader would take the match for a borrowing.

| name | similar content | source |
|---|---|---|
| Lead Ward | no | searched bare; returned only the rapper Leaf Ward, a different name |
| Tin Bulwark | no | returned a tobacco tin brand, HMS Bulwark, and RuneScape's Dinh's bulwark — not the phrase |
| Iron Edge | no | a registered US mark, no. 1878301, class 006, metal edging for landscaping |
| Solar Lance | **yes** | Baldur's Gate 3 superweapon; LEGO Exo-Force weapon; Dawncaster RPG card; a Terraria fan spear |
| Quicksilver Draught | **yes** | Warhammer Age of Sigmar, molten silver with Celestium, grants speed; New World's Draught of Quicksilver |
| Copper Conduit | **yes** | Eternal Card Game unit card; an EverQuest item |
| Silver Mirror | **yes** | a MARDEK RPG item granting Physical Shield to the party; also a hard rock band |

Four of seven appear in a fantasy game under the exact phrase. The other three
carry no similar-content use the searches above could surface.

---

## The five loot tiers as a rarity ladder

Five tiers sit in `loot_drop.LOOT_TIERS`, and `materials.QUALITY_GRADES` points at
the same tuple object, so these five names also serve as the five ore quality
grades. No search found a game using any of them as a rarity tier or a grade.

| name | similar content | source |
|---|---|---|
| Calx | no | searched bare; returned Calyx, Mira Calix and California X, all different names |
| Cauda Pavonis | no game | an English gothic rock band since 1998, six albums — music, not similar content |
| Flores | no | returned the apothecary term flores sulphuris and the Indonesian island |
| Elixir | as a resource | Clash Royale's core battle resource, accrued and spent to place cards. Also the Elixir programming language |
| Magisterium | as a title | The Magisterium, a five-book fantasy novel series by Cassandra Clare and Holly Black, 2014 to 2018 |

Two carry a similar-content echo and neither is a rarity tier. A novel series and
a battle resource are not a loot ladder, and both words are centuries older than
either.

---

## Quintessence, Impetus and Pleroma as this project uses them

These three are the project's own vocabulary rather than item names, so the
question is narrower: does another game use the word for the same kind of thing.

| name | module | similar content | source |
|---|---|---|---|
| Quintessence | `conversion_rates.QUINTESSENCE` | **yes** | a RuneScape Archaeology material at level 91, excavated from caches, described in game as a fifth base alchemical element |
| Impetus | `poa_modes.IMPETUS_AT_FIRST_LEVEL` | no | returned a Clutch EP on Earache Records and two record labels; no game resource |
| Pleroma | the fourth bucket in `quintessence_ledger` | no game | a federated social network server, and a one-man band from Kiev with nineteen releases |
| Acervator | `project_age.USER_AGENT` | no | no trademark, company or product surfaced |
| ACRV | `token_ledger` | **yes, outside games** | Aave CRV trades under ACRV, an ERC-20 token on Ethereum, total supply 11,802,716 |

The RuneScape hit is the one worth his attention. That game uses the same word
for a collectible material and gives it the same justification this project does.
This project spends it as a currency and also embeds it in materials through
`materials.embedded_quintessence`, so the two uses overlap in both roles.

The ACRV hit is not similar content. The ticker trades live in the same
blockchain ecosystem the PoA token targets.

---

## The creature names and the planetary pairings

Twenty-three entity names sit in `monster_table.MONSTER_DESIGNS`, twenty-one of
them attested in a named pre-modern text. **These appear in many games by design,
and that is not a finding.** The operator's own sourcing rule in
`monster_table.ADMISSION_CONDITIONS` requires a source attested in its own
pre-modern text, so any creature admitted is one other games have also drawn
from. Nobody owns Lamashtu, Lilith, Empousa, Typhon, Echidna, Asmodeus or Mot.

The same holds for the seven planets and the three Paracelsian principles. All
are terms of art older than any modern work.

```
unownable by source   Lamashtu, Lilith, Empousa, the gallû, Ammit, the Keres,
                      the Sebitti, Humbaba, Mot, Apophis, Anzû, Asag, Typhon,
                      Echidna, the Gigantes, Aži Dahāka, the Watchers, the
                      Nephilim, Asmodeus, Angra Mainyu, the daevas
composed here          the Avatar, a direct servant
```

The module marks the two composed entries `INVENTED`, and its
`INVENTED_SOURCE` constant names them as built on Lovecraft and modern fiction.
The module already states that as invention rather than attestation.

---

## The trophy set

`trophy_generator.GENERATORS` holds five trophy tiers, and three further name
sets sit beside them as literals. None is a game item.

| name | kind | similar content |
|---|---|---|
| Harvest, Gold Fold, Bear Slayer, Grand Accumulator | composed tier names | no; no band, game or mark surfaced for Gold Fold or Grand Accumulator |
| Nigredo, Albedo, Citrinitas, Rubedo | phase labels | **yes**; The Witcher uses Nigredo, Albedo and Rubedo as alchemical ingredients |
| Unio Mystica, Prima Materia, Purificatio, Opus Magnum, Sol Devoratur, Hen To Pan | mottoes | Opus Magnum is a Zachtronics alchemy puzzle game, 2017. Hen To Pan titles a track on Nox Aeternus's 2019 album Alchemy |

Opus Magnum is the sharpest of these, because the game's subject is alchemical
transmutation and a reader would hear the reference. The phrase sits in one
module as a motto string rather than a product name, and *magnum opus* is the
standard name for the Great Work in every source that discusses it.

---

## Ekthelius, cleared by the operator

He checked this one himself and said so.

```
"Definitely unique. Have checked."
"Ekthelius on Bandcamp is me."
```

The name also stands as his authorship line in this repository, which makes it
prior art of his own rather than a name cleared by absence.

```
src/__init__.py:2   Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator)
git author          Anthony L. Brown <274356317+ekthelius@users.noreply.github.com>
```

`season_schedule.py` and `contracts/AcervatorTrophy.sol` both carry Ekthelius as
the top trophy tier, capped at twenty-one ever. This unit spent no search on it.
One line from a search that ran anyway: the nearest modern name is Ekthelion, a
black metal project formed in 2014, which is a different word.

---

## Every name, with its similar-content verdict

The package declares 124 entries across 21 name sets, plus 18 more held as
module constants rather than in a set. Twenty-four entries repeat between sets,
so the distinct count is 118. Both figures come from importing the package and
reading the sets, not from pattern matching.

| set | count | verdict |
|---|---|---|
| loot tiers and grades | 5 | no tier collision; Elixir and Magisterium echo elsewhere |
| loot tier short forms | 5 | four equal the full name; Pavonis is the fifth |
| classes | 7 | four appear in fantasy games, three do not |
| class planets | 7 | Saturn, Jupiter, Mars, Sol, Mercury, Venus, Luna — ancient, unownable |
| class metals | 7 | plain nouns: lead, tin, iron, gold, quicksilver, copper, silver |
| tria prima principles | 3 | Salt, Sulphur, Mercury — Paracelsian terms of art |
| roles | 4 | Tank, Damage, Healer, Support — the standard role words of the genre |
| event mode labels | 4 | Monster Smash matches a Google Play title and a Steam title of that name |
| event variant labels | 2 | Standard and Elite — generic |
| materials | 7 | metal plus the suffix in `materials.ORE_SUFFIX`; plain nouns |
| storage classes | 3 | gear, consumable, resource — plain nouns |
| item types | 4 | armour, weapons, accessories, consumables — plain nouns |
| monster designs | 21 | attested pre-modern sources; shared by design |
| monster entity names | 23 | the same, two of them marked invented |
| descending tier names | 6 | descriptive phrases, not proper names |
| ascending families | 3 | Angels, Watchers, Others — scriptural, unownable |
| map mark families | 3 | Vessel, Loot tier, Event mode — generic |
| skills | 1 | Quintessence Transfer — composed, no collision surfaced |
| alignment poles | 2 | creation, destruction — plain nouns |
| consecration directions | 2 | blessed, cursed — plain nouns |
| trophy tiers | 5 | composed; Ekthelius is his |
| constants outside a set | 18 | Quintessence, pleroma, Impetus, Reincarnate, Sephirot, ACRV, Acervator, Corpus Hermeticum, four phases, five mottoes |

---

## Where the project's use stretches the term

This is the second test and it needs no search. It needs the source's own meaning
beside the module's own use.

**The five tiers as a ladder sit comfortably, and better than they look.** The
ladder is not arbitrary: the five operations behind the tier names are gates 1, 5,
8, 9 and 10 of George Ripley's twelve, composed around 1471, and the rarity order
reproduces that gate order exactly. Ripley's tenth gate, Exaltation, yields the
Philosopher's Stone, and the rarest tier takes its name from that gate.

```
Calcination      gate  1   Calx           60.0%   commonest
Putrefaction     gate  5   Cauda Pavonis  25.0%
Sublimation      gate  8   Flores         11.0%
Fermentation     gate  9   Elixir          3.5%
Exaltation       gate 10   Magisterium     0.5%   rarest
```

**The grade reuse is the widest stretch on this page.** The tuple
`materials.QUALITY_GRADES` is the same object as `loot_drop.TIER_NAMES`, so a unit
of ore carries the name of a finished philosophical preparation as its grade. A
magistery in its sources is a perfected product with the power to transmute, not a
grade of raw rock. The ladder fits a rarity scale and does not fit a scale of ore
purity.

```
src/competition/materials.py
    QUALITY_GRADES: tuple[str, ...] = TIER_NAMES
    embedded_rows()  serves one row a material at a grade, so a row reads
                     iron ore at Magisterium quality
```

**My recommendation, and I mark it as mine.** Give ore its own grade names and
leave the five operations on the loot ladder. Nothing in the sources ties a grade
of ore to a stage of the Work, and two different consumers read the two scales —
`loot_drop.tier_for_roll` for one and `materials.embedded_quintessence` for the
other. He decides, and this unit renames nothing.

**The tria prima assignment is the second stretch.** Each entry of
`rpg_classes.CharacterClass` carries one principle a metal, and the docstring
calls that principle the Paracelsian body the metal belongs to. Paracelsus says
the opposite: three principles compose every metal.

```
Paracelsus, quoted in the Tria prima sources
  "all seven metals are born and composed from three substances ... the three
   principia, that is, mercury, sulphur, and salt, out of which all seven
   metals originate. Mercury is the spirit, sulphur is the soul, salt the body."
```

A reader who knows the text would see lead assigned to Salt and note that lead
holds Sulphur and Mercury too. The game needs a partition to split seven classes
into four roles, and the tradition does not supply one. **My recommendation: keep
the partition and stop calling it the principle the metal belongs to.** Naming it
the principle a class *expresses* is true of the design and does not contradict
the source.

**The seven planetary pairings are exact and need no change.** Every pair in
`rpg_classes.CLASSES` matches the medieval set.

```
Saturn lead      Jupiter tin      Mars iron       Sol gold
Venus copper     Mercury quicksilver             Luna silver
```

**Quintessence as a currency is a comfortable fit.** Aristotle's fifth element is
the incorruptible substance of the heavens, and the alchemical quintessence is the
purest essence drawn out of a body. The ledger's own movement kind for earning is
`DISTIL`, the operation the sources name, and nothing in the ledger mints new
supply. The stretch is that a countable balance under a cap of 33,000,000 is a
quantity and an essence is not, which is a normal game move.

**Pleroma as a ledger bucket is a register shift rather than a contradiction.**
The Gnostic pleroma is the fullness all emanation returns to, and
`vessels.MERGED_WITH_PLEROMA` names a Reincarnate holding no balance, which is the
source's own sense. One thing worth his eye: the design names the same place the
platonic space in his own words and the pleroma in the code, and those two words
come from two different traditions.

**Impetus as a per-turn allowance is the closest fit of the three.** In
pre-modern physics an impetus is a force impressed on a body and used up as the
body moves. The pool in `poa_modes.ImpetusPool` grants four at first level, one
more every twenty levels, and spends down within one turn. Impressed, then
consumed, is what the term means.

---

## The stretches ranked by how wide the gap is

Ranked by the width of the gap, not by how many sources mention the word.

```
1  the ore grades          a finished magistery used as a grade of raw ore.
                           Same tuple object, two unrelated scales
2  the tria prima          one principle assigned per metal, where the source
                           says all three compose every metal
3  the pleroma wording      platonic space and pleroma used for one place
4  Quintessence as a count  an essence given a countable cap. Normal for a game
5  Impetus                  no gap
6  the planetary pairings   no gap; all seven match
```

---

## Cauda Pavonis stays

He withdrew his own objection, and that closes the question.

```
"Cauda Pavonis is probably fine."
```

The band exists — an English gothic rock act since 1998, six albums and four
anthology releases. The act makes music, not similar content, and no game uses the
phrase. **Nothing needs renaming and nobody should reopen this.** The two sections
below keep the searched alternatives and the measured rename cost, so the work
survives.

---

## The alternatives searched before the reversal

The searches turned up three pre-modern names for the same stage and checked each.
This page keeps them because they carry sources, not because the design wants them.

| candidate | source | collision |
|---|---|---|
| Iris | Pernety's dictionary of 1758 records that the Hermetic philosophers name their matter Iris once the putrefaction leaves it rainbow-hued. Pliny 37.52 names a rock-crystal iris that throws a rainbow onto a nearby wall | broad but unownable; a goddess from Hesiod, a flower, an eye part |
| Arcus | Ripley's Putrefaction gate promises a rainbow marvellous to sight in the glass | none surfaced in a game, band or album |
| Thaumantias | Ovid and Virgil's own name for Iris, daughter of Thaumas | none surfaced; nearest are a 2023 synth-pop album and a 2024 game, both different words |

One candidate failed its search. Fermata released an album under the title Omnes
Colores in 2023, which is the exact shape he objected to. Pavo fails on his own
grounds, because it keeps the peacock.

---

## The rename cost, measured and no longer needed

The five tier names are one shared tuple, so the measurement covers both the
loot ladder and the ore grades at once. Eleven files read a tier name or a grade,
resolved by reading the import statements rather than by pattern.

```
src/competition/loot_drop.py      declares the five as string literals
src/competition/materials.py      QUALITY_GRADES = TIER_NAMES
src/competition/conversion_rates.py, crafting.py, items.py, inventory.py
src/competition/world_tier.py, map_glyphs.py
src/competition/__init__.py        re-exports all five
src/gui/main_tabs/proof_of_accumulation_tab_surface.py
contracts/AcervatorLoot.sol        the five names and short forms in its constructor
```

Two false consumers fell out of that list. The surface file
`visualizer_themes_surface.py` declares its own tuple of the same name from a
palette table, and its keys name display themes rather than loot tiers. The string
`calX` in the bundled charting library is a vendor variable. **No JavaScript file
carries a tier-name literal**, searched in snake, camel and Pascal spelling; the
names reach the screen only through the Python view model.

No Python test names a tier literal. The only test that does is
`tests/contracts/AcervatorLoot.t.sol`. Nothing records a deployment address for
`contracts/AcervatorLoot.sol`, so a rename there means a recompile, not a
migration.

---

## What a stored loot file does with a retired grade name

This answer came from driving the real code rather than reasoning about it. A probe
stored one drop, retired one grade name, then replayed the store.

```
replay with the name live          1 drop held
replay after the rename           LootStoreError
  "loot_store.json could not be replayed: 'Cauda Pavonis' is not a PoA quality
   grade; the grades are Calx, Iris, Flores, Elixir, Magisterium"
replay with the grades restored    1 drop held
```

**A retired grade name stops the whole file replaying, not just the one drop.** A
reader gets a refusal naming the old grade and the five current ones, and the
file's other drops sit unreachable behind it. Four calls make that chain, and the
last one refuses any grade the grade tuple does not carry.

```
LootStore.load
  LootDrop.from_dict
    LootDrop.__post_init__
      materials.quality_index   raises UnknownQualityError
```

Two figures matter and one of them is absent. The constant `LOOT_FILE_VERSION`
stands at 2 and the loader refuses a version it does not know, so a rename would
need that version raised and a read path for the old names. **No migration step
exists in the module**, and only a unit that writes one would set it.

One measured relief: the runtime directory on this machine holds no loot store
file, so no file is at risk today. Only a live world would create one.

Item ids would move. The helper `loot_drop.item_id_for` hashes a payload carrying
the tier name, so every new drop takes a new id while stored ids keep their old
hash. A rename leaves the roll to tier mapping alone, because `tier_bounds` cuts
its spans from the weights and never from the names.

---

## What this page reads, and what reads it

**What this reads that nothing provides.** A decision on the ore grades. The
module shares one tuple between a rarity ladder and a scale of ore purity, and
nothing in the sources supports the second use. It also reads a migration path
for a stored grade name, and `loot_drop` has none.

**What this provides that nothing reads.** Every verdict here. No module, test or
screen consumes this page, and no check enforces a name against it. The naming
rules live in the issue and in the operator's words; this page records one
measurement against them.

---

## Sources

- [Cauda Pavonis, the band](http://www.caudapavonis.com/biog.html)
- [Cauda Pavonis on Bandcamp](https://caudapavonis.bandcamp.com/)
- [Vorpal Sword, D&D Beyond](https://www.dndbeyond.com/magic-items/5397-vorpal-sword)
- [Quicksilver Draught, Age of Sigmar Lexicanum](https://ageofsigmar.lexicanum.com/wiki/Quicksilver_Draught)
- [Draught of Quicksilver, New World Database](https://nwdb.info/db/item/quicksilvert3)
- [Solar Lance, Exo-Force Wiki](https://exo-force.fandom.com/wiki/Solar_Lance)
- [Copper Conduit, Eternal Card Game Wiki](https://eternalcardgame.fandom.com/wiki/Copper_Conduit)
- [Copper Conduit, EverQuest item](https://everquest.allakhazam.com/db/item.html?item=56846)
- [Silver Mirror, Figverse Wiki](https://figverse.fandom.com/wiki/Silver_Mirror_(Item))
- [Dinh's bulwark, Old School RuneScape Wiki](https://oldschool.runescape.wiki/w/Dinh%27s_bulwark)
- [IRON EDGE trademark, Justia](https://trademarks.justia.com/744/57/iron-74457396.html)
- [Quintessence, The RuneScape Wiki](https://runescape.wiki/w/Quintessence)
- [Elixir, Clash Royale Wiki](https://clashroyale.fandom.com/wiki/Elixir)
- [Elixir, the programming language](https://elixir-lang.org/)
- [The Magisterium Series](https://en.wikipedia.org/wiki/The_Magisterium_Series)
- [Nigredo, Witcher Wiki](https://witcher.fandom.com/wiki/Nigredo)
- [Opus Magnum, Zachtronics](https://www.zachtronics.com/opus-magnum/)
- [Pleroma, the fediverse server](https://pleroma.social/)
- [Aave CRV, ACRV on CoinGecko](https://www.coingecko.com/en/coins/aave-crv)
- [Omnes Colores by Fermata, Discogs](https://www.discogs.com/release/28180249-Fermata-Omnes-Colores)
- [Ripley's Twelve Gates](https://www.alchemywebsite.com/ripgates.html)
- [The Compound of Alchemy, Putrefaction](https://www.arthistoryproject.com/artists/george-ripley/the-compound-of-alchemy/putrefaction/)
- [Tria prima, Wikiquote](https://en.wikiquote.org/wiki/Tria_prima)
- [Pernety, Dictionnaire mytho-hermétique, Q to Z](https://le-miroir-alchimique.blogspot.com/2009/10/pernety-dictionnaire-mytho-hermetique-q.html)
- [Pliny, Natural History 37](https://www.attalus.org/translate/pliny_hn37b.html)
- [Flowers of sulfur](https://en.wikipedia.org/wiki/Flowers_of_sulfur)
- [The seven alchemical metals](https://www.astroak.com/en/blog/the-seven-metals-alchemy-and-the-planets)
