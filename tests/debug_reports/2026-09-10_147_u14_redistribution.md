# `src/competition/event_redistribution.py`

The pot that divides on a normalised performance score, and the reserve the
division leaves behind. Five errors came out of driving the real construction
path and reading what the program reported about itself. Each correction and its
rerun is below.

## Error 1, the error — the division refused a pot typed as text

```
Traceback (most recent call last):
  File "U14_drive_surface.py", line 117, in <module>
    print("EMPTY SCORES", divide_pot("e", "0.1", []).to_dict())
                          ~~~~~~~~~~^^^^^^^^^^^^^^^^
  File "...event_redistribution.py", line 217, in divide_pot
    pot_units = to_base_units(pot, "pot")
  File "...event_redistribution.py", line 69, in to_base_units
    quantity = _as_quantity(amount, name)
  File "...event_redistribution.py", line 49, in _as_quantity
    raise RedistributionError(
        f"{name} must be int, float or Decimal, not {type(value).__name__}"
    )
src.competition.event_redistribution.RedistributionError: pot must be int,
float or Decimal, not str
```

## Error 1, reproduction

The edge cases at the end of the surface driver, run under
`python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.

## Error 1, the cause

The driver passed `"0.1"`. `_as_quantity` admits `int`, `float` and `Decimal`
and refuses every other type, which is the same refusal
`QuintessenceLedger._as_amount` makes on an amount.

## Error 1, the correction

The driver now passes `Decimal("0.1")`. Widening `_as_quantity` to parse a
string was rejected: a pot is money, a string amount is an unchecked parse, and
the ledger refuses one on the same grounds.

## Error 1, the rerun

```
NO SCORES {"event_id": "e", "pot": "0.1", "return_pool": "0.075",
  "shares": [], "paid_total": "0", "held_back": "0.025",
  "division_remainder": "0.075", "reserve": "0.1", "is_exact": true}
```

## Error 2, the error — three scored participants came back unscored

No traceback. The program reported three participants with four scored axes each
as carrying no score, and divided nothing.

```
THREE EQUAL ON 0.1 {"shares": [], "unscored": ["a", "b", "c"],
  "paid_total": "0", "reserve": "0.1"}
```

## Error 2, reproduction

`performance_score("a", {"grade_numeric": 1.0, "scored_axes": 4})` in the
surface driver, same command as Error 1.

## Error 2, the cause

`rpg_metrics.grade_metrics` reads `overall_numeric` off the grade and publishes
it under the name `grade_numeric`. The driver's dict carried the published name
and not the source name, so `grade_metrics` answered None, `performance_score`
fell back to a score of nought with no axes, and `is_scoreable` was false.

## Error 2, the correction

The driver now builds its grades with `grade_trade`, which is the shape
`grade_metrics` reads. The fixture was wrong and the module was right: it reads
Unit 11's conversion rather than a field name of its own.

## Error 2, the rerun

```
EVEN GRADE 1.0 axes 2
THREE EQUAL SCORES [{'address': 'a', 'score': '1', 'scored_axes': 2,
  'standing': 'scored'}, ...]
THREE EQUAL ON 0.1 shares a 0.025, b 0.025, c 0.025
  paid_total 0.075   division_remainder 0   reserve 0.025
```

## Error 3, the error — the summary printed an exponent where a balance belongs

No traceback. `EventRedistribution.summary` and the ledger's own conservation
report both printed a zero as `0E-18`, which is the text a wallet row and a pot
row put on screen.

```
SUMMARY {"pot": "0E-18", "return_pool": "0E-18", "reserve": "0E-18"}
AFTER {"delta": "0E-18", ...}
```

## Error 3, reproduction

`SharedTestnetBridge.install_on` with every path in a scratch directory, then
`summary("elite-1")` on an event nobody acted in, under the same command.

## Error 3, the cause

`from_base_units` scales an integer by `-18`, so `Decimal(0).scaleb(-18)` is
`Decimal('0E-18')` and `str` prints the exponent. Every payout amount then
reaches the ledger at eighteen places, so `QuintessenceConservation.to_dict` and
the wallet balance printed the same form.

## Error 3, the correction

`quintessence_ledger.amount_text` formats a Decimal in plain notation with no
exponent and no trailing zeros, and it is the one definition. The ledger's
movement, conservation and supply readouts use it, the redistribution's readouts
import it, and `quintessence_section` uses it for the wallet balance. The
Decimal fields keep every place they had, so no amount changed.

## Error 3, the rerun

```
SUMMARY {"pot": "0", "return_pool": "0", "reserve": "0"}
AFTER {"delta": "0", "held_total": "0.077750000000000001", ...}
WALLET small_spender 4.394764541529083058
```

## Error 4, the error — a settled pot reported itself unsettled, and would pay twice

No traceback. The panel drew `is_settled` false on an event whose pot had
already been paid out, because the only record of the payout was in the object
that made it.

```
PANEL live "paid_total": "0.233249999999999999", "is_settled": false
```

## Error 4, reproduction

Fill one chain, call `settle`, then build a second `EventRedistribution` over
the same two files and read `summary`, which is what the tab surface does on
every request.

## Error 4, the cause

`settle` kept its division in `self._settled`, an in-process dict. A second
object over the same files saw no settlement, so `settle` would have divided the
pot again and paid every share a second time out of whatever still rested at the
pot address.

## Error 4, the correction

`PoaRecordStore.write_payout` stamps `paid` and `settled_at` onto every record
in the event and saves, and `event_settled_at` reads the latest stamp back.
`settle` refuses an event that carries a stamp. The store is stamped before the
ledger moves and `clear_payout` takes the stamp off when the ledger refuses, so
a failure leaves the pot unpaid rather than paid twice.

## Error 4, the rerun

One run paid the event and exited. A second run read the files back.

```
SETTLED AT live 1700000500.0
SECOND SETTLE REFUSED live raid was settled at 1700000500.0; a second payout
  would take Quintessence the pot no longer rests
PANEL live "is_settled": true, "settled_at": 1700000500.0
alpha paid 0.103724233673922701   beta paid 0.129525766326077298   gamma paid 0
```

## Error 5, the error — the page run crashed and drew nothing

```
exit=139
=== DRAWN live 0 characters ===
Windows fatal exception: access violation
Current thread 0x00002f7c [CrBrowserMain] (most recent call first):
  <no Python frame>
```

## Error 5, reproduction

Driving `ProofOfAccumulationReactPanel` and reading `DRAWN_TEXT_JS`, with
`app.processEvents()` in a counting loop and `QTimer.singleShot(0, app.quit)` at
the end.

## Error 5, the cause

Three faults in the driver. `processEvents` in a loop never let the web engine
finish its load, so `runJavaScript` answered an empty document. The widget was
deleted while its page was still live, which is the access violation. And
`os._exit` skipped the flush, so a later run printed nothing at all.

## Error 5, the correction

The driver waits on `loadFinished` through a `QEventLoop`, reads the text in a
second loop, holds every widget for the life of the process, and flushes both
streams before `os._exit`. The GPU path is taken out of the picture with
`QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu`, which is a fact about this host and
not about the page.

## Error 5, the rerun

```
PAGE READY live True        PAGE READY testnet True
=== DRAWN live 3180 characters ===      === DRAWN testnet 3188 characters ===
  'Redistribution' drawn: True
  'Return pool, 75%' drawn: True
  'Paid to participants' drawn: True
  'Division remainder' drawn: True
  'Reserve, resting on-chain' drawn: True
  '0.311' drawn: True
  '0.23325' drawn: True
  '0.233249999999999999' drawn: True
  '0.000000000000000001' drawn: True
  '0.077750000000000001' drawn: True
  'alpha - score 0.8008' drawn: True
  'beta - score 1' drawn: True
  'gamma - no scored axis, so no share' drawn: True
  'never sizes a share' drawn: True
  'No control starts a payout' drawn: True
  "The record store holds each use's quality" drawn: True
  "No field holds a use's quality" drawn: False
```

## What the run could not answer

Nothing joins a certified fill to a participant's event record, so no run could
show a live performance score reaching a share. `CertifiedFill` in
`src/competition/certification_socket.py` carries `trade_grade` and
`scored_axes`, and `EventRedistribution.write_grade` takes a grade, but no code
path connects the two.
