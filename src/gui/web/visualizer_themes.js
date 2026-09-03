// The visualizer canvas themes and bot tier palettes, as the Python
// surface serves them.
//
// Every colour, name and threshold reaches this file over the bridge
// from `src/gui/main_tabs/visualizer_themes_surface.py`. The module
// holds no theme value, no tier value and no threshold of its own.
//
// A colour arrives as `#rrggbbaa`, the CSS order the surface
// documents. `channels` splits it red first; a caller building
// `rgba(...)` reads the four numbers in that order. Qt reads eight hex
// digits alpha first, so a value from here must never reach a Qt
// widget as a colour string.
//
// `tierAnswer` walks the ceilings the surface sent, in the order they
// arrived, so a caller can price a balance again without a second
// round trip. The ceiling keys are words, so the browser keeps the
// order the surface built them in.
(function (global) {
  "use strict";

  var METHOD = "visualizer_themes.state";

  var THEME_FIELD_NAMES_FIELD = "theme_field_names";
  var TIER_FIELD_NAMES_FIELD = "tier_field_names";
  var THEME_COLOUR_FIELDS_FIELD = "theme_colour_fields";
  var TIER_COLOUR_FIELDS_FIELD = "tier_colour_fields";
  var DISPLAY_NAMES_FIELD = "display_names";
  var TIER_DISPLAY_NAMES_FIELD = "tier_display_names";
  var THEMES_FIELD = "themes";
  var TIER_PALETTES_FIELD = "tier_palettes";
  var THEME_CHANNELS_FIELD = "theme_channels";
  var TIER_CHANNELS_FIELD = "tier_channels";
  var CEILINGS_FIELD = "tier_ceilings_usd";
  var TOP_TIER_FIELD = "top_tier";
  var REQUESTED_THEME_FIELD = "requested_theme";
  var REQUESTED_TIER_FIELD = "requested_tier";
  var THEME_FIELD = "theme";
  var TIER_PALETTE_FIELD = "tier_palette";
  var UNKNOWN_THEME_FIELD = "unknown_theme";
  var UNKNOWN_TIER_FIELD = "unknown_tier";
  var TARGET_BALANCE_TEXT_FIELD = "target_balance_text";
  var TIER_FIELD = "tier";
  var TIER_REFUSAL_FIELD = "tier_refusal";
  var ACTIONS_FIELD = "actions";
  var TIMERS_FIELD = "timers";
  var TIMER_DELAYS_FIELD = "timer_delays_ms";
  var BUS_TOPICS_FIELD = "bus_topics";
  var SKIN_FIELD = "skin";

  var NAME_PARAM = "name";
  var TIER_PARAM = "tier";
  var BALANCE_PARAM = "target_balance";

  var NOT_ASKED = "";
  var NO_BRIDGE = "the preload bridge is not present";
  var NOT_LOADED = "the visualizer themes have not loaded";
  var NOT_A_NUMBER = "target_balance is not a number";
  var HEX_PAIR = /^[0-9a-fA-F]{2}$/;
  var RGBA_OPEN = "rgba(";
  var COMMA = ", ";
  var CLOSE = ")";

  var held = null;
  var loadFault = null;
  var asked = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function textField(model, field) {
    return isPlainObject(model) && typeof model[field] === "string"
      ? model[field]
      : NOT_ASKED;
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  // ---- the pure functions the surface also publishes ------------------

  // The red, green, blue and transparency of an `#rrggbbaa` colour, red
  // first, refusing anything shorter than eight hex digits.
  function channels(colour) {
    var digits = String(colour).replace(/^#+/, "");
    if (digits.length < 8) {
      throw new Error("not an eight-digit colour: " + colour);
    }
    return [
      digits.slice(0, 2),
      digits.slice(2, 4),
      digits.slice(4, 6),
      digits.slice(6, 8)
    ].map(function (pair) {
      if (!HEX_PAIR.test(pair)) {
        throw new Error("not a hex byte in " + colour + ": " + pair);
      }
      return parseInt(pair, 16);
    });
  }

  // The name a caller asked for, and the empty string for anything
  // else that is not text.
  function requestedName(name) {
    return typeof name === "string" ? name : NOT_ASKED;
  }

  // One `#rrggbbaa` colour as the `rgba(...)` text a style sheet reads,
  // in the order `channels` reports.
  function rgbaText(colour) {
    var parts = channels(colour);
    return (
      RGBA_OPEN +
      parts[0] +
      COMMA +
      parts[1] +
      COMMA +
      parts[2] +
      COMMA +
      parts[3] / 255 +
      CLOSE
    );
  }

  // ---- loading the surface's answer ------------------------------------

  function setThemes(model) {
    if (!isPlainObject(model)) {
      held = null;
      return { loaded: false, fault: "not-an-object" };
    }
    held = {
      themeFieldNames: listField(model, THEME_FIELD_NAMES_FIELD),
      tierFieldNames: listField(model, TIER_FIELD_NAMES_FIELD),
      themeColourFields: listField(model, THEME_COLOUR_FIELDS_FIELD),
      tierColourFields: listField(model, TIER_COLOUR_FIELDS_FIELD),
      displayNames: objectField(model, DISPLAY_NAMES_FIELD),
      tierDisplayNames: objectField(model, TIER_DISPLAY_NAMES_FIELD),
      themes: objectField(model, THEMES_FIELD),
      tierPalettes: objectField(model, TIER_PALETTES_FIELD),
      themeChannels: objectField(model, THEME_CHANNELS_FIELD),
      tierChannels: objectField(model, TIER_CHANNELS_FIELD),
      ceilings: objectField(model, CEILINGS_FIELD),
      topTier: textField(model, TOP_TIER_FIELD),
      requestedTheme: textField(model, REQUESTED_THEME_FIELD),
      requestedTier: textField(model, REQUESTED_TIER_FIELD),
      theme: objectField(model, THEME_FIELD),
      tierPalette: objectField(model, TIER_PALETTE_FIELD),
      unknownTheme: listField(model, UNKNOWN_THEME_FIELD),
      unknownTier: listField(model, UNKNOWN_TIER_FIELD),
      targetBalanceText: textField(model, TARGET_BALANCE_TEXT_FIELD),
      tier: textField(model, TIER_FIELD),
      tierRefusal: textField(model, TIER_REFUSAL_FIELD),
      actions: objectField(model, ACTIONS_FIELD),
      timers: objectField(model, TIMERS_FIELD),
      timerDelaysMs: listField(model, TIMER_DELAYS_FIELD),
      busTopics: listField(model, BUS_TOPICS_FIELD),
      skin: objectField(model, SKIN_FIELD)
    };
    return { loaded: true, fault: null };
  }

  // Asks the backend once and caches the request, so several panels
  // share one round trip.
  function loadVisualizerThemes(name, tier, targetBalance) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    if (typeof name === "string") {
      params[NAME_PARAM] = name;
    }
    if (typeof tier === "string") {
      params[TIER_PARAM] = tier;
    }
    if (typeof targetBalance === "number" && isFinite(targetBalance)) {
      params[BALANCE_PARAM] = targetBalance;
    }
    asked = global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setThemes(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  // ---- reading the loaded table ----------------------------------------

  function isLoaded() {
    return held !== null;
  }

  // Reports the themes actually held, so a name the payload drops
  // disappears from here too.
  function themeNames() {
    return held === null ? [] : Object.keys(held.themes);
  }

  function tierNames() {
    return held === null ? [] : Object.keys(held.tierPalettes);
  }

  function themeFieldNames() {
    return held === null ? [] : held.themeFieldNames.slice();
  }

  function tierFieldNames() {
    return held === null ? [] : held.tierFieldNames.slice();
  }

  function themeColourFieldNames() {
    return held === null ? [] : held.themeColourFields.slice();
  }

  function tierColourFieldNames() {
    return held === null ? [] : held.tierColourFields.slice();
  }

  function hasTheme(name) {
    return held !== null && typeof name === "string" && owns(held.themes, name);
  }

  function hasTier(name) {
    return held !== null && typeof name === "string" && owns(held.tierPalettes, name);
  }

  // One canvas theme's values, or an empty table for a name `hasTheme`
  // reports as absent.
  function themeColours(name) {
    return hasTheme(name) ? copyOf(held.themes[name]) : {};
  }

  // One tier palette's values, or an empty table for a name `hasTier`
  // reports as absent.
  function tierColours(name) {
    return hasTier(name) ? copyOf(held.tierPalettes[name]) : {};
  }

  function themeDisplayName(name) {
    if (held === null || !owns(held.displayNames, name)) {
      return undefined;
    }
    return held.displayNames[name];
  }

  function tierDisplayName(name) {
    if (held === null || !owns(held.tierDisplayNames, name)) {
      return undefined;
    }
    return held.tierDisplayNames[name];
  }

  // The channels the surface already worked out for one theme colour,
  // read back rather than reparsed from the hex text.
  function themeChannelsFor(name, field) {
    if (held === null || !owns(held.themeChannels, name)) {
      return undefined;
    }
    var row = held.themeChannels[name];
    return owns(row, field) ? row[field].slice() : undefined;
  }

  function tierChannelsFor(name, field) {
    if (held === null || !owns(held.tierChannels, name)) {
      return undefined;
    }
    var row = held.tierChannels[name];
    return owns(row, field) ? row[field].slice() : undefined;
  }

  function ceilings() {
    return held === null ? {} : copyOf(held.ceilings);
  }

  function topTier() {
    return held === null ? NOT_ASKED : held.topTier;
  }

  // The tier one balance maps to, walking the loaded ceilings in their
  // own order.
  function tierAnswer(targetBalance) {
    if (held === null) {
      return [NOT_ASKED, NOT_LOADED];
    }
    if (typeof targetBalance !== "number" && typeof targetBalance !== "boolean") {
      return [NOT_ASKED, NOT_A_NUMBER];
    }
    var value = Number(targetBalance);
    var order = Object.keys(held.ceilings);
    for (var i = 0; i < order.length; i += 1) {
      if (value < held.ceilings[order[i]]) {
        return [order[i], NOT_ASKED];
      }
    }
    return [held.topTier, NOT_ASKED];
  }

  function tierForTargetBalance(targetBalance) {
    return tierAnswer(targetBalance)[0];
  }

  function requestedTheme() {
    return held === null ? NOT_ASKED : held.requestedTheme;
  }

  function requestedTier() {
    return held === null ? NOT_ASKED : held.requestedTier;
  }

  function askedTheme() {
    return held === null ? {} : copyOf(held.theme);
  }

  function askedTierPalette() {
    return held === null ? {} : copyOf(held.tierPalette);
  }

  function unknownTheme() {
    return held === null ? [] : held.unknownTheme.slice();
  }

  function unknownTier() {
    return held === null ? [] : held.unknownTier.slice();
  }

  function targetBalanceText() {
    return held === null ? NOT_ASKED : held.targetBalanceText;
  }

  function tier() {
    return held === null ? NOT_ASKED : held.tier;
  }

  function tierRefusal() {
    return held === null ? NOT_ASKED : held.tierRefusal;
  }

  function actions() {
    return held === null ? {} : copyOf(held.actions);
  }

  function timers() {
    return held === null ? {} : copyOf(held.timers);
  }

  function timerDelaysMs() {
    return held === null ? [] : held.timerDelaysMs.slice();
  }

  function busTopics() {
    return held === null ? [] : held.busTopics.slice();
  }

  function skin() {
    return held === null ? {} : copyOf(held.skin);
  }

  function loadError() {
    return loadFault;
  }

  function forget() {
    held = null;
    loadFault = null;
    asked = null;
  }

  global.acervatorSetVisualizerThemes = setThemes;
  global.acervatorLoadVisualizerThemes = loadVisualizerThemes;
  global.acervatorVisualizerThemes = {
    method: METHOD,
    channels: channels,
    requestedName: requestedName,
    rgbaText: rgbaText,
    isLoaded: isLoaded,
    themeNames: themeNames,
    tierNames: tierNames,
    themeFieldNames: themeFieldNames,
    tierFieldNames: tierFieldNames,
    themeColourFieldNames: themeColourFieldNames,
    tierColourFieldNames: tierColourFieldNames,
    hasTheme: hasTheme,
    hasTier: hasTier,
    themeColours: themeColours,
    tierColours: tierColours,
    themeDisplayName: themeDisplayName,
    tierDisplayName: tierDisplayName,
    themeChannelsFor: themeChannelsFor,
    tierChannelsFor: tierChannelsFor,
    ceilings: ceilings,
    topTier: topTier,
    tierAnswer: tierAnswer,
    tierForTargetBalance: tierForTargetBalance,
    requestedTheme: requestedTheme,
    requestedTier: requestedTier,
    theme: askedTheme,
    tierPalette: askedTierPalette,
    unknownTheme: unknownTheme,
    unknownTier: unknownTier,
    targetBalanceText: targetBalanceText,
    tier: tier,
    tierRefusal: tierRefusal,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    busTopics: busTopics,
    skin: skin,
    loadError: loadError,
    forget: forget
  };
})(window);
