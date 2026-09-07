# Phase four applies each push target's ceiling

Nothing was posted. No account and no credential was used. Every run took a
throwaway home directory. The settings file hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

One file changed: `src/trading/ata_spm_push.py`.

`PushTarget` gained three fields. They hold the numbers each platform publishes
and the unit it counts in. Every number comes from the push target rules page
and nothing was guessed.

| target | body ceiling | title ceiling | counted in |
|---|---|---|---|
| X | 280 | none | weighted characters, a link costs 23 |
| Instagram | 2,200 | none | characters |
| LinkedIn | 3,000 | none | characters |
| TikTok | 4,000 | 90 | UTF-16 runes |
| Facebook | not published | none | characters |
| Threads | 500 | none | characters, an emoji counts its bytes |
| Reddit | 40,000 | 300 | characters |

Facebook publishes no ceiling. Its row carries none, and the formatter measures
its post without refusing it.

`measure_text` reads a post's length in the unit the target names. A character
outside the plain Latin set always takes the heavier count, so the reading can
be one too high and never one too low.

`fit_to_target` drops whole lines until the body fits. `ranked_lines` sets the
order they go in.

`FormattedPost` gained the ceiling it was written against, the count of lines
dropped, and the notes phase five records. Its new reader answers the body's
length, and a second answers whether that length is over the ceiling.

`deliver_one` refuses a post that is still over its ceiling. The refusal is the
first check it makes, so such a post never reaches the sender.

## Errors detected

The formatter applied no ceiling. Phase four wrote a body for X that X would
reject.

Run under the development interpreter with warnings raised, one bullish call on
BTC-USD 1wk carrying two confirming voters:

```
X body 306
Instagram body 354
LinkedIn body 345
TikTok body 393
Facebook body 393
Threads body 306
Reddit body 393
```

X publishes 280. The body measured 306, which is 26 over.

## Resolution

### Every target, read back off the real post

The same call, after the change. `measured` and `dropped` are read off the
object phase four answered.

| target | ceiling | before | after | lines dropped | over |
|---|---|---|---|---|---|
| X | 280 | 306 | 275 | 1 | no |
| Instagram | 2,200 | 354 | 354 | 0 | no |
| LinkedIn | 3,000 | 345 | 345 | 0 | no |
| TikTok | 4,000 | 393 | 393 | 0 | no |
| Facebook | none | 393 | 393 | 0 | no |
| Threads | 500 | 306 | 306 | 0 | no |
| Reddit | 40,000 | 393 | 393 | 0 | no |

The X body afterwards, printed from the object:

```
This is not investment advice. It is a demonstration of Ekthelius's proprietary TA engine housed in the Acervator governance execution platform.
BTC-USD on 1wk: bullish reversal called.
RSI: RSI 28.41. Votes bullish at 66% confidence.
Abbreviated: 1 evidence line(s) omitted.
```

The header is whole. The ticker, the timeframe and the direction are whole. The
longer of the two indicator explanations went, and the post says one line was
left out.

### At the ceiling and over it

Threads publishes 500. One indicator explanation was padded until the body
measured exactly 500, then padded by one more character.

```
AT LIMIT   Threads limit 500 measured 500 dropped 0 over False
OVER       Threads limit 500 measured 347 dropped 1 over False
OVER body last line: 'Abbreviated: 1 evidence line(s) omitted.'
```

A body of exactly 500 passes through untouched. A body of 501 is brought down to
347 by dropping one line, and it says so.

### A post over the ceiling does not leave

Two target rows were driven through phase five with a credential held, a sender
wired and the rate open. They differ only in the ceiling on the row.

```
Tiny   limit 150 measured 226 over True  -> sent False | not sent - Tiny publishes 150; this post measures 226.
Roomy  limit 500 measured 306 over False -> sent True  | sent to recorded
```

The refusal is the two-sided proof. The same setup sends when the post fits and
refuses when it does not, so the refusal is the ceiling and not the setup.

### What may be truncated, and what may not

This unit decided the following.

**Never dropped.** The fixed header. The line naming the ticker, the timeframe
and the direction.

**Never cut.** A line. Every drop takes a whole line, so a price, a band value
or a percentage can never lose its last digits. A number cut mid-digit is a
wrong reading, and this feature posts in public.

**Dropped first.** The indicator explanations, the longest of them first.

**Dropped after those.** The chart line and the band line, the longest first.

**Always said.** A drop adds a last line counting the lines left out. Nothing is
removed in silence.

**Refused.** A post still over its ceiling after every drop. Phase five records
the target, the ceiling and the measured length, and sends nothing.

### The TikTok title

TikTok's title field holds 90. The fixed header is 144. The header does not fit,
so the title cannot carry it.

The header was not cut to fit. TikTok's post carries no title field at all, and
`title_notes` records why:

```
TikTok title holds 90 and the header with the headline measures 163, so no artefact maps to it.
```

The header ships in TikTok's description, which holds 4,000 runes. Every
artefact a TikTok post does carry opens with the header, as it did before.

Reddit's title holds 300, so Reddit does carry one, and it opens with the header.

### The link rule

X counts any link as 23, whatever its real length. The reading was taken off
`measure_text`:

```
URL real length 80
X weighted count of the URL alone 23
X weighted count of two words + URL 31
plain character count of the same 88
```

### Phase seven

Follow-up posts pass through the same fit. Every target measured under its
ceiling with nothing dropped.

```
X          limit    280 measured    274 dropped 0 over False
Instagram  limit   2200 measured    321 dropped 0 over False
LinkedIn   limit   3000 measured    310 dropped 0 over False
TikTok     limit   4000 measured    358 dropped 0 over False
Facebook   limit      0 measured    358 dropped 0 over False
Threads    limit    500 measured    274 dropped 0 over False
Reddit     limit  40000 measured    358 dropped 0 over False
```

### The Ready to Send zone still reads the post

No zone code was changed. The zone's own reader was driven against a capped
post:

```
X BTC-USD line 0 | This is not investment advice. It is a demonstration of Ekth
X BTC-USD line 1 | BTC-USD on 1wk: bullish reversal called.
X BTC-USD line 2 | RSI: RSI 28.41. Votes bullish at 66% confidence.
X BTC-USD line 3 | Abbreviated: 1 evidence line(s) omitted.
bucket_entry ok: True
```

### The debugger

Every run above was taken with the development interpreter, the crash handler on
and every warning raised as an error:

```
PYTHONWARNINGS=error python -X dev -X faulthandler
```

Both phases were driven over all seven targets. The command exited 0 and wrote
nothing to the error channel:

```
EXIT=0
--- stdout ---
faulthandler enabled: True
dev mode: True
--- stderr ---
--- end ---
```

The remote debugger was not pointed at the application:

```
python -m debugpy --listen 5678 --wait-for-client main.py
```

It was not run. The live platform is trading 38 bots with real money, and
starting a second instance of it is not permitted. The reading above comes from
the same interpreter switches, driven over the code this unit changed.

### Gate

Fixture controls, exit codes read directly:

```
coding_archetype  known_good exit=0   known_bad exit=1
docs_archetype    known_good exit=0   known_bad exit=1
```

Every tool reported `ok` in both.

Formatting and lint on the changed file:

```
black   exit 0
flake8  exit 0
```
