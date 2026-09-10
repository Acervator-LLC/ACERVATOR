# Concept document — part 7 of 7

This part carries the withdrawals in full and the naming standard in full. The body
carries both in short form: a table of what was withdrawn and what replaced it, and the
naming rules without their reasoning.

| What is here | Body section it belongs to |
| ------------ | -------------------------- |
| Every superseded reading, with the statement that replaced it | the superseded readings |
| The naming standard, in full | 17 |

Nothing here is changed from the body it left. The same marks apply: HIS, MEASURED,
DECIDED, PROPOSED.

---

## The superseded readings, in full

He corrected himself twice on 2026-09-09. **The later statement wins in both
cases.** Both earlier readings are recorded here as withdrawn so no builder
picks one up from a comment.

### Quintessence is never burned

**HIS, later and binding.**

> "Well, do not mean for Quint to be 'burned'...used the wrong word here. It is
> stored on the blockchain for future use."

> "Quint is the essence...should not be able to be destroyed from a
> philosophical standpoint..."

```
spend   a participant's Quintessence leaves their wallet
store   it rests on-chain
reuse   it funds later awards and later event pools
```

**Withdrawn.** The earlier reading of his Elite Events note took "the Quint burn
/ spend mechanic" literally and concluded that a Quintessence contract must be
able to burn, and that the supply becomes deflationary. Both are wrong and both
are withdrawn. The no-burn property of the existing token contract suits
Quintessence after all, the cap is a ceiling on total ever minted, and the share
not redistributed is a reserve that keeps events fundable once the cap is
reached.

### Project age replaces per-exchange listing age

**HIS, later and binding.**

> "Can research with CoinGecko. Project age for all blockchains is known. This
> is an inherent characteristic."

```
project age   when the chain or token came into existence
listing age   when one exchange began carrying that market
```

**Withdrawn.** An earlier note recorded that listing age cannot be answered and
treated that as a blocker on his six-month rule. Project age is the better test
for what he asked for: a token three years old, newly listed on one venue, is
not an obscure pump, while a token three weeks old is one on every venue at
once. Per-exchange listing age stays unavailable and is no longer needed.

Section 9, in part 3 below, carries the whole project-age mechanism: the
endpoint, the field, the identifier map that limits it, the cost of a backfill,
and what happens when an age is unknown. The per-exchange measurement that the
correction retired is kept there too, marked retired, because it is the evidence
that the platform cannot answer the older question.

### One further withdrawal, inside the capture bounds

**Withdrawn.** An earlier reading recorded the split of a market's pool among
its certifiers as the largest unbounded hole in the rotation, and recommended an
equal share above a minimum qualifying volume. **His capture-bounds directive of
2026-09-09 answers it and supersedes that recommendation.** One allotment per
participant per activation per market, a share ceiling, a cooldown in candles
and a graded curve bound the split directly. The earlier recommendation is
withdrawn and Choice 9, in part 6, is closed. The one item that stays
unbounded is how many exchanges a single participant may draw from, and section 9
records it.

### Quintessence is transferable after all

**HIS, later and binding.**

> "Quint is transferable between players via a specific skill isolated to common
> Guild members, takes significant time to complete based on amount and skill
> level, and has a negative effect of 'bleeding' quint back into the 'platonic'"

**Withdrawn.** This page recommended that Quintessence be bound to the participant
who distilled it and not transferable at all. His ruling answers it in the other
direction, and the anti-whale property survives because each of his four terms taxes
the attempt. The option table that produced the recommendation stays in part 6, and
section 13 carries the rule.

### The Exchange Participation Layer was recorded as unresearched

**Withdrawn.** A research comment recorded the manipulation protection on this layer
as the one thing no published source could answer. **His exclusion-only rule of
2026-09-10 answers it**, and section 15 carries it with the three closures it needs.
That entry stands as written in its own comment, because it was true when written.

### Three healers became a healer, a support healer and a support

**HIS, later and binding.**

> "Also need pure healer, support healer, and pure support classes. Not three exclusive
> healer types."

**Withdrawn.** This page read Mercury's three classes as three healers and said so in
one line — two Tanks, two Damage and three Healers. His correction splits them across
pure healing, support healing and pure support. The array keeps its seven classes and
its three principles; only Mercury's labels change. Section 3 carries the mapping.

### Two measurements this page carried wrongly

Neither is his correction. Both are read out of the tree today, on `origin/current`.

```
the identity module      252 lines, not the 285 this page and several comments
                         carried — section 14
lifetime trophy caps     the Python declares a cap on three tiers, including
                         Bear Slayer at 10,000; only the Solidity declares two
                         — section 13
```

The second one changes what unit 17 builds. Bear Slayer was never a missing
number. Gold Fold is the only cap this design has to invent, and the existing
caps sit in the wrong contract.

---

## 17. The naming standard — in full

**HIS.**

> "Loot - Can use latin and exotic names of moderate complexity as needed for thematic
> accuracy. We are dealing with some ancient ideas that do not have a modern term."

```
allowed    Latin and exotic names, of moderate complexity
for        thematic accuracy, where an ancient idea has no modern term
```

The reason is the bound. A historical term earns its place because it names something no
plain word names: an athanor is not a furnace, prima materia is not raw material, and
azoth is not solvent.

### The discipline that keeps it working

**PROPOSED**, three rules, and the third is the one that gets broken.

```
take the real term    where the tradition already named the thing, use its name
                      rather than inventing a near-miss
invent nothing        pseudo-Latin assembled to sound old reads as costume, and
                      the genuine terms beside it lose their weight
plain word wins       where an exact English word exists, use it. A Latin name
                      for a thing English already names is affectation, and it
                      spends the reader's patience on nothing
```

The third rule protects the first. If every noun is exotic then none of them lands, and
the summit items tied to hermetic figures arrive sounding like everything else.

### This does not loosen how the design is written about

The repository writes its documentation in Simple Technical English, and that stands.

**The standard governs the world's nouns, not the prose.** An item may be called *prima
materia*; the sentence describing it stays short, active and plain. The two rules do not
conflict because they apply to different things.

### One hard constraint his own layout imposes

The party window shows up to 120 participants at forty to a page. The row carries a health
bar, a role colour, a **truncated name** and one mark slot.

A long name will not survive that row, and the enemy screen and player window face the
same limit at smaller sizes.

**PROPOSED.** Every named thing therefore needs two forms: the full name that carries the
meaning, and a short form that fits a row. That is a design requirement rather than a
formatting detail — a name whose short form is unreadable has failed at the place the
participant actually reads it.

### What the design owes

```
the short form   how long a row can hold, measured against the party window
                 at 40 to a page
the glossary     where a participant learns what an unfamiliar term means,
                 given that the whole point is terms they will not know
consistency      one authority for the vocabulary, so two units do not name
                 the same idea differently
```
