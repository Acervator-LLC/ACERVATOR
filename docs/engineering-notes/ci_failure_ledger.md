# CI failure ledger

Every CI failure on the `current` pull request, its class, the change that closed it, and the green run that proves it closed.

## How this file stays small

- One row per failure. A row records a run id, a failing test, and a class. Never a row about a row.
- A class **closes** when three consecutive green runs contain its tests. The row is then deleted from this file and its rule lives on in the `ocir` skill.
- No entry without a run id and a measured cause.
- If this file passes 20 rows, the work is producing failures faster than it closes them, and that is the finding.

## Open

| run | commit | failing test | class |
|---|---|---|---|
| 33278823149 | `0e36ab2` | `test_a_label_padding_is_reported_by_the_right_check[SPACE_CARD_PAD]` | a test renders a payload it modified |
| 33279699299 | `640005a` | same | same |

1 failed of 12,248 and 1 failed of 12,792.

The test compares an old render against a new render, which looks like the rule. It is not: the test alters one payload first to show a padding value is invisible to a picture. That is the same side twice with a value changed. Whether the change is invisible depends on the host's fonts.

## Closed

### Class: a test asserts a property of the host it runs on

| run | commit | failing test |
|---|---|---|
| 33260134646 | `9e8a084` | `test_the_offscreen_host_paints_no_glyphs`, two files |
| 33263318916 | `9c52361` | same |
| 33265643444 | `eeccc32` | same, third file |

`QFontDatabase.families() == []` is true on the development host and false on the runner, which ships the DejaVu family.

Closed by `eeccc32` and `319f187`. The second commit deleted four private copies of the question and left one shared helper at `tests/fixtures/host_fonts.py`. Every caller asks the host and proves both answers.

Proof: run `33272488462` on `e88e350`, 10,411 passed, 0 failed.

### Class: a picture compared against a payload from the same side

| run | commit | failing test |
|---|---|---|
| 33267923441 | `7dc20a3` | `test_everything_a_picture_cannot_see_is_named_and_covered` |
| 33270003679 | `1a646aa` | same, plus `test_the_wide_render_gives_the_button_row_room_to_move` |

Painting one side twice with a value changed, then asserting the pictures match, states a fact about the host's fonts.

Closed by `e88e350`, which swept 50 host-dependent checks across 8 parity files — 18 same-side pictures and 32 fixed pixel counts — and put one picture helper at `tests/fixtures/surface_pictures.py`.

Proof: runs `33272488462`, `33275289190` and `33276982009`, on `e88e350`, `bc21a45` and `60aaa28`. 10,411 / 10,645 / 10,916 passed, 0 failed.

## The gate order

The pull request CI is the prevailing gate. The archetype harness runs after CI passes, as a backup.

A unit branch opens a pull request into `current`. The `pull_request` trigger carries no branch filter, so CI runs on it. The unit merges on green. The next unit builds while CI runs on the previous one: a unit takes 20 to 40 minutes and CI takes 9.
