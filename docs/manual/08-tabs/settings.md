# Settings

Reference. `SettingsDialog` in `src/gui/settings_dialog.py`. The two pages
below are the ones Part 3 names.

## The eleven pages

One method adds them, in one order.

`src/gui/settings_dialog.py` — `SettingsDialog._setup_ui`

```python
tabs.addTab(self._create_user_tab(), "User")
tabs.addTab(self._create_exchange_tab(), "Exchanges")
tabs.addTab(self._create_trading_tab(), "Trading")
tabs.addTab(self._create_folding_tab(), "Profit Folding")
tabs.addTab(self._create_ta_tab(), "TA Indicators")
tabs.addTab(self._create_phantom_tab(), "Phantom Bots")
tabs.addTab(self._create_theme_tab(), "Theme")
tabs.addTab(self._create_logging_tab(), "Logging")
tabs.addTab(self._create_sound_tab(), "Sound")
tabs.addTab(self._create_sms_tab(), "SMS")
tabs.addTab(self._create_ai_monitor_tab(), "AI Monitor")
```

## What each page persists

`_save` writes and `_load_current` reads back. A control neither method touches
keeps its build-time default for the life of the process and reaches no engine.

| Page | Controls | `_save` writes | `_load_current` restores |
| ---- | -------: | -------------- | ------------------------ |
| User | 1 | the row | the row |
| Exchanges | 6 plus 3 buttons | on Add and Remove | the configured list |
| Trading | 6 | all six | four of six |
| Profit Folding | 11 | the whole group | `active` alone |
| TA Indicators | 12 | nothing | nothing |
| Phantom Bots | 13 | nothing | nothing |
| Theme | 6 | all six | the theme and the accent |
| Logging | 6 | the whole group | nothing |
| Sound | 10 plus 6 buttons | nothing | nothing |
| SMS | 17 | nothing | nothing |
| AI Monitor | 7 | all seven | all seven |

`AppSettings` in `src/core/settings.py` is the whole schema, and a key it does
not declare is refused outright rather than stored somewhere unread.

`src/core/settings.py` — `SettingsManager.set`

```python
def set(self, key: str, value: Any) -> None:
    """Set the ``AppSettings`` attribute *key* and call ``_save``.

    A *key* that ``AppSettings`` does not declare raises ``KeyError``.
    """
    with self._lock:
        if not hasattr(self._settings, key):
            raise KeyError(f"Unknown setting: {key}")
```

Four pages hold controls `_save` never reads, and the schema declares no field
any of them could land in: TA Indicators, Phantom Bots, Sound and SMS. Issue
#423 carries all four and counts the controls.

The Exchanges page is the exception to the whole pattern. `_add_exchange` and
`_remove_exchange` write through the settings manager as the operator uses
them, rather than waiting for Save.

The Sound page reaches its engine by one other route. The slider handler builds
a fresh configuration from every checkbox, pushes it in, and clears the sample
cache, because each sample bakes its volume at synthesis time.

`src/gui/settings_dialog.py` — `_on_sfx_volume_changed`

```python
se = get_sound_engine()
new_cfg = SoundConfig(
    enabled=self._sound_enabled.isChecked(),
    buy_sound=self._sound_buy.isChecked(),
    sell_sound=self._sound_sell.isChecked(),
    error_sound=self._sound_error.isChecked(),
    bot_state_sound=self._sound_state.isChecked(),
    fire_sound=self._sound_fire.isChecked(),
    track_sound=self._sound_track.isChecked(),
    profit_sound=self._sound_profit.isChecked(),
    drip_sound=self._sound_drip.isChecked(),
    volume=v / 100.0,
)
```

That path runs when the slider moves or a test button plays a sample, and at no
other time.

The parent section, [08-tabs.md](../08-tabs.md), carries the figure for each of
the eleven pages and names every control on it.

## Settings, User page

The whole page is one form row. No credential field, no licence field and no
key import.

`src/gui/settings_dialog.py` — `_create_user_tab`

```python
def _create_user_tab(self) -> QWidget:
    w = QWidget()
    form = QFormLayout(w)
    self._username = QLineEdit()
    form.addRow("Username:", self._username)
    return w
```

`_load_current` reads the stored value and `_save` writes it back through the
settings manager, which persists the schema under a home-relative directory as
a TOML file, or as JSON when no TOML writer is available. One lock guards every
read and write, shared across every manager instance.

### What a credential store would rest on

Both halves already exist, and the User page reads neither.

The first is encryption. A passphrase and a random salt derive a 256-bit key,
and each token carries its own salt and nonce.

`src/core/encryption.py` — `derive_key`

```python
def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from *passphrase* + *salt* via PBKDF2."""
```

`KeyringManager` holds the passphrase in the operating system's credential
store. Without the `cryptography` package a fallback keystream with an
HMAC-SHA256 tag takes over.

The second is the hardware-key path. A credential list encrypts against a USB
volume's serial and writes at that mount point, so the file decrypts on that
stick and nowhere else.

`src/core/usb_auth.py` — `write_auth_file`

```python
def write_auth_file(
    usb_path: Path,
    volume_serial: str,
    credentials: list[dict],
) -> Path:
    """Encrypt *credentials* under ``_derive_usb_key`` and write ``AUTH_FILENAME``.

    Each dict carries ``exchange_id``, ``api_key``, ``api_secret`` and
    ``passphrase``, and the written path under *usb_path* is returned.
    """
```

`find_auth_volume` matches the volume serial that `read_auth_file` needs to
derive the same key.

## Settings, Exchanges page

`_create_exchange_tab` lists the configured exchanges and offers a form to add
one: the exchange picker, an API key, an API secret, and a passphrase field
that appears only when the exchange needs one.

The picker lists what the connector layer can actually reach.

`src/exchange/ccxt_connector.py` — `SUPPORTED_EXCHANGES`, the first six

```python
SUPPORTED_EXCHANGES: dict[str, str] = {
    "binance": "binance",
    "coinbase": "coinbase",
    "kraken": "kraken",
    "kucoin": "kucoin",
    "bybit": "bybit",
    "okx": "okx",
```

Three venues need a passphrase, and the field appears for those alone.

`src/exchange/ccxt_connector.py` — `PASSPHRASE_EXCHANGES`

```python
PASSPHRASE_EXCHANGES: set[str] = {
    "kucoin",
    "okx",
    "bitget",
}
```

The key field accepts a Coinbase CDP key string as well as a plain key, and the
secret field accepts a PEM elliptic-curve private key. Escaped newlines inside
a pasted PEM convert on the way in.

Three handlers sit behind the buttons.

| Handler | What it does |
| ------- | ------------ |
| `_test_api_connection` | Authenticates against the venue and reports through `_set_feedback` |
| `_add_exchange` | Runs that test first and stores nothing when it fails |
| `_remove_exchange` | Drops the selected entry |

### The stock wing

The same page in the stock wing shows a banner and disables Add and Test.

`src/gui/settings_dialog.py` — `_create_exchange_tab`

```python
_banner = QLabel(
    "<b>Stock Wing:</b> equity-broker integration is "
    "queued — no live brokers are wired up yet. The "
    "list below shows the planned brokers; Add / Test "
    "are disabled until the broker connectors ship. "
    "Use the Crypto Wing for active trading today."
)
```

`EQUITY_EXCHANGE_IDS` fills the list with the planned brokers, each labelled as
planned. Crypto is the wing that trades today.

### What adding one does

The new exchange routes to the crypto layer or the stock layer, and the method
removes the placeholder tab if one stood there.

`src/gui/main_window.py` — `add_exchange_tab`

```python
def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
    """Add exchange tab to the correct layer (crypto or stock)."""
    is_equity = self._is_equity_exchange(exchange_id)
```

The method emits a signal naming which layer the tab actually landed in, read
back from both layer widgets rather than from the argument it was given.

## Bridge

Two methods serve this screen.

| Bridge method | Serves | Renderer module |
| ------------- | ------ | --------------- |
| `settings_dialog.state` | The dialog and its eleven pages | `settings_dialog.js` |
| `exchange_tab.state` | One venue's tab | `exchange_tab.js` |

Back to [the subsystem index](README.md).
