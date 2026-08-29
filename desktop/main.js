// Acervator desktop shell, main process.
//
// Owns two things: the window, and the Python backend the window talks
// to. The backend is a child process reached over its own stdin and
// stdout, so the frontend opens no socket and listens on no port.

"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const REPO_ROOT = path.join(__dirname, "..");
const BRIDGE_MODULE = "src.core.desktop_bridge";
const CALL_CHANNEL = "acervator:call";

function pythonExecutable() {
  return process.env.ACERVATOR_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

// The Python backend, and the requests waiting on it. `pending` maps a
// request id to the promise callbacks for that id, which is what lets
// several surfaces share one pipe.
class Bridge {
  constructor() {
    this.child = null;
    this.pending = new Map();
    this.nextId = 1;
    this.buffer = "";
  }

  start() {
    this.child = spawn(pythonExecutable(), ["-m", BRIDGE_MODULE], {
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

  onFrame(line) {
    let frame;
    try {
      frame = JSON.parse(line);
    } catch (err) {
      process.stderr.write("[bridge] unparseable frame: " + line + "\n");
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

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    backgroundColor: "#0a0a0f",
    title: "Acervator",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
  return win;
}

app.whenReady().then(() => {
  bridge.start();
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

module.exports = { Bridge: Bridge, pythonExecutable: pythonExecutable };
