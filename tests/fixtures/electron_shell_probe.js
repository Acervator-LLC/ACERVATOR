// Runs the shipped desktop/main.js under Electron and reports what each
// panel drew, as JSON on the path ACERVATOR_PROBE_OUT.
//
// Two things are redirected before main.js is required: the backend child
// becomes `python -m src.core.desktop_bridge` under a throwaway home, and
// every BrowserWindow opens hidden. Everything else is the shipped shell.

"use strict";

const Module = require("module");
const path = require("path");
const fs = require("fs");

const OUT = process.env.ACERVATOR_PROBE_OUT;
const MAIN = process.env.ACERVATOR_PROBE_MAIN;
const PYTHON = process.env.ACERVATOR_PROBE_PYTHON || "python";
const PROBE_HOME = process.env.ACERVATOR_PROBE_HOME;
const SETTLE_MS = Number(process.env.ACERVATOR_PROBE_SETTLE_MS || 4000);
const DEADLINE_MS = Number(process.env.ACERVATOR_PROBE_DEADLINE_MS || 180000);
const BRIDGE_MODULE = "src.core.desktop_bridge";

const realLoad = Module._load;
const spawned = [];

function childEnvironment() {
  const env = Object.assign({}, process.env);
  env.USERPROFILE = PROBE_HOME;
  env.HOME = PROBE_HOME;
  env.ACERVATOR_TEST_HOME = PROBE_HOME;
  return env;
}

Module._load = function (request, parent, isMain) {
  const loaded = realLoad.apply(this, arguments);
  if (request === "child_process") {
    const patched = Object.create(loaded);
    patched.spawn = function (command, args, options) {
      spawned.push({ command: command, args: args });
      const settings = Object.assign({}, options, { env: childEnvironment() });
      return loaded.spawn(PYTHON, ["-m", BRIDGE_MODULE], settings);
    };
    return patched;
  }
  if (request === "electron" && loaded && loaded.BrowserWindow) {
    const real = loaded.BrowserWindow;
    function HiddenWindow(options) {
      const preferences = Object.assign({}, (options || {}).webPreferences, {
        backgroundThrottling: false
      });
      return new real(
        Object.assign({}, options, { show: false, webPreferences: preferences })
      );
    }
    HiddenWindow.getAllWindows = real.getAllWindows.bind(real);
    HiddenWindow.fromWebContents = real.fromWebContents.bind(real);
    return Object.assign({}, loaded, { BrowserWindow: HiddenWindow });
  }
  return loaded;
};

const electron = require("electron");

function collectScript() {
  return (
    "(function () { return new Promise(function (resolve) {" +
    "  var host = window.acervatorPanelHost;" +
    "  if (!host) { resolve({ error: 'the page holds no acervatorPanelHost' }); return; }" +
    "  var container = document.getElementById('panels');" +
    "  var reactCalls = 0;" +
    "  var react = window.React;" +
    "  if (react && typeof react.createElement === 'function') {" +
    "    var real = react.createElement;" +
    "    react.createElement = function () {" +
    "      reactCalls += 1; return real.apply(react, arguments); };" +
    "  }" +
    "  var names = host.names();" +
    "  var drawn = [];" +
    "  var at = 0;" +
    "  function fibred(root) {" +
    "    var nodes = root ? root.querySelectorAll('*') : [];" +
    "    for (var at = 0; at < nodes.length; at++) {" +
    "      var keys = Object.keys(nodes[at]);" +
    "      for (var k = 0; k < keys.length; k++) {" +
    "        if (keys[k].indexOf('__reactFiber$') === 0) { return true; } } }" +
    "    return false; }" +
    "  function record(name, target, ok, late) {" +
    "    drawn.push({ panel: name, ok: Boolean(ok), late: Boolean(late)," +
    "      children: target ? target.children.length : 0," +
    "      markup: target ? String(target.innerHTML || '').length : 0," +
    "      html: target ? String(target.innerHTML || '').slice(0, 400) : ''," +
    "      fiber: fibred(target)," +
    "      text: target ? String(target.textContent || '').slice(0, 600) : ''," +
    "      react: reactCalls," +
    "      registered: host.registered().indexOf(name) >= 0," +
    "      fault: target ? target.getAttribute('data-panel-error') : null }); }" +
    "  function step() {" +
    "    if (at >= names.length) {" +
    "      resolve({ panels: drawn, registered: host.registered()," +
    "        names: names, missing: window.acervatorModules ?" +
    "          window.acervatorModules.missing() : null," +
    "        bridge: typeof (window.acervator || {}).call });" +
    "      return; }" +
    "    var name = names[at]; at += 1;" +
    "    var held = container.querySelector('[data-panel=\"' + name + '\"]');" +
    "    if (held) { container.removeChild(held); }" +
    "    var target = host.hostFor(container, name);" +
    "    reactCalls = 0;" +
    "    var settled = false;" +
    "    var finish = function (ok, late) {" +
    "      if (settled) { return; } settled = true;" +
    "      setTimeout(function () { record(name, target, ok, late); step(); }, " +
    String(Number(process.env.ACERVATOR_PROBE_DRAW_MS || 150)) +
    "); };" +
    "    setTimeout(function () { finish(false, true); }, " +
    String(Number(process.env.ACERVATOR_PROBE_PANEL_MS || 5000)) +
    ");" +
    "    try {" +
    "      host.open(name, target).then(finish, function () { finish(false); });" +
    "    } catch (err) { finish(false); }" +
    "  }" +
    "  step();" +
    "}); })()"
  );
}

function write(payload) {
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 1), "utf8");
}

function fail(reason) {
  write({ ok: false, reason: String(reason), spawned: spawned });
  electron.app.exit(0);
}

electron.app.on("browser-window-created", function (_event, win) {
  win.hide();
  win.webContents.setBackgroundThrottling(false);
  win.webContents.once("did-finish-load", function () {
    setTimeout(function () {
      win.webContents
        .executeJavaScript(collectScript(), true)
        .then(function (result) {
          write({ ok: true, spawned: spawned, result: result });
          electron.app.exit(0);
        })
        .catch(function (err) {
          fail("executeJavaScript refused: " + (err && err.message));
        });
    }, SETTLE_MS);
  });
});

setTimeout(function () {
  fail("the probe reached its deadline");
}, DEADLINE_MS);

require(path.resolve(MAIN));
