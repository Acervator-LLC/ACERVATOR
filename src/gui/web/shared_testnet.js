// Reads the shared TestNet bridge from the shared_testnet.state payload.
//
// The bridge itself is backend work: one chain, one queue, one worker at
// a time, and a saved file. It draws nothing, so this module draws
// nothing either. It holds what the bridge answered so a panel can show
// the chain, the queue and the last save without asking again.
//
// Every value here arrives from `src/gui/main_tabs/shared_testnet_surface.py`.
// The chain fields are read by the names that payload publishes, so a
// field added on the Python side reaches a reader here with no edit.
(function (global) {
  "use strict";

  var METHOD = "shared_testnet.state";

  var ACTIONS = "actions";
  var AUTOSTART_TIMERS = "autostart_timers";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CHAIN = "chain";
  var CLOCK_DEFAULTED = "clock_defaulted";
  var DEFAULT_BOT_COUNT = "default_bot_count";
  var DEFAULT_RESET_REASON = "default_reset_reason";
  var DEFAULTS = "defaults";
  var GENESIS_HASH = "genesis_hash";
  var INSTALL_ATTRIBUTES = "install_attributes";
  var LOGGER_NAME = "logger_name";
  var PARTS = "parts";
  var PAYLOAD_KEYS = "payload_keys";
  var PERSIST = "persist";
  var PERSISTED = "persisted";
  var QUEUED = "queued";
  var RAISED_SIGNALS = "raised_signals";
  var RELATIVE_TEXT = "relative_text";
  var REQUEST_FIELDS = "request_fields";
  var REQUIRED = "required";
  var ROWS = "rows";
  var SAVE_PENDING = "save_pending";
  var SCHEMA_VERSION = "schema_version";
  var SIGNALS = "signals";
  var SINGLE_SHOT_TIMERS = "single_shot_timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TX_KEY_FIELD = "tx_key_field";
  var WIRED = "wired";
  var WORKER_HELD = "worker_held";
  var WORKER_RUNNING = "worker_running";
  var WORKER_SIGNAL = "worker_signal";

  var NOT_ASKED = "";
  var NO_BRIDGE = "the preload bridge is not present";
  var NOT_AN_OBJECT = "not-an-object";

  var ZERO = Number(NOT_ASKED);

  var held = null;
  var loadFault = null;
  var asked = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return isPlainObject(bag) && Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(model, field) {
    return owns(model, field) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return owns(model, field) && Array.isArray(model[field]) ? model[field] : [];
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  // ---- loading ---------------------------------------------------------

  function setSharedTestnet(model) {
    if (!isPlainObject(model)) {
      held = null;
      return { loaded: false, fault: NOT_AN_OBJECT };
    }
    held = model;
    return { loaded: true, fault: null };
  }

  // Asks the backend once and caches the request, so several panels
  // share one round trip.
  function loadSharedTestnet(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setSharedTestnet(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function forget() {
    held = null;
    loadFault = null;
    asked = null;
  }

  function payload() {
    return held;
  }

  function isLoaded() {
    return held !== null;
  }

  function loadError() {
    return loadFault;
  }

  function loggerName() {
    return owns(held, LOGGER_NAME) ? held[LOGGER_NAME] : undefined;
  }

  // ---- the saved file --------------------------------------------------

  function schemaVersion() {
    return owns(held, SCHEMA_VERSION) ? held[SCHEMA_VERSION] : undefined;
  }

  function persistParts() {
    return listField(objectField(held, PERSIST), PARTS).slice();
  }

  // The saved chain file relative to the home directory, as the surface
  // writes it. This module opens nothing.
  function persistPath() {
    var found = objectField(held, PERSIST);
    return owns(found, RELATIVE_TEXT) ? found[RELATIVE_TEXT] : NOT_ASKED;
  }

  function persistWired() {
    return objectField(held, PERSIST)[WIRED] === true;
  }

  function persisted() {
    var found = held === null ? null : held[PERSISTED];
    return isPlainObject(found) ? copyOf(found) : null;
  }

  // ---- the chain -------------------------------------------------------

  function chain() {
    return copyOf(objectField(held, CHAIN));
  }

  // The names a saved payload carries, as the surface publishes them.
  function payloadKeys() {
    return listField(held, PAYLOAD_KEYS).slice();
  }

  // One chain field by its published name, so a field added on the
  // Python side is readable here with no edit.
  function chainField(name) {
    var found = objectField(held, CHAIN);
    return owns(found, name) ? found[name] : undefined;
  }

  function chainList(name) {
    var found = chainField(name);
    return Array.isArray(found) ? found.slice() : [];
  }

  function genesisHash() {
    return owns(held, GENESIS_HASH) ? held[GENESIS_HASH] : NOT_ASKED;
  }

  function txKeyField() {
    return owns(held, TX_KEY_FIELD) ? held[TX_KEY_FIELD] : NOT_ASKED;
  }

  function clockDefaulted() {
    return listField(held, CLOCK_DEFAULTED).slice();
  }

  // ---- the chain rows a saved file restores ----------------------------

  function rowNames() {
    return Object.keys(objectField(held, ROWS));
  }

  function rowRequired(name) {
    return listField(objectField(objectField(held, ROWS), name), REQUIRED).slice();
  }

  function rowDefaults(name) {
    return copyOf(objectField(objectField(objectField(held, ROWS), name), DEFAULTS));
  }

  // ---- the queue and the worker ----------------------------------------

  function queued() {
    return listField(held, QUEUED).slice();
  }

  function queueDepth() {
    return listField(held, QUEUED).length;
  }

  function workerHeld() {
    return held !== null && held[WORKER_HELD] === true;
  }

  function workerRunning() {
    return held !== null && held[WORKER_RUNNING] === true;
  }

  function savePending() {
    return held !== null && held[SAVE_PENDING] === true;
  }

  function requestFields() {
    return listField(held, REQUEST_FIELDS).slice();
  }

  function defaultBotCount() {
    return owns(held, DEFAULT_BOT_COUNT) ? held[DEFAULT_BOT_COUNT] : undefined;
  }

  function defaultResetReason() {
    return owns(held, DEFAULT_RESET_REASON) ? held[DEFAULT_RESET_REASON] : NOT_ASKED;
  }

  // One competition request, carrying the four fields the surface names
  // and no other, in the order it names them.
  function requestFrom(given) {
    var asking = isPlainObject(given) ? given : {};
    var found = {};
    requestFields().forEach(function (field) {
      found[field] = owns(asking, field) ? asking[field] : null;
    });
    return found;
  }

  // ---- what the bridge did and said -------------------------------------

  function calls() {
    return listField(held, CALLS).slice();
  }

  function callNames() {
    return listField(held, CALL_NAMES).slice();
  }

  function raisedSignals() {
    return listField(held, RAISED_SIGNALS).slice();
  }

  function signals() {
    return listField(held, SIGNALS).slice();
  }

  function workerSignal() {
    return owns(held, WORKER_SIGNAL) ? held[WORKER_SIGNAL] : NOT_ASKED;
  }

  function actions() {
    return copyOf(objectField(held, ACTIONS));
  }

  function timers() {
    return copyOf(objectField(held, TIMERS));
  }

  function timerDelaysMs() {
    return listField(held, TIMER_DELAYS_MS).slice();
  }

  function singleShotTimers() {
    return listField(held, SINGLE_SHOT_TIMERS).slice();
  }

  function autostartTimers() {
    return listField(held, AUTOSTART_TIMERS).slice();
  }

  function busTopics() {
    return listField(held, BUS_TOPICS).slice();
  }

  function installAttributes() {
    return listField(held, INSTALL_ATTRIBUTES).slice();
  }

  // How many of a call name the bridge recorded, for a panel counting
  // drains, saves or refusals.
  function callCount(name) {
    var seen = ZERO;
    calls().forEach(function (one) {
      if (one === name) {
        seen += Number(true);
      }
    });
    return seen;
  }

  // What a status strip shows: where the chain is, how deep the queue
  // is, and whether the bridge is busy or owes a save.
  function summary() {
    if (held === null) {
      return null;
    }
    var found = {};
    payloadKeys().forEach(function (name) {
      var value = chainField(name);
      if (Array.isArray(value)) {
        found[name] = value.length;
      } else if (typeof value === "number") {
        found[name] = value;
      }
    });
    found[QUEUED] = queueDepth();
    found[WORKER_RUNNING] = workerRunning();
    found[SAVE_PENDING] = savePending();
    return found;
  }

  global.acervatorSetSharedTestnet = setSharedTestnet;
  global.acervatorLoadSharedTestnet = loadSharedTestnet;
  global.acervatorSharedTestnet = {
    method: METHOD,
    payload: payload,
    isLoaded: isLoaded,
    loadError: loadError,
    forget: forget,
    loggerName: loggerName,
    schemaVersion: schemaVersion,
    persistParts: persistParts,
    persistPath: persistPath,
    persistWired: persistWired,
    persisted: persisted,
    chain: chain,
    chainField: chainField,
    chainList: chainList,
    payloadKeys: payloadKeys,
    genesisHash: genesisHash,
    txKeyField: txKeyField,
    clockDefaulted: clockDefaulted,
    rowNames: rowNames,
    rowRequired: rowRequired,
    rowDefaults: rowDefaults,
    queued: queued,
    queueDepth: queueDepth,
    workerHeld: workerHeld,
    workerRunning: workerRunning,
    savePending: savePending,
    requestFields: requestFields,
    defaultBotCount: defaultBotCount,
    defaultResetReason: defaultResetReason,
    requestFrom: requestFrom,
    calls: calls,
    callNames: callNames,
    callCount: callCount,
    raisedSignals: raisedSignals,
    signals: signals,
    workerSignal: workerSignal,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    singleShotTimers: singleShotTimers,
    autostartTimers: autostartTimers,
    busTopics: busTopics,
    installAttributes: installAttributes,
    summary: summary
  };
})(window);
