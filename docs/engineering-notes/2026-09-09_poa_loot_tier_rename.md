# PoA — the five loot tiers renamed to products, 2026-09-09

Reference. This page carries the five renames, the source behind each product
term, and the terms the design cannot use.

Every statement carries one mark.

```
HIS         his words or his ruling
MEASURED    read out of the tree or the issue, with the file named
PROPOSED    mine, and open for him to refuse
```

## His ruling

**HIS.**

> "PoA - Loot Tier - Alchemical Operation Naming Conflict - Will need to rename the
> Tiers to mean 'the result of...'."

**HIS.** He added a second direction for the rarest tier, after the quintessence
collision reached him.

> "Could use something alchemical meaning coalesced or focused power..."

## What the issue carries now

**MEASURED.** Section 11 of the concept document holds the five tiers. Its base
column matches the five weights in the brief exactly.

```
tier           gate   base weight   Elite weight
CALCINATION      1        60.0%         55.0%
PUTREFACTION     5        25.0%         22.9%
SUBLIMATION      8        11.0%         10.1%
FERMENTATION     9         3.5%         10.5%
EXALTATION      10         0.5%          1.5%
```

**MEASURED.** Decision 47 sets the label length. Every named thing carries a full
name plus a short form of at most twelve characters, and the design writes that
short form rather than letting the surface cut the name.

## The five renames

**PROPOSED.** Each tier drops the operation and takes the name of what that
operation leaves behind.

| weight | old name | new name | short form | characters |
|---|---|---|---|---|
| 60% | CALCINATION | Calx | Calx | 4 |
| 25% | PUTREFACTION | Cauda Pavonis | Pavonis | 7 |
| 11% | SUBLIMATION | Flores | Flores | 6 |
| 3.5% | FERMENTATION | Elixir | Elixir | 6 |
| 0.5% | EXALTATION | Magisterium | Magisterium | 11 |

The full name of the second tier runs thirteen characters. The twelve-character
rule binds the short form, and `Pavonis` holds the row.

### Calx, at 60%

**PROPOSED.** Calcination burns a body in an open fire. A powder stays in the
dish, and the dictionaries name that powder.

```
Wiktionary, calx, chemistry and alchemy, historical
  "The substance which remains after a metal or mineral has been
   thoroughly burnt"

Wordnik, calx
  "the substance which remains when a metal or mineral has been subjected
   to calcination or combustion by heat, and which is, or may be, reduced
   to a fine powder"
```

**PROPOSED.** Every fire leaves ash, so ash carries the commonest tier. The word
also stays the plainest of the five, which suits the label a participant reads
most often.

### Cauda Pavonis, at 25%

**PROPOSED.** Putrefaction is the hard one, and a primary text answers it
directly. The colours are what the operation yields once the rot finishes.

```
Collectanea Chemica, "The Stone of the Philosophers"
  "When the putrefaction of our seed has been thus completed, the fire may
   be increased till glorious colours appear, which the Sons of Art have
   called Cauda Pavonis, or the Peacock's Tail."
```

**PROPOSED.** The accounts of the sequence agree on the position, which makes it a
convention rather than one author's scheme: the blackening, then the many colours,
then the whitening, then the reddening. Second place in that order carries the
second tier.

### Flores, at 11%

**PROPOSED.** Sublimation drives a solid to vapour, and the vapour settles as
crystals. The apothecaries named the crystals for what they look like.

```
The Chymistry of Isaac Newton, alchemical glossary, Indiana University
  "Flowers: A sublimate; the term arises from the radiate crystals
   resembling flowers that are often produced during the sublimation of
   certain substances."

Flowers of sulphur, flores sulphuris, survives as the apothecary term for
sulphur purified by sublimation.
```

**PROPOSED.** The Latin form keeps the tier clear of the ordinary English word. A
crystal that grew out of vapour ranks above ash and below a finished preparation.

### Elixir, at 3.5%

**PROPOSED.** Ripley's ninth gate ferments the medicine. The tradition's name for
the perfected medicine is the elixir.

```
George Ripley, The Compound of Alchemy, Fermentation
  "So you shall ferment your medicine"
  "For that is medicine each deal perfected"

The Chymistry of Isaac Newton, alchemical glossary
  "Elixir: Most usually, a synonym for the philosophers' stone. In some
   cases, however ... elixir can mean merely a potent medical arcanum."
```

**PROPOSED.** The tier takes the glossary's second sense, a potent preparation
rather than the summit. One drop in twenty-nine is powerful and is not the top.

### Magisterium, at 0.5%

**PROPOSED.** The rarest tier takes the word for both the perfected preparation
and the mastery behind it. It answers his “coalesced or focused power”, and the
sources state it as a result.

```
Wiktionary, magistery, alchemy, historical
  "A pure quality with the power to cure or to turn one substance into
   another; also, a substance such as a philosopher's stone able to turn
   one substance into another."

Wiktionary, magistery, chemistry
  "A fine substance deposited by precipitation"   e.g. magistery of bismuth

The Paracelsian maxim
  "Solve et coagula, et habebis magisterium"
  dissolve and combine, and you will have the magistery
```

**PROPOSED.** Three things put it at the top. The maxim names it as what an
operation hands back, which is his rule exactly. Pernety's dictionary sends the
ferments through all the principal regimes of the magistery, which ranks the
magistery above the fermentation product and settles the order of the two rarest
tiers on a source rather than a preference. The chemistry sense names a
precipitate, which is concentration made physical.

## Clearing exaltation

**MEASURED.** Pernety's *Dictionnaire Mytho-Hermétique* gives exaltation two
products, and this design already holds both.

```
Pernety, exaltation
  the matter stands exalted when it "has already acquired the degree of
  perfection it must have to be white or red elixir"

Pernety, exaltation of water
  "the fixation of the mercury of the Sages in stone"
```

**MEASURED.** The quintessence is the currency, and a ledger already carries it.

```
src/competition/quintessence_ledger.py
```

**PROPOSED.** The rarest tier cannot take exaltation's own product. His direction
names the replacement sense rather than the replacement word. Of the three
candidates that carry that sense, the tree blocks one, the sources grade another in
two halves, and `Magisterium` stays clear. The two lists below weigh all three.

## Clearing putrefaction

**MEASURED.** Every source that names a residue of putrefaction names it for
waste.

```
caput mortuum    "dead head", the nonvolatile residue left in the bottom of
                 a retort after distillation
terra damnata    "damned earth", the solid waste of an operation
```

**PROPOSED.** A tier at one in four must not carry a waste name. The resolution
takes the sign instead of the dregs. Collectanea Chemica names the colours that
appear the moment putrefaction finishes, which makes them a product of the
operation by the same reading the other four tiers use.

**MEASURED.** I checked one further reading, and it does not hold. Paracelsus has
putrefaction destroy the mumia rather than yield it, so the term contradicts the
sense.

## Rejected for collision, and what each collided with

**MEASURED.** Every line names the file.

```
Quintessence            the currency, src/competition/quintessence_ledger.py
Coagulum                SOLVE · ET · COAGULA letters every trophy ring
                        src/competition/trophy_generator.py:51
                        and the manual glossary
                        docs/manual/12-adr-index-and-glossary.md:176
Lapis Philosophorum     LAPIS PHILOSOPHORUM letters the rubedo trophy
                        src/competition/trophy_generator.py:172
Nigredo Albedo          the five trophy stages
Citrinitas Rubedo       src/competition/trophy_generator.py:243-247
Unio Mystica
Fermentum, Levamen      the Fermentation crafting verb, the collision the
                        rename exists to remove
Sublimate               the Sublimation crafting verb, same reason
Azoth                   another name for mercury, and Mercury is the Healer role
Prima Materia           the Harvest trophy subtitle
                        src/competition/trophy_generator.py:250
```

**MEASURED.** One line matters because the issue records the opposite. The concept
document measures Philosopher's Stone as free in the tree and reserves it for a
summit item. The English phrase is free. The Latin form is not, because the rubedo
trophy letters it.

## Rejected on sense or grade, with no collision

**PROPOSED.** These carry no collision. Each one fails on meaning.

```
Tincture       no file holds it, and the sources grade it in two halves: a
               white tincture that transmutes to silver, a red one that
               transmutes to gold. One tier name leaves the other grade unplaced
Caput Mortuum  an attested product of putrefaction, and it names waste
Terra Damnata  the same
Terra Foliata  attested for putrefaction in Pernety, and its own sources call it
               "ash of ashes", which repeats Calx at tier 1
Mumia          Paracelsus has putrefaction destroy it, not yield it
Medicina       Ripley's own word at the ninth gate, and it reads as a consumable
               category beside armour and weapons
```

## The collision check itself

**MEASURED.** I counted the five chosen words across the tree, with a control word
in the same pattern. The control is the currency, which must report.

```
pattern with the control      155 occurrences, 5 files, all quintessence
pattern without the control   0 occurrences, 0 files
```

**PROPOSED.** The zero reads the tree rather than a broken search. Calx, Flores,
Pavonis, Elixir and Magisterium appear in no file.

## What the operator sees differently

**PROPOSED.** Nothing on screen yet. The loot tiers are names in a concept
document, and no surface draws them. The change is that the five names now
describe an item instead of a step, and the twelve operations stay free for the
crafting verbs.
