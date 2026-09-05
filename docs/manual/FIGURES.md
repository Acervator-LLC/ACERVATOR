# Figure Inventory

Reference for the images embedded in the Acervator product manual. The manual
carries 38 images across 29 of its 44 pages. The manual text is in
[README.md](README.md) and the part files listed there.

Two figure sets reach the built PDF, and this file inventories both. The 38
above come out of the source PDF's own pages, and
`tools/extract_product_manual.py` unpacks them. A second set of 39 VWAP charts
belongs to [Part 9](10-live-trade-history.md), built from the operator's venue
export rather than from the PDF. The two sets never mix: they land in
directories of their own, `artifacts/manual-figures/` and
`artifacts/vwap-charts/`. Counting both, the built manual embeds 77 images.

## Where the figures are written

The images are captured output, so they are not tracked.
`tools/extract_product_manual.py` writes them to `artifacts/manual-figures/`
under the repository root, a path `.gitignore` excludes. Re-create them by
running that tool with `--pdf` set to the manual PDF.

File names carry the source page and the image index on that page,
`p<page>-i<index>.png`. Every image is a PNG.

## Inventory

| Page | Index | File | Bytes | Pixels | Page carries text |
| ---: | ----: | ---- | ----: | ------ | ----------------- |
| 15 | 0 | `p15-i0.png` | 181,299 | 1918 x 1198 | yes |
| 16 | 0 | `p16-i0.png` | 33,067 | 1371 x 777 | yes |
| 17 | 0 | `p17-i0.png` | 20,809 | 1377 x 776 | yes |
| 18 | 0 | `p18-i0.png` | 28,853 | 1363 x 551 | yes |
| 19 | 0 | `p19-i0.png` | 36,634 | 1363 x 765 | yes |
| 20 | 0 | `p20-i0.png` | 32,032 | 1357 x 727 | yes |
| 21 | 0 | `p21-i0.png` | 25,818 | 1356 x 501 | yes |
| 22 | 0 | `p22-i0.png` | 35,039 | 1357 x 683 | yes |
| 22 | 1 | `p22-i1.png` | 10,330 | 1353 x 207 | yes |
| 23 | 0 | `p23-i0.png` | 16,970 | 1375 x 325 | yes |
| 24 | 0 | `p24-i0.png` | 34,716 | 1367 x 813 | no |
| 24 | 1 | `p24-i1.png` | 34,240 | 1367 x 762 | no |
| 25 | 0 | `p25-i0.png` | 33,255 | 1356 x 677 | yes |
| 26 | 0 | `p26-i0.png` | 16,553 | 1356 x 321 | yes |
| 26 | 1 | `p26-i1.png` | 19,173 | 957 x 171 | yes |
| 26 | 2 | `p26-i2.png` | 10,460 | 958 x 158 | yes |
| 27 | 0 | `p27-i0.png` | 2,568 | 1072 x 45 | yes |
| 27 | 1 | `p27-i1.png` | 53,618 | 741 x 777 | yes |
| 29 | 0 | `p29-i0.png` | 29,389 | 1917 x 248 | yes |
| 29 | 1 | `p29-i1.png` | 91,364 | 1917 x 1003 | yes |
| 30 | 0 | `p30-i0.png` | 137,535 | 1918 x 1002 | yes |
| 30 | 1 | `p30-i1.png` | 547,512 | 1917 x 1005 | yes |
| 31 | 0 | `p31-i0.png` | 201,916 | 1912 x 1000 | yes |
| 32 | 0 | `p32-i0.png` | 254,254 | 1916 x 1001 | yes |
| 32 | 1 | `p32-i1.png` | 265,640 | 1918 x 1197 | yes |
| 33 | 0 | `p33-i0.png` | 109,070 | 1917 x 1127 | yes |
| 34 | 0 | `p34-i0.png` | 290,497 | 1918 x 1001 | yes |
| 34 | 1 | `p34-i1.png` | 16,988 | 872 x 837 | yes |
| 35 | 0 | `p35-i0.png` | 42,467 | 881 x 841 | yes |
| 36 | 0 | `p36-i0.png` | 30,857 | 877 x 840 | no |
| 37 | 0 | `p37-i0.png` | 45,908 | 873 x 840 | no |
| 38 | 0 | `p38-i0.png` | 37,114 | 876 x 842 | no |
| 39 | 0 | `p39-i0.png` | 29,314 | 877 x 841 | no |
| 40 | 0 | `p40-i0.png` | 37,022 | 885 x 840 | no |
| 41 | 0 | `p41-i0.png` | 25,332 | 872 x 838 | no |
| 42 | 0 | `p42-i0.png` | 41,980 | 878 x 840 | no |
| 43 | 0 | `p43-i0.png` | 45,467 | 876 x 841 | no |
| 44 | 0 | `p44-i0.png` | 52,328 | 881 x 842 | no |

## Pages that carry a figure and no text

Page 24, and pages 36 to 44, extract zero visible characters. Their whole
content is the image listed above. Page 24 holds two images; pages 36 to 44
hold one each.

Page 28 is the only page from 15 to 35 that carries text and no image.

## Where each figure is described

Every figure carries a description of the controls, columns, colours and
numbers it shows, written from the code behind the screen.

| Pages | Figures | Described in |
| ----- | ------: | ------------ |
| 15 to 27 | 18 | [06-trading-tab.md](06-trading-tab.md) |
| 29 to 44 | 20 | [08-tabs.md](08-tabs.md) |

The nine text-less Settings pages, 36 to 44, take one section each in
[08-tabs.md](08-tabs.md), named for the page they show.
[06-trading-tab.md](06-trading-tab.md) holds its eighteen figures in page
order. [08-tabs.md](08-tabs.md) holds each of its twenty inside the section it
illustrates, and those sections run in the order the tab list in
[04-manual-parts.md](04-manual-parts.md) sets.

## The second figure set — Part 9's VWAP charts

39 charts, one per charted base plus one combined view.
[10-live-trade-history.md](10-live-trade-history.md) embeds and describes every
one. They carry no page number, because the source PDF is not their source: a
generator drew them from the operator's Coinbase export, over the same 5,661
fills that part opens with. They live in `artifacts/vwap-charts/`, a directory
of their own beside `artifacts/manual-figures/`, under the same `.gitignore`
rule. This repository tracks no chart.

File names carry the asset, `vwap_<ASSET>.png`, and the combined view is
`vwap_combined.png`.

| File | Asset | Fills | Described in |
| ---- | ----- | ----: | ------------ |
| `vwap_combined.png` | top eight by fill count | 3,113 | [10-live-trade-history.md](10-live-trade-history.md), under the combined-chart section |
| `vwap_RAVE.png` | RAVE | 900 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_CHIP.png` | CHIP | 495 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_BILL.png` | BILL | 459 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ALLO.png` | ALLO | 322 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ZEC.png` | ZEC | 261 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_KAT.png` | KAT | 230 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_BIO.png` | BIO | 226 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_SPK.png` | SPK | 220 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ORCA.png` | ORCA | 196 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_BONK.png` | BONK | 191 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_CAP.png` | CAP | 178 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_PENGU.png` | PENGU | 159 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_VVV.png` | VVV | 147 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ETH.png` | ETH | 141 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_BTC.png` | BTC | 124 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_TAO.png` | TAO | 124 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ONDO.png` | ONDO | 119 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_XRP.png` | XRP | 119 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_IMU.png` | IMU | 113 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_BICO.png` | BICO | 87 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_LINK.png` | LINK | 83 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_DOGE.png` | DOGE | 80 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_SOL.png` | SOL | 77 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_GROVE.png` | GROVE | 75 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_SUI.png` | SUI | 74 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_RE.png` | RE | 73 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_XLM.png` | XLM | 73 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_HYPE.png` | HYPE | 66 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_PUMP.png` | PUMP | 63 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_NEAR.png` | NEAR | 58 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_HBAR.png` | HBAR | 25 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_AERO.png` | AERO | 24 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ENA.png` | ENA | 23 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_ADA.png` | ADA | 23 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_AGLD.png` | AGLD | 16 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_LTC.png` | LTC | 6 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_WLFI.png` | WLFI | 6 | [10-live-trade-history.md](10-live-trade-history.md) |
| `vwap_LSETH.png` | LSETH | 5 | [10-live-trade-history.md](10-live-trade-history.md) |

The 38 per-asset counts sum to 5,661. The combined view's 3,113 counts the
eight assets it draws, which the 38 rows already carry.

## What produces each set

| Set | Count | Producer | Reachable from this repository |
| --- | ----: | -------- | --- |
| Manual pages 15 to 44 | 38 | `write_figures` in `tools/extract_product_manual.py`, given the PDF | yes, with the PDF |
| Part 9 VWAP charts | 39 | a generator outside this repository | no |

`git log --all --diff-filter=ADR --name-only` reaches 1,606 distinct paths and
returns one whose name carries `vwap`,
`tests/test_vwap_band_scales_to_price.py`, which drives the Simulator's price
band rather than any chart. A pickaxe over every `.py` in every commit returns
nothing for `draw_combined`, `vwap_combined` or `buy_vwap`, against controls of
16 commits for `avg_entry`, 7 for `sync_ytd_trade_count`, and 0 for a coined
term. A fresh clone has 38 figures it can rebuild and 39 it cannot.

## The legacy manual's 55 figures

Source: LEGACY, the fourteen-part manual, 479 pages and 55 images. The three
figure sets stay apart, so a reader always knows which manual a picture came
from.

| Set | Count | Where the files are written |
| --- | ----: | --------------------------- |
| The operator's manual | 38 | `artifacts/manual-figures/` |
| The year-to-date charts | 39 | see [10-live-trade-history.md](10-live-trade-history.md) |
| The legacy fourteen-part manual | 55 | `artifacts/legacy-manual-figures/` |

`artifacts/` is excluded by `.gitignore`, so none of the three sets is tracked.
Re-create the legacy set by running `pypdf` over the fourteen part files and
writing each page image out; the file name carries the part, the page and the
image index on that page, as `<part>_p<page>_i<index>.png`.

Two instruments agree on the totals: the claim audit counted 479 pages and 55
images with `pypdf`, and a second extraction run over the same fourteen files
returned 479 and 55 again.

Only three of the fourteen legacy parts carry an image. Part 5b carries 4, Part
5c carries 2 and Part 8 carries 49. The other eleven parts carry none.

### Every one of the 55, and what it shows

Each row below was opened and read. The image index is the order `pypdf`
returns the images on a page, which is not always the order the page prints
them, so a row records what the picture shows rather than what the paragraph
above it says.

| Part | Page | Fig | Bytes | Pixels | sha256 | What it shows |
| ---- | ---: | --: | ----: | ------ | ------ | ------------- |
| 5b | 3 | 1 | 31,775 | 1037 x 589 | `75ef881b8841` | Battery outcomes by regime: 41 bull wins, 17 bear wins with 4 losses, 16 sideways wins, titled 74 wins and 4 losses of 78 |
| 5b | 4 | 1 | 33,037 | 1038 x 583 | `fb8117d187cc` | Median advantage per run by regime on a log axis: bull $2,300,000, sideways $5,625, bear $180 |
| 5b | 5 | 1 | 21,938 | 1039 x 467 | `9b108084119c` | Price-floor invariant compliance: 78 runs hold it, 0 violate |
| 5b | 6 | 1 | 41,633 | 1037 x 514 | `7283652ae18c` | Charge-up fee economics: $214 average fees unbundled against $87 bundled, titled a 59 percent fee reduction and a 0.3 percent uplift |
| 5c | 4 | 1 | 39,231 | 1037 x 588 | `6000cd234745` | Units held on the same $100: 0.002175 passive against 0.003918 for the accumulator, annotated 80.1 percent more |
| 5c | 5 | 1 | 72,941 | 1037 x 662 | `af9d647e4640` | Three-year price line with a spawn threshold at 70 percent of entry, an explode threshold at 98 percent, a shaded 20-tranche accumulation band, a spawn marker and an explode marker |
| 8 | 25 | 1 | 50,143 | 910 x 442 | `0815d17eae58` | CHIP cost-basis chart, 206 fills, Apr 22 to May 31. Bot VWAP 0.0828, average sell 0.0910, ratio 1.100 |
| 8 | 25 | 2 | 57,699 | 910 x 442 | `83d756128fb5` | RAVE cost-basis chart, 672 fills, Apr 21 to May 30. Bot VWAP 0.9734, average sell 0.9196, ratio 0.945 |
| 8 | 26 | 1 | 49,876 | 910 x 442 | `910bbfce4005` | BILL cost-basis chart, 144 fills, May 09 to May 31. Bot VWAP 0.0935, average sell 0.0987, ratio 1.055 |
| 8 | 26 | 2 | 47,604 | 910 x 442 | `935cb5f8a68d` | SPK cost-basis chart, 99 fills, Apr 23 to May 31. Bot VWAP 0.0355, average sell 0.0387, ratio 1.090 |
| 8 | 27 | 1 | 40,185 | 910 x 442 | `10d364b6dc4c` | BTC cost-basis chart, 47 fills, Apr 23 to May 31. Bot VWAP 77051.49, average sell 77749.50, ratio 1.009 |
| 8 | 27 | 2 | 49,946 | 910 x 442 | `79e99b5d4424` | KAT cost-basis chart, 95 fills, Apr 24 to May 30. Bot VWAP 0.0113, average sell 0.0128, ratio 1.135 |
| 8 | 28 | 1 | 43,412 | 910 x 442 | `3c0866a3b5b8` | ETH cost-basis chart, 58 fills, Apr 23 to May 31. Bot VWAP 2248.01, average sell 2313.48, ratio 1.029 |
| 8 | 28 | 2 | 46,128 | 910 x 442 | `5a040455cf20` | ZEC cost-basis chart, 81 fills, Apr 24 to May 30. Bot VWAP 459.14, average sell 530.20, ratio 1.155 |
| 8 | 36 | 1 | 59,888 | 910 x 442 | `88fe208a9027` | RAVE cost-basis chart, 745 fills, Apr 21 to Jun 05. Bot VWAP 0.8797, average sell 0.8713, ratio 0.990 |
| 8 | 37 | 1 | 52,755 | 910 x 442 | `66883901d4f1` | BILL cost-basis chart, 195 fills, May 09 to Jun 05. Bot VWAP 0.0903, average sell 0.0952, ratio 1.054 |
| 8 | 37 | 2 | 53,892 | 910 x 442 | `4559817bf70f` | CHIP cost-basis chart, 247 fills, Apr 22 to Jun 05. Bot VWAP 0.0743, average sell 0.0816, ratio 1.098 |
| 8 | 38 | 1 | 51,559 | 910 x 442 | `44ad779cc7f0` | SPK cost-basis chart, 138 fills, Apr 23 to Jun 05. Bot VWAP 0.0307, average sell 0.0304, ratio 0.988 |
| 8 | 38 | 2 | 49,018 | 910 x 442 | `a9a2a90aa033` | KAT cost-basis chart, 125 fills, Apr 24 to Jun 05. Bot VWAP 0.0097, average sell 0.0108, ratio 1.113 |
| 8 | 39 | 1 | 45,445 | 910 x 442 | `f64614336c84` | ETH cost-basis chart, 98 fills, Apr 23 to Jun 05. Bot VWAP 2098.32, average sell 2239.48, ratio 1.067 |
| 8 | 39 | 2 | 43,071 | 910 x 442 | `ce9d60f7647a` | BTC cost-basis chart, 87 fills, Apr 23 to Jun 05. Bot VWAP 72034.95, average sell 68257.38, ratio 0.948 |
| 8 | 40 | 1 | 51,859 | 910 x 442 | `49158a3cd7b4` | ZEC cost-basis chart, 156 fills, Apr 24 to Jun 05. Bot VWAP 449.91, average sell 491.24, ratio 1.092 |
| 8 | 44 | 1 | 59,888 | 910 x 442 | `88fe208a9027` | RAVE cost-basis chart, 745 fills, Apr 21 to Jun 05. Bot VWAP 0.8797, average sell 0.8713, ratio 0.990. Byte-identical to Part 8 page 36 figure 1 |
| 8 | 45 | 1 | 52,755 | 910 x 442 | `66883901d4f1` | BILL cost-basis chart, 195 fills, May 09 to Jun 05. Bot VWAP 0.0903, average sell 0.0952, ratio 1.054. Byte-identical to Part 8 page 37 figure 1 |
| 8 | 45 | 2 | 54,241 | 910 x 442 | `db38559a2542` | CHIP cost-basis chart, 248 fills, Apr 22 to Jun 05. Bot VWAP 0.0743, average sell 0.0803, ratio 1.081 |
| 8 | 46 | 1 | 51,559 | 910 x 442 | `44ad779cc7f0` | SPK cost-basis chart, 138 fills, Apr 23 to Jun 05. Bot VWAP 0.0307, average sell 0.0304, ratio 0.988. Byte-identical to Part 8 page 38 figure 1 |
| 8 | 46 | 2 | 49,018 | 910 x 442 | `a9a2a90aa033` | KAT cost-basis chart, 125 fills, Apr 24 to Jun 05. Bot VWAP 0.0097, average sell 0.0108, ratio 1.113. Byte-identical to Part 8 page 38 figure 2 |
| 8 | 47 | 1 | 45,445 | 910 x 442 | `f64614336c84` | ETH cost-basis chart, 98 fills, Apr 23 to Jun 05. Bot VWAP 2098.32, average sell 2239.48, ratio 1.067. Byte-identical to Part 8 page 39 figure 1 |
| 8 | 47 | 2 | 43,071 | 910 x 442 | `ce9d60f7647a` | BTC cost-basis chart, 87 fills, Apr 23 to Jun 05. Bot VWAP 72034.95, average sell 68257.38, ratio 0.948. Byte-identical to Part 8 page 39 figure 2 |
| 8 | 48 | 1 | 51,888 | 910 x 442 | `ecaf8227379d` | ZEC cost-basis chart, 158 fills, Apr 24 to Jun 05. Bot VWAP 449.91, average sell 484.87, ratio 1.078 |
| 8 | 74 | 1 | 60,888 | 910 x 442 | `97fa3501aebf` | RAVE cost-basis chart, 748 fills, Apr 21 to Jun 06. Bot VWAP 0.865769, average sell 0.863246, ratio 0.997 |
| 8 | 75 | 1 | 54,681 | 910 x 442 | `224bef980c1c` | CHIP cost-basis chart, 249 fills, Apr 22 to Jun 06. Bot VWAP 0.073352, average sell 0.080283, ratio 1.094 |
| 8 | 75 | 2 | 54,073 | 910 x 442 | `076a135885a4` | BILL cost-basis chart, 201 fills, May 09 to Jun 06. Bot VWAP 0.089805, average sell 0.093644, ratio 1.043 |
| 8 | 76 | 1 | 51,879 | 910 x 442 | `28c7298c06f2` | ZEC cost-basis chart, 164 fills, Apr 24 to Jun 06. Bot VWAP 446.158, average sell 484.872, ratio 1.087 |
| 8 | 76 | 2 | 51,541 | 910 x 442 | `37797e18b259` | SPK cost-basis chart, 140 fills, Apr 23 to Jun 06. Bot VWAP 0.030324, average sell 0.029364, ratio 0.968 |
| 8 | 77 | 1 | 51,763 | 910 x 442 | `bdb9351b7908` | BIO cost-basis chart, 138 fills, May 03 to Jun 06. Bot VWAP 0.038770, average sell 0.037447, ratio 0.966 |
| 8 | 77 | 2 | 48,990 | 910 x 442 | `6716ba602783` | ORCA cost-basis chart, 137 fills, Apr 27 to Jun 06. Bot VWAP 1.48185, average sell 1.57992, ratio 1.066 |
| 8 | 78 | 1 | 45,813 | 910 x 442 | `aa0bceeccfdc` | BONK cost-basis chart, 123 fills, Apr 12 to Jun 06. Bot VWAP 6.33564e-06, average sell 6.38218e-06, ratio 1.007 |
| 8 | 78 | 2 | 50,182 | 910 x 442 | `3ae8de55abb7` | KAT cost-basis chart, 127 fills, Apr 24 to Jun 06. Bot VWAP 0.009533, average sell 0.010166, ratio 1.066 |
| 8 | 79 | 1 | 45,575 | 910 x 442 | `9d4dc07e0cd5` | PENGU cost-basis chart, 92 fills, Apr 27 to Jun 06. Bot VWAP 0.008430, average sell 0.008046, ratio 0.954 |
| 8 | 79 | 2 | 44,450 | 910 x 442 | `b463f8883400` | ETH cost-basis chart, 98 fills, Apr 23 to Jun 05. Bot VWAP 2098.32, average sell 2239.48, ratio 1.067 |
| 8 | 80 | 1 | 41,860 | 910 x 442 | `c5ee3de3316d` | BTC cost-basis chart, 87 fills, Apr 23 to Jun 05. Bot VWAP 72034.9, average sell 68257.4, ratio 0.948 |
| 8 | 80 | 2 | 44,627 | 910 x 442 | `e594a45ab3a9` | ALLO cost-basis chart, 88 fills, May 29 to Jun 06. Bot VWAP 0.222914, average sell 0.253686, ratio 1.138 |
| 8 | 81 | 1 | 47,115 | 910 x 442 | `c02ef2709545` | VVV cost-basis chart, 86 fills, May 09 to Jun 06. Bot VWAP 16.3564, average sell 17.7337, ratio 1.084 |
| 8 | 81 | 2 | 44,042 | 910 x 442 | `40794a8ee57a` | ONDO cost-basis chart, 80 fills, May 07 to Jun 05. Bot VWAP 0.369446, average sell 0.397263, ratio 1.075 |
| 8 | 82 | 1 | 44,995 | 910 x 442 | `74d4df8cd628` | TAO cost-basis chart, 68 fills, May 02 to Jun 05. Bot VWAP 260.562, average sell 264.081, ratio 1.014 |
| 8 | 82 | 2 | 34,539 | 910 x 442 | `88863bb8c737` | XRP cost-basis chart, 64 fills, Apr 23 to Jun 05. Bot VWAP 1.42145, average sell 1.428, ratio 1.005 |
| 8 | 83 | 1 | 37,803 | 910 x 442 | `a8c3e8aae1d2` | SOL cost-basis chart, 52 fills, Apr 23 to Jun 05. Bot VWAP 83.9718, average sell 84.7145, ratio 1.009 |
| 8 | 83 | 2 | 44,635 | 910 x 442 | `b34a4750bc09` | SUI cost-basis chart, 50 fills, May 09 to Jun 05. Bot VWAP 0.909808, average sell 0.908325, ratio 0.998 |
| 8 | 84 | 1 | 44,545 | 910 x 442 | `4e5cfde83d48` | DOGE cost-basis chart, 46 fills, Apr 25 to Jun 06. Bot VWAP 0.098639, average sell 0.104011, ratio 1.054 |
| 8 | 84 | 2 | 41,058 | 910 x 442 | `9e962c2c1ccf` | LINK cost-basis chart, 42 fills, Apr 24 to Jun 05. Bot VWAP 9.17699, average sell 9.29312, ratio 1.013 |
| 8 | 85 | 1 | 40,837 | 910 x 442 | `e2b203476cad` | XLM cost-basis chart, 28 fills, May 29 to Jun 05. Bot VWAP 0.21485, average sell 0.245098, ratio 1.141 |
| 8 | 85 | 2 | 38,917 | 910 x 442 | `910ff86f5f4a` | NEAR cost-basis chart, 23 fills, May 29 to Jun 05. Bot VWAP 2.32719, average sell 2.48465, ratio 1.068 |
| 8 | 86 | 1 | 40,298 | 910 x 442 | `d515f5d43472` | HYPE cost-basis chart, 18 fills, May 29 to Jun 06. Bot VWAP 64.1369, average sell 69.1276, ratio 1.078 |
| 8 | 86 | 2 | 39,614 | 910 x 442 | `029e68980622` | HBAR cost-basis chart, 11 fills, May 29 to Jun 05. Bot VWAP 0.092008, average sell 0.098843, ratio 1.074 |

### Where each legacy figure is placed

No legacy image is embedded in a part file. The build tool resolves an image
reference against `artifacts/manual-figures/` and stops the build by name when
it cannot find one, and the legacy set is written to a directory of its own so
the three sets never mix. Each figure is therefore described at the passage it
illustrates, and named there in prose.

| Set | Figures | Described in |
| --- | ------: | ------------ |
| Legacy Part 5b, pages 3 to 6 | 4 | [17-legacy-overview.md](17-legacy-overview.md), and the rows above |
| Legacy Part 5c, pages 4 and 5 | 2 | [17-legacy-overview.md](17-legacy-overview.md), and the rows above |
| Legacy Part 8, pages 25 to 28 | 8 | [13-live-evidence.md](13-live-evidence.md), and the rows above |
| Legacy Part 8, pages 36 to 40 | 8 | [13-live-evidence.md](13-live-evidence.md), and the rows above |
| Legacy Part 8, pages 44 to 48 | 8 | [13-live-evidence.md](13-live-evidence.md), and the rows above |
| Legacy Part 8, pages 74 to 86 | 25 | [13-live-evidence.md](13-live-evidence.md), and the rows above |

### What the figures say that their captions do not

Six observations came out of opening all 55, and each is a fact about the
pictures rather than about the market.

**Six of the eight charts in the third gallery are the same files as the second
gallery.** The text presents pages 44 to 48 as a refreshed gallery against a
newer export and says most charts look near-identical because the delta was
small. Byte-for-byte, six of the eight are not near-identical; they are the same
image. The sha256 column above names each pair. Only two were re-rendered, and
both changed.

**One of those two moved the opposite way from its caption.** The caption under
the second gallery's ZEC chart reports a small upward tick on the morning sells.
The chart's own stats box has the average sell falling from 491.24 to 484.87 and
the ratio falling from 1.092 to 1.078, with the bot's own cost basis unchanged
at 449.9098. The figure refutes the sentence beneath it.

**The battery outcome chart does not fit the universe its own part declares.**
The part defines the battery as 26 assets across 3 regime periods, which makes
26 runs in each regime. The chart shows 41 bull runs, 21 bear runs and 16
sideways runs. The caption's claim of 57 unbroken bull and sideways wins matches
the chart, 41 plus 16, and contradicts the 26-by-3 universe, which would give
52. The chart and the text cannot both be right, and neither can be checked,
because the engine has no source in this repository.

**The three-year lifecycle chart is a schematic, not a tape.** Its price series
holds a flat line at roughly $12,000 from about month 4 to month 20, then steps
almost vertically to $60,000 and holds flat again. No traded market prints that
shape. The chart also places its spawn marker at about $12,000 while its own
spawn-threshold line sits at about $32,000, so the marker is far below the
threshold it is supposed to mark. Read the figure as an illustration of an idea.

**Its two legend entries overlap the annotation.** The legend labels and the
hold-discipline annotation are drawn on top of one another in the upper-right
corner and neither is fully readable. This is a rendering defect in the figure
as shipped.

**The complete gallery mixes two exports.** The section introducing it says all
25 charts come from one evening export, and 10 of the 25 title bars end a day
earlier than the other 15. The gallery's other claim holds: sorted by fill
count, the 25 charts do descend without a break, from 748 down to 11.

### What every legacy figure has in common

All 49 charts in Part 8 draw the same four things: a green marker per buy, a red
marker per sell, a solid line for the bot's own running cost basis, and a dashed
line for the volume-weighted price of every fill. A stats box gives the final
cost basis, the average sell and the ratio between them.

That ratio is the metric this repository cannot reproduce. No module computes an
average sell price: a search for the obvious spellings across `src/` and
`dev_harness/` returns zero, against 61 hits for the average-entry term in the
same sweep, which is the control. `src/exchange/position_health.py` derives an
average entry and a realised figure from venue-pulled trades, and that is the
nearest real instrument.

The figures are therefore carried as a record of what was published, with their
producer named as absent. [13-live-evidence.md](13-live-evidence.md) holds the
readers this repository does have, and
[10-live-trade-history.md](10-live-trade-history.md) holds the year-to-date
chart set that replaces this one.
