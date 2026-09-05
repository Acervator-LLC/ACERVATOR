# The desktop shell

The Electron frontend and the Python backend it talks to. It hosts the
History surface in `#root` and every other registered panel in `#panels`.

## The parts

| Path | Role |
|------|------|
| `desktop/main.js` | Main process. Owns the window and the Python child process. |
| `desktop/preload.js` | Exposes one function, `window.acervator.call`, to the page. |
| `desktop/renderer/index.html` | The page. Loads the panel assets that already exist. |
| `desktop/renderer/panel_host.js` | Draws a panel into a host element addressed by name. |
| `desktop/renderer/boot.js` | Asks the backend for the view model and pushes it to the panel. |
| `src/core/desktop_bridge.py` | The Python side of the channel. Dispatches one method per surface. |
| `src/exchange/history_surface.py` | Builds the History view model from `history_read_contract`. |

The renderer loads `src/gui/web/history_panel.js`, its stylesheet and the
vendored React from where they already are. No second copy exists.

## The panel host

A panel's name is its module file name without `.js`. The roster of names
is `window.ACERVATOR_MODULES`, which `tools/sync_renderer_modules.py`
writes, so the shell carries no list of panels.

A module joins the roster from its own script tag:

```js
if (global.acervatorPanelHost) {
  global.acervatorPanelHost.register({
    render: renderTab,
    load: loadConsole,
    loadError: loadError
  });
}
```

`document.currentScript` supplies the name, so the module spells out
none. `render(target, model)` draws into an element; `load(params)` asks
the bridge; `loadError()` reports a refusal the loader caught.

`boot.js` calls `acervatorPanelHost.mountAll(document.getElementById("panels"))`
once the bridge is present. Each registered panel gets its own
`<div data-panel="NAME">` under `#panels`, in manifest order.

A panel that does not draw is named rather than left blank. The reason
goes onto the host element as text and as `data-panel-error`, onto
`<html>` as `data-panel-error`, into `console.error`, and into
`acervatorPanelHost.faults()`. The four reasons are: the manifest names
no such module, the module did not load, the module registered no panel,
and the panel threw while drawing. A backend that refuses the view model
is reported the same way, from the promise's rejection handler.

`src/gui/web/console_tab.js` and `src/gui/web/header_strip.js` register
today. `tests/test_desktop_panel_host.py` draws both through the host and
compares each against the Qt widget it stands for.

## The channel

One request is one JSON object on one line, written to the Python child
process on its stdin. One response is one JSON object on one line, read
back on its stdout.

```
-> {"id": 1, "method": "history.view_model", "params": {"page": 0}}
<- {"id": 1, "ok": true, "result": {...}}
```

The channel uses no socket and no port. The backend is reachable only by the
process that started it, and it exits when that process exits.

`main` in `desktop_bridge.py` moves `sys.stdout` to stderr before it
reads the first request. A print anywhere in the backend then goes to
stderr instead of putting a line that is not a frame into the channel.

## To add a surface

1. Write a function that takes the request parameters and returns a
   serialisable result. Put it in the package that owns the domain.
2. Add it to `build_registry` in `src/core/desktop_bridge.py`.
3. Call it from the page with `window.acervator.call`.

The transport needs no change.

## To run it

Node and npm are not installed on the trading machine. Install Node
first. It supplies npm.

```
winget install OpenJS.NodeJS.LTS
```

Open a new terminal, then install Electron and start the shell:

```
cd desktop
npm install
npm start
```

`npm install` downloads Electron. It needs a network connection and
approximately 300 MB.

Set `ACERVATOR_PYTHON` if `python` is not the interpreter that has the
project dependencies.

## What runs without Node

Everything except Electron itself. The Python backend, the view model
and the panel assets are all verifiable now:

```
python -m pytest tests/test_desktop_bridge.py tests/test_desktop_shell_assets.py
```

`tests/test_desktop_shell_assets.py` parses the shell JavaScript with
the engine PySide6 ships, so a syntax error and a missing asset are
caught without a Node toolchain.
