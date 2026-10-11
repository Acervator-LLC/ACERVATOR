# E*TRADE's verification code reaches the Add form

Connection 3 of the eight a wired venue owes — the operator can enter his
credentials — for the one venue where he could not.

E*TRADE grants no session until the operator approves this program on E*TRADE's
own web page. That page then shows him a short verification code and redirects
nowhere, so nothing in this program can collect the code for him. The Add form
had no row to paste it into.

The three authorization legs were already written and reached nothing:

```
begin_authorization        0 callers outside its own module
complete_authorization     0 callers outside its own module
renew_authorization        0 callers outside its own module
authorize_url              0 callers outside its own module
oauth_verifier             1 site in src/, inside complete_authorization
```

Positive control: the same search for `EtradeConnector` answers
`src/stocks/alpaca_connector.py`, so it finds a caller where one exists.

## What the operator does now

Four steps on the Exchanges tab.

1. Press E*TRADE. The form draws an extra row, **Verification Code**, and the
   line under the form says what to do with it.
2. Type the API key and secret, press Add. The line prints the web address
   E*TRADE answered with.
3. Open that address, sign in, approve this program. E*TRADE shows a short code.
4. Paste the code into **Verification Code**, press Add again.

## What changed

| Change | Symbol |
| ------ | ------ |
| which venues draw the row | `src/stocks/etrade_connector.py`, in `VERIFICATION_CODE_VENUES` |
| leg one walkable before a session exists | `src/stocks/etrade_connector.py`, in `begin_authorization` |
| the row set both builds read | `src/gui/main_tabs/settings_dialog_surface.py`, in `credential_form` |
| which leg a press walks | `src/gui/main_tabs/settings_dialog_surface.py`, in `connect_verification_code_venue` |
| the row drawn and hidden | `src/gui/settings_dialog.py`, in `_sync_credential_kind` |
| the press that walks a leg | `src/gui/settings_dialog.py`, in `_connect_verification_code_venue` |

`begin_authorization` is the one connector change the screen's shape forced. It
read a consumer pair no caller could hand it, and it targeted the live host while
`connect` opens the paper one. It takes both now, with defaults, and it had no
callers to break.

`PASSPHRASE_EXCHANGES` is the precedent followed: a venue set, a row drawn from
it, a value read at the press.

## The credential store gains nothing

The code is single-use and the request token behind it lives five minutes, so
nothing persists it. `src/trading/ata_spm_signin.py`, in
`credential_store_fields`, still answers two field names for every one of the 26
venues the tab offers, and `src/core/settings.py`, in `ExchangeConfig`, gains no
field.

| Value | Where it lives | How long |
| ----- | -------------- | -------- |
| API key and secret | the vault | until removed |
| the request token | the held connector, in memory | five minutes |
| the verification code | nowhere | the one press that sends it |
| the access token | the held connector, in memory | to the end of the US Eastern day |

## Why the approved browser sign-in does not serve

`src/trading/ata_spm_signin.py` is an OAuth 2.0 flow with a proof key and a
loopback redirect. E*TRADE is OAuth 1.0a with an out-of-band callback.

| What it assumes | What E*TRADE does |
| --------------- | ----------------- |
| `LoopbackReceiver` waits for a redirect to `127.0.0.1` | `OAUTH_CALLBACK` is `oob`, so the venue redirects nowhere and shows a code |
| `code_challenge` and `new_verifier` build a proof key | OAuth 1.0a has no such parameter; the venue signs each leg at `request_signature` |
| `SignInSession.approve` sends a response type, state and redirect address | `authorize_url` takes a key and a token and nothing else |
| `GRANT_AUTHORIZATION_CODE` names the grant posted | `ACCESS_GRANT_ROUTE` takes a verifier |

`etrade` is in none of `SIGN_IN_ROUTES`, which holds ten rows, nor in
`REDIRECT_POLICIES` or `AUTHORIZE_ADDRESSES`, and `BROWSER_AUTHORIZATION_VENUES`
holds one venue. So the smallest field the screen can carry shipped instead: one
text row. No browser automation, no listener, no new window.

## Driven, with no host contacted

Built the real Exchanges tab on the crypto wing and pressed each venue's own
button.

| Step | Reading |
| ---- | ------- |
| before any press | key, secret, passphrase box drawn; code row hidden |
| E*TRADE pressed | code row and label drawn; prompt names the page and the paste |
| Coinbase pressed | code row hidden; key and secret rows unchanged |
| Add, row empty | leg one walked, address printed, no session |
| Add, code pasted | leg three walked, session granted, row cleared |

The typed code was read off a real `EtradeConnector` at
`complete_authorization` as `oauth_verifier`, carrying the request token leg one
held, with the venue transport replaced by a recorder that reaches no host and
raises on any route it was not told to answer.

The other build reads the same row logic through
`src/gui/main_tabs/settings_dialog_surface.py`, in
`SettingsDialogModel.on_exchange_changed`, driven by binding each venue through
its own array row:

| Venue | Code row | Passphrase row |
| ----- | -------- | -------------- |
| etrade | drawn | hidden |
| coinbase | hidden | hidden |
| kucoin | hidden | drawn |

The two conditional rows are independent — the venue that grows one does not grow
the other. A value left in the row cannot be sent by a venue that draws no row:
with E*TRADE bound the row reads back the typed code, and binding Coinbase then
reads back the empty string, because `typed_verification_code` answers an empty
string while the row is not drawn.

## Controls, each two-sided

| Control | Reading |
| ------- | ------- |
| a venue needing no code must not grow the row | Coinbase drew no code row, key and secret rows unchanged |
| the row is conditional over the whole offered set | 1 of 26 venues draws it, 25 do not |
| an invented venue id | draws no row |
| an empty row walks no third leg | the empty press answered the page stage and granted nothing |
| the code reaches no store | no stored entry, and no value of the seam's answer carries it |
| archetypes | coding, GUI and docs each read 0 on `known_good` and 1 on `known_bad`, then 0 on every file here |
| flake8 lane | exit 0 on the tree, exit 1 on F401 and F821 |
| black lane | exit 0, read directly and not through a pipe |
| the manual edit is add-only | 0 of 7595 base lines absent; the control reworded one sentence inside the sentence and the count rose to 1 |

Both pytest lanes answer exit 5 with no tests collected. That is this tree's
baseline: `tests/` holds no Python test file, and this change touches none.

## Two readings that were the measuring, not the subject

**A visibility read that cannot work offscreen.** The first reading used Qt's
`isVisible`, which answers False for every row while the tab page is never
mapped. It reported every row absent — including Coinbase's API Key row, which
named the reading as the fault rather than the feature. `isHidden` is the read.

**A stand-in that died before it distinguished anything.** An earlier reading of
the label defect had both arms dying on `_new_api_key`, which the real build
creates from `CONTROL_SPECS`. Both arms failing identically proved nothing, and
the stand-in was the fault, not the fix. It was rebuilt the way
`src/gui/react_settings_dialog.py`, in `SettingsDialogReact`, builds its holders.

## A defect this unit found and fixed

`_sync_credential_kind` hides each row's label beside its row, and only
`_create_exchange_tab` holds one. `SettingsDialogReact` overrides `_setup_ui`
alone, so that method never runs there — and `ACTION_HANDLERS` maps the Add press
to the inherited `_add_exchange`, whose `finally` calls `_sync_credential_kind`
on every press.

`_build_holders` gives every `CONTROL_SPECS` row an attribute of the same name,
so the rows exist on that build. No spec row and no `TEXT_NAMES` entry names a
label, so the three label names did not. `__init__` declares all three now, and
`_create_exchange_tab` still overwrites them with the real labels on the Qt
build. Driven on a dialog overriding `_setup_ui` alone,
`_sync_credential_kind` raises nothing; with the new label name removed it raises
`AttributeError` on exactly that name. The two labels that preceded this row
carried the same hazard and are closed by the same three lines.

## What this row does not answer

`src/gui/settings_dialog.py`, in `_create_exchange_tab`, disables six controls on
the stock wing, carrying `STOCK_DISABLED_TIP`: "Stock broker connector
integration is queued; no live brokers ship yet." E*TRADE is offered under all
six sectors and `wing_or_default` maps five of them onto the crypto wing, where
every control is enabled, so the operator reaches an enabled E*TRADE form on five
of six sectors and this row is reachable. That sentence is stale for all 21
stocks venues equally, which makes it its own row.

`PASSPHRASE_EXCHANGES` names four venues and the settings manual page said three.
The sentence is kept verbatim there under `OVERTAKEN, quoted whole:` with a
`True today:` line beneath it.
