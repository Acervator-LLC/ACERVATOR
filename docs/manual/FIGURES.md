# Figure Inventory

Reference for the images embedded in the Acervator product manual. The manual
carries 38 images across 29 of its 44 pages. The manual text is in
[README.md](README.md) and the part files listed there.

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
