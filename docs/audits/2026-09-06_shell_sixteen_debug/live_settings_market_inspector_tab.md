# `src/gui/live_settings/market_inspector_tab.py`

48 source lines. The panel registers and draws. It drew a Python error message
on every open, and after that was corrected it draws an empty slot where the Qt
tab draws the per-bot card.

## The error

The panel drew, with no fault recorded, and the words it drew were:

```
Market Inspector unavailable.

AttributeError: 'NoneType' object has no attribute 'build_per_bot_view'
```

`ok=True`, `registered=True`, `fiber=True`, 10 React calls, 609 characters of
markup.

The Qt tab, built on the same empty state, drew:

```
No Market Inspector scan yet.

Open the Market Inspector top-level tab and press Refresh to populate. The
scan runs across the top-50 CoinGecko markets on daily and weekly candles;
results are shared between the top-level tab and this per-bot view.
```

## Reproduction

The Electron run described in [README.md](README.md) reaches the panel. The
same answer comes from the bridge on its own:

```python
build_registry()["market_inspector_tab.state"]({"reset": True, "build": True})
```

Before the correction that call answered

```
bridge message : "<b>Market Inspector unavailable.</b><br><br>AttributeError: 'NoneType' object has no attribute 'build_per_bot_view'"
bridge delegated: False
```

and the Qt side, driven with the same absent bot, answered the per-bot card.

## The cause, located under `pdb`

`MarketInspectorTabModel.build` catches `Exception`, so the same statement was
run uncaught and `pdb.Pdb.setup` positioned on its traceback:

```
model.source is None
model.bot    is None
AttributeError: 'NoneType' object has no attribute 'build_per_bot_view'
pdb frame: ...(26)<module>(): model.source.build_per_bot_view(model.bot)
pdb p model.source -> None
```

`pdb` names the failing frame and the attribute: the model's `source` is
`None` at the call site.

`src/gui/web/market_inspector_tab.js` opens with

```js
function openingRequest() {
  return { reset: true, build: true };
}
```

`reset` makes a fresh `MarketInspectorTabModel`, whose `source` is `None`.
`build` then ran `MarketInspectorTabModel.build`, which does
`self.source.build_per_bot_view(self.bot)`. On a `None` source that raises
`AttributeError`, the method's own `except Exception` catches it, and the tab
fills its fallback screen with the type and text of the exception. The panel
was reporting a failure that the handler had manufactured: nothing had been
asked to build a view, so nothing could fail.

`src/core/desktop_bridge.build_registry` registers
`market_inspector_tab_surface.view_model` with no live system bound to it, so
the model never has a real builder and the fallback fired on every open.

## The correction

`view_model` now runs the delegation only once the request has given the model
a source, in `src/gui/main_tabs/market_inspector_tab_surface.py`:

```python
    asked = params.get("build", driven)
    return build_view_model(PANE_MODEL, asked and PANE_MODEL.source is not None)
```

This is the cause and not a symptom. Silencing the message in the renderer
would leave `build` dereferencing `None` for the next caller. The guard stops a
build that has nothing to build from, and leaves every other path alone.

## The rerun

The bridge, driven three ways:

```
opening   delegated: False message: ''
error     delegated: False message: '<b>Market Inspector unavailable.</b><br><br>RuntimeError: no scan'
view      delegated: True  view: 'a card'
```

The second line is the control: a real failure still fills the fallback screen,
so the guard did not blind it. The third shows delegation still works.

The Electron run afterwards: `ok=True`, `fault=None`, markup down from 609 to
222 characters, text empty. The Python error is off the screen.

## What is still not equal

The React panel draws `ViewSlot`, an empty div, wherever the view belongs.
`Tab` returns that slot whenever `delegated` is true, and the fallback screen
otherwise, so the per-bot card itself has no React drawing at all. The Qt tab
delegates to `build_per_bot_view` in `src/gui/market_inspector.py`, which
builds the asset card, the top-five markets and the opposing pairs as Qt
widgets.

The panel's handler is also never bound to the shared analyzer, so the bridge
has no scan to serve even if the slot were filled.

The row is not equal across the two variants until the per-bot view is drawn in
React and its handler reads the shared analyzer.
