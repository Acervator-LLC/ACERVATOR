# The Storyteller Subtype Of The Docs Archetype

**Mode: Reference.**

A chronicle is history by definition. It breaks the archetype's reference rules
— no narrative, no history, explain what and not why — and it is still correct.
Today a chronicle can pass only by being flattened into a feature list. This
unit adds four rules a chronicle can be held to, and applies them to declared
story documents alone.

## How a document declares itself

One way, and only one. A YAML front-matter block opened by `---` on the first
line of the file, carrying `mode: story`.

```markdown
---
mode: story
---

# How I Built Acervator
```

`story.is_story` reads that block and nothing else. A directory, a filename, or
the words in the body declare nothing, so moving or renaming a file can neither
apply the subtype nor remove it.

Measured across the 104 tracked markdown files on this branch: one carries front
matter, `dev_harness/agents/evaluator.md`, and its keys are `name`,
`description` and `tools`. The string `mode: story` appears in no tracked file.
No page can be swept in by accident.

## The four rules

| id | what it reports | severity |
| -- | --------------- | -------- |
| DOC007 | an entry dated before the entry above it | high |
| DOC008 | a voice count outside the operator's measured band | high |
| DOC009 | code-shaped terms the page never explains, over a per-page ceiling | high |
| DOC010 | a dated entry with no commit, issue or repo path behind it | high |

An entry is a heading carrying an ISO date. Its date is the first date in the
heading, and its body runs to the next dated heading.

## The voice band, and what it was measured on

The corpus is the operator's own words, from two sources inside the tree.

```
81 sentences   blockquoted verbatim directives across the tracked markdown
 8 sentences   the seven markdown commits he typed in the GitHub web editor
--
89 sentences, 1337 words
```

Two contrast corpora were measured beside it: the 251 sentences of the
chronicle he deleted whole on 2026-09-06, and the 3013 sentences of
`docs/manual`.

```
measure                      operator   deleted chronicle   docs/manual
median sentence words              11                  14            16
mean sentence words             15.02               16.04         17.22
sentences opening "The"          5.6%               28.3%         27.6%
sentences with I/me/my/we       15.7%                2.0%          2.7%
sentences with a contraction     3.4%                1.6%          6.5%
```

Three counts are keyed. `MEDIAN_WORDS_CEILING` is 15, the operator's own mean
sentence length. `THE_OPENER_CEILING_PCT` is 10 and `FIRST_PERSON_FLOOR_PCT` is
5; each sits between his measured rate and both contrast rates.

Contraction rate was measured and is **not** keyed. The two contrast corpora
straddle him at 1.6% and 6.5%, so it separates nothing.

His issue bodies and issue comments were read and rejected as a corpus. All 208
issues and all 418 comments posted under his account carry the agent's shape —
`**What it is** / **How to resolve**` headings, `file:line` citations — so they
measure the archetype's voice, not his.

## The jargon ceiling

A term is code-shaped text: an inline code span, or a bare token that is
snake_case, dotted, or interior-capitalised. A term is explained when its first
appearance is followed on the same line by a parenthetical, an em-dash clause,
`, which`, `, meaning`, or a colon. Everything else is unexplained.

```
operator directives            6.2 unexplained terms per 100 sentences
the chronicle he deleted       0.8
the archived chronicle        27.3
```

The ceiling is one unexplained term per ten prose sentences. His rate passes at
6.2, the chronicle he deleted passes at 0.8, and the archived chronicle fails at
27.3.

## The program error, and the correction

`map_low_confidence_dates` read the word `low`. The forensic development map at
`docs/audits/2026-09-08_development_map.md` landed mid-unit and grades its rows
`recorded` and `inferred`, not high and low. Driven against the real file the
function returned zero dates, so the map half of DOC010 could never have fired.

```
before   map characters read 33546, dates returned 0
after    map characters read 33546, dates returned 3
```

The function is now `map_thin_dates` and reads `inferred` or `low`, returning
the marker word so the finding quotes what the map actually said.

```
2026-04-19  inferred
2026-04-26  inferred
2026-05-10  inferred
```

Driven against the real map, both ways:

```
2026-04-19 cited, map not read              0 findings
2026-04-19 cited, real map read             1 finding, DOC010
2026-04-19 declared thin, real map read     0 findings
2026-04-01 cited, map backs the date        0 findings
```

## The fixture pairs

Four pairs under `harness_fixtures/docs_archetype`. Each bad is the good with
one property broken, and each bad's only blocking finding is its own rule.

```
story_chronology_good.md   exit 0     story_chronology_bad.md   exit 1  DOC007
story_voice_good.md        exit 0     story_voice_bad.md        exit 1  DOC008
story_plain_good.md        exit 0     story_plain_bad.md        exit 1  DOC009
story_honest_good.md       exit 0     story_honest_bad.md       exit 1  DOC010
```

`story_voice_bad.md` fires two of DOC008's three counts: median 27 words and
91.7% of sentences opening with "The". The first-person floor was watched
separately, on a page written with no first-person pronoun at all.

```
0.0% of sentences carry I, me, my, we, our or us, under the 5% floor
exit 1
```

## Unread is never clean

A declared story with no dated entry cannot be read by DOC007 or DOC010, and one
with fewer than ten authored prose sentences cannot be read by DOC008 or DOC009.
The analyzer reports that rather than reporting clean.

```
story status: unread: probe_unread.md (no dated entry)
why_not_green: required analyzer(s) did not run: story
passed: False, exit 1
```

## Ordinary pages keep the verdict they had

Six markdown targets were reviewed on `origin/current` at 51fd5165 and on this
branch, and every finding matched by rule id, severity and line.

```
CONTRIBUTING.md                                  8 findings   False -> False
docs/manual/07-indicators.md                    85 findings   True  -> True
docs/manual/13-live-evidence.md                 16 findings   True  -> True
docs/manual/README.md                           13 findings   True  -> True
harness_fixtures/docs_archetype/known_good.md    1 finding    True  -> True
harness_fixtures/docs_archetype/known_bad.md    21 findings   False -> False
```

The only difference is a `story: ok` entry in the analyzer list. No reference
page gained a rule and none lost one.

## The real chronicle pages

`docs/manual/14-development-chronicle.md` holds one heading and no prose. Read
as a story it reports `no dated entry` and `fewer than 10 authored prose
sentences`, which is unread, not clean.

The chronicle the operator deleted whole on 2026-09-06 was read from
`c324126b~1`. It fails DOC008 on two counts, independently of the page's fate.

```
sentences          251
median words        14   ceiling 15
opens with 'The'   28.3% ceiling 10.0%   DOC008
first person        2.0% floor    5.0%   DOC008
unexplained terms      2 ceiling 25
entries                0   -> unread: no dated entry
```

`docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md` carries 6045
sentences and 79 dated entries. Its dates run forward, so DOC007 is silent.

```
DOC008     1   first person 3.5%, under the 5% floor
DOC009  1652   unexplained terms, ceiling 604
DOC010    25   dated entries with no artefact behind them
```

Some DOC009 hits on that file are product names with an interior capital —
`StochRSI`, `PyInstaller`, `TradingView`. The rule counts them, and the per-page
ceiling absorbs a page's worth before it reports.

## The runs

```
pytest tests/test_docs_archetype.py tests/test_harness_is_reachable.py
       tests/test_archetype_report_contract.py          128 passed, exit 0
pytest tests/test_hooks.py tests/test_archetype_subprocess_encoding.py
       tests/test_every_test_file_is_collected.py
       tests/test_build_product_manual.py                72 passed, exit 0
python -X dev -X faulthandler -W error, good fixture     exit 0, no warning
python -X dev -X faulthandler -W error, bad fixture      exit 1, no warning
coding_archetype on story.py                             passed=True
coding_archetype on docs_archetype.py                    passed=True
```

`~/.acervator/settings.json` hashes `f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423`
before and after the unit.

## Falsification

This subtype is wrong if a chronicle the operator writes himself fails DOC008,
which would mean 89 sentences do not describe him. It is wrong if a page that
never declared itself draws a DOC007 to DOC010 finding. It is wrong if DOC009's
gloss test accepts a parenthetical that explains nothing, or refuses a gloss
written in another shape. It is wrong if DOC010 reads a commit sha out of a
sentence that is not evidence for the entry holding it.

## One thing left alone

Four archetype modules print `python -m tools.harness.<name>` in their usage
line, naming a path that moved. `tests/test_harness_is_reachable.py` allows
`dev_harness/` to carry the old string on purpose. The line in
`dev_harness/harness/docs_archetype.py` is corrected here because this unit
edits that file; the other three are untouched.
