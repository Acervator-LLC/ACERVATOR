# Issue #104 -- the remaining confidence favours can refuse

floor 0.25, BB-priority skew 0.3, arm-alone floor 0.1923076923076923

rows measured: 2436  (errors: 0)

## Value sweep

```
digest BEFORE  c6dd9686d502e9c3a150a994f84591271e8cb027a13c1f0570aa920f305ee8f0
digest AFTER   a624fe07551add3a95bf9ae31d55f7e31a456f6202a0c9c2efc9df5cab8c24d2
```

**1198 of 2436 rows moved.**

| bars | rows moved |
|---|---|
| 35 | 66 |
| 40 | 111 |
| 60 | 266 |
| 100 | 251 |
| 200 | 252 |
| 400 | 252 |

A row is hashed over the gate's inputs, the confidence it JUDGES, the floor it judges against, and both verdicts. Every row whose favour is non-zero moves in the first two of those even when its verdict does not, because the judged number stops being the inflated one.

### C1 positive control -- injected perturbation, off-arm gate

| injected | verdict flips |
|---|---|
| 0 | 0 |
| 1e-09 | 0 |
| 0.001 | 0 |
| 0.01 | 11 |
| 0.05 | 104 |
| 0.2 | 1501 |

### C2 the BB-priority arm is reached

1800 of 2436 rows satisfy the arm's measured condition (73.9%).

### C3 can the confidence conjunct refuse?

| | rows | conjunct refuses | rows where NO reading could refuse |
|---|---|---|---|
| BEFORE | 2436 | 2218 | 73 |
| AFTER | 2436 | 2322 | 0 |

A BEFORE row is counted unfailable when `position_boost + bb_confidence_boost >= floor`. Consensus confidence is bounded below by 0, so on those rows the comparison has no false case whatever the indicators said. AFTER, the count is 0 BY CONSTRUCTION and not by measurement: the favour divides the floor and a division of a positive floor is positive, so a reading of exactly 0.0 always refuses.

### C4 `position_boost` -- enumerated range against observed

| zone | min | max |
|---|---|---|
| upper | -0.13 | +0.40 | 
| middle | -0.29 | +0.20 | 
| outside | -0.13 | +0.20 | 

enumerated over the whole term structure: **-0.29 to +0.40**

observed over 2436 readings: **-0.1800 to +0.4000**

The observed maximum EQUALS the enumerated ceiling, which is the positive control for the enumeration: a term structure counted wrongly would not land on the same number the tape produced.

### C5 `bb_confidence_boost` -- derived ceiling, NOT observed

| term | source | range |
|---|---|---|
| landing strip | `0.15 + consolidation_strength * 0.20`, strength bounded to 1.0 twice in `bb_proximity.py` | +0.15 to +0.35 |
| tightening | `detect_landing_strip_v2` `0.08 + 0.17 * length_factor * tightness_factor`, both factors bounded to 1.0 | +0.08 to +0.25 |

The two detections are independent and both can fire on one reading, so the sum reaches **+0.60** -- more than twice the 0.25 floor. Observed maximum over 2436 readings: **+0.1437**, so the ceiling is DERIVED and the tape does not reach it. This is stated rather than measured on purpose.

### C6 the two favours land on the same reading

| question | rows |
|---|---|
| both favours strictly positive | 3 |
| their sum at or above the 0.25 floor | 31 |
| BEFORE `eff_confidence` below zero | 316 |

They compound. `position_boost` is built on every tick and `bb_confidence_boost` on every tick a pattern is detected, from the SAME reading, and the BB-priority arm adds a third on top. That is why the repair sums the three and divides once rather than relaxing one floor at a time.

### calibration verdict: PASSED

## Decision sweep

| bars | rows | on the arm | SCRUM before | SCRUM after | FOLD before | FOLD after |
|---|---|---|---|---|---|---|
| 35 | 406 | 300 | 22 | 15 | 28 | 28 |
| 40 | 406 | 300 | 18 | 4 | 14 | 11 |
| 60 | 406 | 300 | 19 | 9 | 18 | 7 |
| 100 | 406 | 300 | 17 | 2 | 16 | 10 |
| 200 | 406 | 300 | 19 | 2 | 18 | 12 |
| 400 | 406 | 300 | 19 | 2 | 18 | 12 |

SCRUM verdict flips: **86**   FOLD verdict flips: **48**

| side | FIRE -> shut | shut -> FIRE | on the arm | off the arm |
|---|---|---|---|---|
| SCRUM | 83 | 3 | 71 | 15 |
| FOLD | 40 | 8 | 35 | 13 |

### every SCRUM flip, named

| tablet@bars | eff_dir | consensus | pos skew | BB skew | BEFORE judged | BEFORE floor | AFTER judged | AFTER floor | on arm | before | after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ASM@35 | BULLISH | 0.3017 | -0.08 | +0.00 | 0.2217 | 0.2500 | 0.3017 | 0.2717 | no | shut | FIRE |
| ESP@35 | BULLISH | 0.1452 | +0.12 | +0.00 | 0.2652 | 0.1923 | 0.1452 | 0.1761 | yes | FIRE | shut |
| LMTS@35 | BULLISH | 0.1359 | +0.08 | +0.00 | 0.2159 | 0.1923 | 0.1359 | 0.1812 | yes | FIRE | shut |
| PLU@35 | BULLISH | 0.1144 | +0.20 | +0.00 | 0.3144 | 0.1923 | 0.1144 | 0.1667 | yes | FIRE | shut |
| PROS@35 | BULLISH | 0.1057 | +0.20 | +0.00 | 0.3057 | 0.1923 | 0.1057 | 0.1667 | yes | FIRE | shut |
| SUP@35 | BULLISH | 0.1913 | +0.08 | +0.00 | 0.2713 | 0.2500 | 0.1913 | 0.2315 | no | FIRE | shut |
| TRIA@35 | BULLISH | 0.1503 | +0.20 | +0.00 | 0.3503 | 0.1923 | 0.1503 | 0.1667 | yes | FIRE | shut |
| XYO@35 | BULLISH | 0.1381 | +0.08 | +0.00 | 0.2181 | 0.1923 | 0.1381 | 0.1812 | yes | FIRE | shut |
| ZKP@35 | BULLISH | 0.1396 | +0.20 | +0.00 | 0.3396 | 0.1923 | 0.1396 | 0.1667 | yes | FIRE | shut |
| AKT@40 | BULLISH | 0.1325 | +0.20 | +0.00 | 0.3325 | 0.1923 | 0.1325 | 0.1667 | yes | FIRE | shut |
| BAND@40 | BULLISH | 0.1742 | +0.20 | +0.00 | 0.3742 | 0.2500 | 0.1742 | 0.2083 | no | FIRE | shut |
| CHECK@40 | BULLISH | 0.0726 | +0.22 | +0.00 | 0.2926 | 0.1923 | 0.0726 | 0.1645 | yes | FIRE | shut |
| CTX@40 | BULLISH | 0.1738 | +0.12 | +0.00 | 0.2938 | 0.1923 | 0.1738 | 0.1761 | yes | FIRE | shut |
| ESP@40 | BULLISH | 0.1739 | +0.12 | +0.00 | 0.2939 | 0.1923 | 0.1739 | 0.1761 | yes | FIRE | shut |
| HIGH@40 | BULLISH | 0.0857 | +0.20 | +0.00 | 0.2857 | 0.1923 | 0.0857 | 0.1667 | yes | FIRE | shut |
| HOME@40 | BULLISH | 0.1072 | +0.20 | +0.00 | 0.3072 | 0.1923 | 0.1072 | 0.1667 | yes | FIRE | shut |
| PLU@40 | BULLISH | 0.0274 | +0.30 | +0.00 | 0.3274 | 0.1923 | 0.0274 | 0.1562 | yes | FIRE | shut |
| PROS@40 | BULLISH | 0.0377 | +0.30 | +0.00 | 0.3377 | 0.1923 | 0.0377 | 0.1562 | yes | FIRE | shut |
| RNBW@40 | BULLISH | 0.1399 | +0.12 | +0.00 | 0.2599 | 0.2500 | 0.1399 | 0.2232 | no | FIRE | shut |
| SUP@40 | BULLISH | 0.0876 | +0.18 | +0.00 | 0.2676 | 0.2500 | 0.0876 | 0.2119 | no | FIRE | shut |
| TRIA@40 | BULLISH | 0.1451 | +0.20 | +0.00 | 0.3451 | 0.1923 | 0.1451 | 0.1667 | yes | FIRE | shut |
| WLFI@40 | BULLISH | 0.1340 | +0.20 | +0.00 | 0.3340 | 0.1923 | 0.1340 | 0.1667 | yes | FIRE | shut |
| ZKP@40 | BULLISH | 0.0524 | +0.20 | +0.00 | 0.2524 | 0.1923 | 0.0524 | 0.1667 | yes | FIRE | shut |
| BAL@60 | BULLISH | 0.1541 | +0.08 | +0.00 | 0.2341 | 0.1923 | 0.1541 | 0.1812 | yes | FIRE | shut |
| BAND@60 | BULLISH | 0.1257 | +0.25 | +0.00 | 0.3757 | 0.2500 | 0.1257 | 0.2000 | no | FIRE | shut |
| CTX@60 | BULLISH | 0.0698 | +0.17 | +0.00 | 0.2398 | 0.1923 | 0.0698 | 0.1701 | yes | FIRE | shut |
| EDGEX@60 | NEUTRAL | 0.0082 | +0.05 | +0.14 | 0.2019 | 0.1923 | 0.0082 | 0.1674 | yes | FIRE | shut |
| ENA@60 | BULLISH | 0.2472 | -0.08 | +0.00 | 0.1672 | 0.1923 | 0.2472 | 0.2049 | yes | shut | FIRE |
| ESP@60 | BULLISH | 0.0627 | +0.25 | +0.00 | 0.3127 | 0.1923 | 0.0627 | 0.1613 | yes | FIRE | shut |
| ETC@60 | BULLISH | 0.1526 | +0.05 | +0.00 | 0.2026 | 0.1923 | 0.1526 | 0.1852 | yes | FIRE | shut |
| HIGH@60 | BULLISH | 0.0496 | +0.20 | +0.00 | 0.2496 | 0.1923 | 0.0496 | 0.1667 | yes | FIRE | shut |
| HOME@60 | BULLISH | 0.0891 | +0.20 | +0.00 | 0.2891 | 0.1923 | 0.0891 | 0.1667 | yes | FIRE | shut |
| IMU@60 | BULLISH | 0.1051 | +0.20 | +0.00 | 0.3051 | 0.1923 | 0.1051 | 0.1667 | yes | FIRE | shut |
| LMTS@60 | BULLISH | 0.1350 | +0.13 | +0.00 | 0.2650 | 0.1923 | 0.1350 | 0.1748 | yes | FIRE | shut |
| TOSHI@60 | BULLISH | 0.2467 | -0.08 | +0.00 | 0.1667 | 0.1923 | 0.2467 | 0.2049 | yes | shut | FIRE |
| TRIA@60 | BULLISH | 0.1118 | +0.25 | +0.00 | 0.3618 | 0.1923 | 0.1118 | 0.1613 | yes | FIRE | shut |
| WLFI@60 | BULLISH | 0.0761 | +0.25 | +0.00 | 0.3261 | 0.1923 | 0.0761 | 0.1613 | yes | FIRE | shut |
| AKT@100 | BULLISH | 0.1505 | +0.20 | +0.00 | 0.3505 | 0.1923 | 0.1505 | 0.1667 | yes | FIRE | shut |
| APR@100 | BULLISH | 0.1104 | +0.22 | +0.00 | 0.3304 | 0.1923 | 0.1104 | 0.1645 | yes | FIRE | shut |
| BAL@100 | BULLISH | 0.1388 | +0.08 | +0.00 | 0.2188 | 0.1923 | 0.1388 | 0.1812 | yes | FIRE | shut |
| BAND@100 | BULLISH | 0.1639 | +0.30 | +0.00 | 0.4639 | 0.2500 | 0.1639 | 0.1923 | no | FIRE | shut |
| CHECK@100 | NEUTRAL | 0.0047 | +0.27 | +0.00 | 0.2747 | 0.1923 | 0.0047 | 0.1592 | yes | FIRE | shut |
| CTX@100 | BULLISH | 0.1358 | +0.22 | +0.00 | 0.3558 | 0.1923 | 0.1358 | 0.1645 | yes | FIRE | shut |
| ESP@100 | BULLISH | 0.1220 | +0.30 | +0.00 | 0.4220 | 0.1923 | 0.1220 | 0.1562 | yes | FIRE | shut |
| HIGH@100 | BULLISH | 0.0719 | +0.25 | +0.00 | 0.3219 | 0.1923 | 0.0719 | 0.1613 | yes | FIRE | shut |
| PROS@100 | BULLISH | 0.0102 | +0.40 | +0.00 | 0.4102 | 0.1923 | 0.0102 | 0.1471 | yes | FIRE | shut |
| RNBW@100 | BULLISH | 0.1333 | +0.22 | +0.00 | 0.3533 | 0.2500 | 0.1333 | 0.2049 | no | FIRE | shut |
| SAPIEN@100 | BULLISH | 0.1691 | +0.15 | +0.00 | 0.3191 | 0.2500 | 0.1691 | 0.2174 | no | FIRE | shut |
| TRIA@100 | BULLISH | 0.1006 | +0.25 | +0.00 | 0.3506 | 0.1923 | 0.1006 | 0.1613 | yes | FIRE | shut |
| USDT@100 | BULLISH | 0.1695 | +0.10 | +0.00 | 0.2695 | 0.1923 | 0.1695 | 0.1786 | yes | FIRE | shut |
| WLFI@100 | NEUTRAL | 0.0064 | +0.22 | +0.00 | 0.2264 | 0.1923 | 0.0064 | 0.1645 | yes | FIRE | shut |
| ZKP@100 | BULLISH | 0.0194 | +0.25 | +0.00 | 0.2694 | 0.1923 | 0.0194 | 0.1613 | yes | FIRE | shut |
| AKT@200 | BULLISH | 0.1506 | +0.20 | +0.00 | 0.3506 | 0.1923 | 0.1506 | 0.1667 | yes | FIRE | shut |
| APR@200 | BULLISH | 0.1156 | +0.22 | +0.00 | 0.3356 | 0.1923 | 0.1156 | 0.1645 | yes | FIRE | shut |
| BAL@200 | BULLISH | 0.1472 | +0.13 | +0.00 | 0.2772 | 0.1923 | 0.1472 | 0.1748 | yes | FIRE | shut |
| BAND@200 | BULLISH | 0.1694 | +0.30 | +0.00 | 0.4694 | 0.2500 | 0.1694 | 0.1923 | no | FIRE | shut |
| CHECK@200 | NEUTRAL | 0.0060 | +0.27 | +0.00 | 0.2760 | 0.1923 | 0.0060 | 0.1592 | yes | FIRE | shut |
| CTX@200 | BULLISH | 0.1411 | +0.22 | +0.00 | 0.3611 | 0.1923 | 0.1411 | 0.1645 | yes | FIRE | shut |
| ESP@200 | BULLISH | 0.1279 | +0.30 | +0.00 | 0.4279 | 0.1923 | 0.1279 | 0.1562 | yes | FIRE | shut |
| HIGH@200 | BULLISH | 0.0775 | +0.25 | +0.00 | 0.3275 | 0.1923 | 0.0775 | 0.1613 | yes | FIRE | shut |
| IMU@200 | BULLISH | 0.0231 | +0.17 | +0.00 | 0.1931 | 0.1923 | 0.0231 | 0.1701 | yes | FIRE | shut |
| PROS@200 | BULLISH | 0.0159 | +0.40 | +0.00 | 0.4159 | 0.1923 | 0.0159 | 0.1471 | yes | FIRE | shut |
| RNBW@200 | BULLISH | 0.1181 | +0.22 | +0.00 | 0.3381 | 0.2500 | 0.1181 | 0.2049 | no | FIRE | shut |
| SAPIEN@200 | BULLISH | 0.1691 | +0.15 | +0.00 | 0.3191 | 0.2500 | 0.1691 | 0.2174 | no | FIRE | shut |
| TGBP@200 | BULLISH | 0.1424 | +0.05 | +0.00 | 0.1924 | 0.1923 | 0.1424 | 0.1852 | yes | FIRE | shut |
| TRIA@200 | BULLISH | 0.1001 | +0.25 | +0.00 | 0.3501 | 0.1923 | 0.1001 | 0.1613 | yes | FIRE | shut |
| USDT@200 | BULLISH | 0.1747 | +0.10 | +0.00 | 0.2747 | 0.1923 | 0.1747 | 0.1786 | yes | FIRE | shut |
| WLFI@200 | NEUTRAL | 0.0009 | +0.22 | +0.00 | 0.2209 | 0.1923 | 0.0009 | 0.1645 | yes | FIRE | shut |
| ZKP@200 | NEUTRAL | 0.0011 | +0.25 | +0.00 | 0.2511 | 0.1923 | 0.0011 | 0.1613 | yes | FIRE | shut |
| AKT@400 | BULLISH | 0.1506 | +0.20 | +0.00 | 0.3506 | 0.1923 | 0.1506 | 0.1667 | yes | FIRE | shut |
| APR@400 | BULLISH | 0.1156 | +0.22 | +0.00 | 0.3356 | 0.1923 | 0.1156 | 0.1645 | yes | FIRE | shut |
| BAL@400 | BULLISH | 0.1472 | +0.13 | +0.00 | 0.2772 | 0.1923 | 0.1472 | 0.1748 | yes | FIRE | shut |
| BAND@400 | BULLISH | 0.1694 | +0.30 | +0.00 | 0.4694 | 0.2500 | 0.1694 | 0.1923 | no | FIRE | shut |
| CHECK@400 | NEUTRAL | 0.0060 | +0.27 | +0.00 | 0.2760 | 0.1923 | 0.0060 | 0.1592 | yes | FIRE | shut |
| CTX@400 | BULLISH | 0.1411 | +0.22 | +0.00 | 0.3611 | 0.1923 | 0.1411 | 0.1645 | yes | FIRE | shut |
| ESP@400 | BULLISH | 0.1279 | +0.30 | +0.00 | 0.4279 | 0.1923 | 0.1279 | 0.1562 | yes | FIRE | shut |
| HIGH@400 | BULLISH | 0.0775 | +0.25 | +0.00 | 0.3275 | 0.1923 | 0.0775 | 0.1613 | yes | FIRE | shut |
| IMU@400 | BULLISH | 0.0231 | +0.17 | +0.00 | 0.1931 | 0.1923 | 0.0231 | 0.1701 | yes | FIRE | shut |
| PROS@400 | BULLISH | 0.0159 | +0.40 | +0.00 | 0.4159 | 0.1923 | 0.0159 | 0.1471 | yes | FIRE | shut |
| RNBW@400 | BULLISH | 0.1181 | +0.22 | +0.00 | 0.3381 | 0.2500 | 0.1181 | 0.2049 | no | FIRE | shut |
| SAPIEN@400 | BULLISH | 0.1691 | +0.15 | +0.00 | 0.3191 | 0.2500 | 0.1691 | 0.2174 | no | FIRE | shut |
| TGBP@400 | BULLISH | 0.1424 | +0.05 | +0.00 | 0.1924 | 0.1923 | 0.1424 | 0.1852 | yes | FIRE | shut |
| TRIA@400 | BULLISH | 0.1001 | +0.25 | +0.00 | 0.3501 | 0.1923 | 0.1001 | 0.1613 | yes | FIRE | shut |
| USDT@400 | BULLISH | 0.1747 | +0.10 | +0.00 | 0.2747 | 0.1923 | 0.1747 | 0.1786 | yes | FIRE | shut |
| WLFI@400 | BULLISH | 0.0196 | +0.22 | +0.00 | 0.2396 | 0.1923 | 0.0196 | 0.1645 | yes | FIRE | shut |
| ZKP@400 | NEUTRAL | 0.0011 | +0.25 | +0.00 | 0.2511 | 0.1923 | 0.0011 | 0.1613 | yes | FIRE | shut |

### every FOLD flip, named

| tablet@bars | eff_dir | consensus | pos skew | BB skew | BEFORE judged | BEFORE floor | AFTER judged | AFTER floor | on arm | before | after |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EDGEX@35 | BEARISH | 0.0859 | +0.00 | +0.14 | 0.2296 | 0.1923 | 0.0859 | 0.1732 | yes | FIRE | shut |
| ERA@35 | BEARISH | 0.2647 | -0.03 | +0.00 | 0.2347 | 0.2500 | 0.2647 | 0.2577 | no | shut | FIRE |
| CRV@40 | BEARISH | 0.2128 | -0.08 | +0.00 | 0.1328 | 0.1923 | 0.2128 | 0.2049 | yes | shut | FIRE |
| EDGEX@40 | BEARISH | 0.0740 | +0.00 | +0.14 | 0.2177 | 0.1923 | 0.0740 | 0.1732 | yes | FIRE | shut |
| FLOW@40 | BEARISH | 0.1757 | +0.00 | +0.14 | 0.3176 | 0.2500 | 0.1757 | 0.2189 | no | FIRE | shut |
| GEOD@40 | BEARISH | 0.1797 | +0.10 | +0.00 | 0.2797 | 0.2500 | 0.1797 | 0.2273 | no | FIRE | shut |
| WIF@40 | BEARISH | 0.1500 | +0.10 | +0.00 | 0.2500 | 0.1923 | 0.1500 | 0.1786 | yes | FIRE | shut |
| CHECK@60 | BEARISH | 0.0757 | +0.22 | +0.00 | 0.2957 | 0.1923 | 0.0757 | 0.1645 | yes | FIRE | shut |
| EDGEX@60 | NEUTRAL | 0.0082 | +0.05 | +0.14 | 0.2019 | 0.1923 | 0.0082 | 0.1674 | yes | FIRE | shut |
| FLOW@60 | BEARISH | 0.1713 | +0.05 | +0.14 | 0.3632 | 0.2500 | 0.1713 | 0.2097 | no | FIRE | shut |
| GEOD@60 | BEARISH | 0.1165 | +0.15 | +0.00 | 0.2665 | 0.2500 | 0.1165 | 0.2174 | no | FIRE | shut |
| IRYS@60 | BEARISH | 0.0520 | +0.05 | +0.14 | 0.2457 | 0.1923 | 0.0520 | 0.1674 | yes | FIRE | shut |
| L3@60 | BEARISH | 0.2375 | +0.02 | +0.00 | 0.2575 | 0.2500 | 0.2375 | 0.2451 | no | FIRE | shut |
| PLU@60 | BEARISH | 0.0166 | +0.25 | +0.00 | 0.2666 | 0.1923 | 0.0166 | 0.1613 | yes | FIRE | shut |
| PROS@60 | BEARISH | 0.0584 | +0.35 | +0.00 | 0.4084 | 0.1923 | 0.0584 | 0.1515 | yes | FIRE | shut |
| SPA@60 | BEARISH | 0.1725 | +0.05 | +0.00 | 0.2225 | 0.1923 | 0.1725 | 0.1852 | yes | FIRE | shut |
| TROLL@60 | BEARISH | 0.1248 | +0.15 | +0.00 | 0.2748 | 0.1923 | 0.1248 | 0.1724 | yes | FIRE | shut |
| ZKP@60 | BEARISH | 0.0426 | +0.20 | +0.00 | 0.2426 | 0.1923 | 0.0426 | 0.1667 | yes | FIRE | shut |
| AURORA@100 | BEARISH | 0.1018 | +0.10 | +0.00 | 0.2018 | 0.1923 | 0.1018 | 0.1786 | yes | FIRE | shut |
| BADGER@100 | BEARISH | 0.2280 | -0.05 | +0.00 | 0.1780 | 0.1923 | 0.2280 | 0.2000 | yes | shut | FIRE |
| CHECK@100 | NEUTRAL | 0.0047 | +0.27 | +0.00 | 0.2747 | 0.1923 | 0.0047 | 0.1592 | yes | FIRE | shut |
| EDGEX@100 | BEARISH | 0.0797 | +0.00 | +0.14 | 0.2234 | 0.1923 | 0.0797 | 0.1732 | yes | FIRE | shut |
| FLOW@100 | BEARISH | 0.2172 | +0.00 | +0.14 | 0.3591 | 0.2500 | 0.2172 | 0.2189 | no | FIRE | shut |
| GEOD@100 | BEARISH | 0.1559 | +0.10 | +0.00 | 0.2559 | 0.2500 | 0.1559 | 0.2273 | no | FIRE | shut |
| PLU@100 | BEARISH | 0.0365 | +0.20 | +0.00 | 0.2365 | 0.1923 | 0.0365 | 0.1667 | yes | FIRE | shut |
| SKL@100 | BEARISH | 0.2236 | -0.05 | +0.00 | 0.1736 | 0.1923 | 0.2236 | 0.2000 | yes | shut | FIRE |
| SUP@100 | BEARISH | 0.0771 | +0.18 | +0.00 | 0.2571 | 0.2500 | 0.0771 | 0.2119 | no | FIRE | shut |
| WLFI@100 | NEUTRAL | 0.0064 | +0.22 | +0.00 | 0.2264 | 0.1923 | 0.0064 | 0.1645 | yes | FIRE | shut |
| AURORA@200 | BEARISH | 0.1075 | +0.10 | +0.00 | 0.2075 | 0.1923 | 0.1075 | 0.1786 | yes | FIRE | shut |
| BADGER@200 | BEARISH | 0.2337 | -0.05 | +0.00 | 0.1837 | 0.1923 | 0.2337 | 0.2000 | yes | shut | FIRE |
| CHECK@200 | NEUTRAL | 0.0060 | +0.27 | +0.00 | 0.2760 | 0.1923 | 0.0060 | 0.1592 | yes | FIRE | shut |
| EDGEX@200 | BEARISH | 0.0854 | +0.00 | +0.14 | 0.2291 | 0.1923 | 0.0854 | 0.1732 | yes | FIRE | shut |
| GEOD@200 | BEARISH | 0.1613 | +0.10 | +0.00 | 0.2613 | 0.2500 | 0.1613 | 0.2273 | no | FIRE | shut |
| PLU@200 | BEARISH | 0.0365 | +0.20 | +0.00 | 0.2365 | 0.1923 | 0.0365 | 0.1667 | yes | FIRE | shut |
| SKL@200 | BEARISH | 0.2239 | -0.05 | +0.00 | 0.1739 | 0.1923 | 0.2239 | 0.2000 | yes | shut | FIRE |
| SUP@200 | BEARISH | 0.0818 | +0.18 | +0.00 | 0.2618 | 0.2500 | 0.0818 | 0.2119 | no | FIRE | shut |
| WLFI@200 | NEUTRAL | 0.0009 | +0.22 | +0.00 | 0.2209 | 0.1923 | 0.0009 | 0.1645 | yes | FIRE | shut |
| ZKP@200 | NEUTRAL | 0.0011 | +0.25 | +0.00 | 0.2511 | 0.1923 | 0.0011 | 0.1613 | yes | FIRE | shut |
| AURORA@400 | BEARISH | 0.1075 | +0.10 | +0.00 | 0.2075 | 0.1923 | 0.1075 | 0.1786 | yes | FIRE | shut |
| BADGER@400 | BEARISH | 0.2337 | -0.05 | +0.00 | 0.1837 | 0.1923 | 0.2337 | 0.2000 | yes | shut | FIRE |
| CHECK@400 | NEUTRAL | 0.0060 | +0.27 | +0.00 | 0.2760 | 0.1923 | 0.0060 | 0.1592 | yes | FIRE | shut |
| EDGEX@400 | BEARISH | 0.0854 | +0.00 | +0.14 | 0.2291 | 0.1923 | 0.0854 | 0.1732 | yes | FIRE | shut |
| GEOD@400 | BEARISH | 0.1613 | +0.10 | +0.00 | 0.2613 | 0.2500 | 0.1613 | 0.2273 | no | FIRE | shut |
| HOME@400 | BEARISH | 0.0783 | +0.12 | +0.00 | 0.1983 | 0.1923 | 0.0783 | 0.1761 | yes | FIRE | shut |
| PLU@400 | BEARISH | 0.0365 | +0.20 | +0.00 | 0.2365 | 0.1923 | 0.0365 | 0.1667 | yes | FIRE | shut |
| SKL@400 | BEARISH | 0.2239 | -0.05 | +0.00 | 0.1739 | 0.1923 | 0.2239 | 0.2000 | yes | shut | FIRE |
| SUP@400 | BEARISH | 0.0818 | +0.18 | +0.00 | 0.2618 | 0.2500 | 0.0818 | 0.2119 | no | FIRE | shut |
| ZKP@400 | NEUTRAL | 0.0011 | +0.25 | +0.00 | 0.2511 | 0.1923 | 0.0011 | 0.1613 | yes | FIRE | shut |

### the sign of the favour explains every flip

| side | direction | favour > 0 | favour < 0 | favour == 0 |
|---|---|---|---|---|
| SCRUM | FIRE -> shut | 83 | 0 | 0 |
| SCRUM | shut -> FIRE | 0 | 3 | 0 |
| FOLD | FIRE -> shut | 40 | 0 | 0 |
| FOLD | shut -> FIRE | 0 | 8 | 0 |

A trade that STOPS firing is a reading a POSITIVE favour had carried over the floor. A trade that STARTS firing is a reading a NEGATIVE favour had dragged under it -- the mirror of issue #102's finding that the only rows its arm could still refuse were ones a negative `position_boost` had already pushed below zero. Rows in the wrong column, or with no favour at all: **0**.


### what varies with tape length, and why one length is a false green

| bars | rows | `position_boost` non-zero | its min | its max | `bb_confidence_boost` non-zero |
|---|---|---|---|---|---|
| 35 | 406 | 63 | -0.08 | +0.20 | 4 |
| 40 | 406 | 108 | -0.13 | +0.30 | 4 |
| 60 | 406 | 266 | -0.13 | +0.35 | 4 |
| 100 | 406 | 248 | -0.18 | +0.40 | 4 |
| 200 | 406 | 249 | -0.18 | +0.40 | 4 |
| 400 | 406 | 249 | -0.18 | +0.40 | 4 |

`position_boost` grows with the tape, and its CEILING grows with it: the market-structure term is guarded by `len(candles) >= 60`, so it contributes nothing at 35 or 40 bars. A sweep run at 35 bars alone would have measured a largest favour of +0.20, under the 0.25 floor, and concluded this gate could always refuse. That is the false green the six lengths exist to prevent.

`bb_confidence_boost` is the opposite and matches issue #102's finding about the proximity condition: it is non-zero on the SAME number of rows at every length, because both detectors read a trailing window rather than the whole tape.

## The measured range of every quantity in the gate

| quantity | min | max | median |
|---|---|---|---|
| consensus_confidence | +0.0002 | +0.3402 | +0.0731 |
| position_boost | -0.1800 | +0.4000 | +0.0000 |
| bb_confidence_boost | +0.0000 | +0.1437 | +0.0000 |
| eff_confidence | -0.1254 | +0.4694 | +0.0686 |

Rows whose BEFORE `eff_confidence` cleared the standing 0.25 floor while the MEASURED consensus confidence did not: **111**. The favour, not the measurement, is what carried them.

