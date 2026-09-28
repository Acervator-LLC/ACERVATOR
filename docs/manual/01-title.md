# ACERVATOR

User Manual and Feature Design Intention Guide

> Turbator aequilibrii dissolvendus reformandusque.
>
> —----------------------------------
>
> “The disturber of the balance is to be dissolved and reformed.”

> “You are either gaining more territory cheaper or you are selling for higher than you bought it in direct response to the market’s moment to moment volatility.” - Ekthelius

## The mark

![The Acervator mark, the sigil the splash screen paints at launch.](splash-mark.png)

The mark is the product's own sigil. It is drawn from triangles, not from a
font, and the splash screen paints it where a single letter used to sit.

### What each element means

| Element | Form | What it stands for |
|---|---|---|
| Compass | The dividers, hinged above centre, their two legs splaying into the frame that carries the rest | Measurement before action |
| Scale | A balance below centre, one beam and two hanging pans | The balance the platform exists to disturb and restore |
| Reptilian eye | An almond eye whose pupil is a vertical slit | Watching the market without predicting it |
| Fiery aura | Thirteen flames wreathing the eye | The volatility the cycle harvests |
| Scythe | A single shaft crossing behind the eye, its blade the feather of Ma'at | The cut that takes the excess above the target |
| Winged caduceus | A staff down the centre, two serpents coiled around it, wings at the top | Exchange, and the two sides of every cycle |

The aura carries thirteen points, and the count is deliberate.

### The maxim on the legs

Each compass leg is engraved with one word, cut dark into the metal and reading
from the hinge downward.

| Leg | Word | Meaning |
|---|---|---|
| Left | SOLVE | dissolve |
| Right | COAGULA | reform |

Together they are the alchemical maxim *solve et coagula*. It is the platform's
own cycle: a position is dissolved when the excess above the target is sold, and
reformed larger when the dip is bought back.

### How it is built

Each element has its own generator in
`src/gui/main_tabs/splash_screen_surface.py`, and each returns triangles rather
than a picture. `compose_still` in `src/gui/main_tabs/splash_screen_painter.py`
runs every generator into its own layer, adds a bloom, a blur, grain, a tone
grade and a vignette, and writes the picture above.

```python
for name, groups in surface.mark_layers(spin, pulse, moment):
    layer = _pillow(bake_groups(groups, side))
```

### The order the layers draw in

`mark_layers` returns one entry per layer, back layer first. The coiled serpents
draw after the aura, so the compass legs do not cover them.

| Order | Layer | Generator |
|---|---|---|
| 1 | Winged caduceus | `caduceus_faces` |
| 2 | Compass | `compass_faces` |
| 3 | Scythe | `scythe_faces` |
| 4 | Scale | `scale_faces` |
| 5 | Fiery aura | `aura_faces` |
| 6 | Coiled serpents | `serpent_faces` |
| 7 | Reptilian eye | `eye_faces` |

`MARK_LAYER_ORDER` in the painter holds the same order for the still frame.

### The letter forms of the maxim

Every capital in the maxim is a chain of straight strokes. No stroke is a curve,
so the words read as archaic capitals cut with a chisel.

```python
if letter == "L":
    return [[[0.13, -0.46], [0.13, 0.42], [0.56, 0.42]]]
```

`letter_strokes` returns the chains and `etched_faces` lays them along a leg.

### How the aura reads as one body

Each flame spreads half of its own share of the turn at its base, so the base of
one flame meets the base of the next. The thirteen flames form one wreath that
turns together, and each flame still tapers to its own point.

```python
AURA_BASE_SPREAD_DEGREES = FULL_TURN_DEGREES / AURA_POINTS / 2.0
```

### What moves at launch

Four things move while the splash is up, and all four run on clocks the splash
already had.

| What moves | How |
|---|---|
| The whole mark | Fades in from 0.2 s, then breathes with the rings |
| The aura | Turns with the rings, fifteen degrees a second |
| The pupil | Narrows and widens on the same breath |
| The scale beam | Swings once, then settles level |
