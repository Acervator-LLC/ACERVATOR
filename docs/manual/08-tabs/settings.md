# Settings

Reference. `SettingsDialog` in `src/gui/settings_dialog.py`. `_setup_ui`
adds eleven pages in this order: User, Exchanges, Trading, Profit
Folding, TA Indicators, Phantom Bots, Theme, Logging, Sound, SMS and AI
Monitor. The two pages below are the ones Part 3 names.

## Settings, User page

`_create_user_tab` builds one form row holding a `Username` line edit.
That is the whole page today. No credential field, no licence field and
no key import.

`_load_current` reads the stored value and `_save` writes it back through
`SettingsManager` in `src/core/settings.py`, which persists `AppSettings`
under a home-relative directory as `settings.toml`, or as `settings.json`
when no TOML writer is available. One lock guards every read and write,
shared across every manager instance.

### What a credential store would rest on

Both halves already exist, and the User page reads neither.

`src/core/encryption.py` encrypts a secret with AES-256-GCM. `derive_key`
runs PBKDF2-HMAC-SHA256 over a passphrase and a random salt, and each
token carries its own salt and nonce. `KeyringManager` holds the
passphrase in the operating system's credential store. Without the
`cryptography` package a fallback keystream with an HMAC-SHA256 tag takes
over.

`src/core/usb_auth.py` is the hardware-key path. `write_auth_file`
encrypts a credential list and writes it at a USB mount point;
`find_auth_volume` matches the volume serial that `read_auth_file` needs
to derive the same key, so the file decrypts on that stick and nowhere
else.

## Settings, Exchanges page

`_create_exchange_tab` lists the configured exchanges and offers a form
to add one: the exchange picker, an API key, an API secret, and a
passphrase field that appears only when the exchange needs one.

`SUPPORTED_EXCHANGES`, `PASSPHRASE_EXCHANGES` and `exchange_label` come
from `src/exchange/ccxt_connector.py`, so the picker lists what the
connector layer can actually reach.

The key field accepts a Coinbase CDP key string as well as a plain key,
and the secret field accepts a PEM elliptic-curve private key. Escaped
newlines inside a pasted PEM convert on the way in.

Two buttons: `_test_api_connection` authenticates against the venue and
reports through `_set_feedback`, and `_add_exchange` tests before it
stores anything. `_remove_exchange` drops the selected entry.

### The stock wing

The same page in the stock wing shows a banner and disables Add and Test.
`EQUITY_EXCHANGE_IDS` fills the list with the planned brokers, each
labelled as planned. Crypto is the wing that trades today.

### What adding one does

`add_exchange_tab` in `src/gui/main_window.py` routes the new exchange to
the crypto or the stock layer by `_is_equity_exchange`, removes the
placeholder tab if one stood there, and constructs an `ExchangeTab` from
`src/gui/widgets/exchange_tab.py` holding that venue's bot list. The
method emits a signal naming which layer the tab actually landed in, read
back from both layer widgets rather than from the argument it was given.

## Bridge

`settings_dialog_surface` answers `settings_dialog.state` and
`exchange_tab_surface` answers `exchange_tab.state`. The renderer modules
are `settings_dialog.js` and `exchange_tab.js`.

Back to [the subsystem index](README.md).
