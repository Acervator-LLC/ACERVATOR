// The renderer's only way into the main process, and through it into
// Python. One function: name a backend method, get its result.

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("acervator", {
  call: (method, params) => ipcRenderer.invoke("acervator:call", method, params)
});
