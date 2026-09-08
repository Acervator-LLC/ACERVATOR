# The five unmeasured push targets

Issue #407 names eight push targets. Four were measured on 6 September 2026.
This unit measured the other five: TikTok, Facebook, YouTube, Threads and
Reddit.

Nothing was posted. No account was used. No credential was used. No request
that creates anything was sent.

## Edits

`src/trading/ata_spm_push.py` gained four target names and four rows in
`PUSH_TARGETS`.

```python
TARGET_TIKTOK = "TikTok"
TARGET_FACEBOOK = "Facebook"
TARGET_THREADS = "Threads"
TARGET_REDDIT = "Reddit"
```

Each row names its own sections, so each target carries its own format over the
same phase three evidence. TikTok, Facebook and Reddit carry the call, the
chart, the bands and the indicator messages, because each publishes a text
field of 4,000 characters or more. Threads carries the call and the indicator
messages only, because Threads publishes 500 characters and the fixed header
takes 144 of them.

`docs/audits/2026-09-06_ata_platform_rules.md` gained five sections in the
shape it already uses, a conflicts table over the whole set, and a section on
what the five add for the formatter. No existing sentence was deleted or
reworded.

**No phase changed.** Phase four is `format_post` and `format_run`, phase five
is `distribute` and `deliver_one`, and phase six is `ReadyToSend`. All three
read the rows in `PUSH_TARGETS` and none names a target. The Settings page
reads `TARGET_NAMES`, which is derived from the same rows, so the credentials
list grew from three entries to seven with no edit to any screen.

## Errors detected

The run was made with `python -X dev -X faulthandler` and `PYTHONWARNINGS=error`
against a throwaway home directory. **No error, no warning and no traceback was
printed.** The command and its whole output follow.

Phase four over every target:

```
TARGET_NAMES: ('X', 'Instagram', 'LinkedIn', 'TikTok', 'Facebook', 'Threads', 'Reddit')
posts formatted: 7
target: X | body chars: 323 | caption chars: 163 | thread_root chars: 163
target: Instagram | body chars: 369 | caption chars: 163 | thread_root chars: 163
target: LinkedIn | body chars: 362 | caption chars: 163 | thread_root chars: 163
target: TikTok | body chars: 408 | caption chars: 163 | thread_root chars: 163
target: Facebook | body chars: 408 | caption chars: 163 | thread_root chars: 163
target: Threads | body chars: 323 | caption chars: 163 | thread_root chars: 163
target: Reddit | body chars: 408 | caption chars: 163 | thread_root chars: 163
```

One body read back off the real object, for the target added last:

```
This is not investment advice. It is a demonstration of Ekthelius's proprietary TA engine housed in the Acervator governance execution platform.
BTC-USD on 1wk: bullish reversal called.
Chart: 200 candles, last close 217.224
Bands: lower 216.5 · middle 224 · upper 231.5
Bollinger Bands: band position 0.3381. Votes bullish at 20% confidence.
Vortex: VI+ less VI- at +0.2000. Votes bullish at 40% confidence.
```

Phases five and six over the same run:

```
phase 6 bucket holds: 7
phase 6 summary: 7 post(s) · 7 approved · 0 declined · 0 waiting
phase 5: X · BTC-USD 1wk · sent to recorded
phase 5: Instagram · BTC-USD 1wk · sent to recorded
phase 5: LinkedIn · BTC-USD 1wk · sent to recorded
phase 5: TikTok · BTC-USD 1wk · sent to recorded
phase 5: Facebook · BTC-USD 1wk · sent to recorded
phase 5: Threads · BTC-USD 1wk · sent to recorded
phase 5: Reddit · BTC-USD 1wk · sent to recorded
phase report: {'Phase 4 Format': 7, 'Phase 5 Distribute': 7, 'Phase 6 Ready to Send': '7 post(s) · 7 approved · 0 declined · 0 waiting', 'Phase 7 Follow-Up': 0}
settings credential row: ['X', True, 'held']
settings credential row: ['Instagram', True, 'held']
settings credential row: ['LinkedIn', True, 'held']
settings credential row: ['TikTok', True, 'held']
settings credential row: ['Facebook', True, 'held']
settings credential row: ['Threads', True, 'held']
settings credential row: ['Reddit', True, 'held']
```

The destination is `RecordedDestination`, which the module already ships. It
keeps the artefacts and reaches no platform.

The same instrument reports both states. With the three rows that shipped
before, it counts three posts; with the seven rows, seven. With no credential
vault, every one of the seven records a refusal instead of a send.

```
control, the three shipped before: ['X', 'Instagram', 'LinkedIn']
control posts: 3
new set posts: 7
no vault: X · BTC-USD 1wk · not sent · No credential held for X.
no vault: TikTok · BTC-USD 1wk · not sent · No credential held for TikTok.
no vault: Facebook · BTC-USD 1wk · not sent · No credential held for Facebook.
no vault: Threads · BTC-USD 1wk · not sent · No credential held for Threads.
no vault: Reddit · BTC-USD 1wk · not sent · No credential held for Reddit.
```

**One limit is broken and it is not new.** The X body measures 323 characters
against the 280 X publishes. `format_post` applies no per-target ceiling, and
it never did. The audit page already records the truncation rule the formatter
owes; this run puts a number on the gap. No target added here is over its own
ceiling.

## Resolution

**Phases four, five and six did not change.** Adding a target is adding a row
to `PUSH_TARGETS`. Issue #407 states that as the test of whether the formatter
is built correctly, and the formatter passes it.

**Five targets were measured. Four join the set and one does not.**

TikTok accepts a still image post. `POST /v2/post/publish/content/init/` takes
a media type of PHOTO, up to 35 images, WebP or JPEG, 20 MB and 1080p each. It
fetches every image from a URL on a domain the developer has verified with
TikTok. The title accepts 90 runes, which is less than the 144-character fixed
header, so the header sits in the description.

Facebook accepts a still image post and takes the bytes directly.

Threads accepts a still image post and fetches it from a public server. Its
text field is 500 characters, the shortest in the set after X.

Reddit accepts a post that names a subreddit. The published source caps the
title at 300 characters and the body at 40,000, guards the call with the
`submit` scope, and refuses a post whose subreddit does not admit the account
or the kind.

**YouTube is not in the set.** Its upload endpoint accepts `video/*` and
`application/octet-stream` and nothing else, and no resource in the Data API
reference publishes a still image or a text post. Phase three renders a still
chart, so a post has no route in. That is reported, not worked around, and
YouTube is left out the way TradingView was.

**Two platforms refused to be read.** Reddit's live API reference, its help
centre article on the Data API, and its Data API terms all refused this reader
on 7 September 2026. TikTok's Community Guidelines pages returned a page title
and no policy text. Every Reddit number above therefore comes from Reddit's own
published source code, which is named beside it, and the per-subreddit
self-promotion rules the issue asks about have no citation on the audit page.

**Three targets need a public address for the image.** Instagram, Threads and
TikTok fetch it rather than receive it. A desktop application holds no such
host, and issue #407 forbids adding an outbound surface to the render path.
Phase five records those three as unreachable until the operator supplies one.
