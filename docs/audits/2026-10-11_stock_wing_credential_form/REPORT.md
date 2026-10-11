# The stock wing's credential form

Issue #1192, connection 3 — the operator can enter his credentials. Measured on
`origin/current` at `980da4b2`, with `Path.home()` redirected to a temp
directory and printed on every run, no venue contacted, and no order placed,
priced, amended, previewed or cancelled.

## What the form did

`src/gui/settings_dialog.py`, in `_create_exchange_tab`, built the Add form for
the stock wing and then switched seven of its controls off, hanging one sentence
on all seven. `src/gui/main_tabs/settings_dialog_surface.py`, in
`SettingsDialogModel._setup`, did the same for the React build over
`STOCK_DISABLED_CONTROLS`.

The brief for this unit counted six controls. The measured count is **seven**:
`test_btn`, `add_btn`, `new_api_key`, `new_api_secret`, `new_passphrase`,
`pp_check`, `new_verification_code`.

## The three defects the disable carried

1. **No broker credential could be entered.** `BROKER_CONNECTORS` names eight
   brokers and `broker_connector_class` builds one for each, so the sentence
   the form showed was false.
2. **No passphrase venue could be connected under stocks.** All four venue ids
   in `src/exchange/ccxt_connector.py`, in `PASSPHRASE_EXCHANGES` — bitget,
   kucoin, okx, okxus — are stocks venues, and the box that ticks for them was
   off.
3. **The Add press could not store a broker credential on either wing.**
   `src/gui/settings_dialog.py`, in `_add_exchange`, ran
   `src/exchange/api_validator.py`, in `validate_credentials`, before it
   stored. That call takes a hand-written connector or `CCXTConnector`, whose
   constructor raises for any id outside `SUPPORTED_EXCHANGES`, so it refused
   nine of the 21 stocks venues and nothing was stored. E*TRADE escaped only
   because its verification-code leg runs first.

## Which sector lands on which wing

`src/gui/main_tabs/settings_dialog_surface.py`, in `wing_or_default`.

```
sector          wing     venues offered   brokers among them
crypto          crypto               24                    8
stocks          stock                21                    8
commodities     crypto               21                    8
forex           crypto               16                    6
indices         crypto               20                    8
futures_perps   crypto               18                    5

venues on the stock wing   21
crypto-wing cells          99
control: wing_or_default('nonsense') -> crypto
```

Every one of the eight brokers serves the stocks sector and at least one sector
that lands on the crypto wing, so every one reached an enabled form on one
sector and a dead form on stocks. The asymmetry was not E*TRADE's alone.

```
alpaca      4 sectors   wings: crypto, stock
etrade      6 sectors   wings: crypto, stock
fidelity    4 sectors   wings: crypto, stock
ibkr        6 sectors   wings: crypto, stock
robinhood   5 sectors   wings: crypto, stock
schwab      6 sectors   wings: crypto, stock
tastytrade  6 sectors   wings: crypto, stock
webull      6 sectors   wings: crypto, stock
```

## The credential route per stocks venue

`credential_route_held` asks what `validate_credentials` can take.

```
alpaca             route=NONE          broker=True
binance            route=ccxt          broker=False
bitget             route=ccxt          broker=False
coinbase           route=ccxt          broker=False
cryptocom          route=ccxt          broker=False
etrade             route=NONE          broker=True
fidelity           route=NONE          broker=True
gateio             route=ccxt          broker=False
huobi              route=ccxt          broker=False
ibkr               route=NONE          broker=True
interactivebrokers route=NONE          broker=False
kraken             route=ccxt          broker=False
kucoin             route=ccxt          broker=False
mexc               route=ccxt          broker=False
okx                route=ccxt          broker=False
okxus              route=ccxt          broker=False
robinhood          route=hand-written  broker=True
schwab             route=NONE          broker=True
tastytrade         route=NONE          broker=True
tdameritrade       route=NONE          broker=False
webull             route=NONE          broker=True

route held   = 12
route absent =  9
control: route('notavenue') -> ''
control: route('coinbase')  -> 'ccxt'
```

`alpaca` is in the nine: `SUPPORTED_EXCHANGES` does not name it, so
`CCXTConnector('alpaca')` raises. Over all 26 venue ids the platform offers,
7 hold a broker class and no route, and 2 — `interactivebrokers`,
`tdameritrade` — hold no connector of any kind.

## The seven controls, settled

| Control | State | Reading |
| ------- | ----- | ------- |
| `new_api_key` | enabled | 19 of 21 stocks venues hold a connector |
| `new_api_secret` | enabled | `src/stocks/broker_base.py`, in `open_session`, refuses an empty secret |
| `pp_check` | enabled | 4 of 21 stocks venues are in `PASSPHRASE_EXCHANGES` |
| `new_passphrase` | enabled | drawn for those 4 |
| `new_verification_code` | enabled | `VERIFICATION_CODE_VENUES` names etrade |
| `add_btn` | enabled for 19, refused for 2 | `connector_held` |
| `test_btn` | enabled for 12, refused for 9 | `credential_route_held` |

The two sentences the refusals carry are
`src/gui/main_tabs/settings_dialog_surface.py`, in `NO_CREDENTIAL_TEST_TIP`,
and in `NO_CONNECTOR_PROMPT`. Neither claims anything about what a venue
publishes; both state what this tree holds.

## What each broker's form fills

Read off each connector's own `connect`.

| Broker | API Key row | API Secret row |
| ------ | ----------- | -------------- |
| alpaca | the key id | the secret key |
| etrade | the consumer key | the consumer signing key |
| fidelity | dropped; `connect` answers False with `ORDER_ROUTE_UNPUBLISHED` | dropped |
| ibkr | the bearer token | unused |
| robinhood | no typed row; `src/trading/ata_spm_signin.py`, in `BROWSER_AUTHORIZATION_SECTORS` | no typed row |
| schwab | the bearer token | unused, and `ORDER_BODY_UNPUBLISHED` refuses the order body |
| tastytrade | the grant's refresh token | the client secret |
| webull | the app key | the app signing key |

No broker needs a row the form did not already draw: 0 rows added, 0 removed.

Two venue ids can hold no session and now say so instead of offering a form.
`interactivebrokers` and `tdameritrade` hold no connector, so their Add press is
refused and the feedback row names the reason. Fidelity holds a connector, so
its credential stores and its own `ORDER_ROUTE_UNPUBLISHED` reaches the status
log when the Start press tries the session.

## Driven on the real Qt screen

Exchanges tab built on the stocks sector, each venue's own button pressed.
`isHidden` is the row reading: an offscreen dialog answers `isVisible` false for
every row, drawn or not.

```
venue                key rows              code row   Test      Add
alpaca               drawn                 absent     refused   press, 'Test and Add Exchange'
etrade               drawn                 drawn      refused   press, 'Test and Add Exchange'
fidelity             drawn                 absent     refused   press, 'Test and Add Exchange'
ibkr                 drawn                 absent     refused   press, 'Test and Add Exchange'
robinhood            absent                absent     refused   press, 'Connect with a Browser'
schwab               drawn                 absent     refused   press, 'Test and Add Exchange'
tastytrade           drawn                 absent     refused   press, 'Test and Add Exchange'
webull               drawn                 absent     refused   press, 'Test and Add Exchange'
coinbase             drawn                 absent     press     press
okx                  drawn, phrase drawn   absent     press     press
interactivebrokers   drawn                 absent     refused   refused
tdameritrade         drawn                 absent     refused   refused
```

A value typed into every drawn row reads back at the consumer that uses it.

```
key    at _new_api_key.text              'typed-key-value'
secret at _typed_secret                  'typed-secret-value'
phrase at _new_passphrase.text           'typed-phrase-value'
code   at _new_verification_code.text    '000000' on etrade, '' on the other seven
```

Blinding the reading flips it: disabling the key row reads disabled, and hiding
the code row reads absent.

## The Add press, driven with no venue contacted

`validate_credentials` was replaced with a stub that raises if called, so a
contacted venue would fail the run loudly.

```
webull        before: nothing stored
              feedback: 'Webull added with stored credentials.'
              after : key and secret both read back out of SettingsManager
              validate_credentials calls = 0

tdameritrade  add press takes a click = False
              driven anyway: feedback names the missing connector
              stored: nothing
              validate_credentials calls = 0

coinbase      driven: validate_credentials calls = 1
              stored: nothing, because the stub refused
```

The route reading is not blind: the broker press called the validator 0 times
and the ccxt venue 1 time, on the same code path.

## The React store draws the same form

`SettingsDialogModel.on_exchange_changed` now reads one `credential_form`
answer. Three readings moved with it.

- `show_key_rows` hides the key, secret and passphrase box for a
  browser-authorization venue. The Qt build already did; the store drew them.
- `bind_venue_row` writes `venue_form_bound`'s sentence, the one
  `SettingsDialog._open_credentials_for_row` writes. The store wrote
  `VENUE_FORM_BOUND` instead, so the two builds said different things.
- `src/gui/react_settings_dialog.py`, in `PagePress`, now takes `setText` and
  `setToolTip`. `_sync_credential_kind` already called both and the holder
  carried neither, so a venue press raised on the React build before it drew
  anything. `src/gui/web/settings_dialog.js`, in `DialogButton`, reads the texts
  bag before its layout node's words.

Driven on the store, the eight brokers and the four control venues answer the
same row set and the same two presses the Qt screen answers, and the crypto wing
is unmoved for coinbase, okx and robinhood.

## The stale sentences

Corpus pinned and printed before counting: `src/gui/settings_dialog.py`
(77,596 bytes), `src/gui/main_tabs/settings_dialog_surface.py` (117,891 bytes),
`docs/manual/08-tabs/settings.md` (331,556 bytes). Eleven phrases asserting the
brokers are queued, planned or unshipped answered 33 hits. An invented phrase
answered 0 in all three files; the word `Exchanges` answered 40.

Three sentences sat in the screen files and are replaced:
`STOCK_DISABLED_TIP`, `STOCK_BANNER_TAIL`, and the `SettingsDialog.__init__`
docstring. Eight sat on the manual page and are kept word for word under
`OVERTAKEN, quoted whole:` with a `True today:` line beneath each.

The manual edit is add-only. Measured against
`git show origin/current:docs/manual/08-tabs/settings.md`, decoded as UTF-8:
5,933 non-blank lines before, 6,112 after, and **0** lines present before and
absent now. Controls: an invented line reads absent, a real line reads present,
and the same real line with one letter changed reads absent, so a reword would
be caught.

## Verification

Archetypes, run serially, one file at a time, read directly.

```
coding_archetype  src/gui/settings_dialog.py                     passed=True
coding_archetype  src/gui/main_tabs/settings_dialog_surface.py   passed=True
coding_archetype  src/gui/react_settings_dialog.py               passed=True
coding_archetype  src/gui/web/settings_dialog.js                 passed=True
ta_archetype      src/gui/main_tabs/settings_dialog_surface.py   passed=True
gui_archetype     src/gui/settings_dialog.py                     passed=True
gui_archetype     src/gui/main_tabs/settings_dialog_surface.py   passed=True
gui_archetype     src/gui/react_settings_dialog.py               passed=True
gui_archetype     src/gui/web/settings_dialog.js                 passed=True
docs_archetype    docs/manual/08-tabs/settings.md                passed=True
```

Calibration, exit codes read directly and not through a shell that has already
run a command substitution.

```
coding_archetype known_good.py             exit 0
coding_archetype known_bad.py              exit 1
gui_archetype    known_good_widget.py      exit 0
gui_archetype    known_bad_widget.py       exit 1
docs_archetype   known_good.md             exit 0
docs_archetype   known_bad.md              exit 1
docs_archetype   citation_good.md          exit 0
docs_archetype   citation_bad.md           exit 0
```

The citation fixture pair does not discriminate on the exit code, because the
citation rule fires below the verdict threshold. Every path this report and the
manual section cite was checked on disk instead: 18 resolve, and the control
path `src/trading/profit_fold.py` does not, which the manual page already cites
and this unit did not add.

Merge gate lanes, run individually because the RAM hook refuses
`python -m tools.local_ci --all` while the live build is running. Pytest runs
serially, with no `-n`.

```
black   --check --diff src tests tools *.py    529 files would be left unchanged, exit 0
flake8  src tests tools *.py                   no findings, exit 0
fast    pytest -m "not slow and not archetype" no tests ran, exit 5, known-empty
full    pytest -m "slow or archetype"          no tests ran, exit 5, known-empty
```

The flake8 lane's control fired: a file holding `return undefined_name_1192`
was reported as `F821 undefined name`, and the lane returned to silent once it
was removed. E501 is handed to black by the config, so it is not the control to
use.

`fast` and `full` report on a tree that holds no Python test, by the operator's
own directive. They are quoted as known-empty.

## Security

No venue was contacted on any run. No credential, passphrase or verification
code appears anywhere in this report: the three values typed in the drive are
the literal strings `typed-key-value`, `typed-secret-value` and
`typed-phrase-value`, and the code typed is `000000`. Nothing under the
operator's runtime tree was opened or written; every run printed its redirected
`Path.home()` first.
