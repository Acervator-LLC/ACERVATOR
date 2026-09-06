// The renderer's only way into the main process, and through it into
// Python. Two functions: `call` names a backend method and gets its
// result, `onPush` takes a frame the backend sent unasked.

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

const CALL_CHANNEL = "acervator:call";
const PUSH_CHANNEL = "acervator:push";

// Returns the function that takes `handler` off the channel again.
function onPush(handler) {
  const relay = (_event, section, values) => handler(section, values);
  ipcRenderer.on(PUSH_CHANNEL, relay);
  return () => ipcRenderer.removeListener(PUSH_CHANNEL, relay);
}

contextBridge.exposeInMainWorld("acervator", {
  call: (method, params) => ipcRenderer.invoke(CALL_CHANNEL, method, params),
  onPush: onPush
});
