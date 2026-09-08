// Acervator desktop shell, main process.
//
// Owns two things: the window, and the Python backend the window talks
// to. The backend is a child process reached over its own stdin and
// stdout, so the frontend opens no socket and listens on no port.
//
// That child is the trading program itself, started as `main.py --bridge`,
// so a panel reads the bots, exchange sessions and state of a running
// system rather than an empty one.

"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const REPO_ROOT = path.join(__dirname, "..");
const BRIDGE_SCRIPT = "main.py";
const BRIDGE_FLAG = "--bridge";
const CALL_CHANNEL = "acervator:call";
const PUSH_CHANNEL = "acervator:push";

function pythonExecutable() {
  return process.env.ACERVATOR_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

// ACERVATOR_BRIDGE_ARGV names the backend to spawn, one argument a space, so
// the shell can be pointed at `-m src.core.desktop_bridge` and reach the
// surfaces without the trading window. Unset, it starts the trading program.
function bridgeArguments() {
  const asked = String(process.env.ACERVATOR_BRIDGE_ARGV || "").trim();
  return asked ? asked.split(/\s+/) : [BRIDGE_SCRIPT, BRIDGE_FLAG];
}

// The Python backend, and the requests waiting on it. `pending` maps a
// request id to the promise callbacks for that id, which is what lets
// several surfaces share one pipe. `pushHandlers` holds the callbacks for
// the frames that answer no request.
class Bridge {
  constructor() {
    this.child = null;
    this.pending = new Map();
    this.pushHandlers = new Set();
    this.nextId = 1;
    this.buffer = "";
  }

  start() {
    this.child = spawn(pythonExecutable(), bridgeArguments(), {
      cwd: REPO_ROOT,
      stdio: ["pipe", "pipe", "pipe"]
    });
    this.child.stdout.setEncoding("utf8");
    this.child.stdout.on("data", (chunk) => this.onData(chunk));
    this.child.stderr.setEncoding("utf8");
    this.child.stderr.on("data", (text) => process.stderr.write("[backend] " + text));
    this.child.on("exit", (code) => this.onExit(code));
    this.child.on("error", (err) => this.failAll(err.message));
  }

  // One response is one line. A chunk may carry part of a line, or
  // several, so the remainder is held until its newline arrives.
  onData(chunk) {
    this.buffer += chunk;
    let cut = this.buffer.indexOf("\n");
    while (cut >= 0) {
      const line = this.buffer.slice(0, cut).trim();
      this.buffer = this.buffer.slice(cut + 1);
      if (line) {
        this.onFrame(line);
      }
      cut = this.buffer.indexOf("\n");
    }
  }

  // A push carries `push` and no `id`, so it matches no waiter and would
  // otherwise be dropped here.
  onFrame(line) {
    let frame;
    try {
      frame = JSON.parse(line);
    } catch (err) {
      process.stderr.write("[bridge] unparseable frame: " + line + "\n");
      return;
    }
    if (typeof frame.push === "string") {
      this.deliverPush(frame.push, frame.values || {});
      return;
    }
    const waiter = this.pending.get(frame.id);
    if (!waiter) {
      return;
    }
    this.pending.delete(frame.id);
    if (frame.ok) {
      waiter.resolve(frame.result);
    } else {
      const error = frame.error || {};
      waiter.reject(new Error((error.type || "Error") + ": " + (error.message || "")));
    }
  }

  // Returns the function that takes the handler off again.
  onPush(handler) {
    this.pushHandlers.add(handler);
    return () => this.pushHandlers.delete(handler);
  }

  deliverPush(section, values) {
    for (const handler of this.pushHandlers) {
      try {
        handler(section, values);
      } catch (err) {
        process.stderr.write("[bridge] push handler for " + section + ": " + err.message + "\n");
      }
    }
  }

  onExit(code) {
    this.child = null;
    this.failAll("the Python backend exited with code " + code);
  }

  failAll(message) {
    for (const waiter of this.pending.values()) {
      waiter.reject(new Error(message));
    }
    this.pending.clear();
  }

  call(method, params) {
    if (!this.child) {
      return Promise.reject(new Error("the Python backend is not running"));
    }
    const id = this.nextId++;
    const request = JSON.stringify({ id: id, method: method, params: params || {} });
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve: resolve, reject: reject });
      this.child.stdin.write(request + "\n");
    });
  }

  stop() {
    if (this.child) {
      this.child.stdin.end();
      this.child = null;
    }
  }
}

const bridge = new Bridge();

function broadcastPush(section, values) {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed() && !win.webContents.isDestroyed()) {
      win.webContents.send(PUSH_CHANNEL, section, values);
    }
  }
}

function createWindow() {
  // No background colour is named here. design_tokens.js serves every colour
  // from the Python surface, so the window stays hidden until the page has
  // painted its own ground and there is nothing for the shell to guess.
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    show: false,
    title: "Acervator",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });
  win.once("ready-to-show", () => win.show());
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  return win;
}

app.whenReady().then(() => {
  bridge.start();
  bridge.onPush(broadcastPush);
  ipcMain.handle(CALL_CHANNEL, (_event, method, params) => bridge.call(method, params));
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  bridge.stop();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

module.exports = {
  Bridge: Bridge,
  pythonExecutable: pythonExecutable,
  bridgeArguments: bridgeArguments,
  broadcastPush: broadcastPush,
  CALL_CHANNEL: CALL_CHANNEL,
  PUSH_CHANNEL: PUSH_CHANNEL
};
