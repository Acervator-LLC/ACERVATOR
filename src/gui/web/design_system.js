// Renders each design token into the CSS declaration a screen paints
// with, units and alpha included.
(function (global) {
  "use strict";

  var METHOD = "design_system.state";

  var GROUP_NAMES_FIELD = "group_names";
  var GROUP_MEMBERS_FIELD = "group_members";
  var ALIASES_FIELD = "alias_targets";

  var MISSING_FAULT = "missing";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NO_TOKENS_FAULT = "no-token-table";
  var NO_VALUE_FAULT = "no-value";
  var NOT_A_NUMBER_FAULT = "not-a-number";
  var NOT_PLAIN_FAULT = "not-a-plain-number";
  var NOT_TEXT_FAULT = "not-text";
  var UNKNOWN_KIND_FAULT = "unknown-kind";
  var SPLIT_HEX_FAULT = "hex-read-differently";
  var ODD_HEX_FAULT = "hex-dropped-by-both";
  var SHADOW_SHAPE_FAULT = "not-a-shadow";
  var NOT_A_COLOUR_FAULT = "not-a-colour";
  var NO_UNIT_FAULT = "no-unit-for-kind";
  var NO_CARRIER = "no-name-carries-it";
  var SEVERAL_CARRIERS = "several-names-carry-it";
  var OTHER_KIND = "a-name-of-another-kind";

  var COLOUR_KIND = "colour";
  var LENGTH_KIND = "length";
  var TIME_KIND = "time";
  var PLAIN_KIND = "plain";
  var TEXT_KIND = "text";
  var SHADOW_KIND = "shadow";

  var KIND_BY_GROUP = {
    colors: COLOUR_KIND,
    aliases: COLOUR_KIND,
    type_scale: LENGTH_KIND,
    spacing: LENGTH_KIND,
    radii: LENGTH_KIND,
    target_sizes: LENGTH_KIND,
    table_columns: LENGTH_KIND,
    focus: LENGTH_KIND,
    motion_ms: TIME_KIND,
    weights: PLAIN_KIND,
    line_heights: PLAIN_KIND,
    font_families: TEXT_KIND,
    shadows: SHADOW_KIND
  };

  var UNIT_BY_KIND = {};
  UNIT_BY_KIND[LENGTH_KIND] = "px";
  UNIT_BY_KIND[TIME_KIND] = "ms";
  UNIT_BY_KIND[PLAIN_KIND] = "";

  var CSS_PREFIX = "--";
  var VAR_OPEN = "var(";
  var VAR_CLOSE = ")";
  var DECLARATION_MARK = ": ";
  var RGBA_OPEN = "rgba(";
  var RGBA_CLOSE = ")";
  var SEPARATOR = ",";
  var SPACER = " ";
  var HEX_MARK = "0x";
  var HASH = "#";
  var EXPONENT_MARK = "e";

  // The alpha byte Qt writes runs to this scale, and a browser wants a share.
  var ALPHA_SCALE = 255;
  var ALPHA_STEP = Math.pow(ALPHA_SCALE, -1);
  var OPAQUE = 1;

  var RGBA_PARTS = 4;
  var ALPHA_AT = 3;
  var SHADOW_PARTS = 3;
  var OFFSET_AT = 0;
  var BLUR_AT = 1;
  var SHADOW_ALPHA_AT = 2;
  var NO_OFFSET = 0;
  var CHANNEL_DIGITS = 2;
  var CHANNELS = 3;
  var SHORT_HEX = 3;
  var LONG_HEX = 6;
  var SPLIT_HEX = 8;

  var held = null;
  var systemFaults = [];
  var refusalList = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function fault(name, kind, detail) {
    return { name: name, fault: kind, detail: detail };
  }

  function refusal(value, reason, carriers) {
    return { value: value, reason: reason, carriers: carriers };
  }

  // The token table `design_tokens.js` publishes, or null when it has not run.
  function tokenTable() {
    var api = global.acervatorTokens;
    var usable =
      api &&
      typeof api.has === "function" &&
      typeof api.token === "function" &&
      typeof api.names === "function";
    return usable ? api : null;
  }

  function cssVariable(name) {
    return CSS_PREFIX + name;
  }

  function cssReference(name) {
    return VAR_OPEN + cssVariable(name) + VAR_CLOSE;
  }

  function hexDigitsOf(value) {
    if (typeof value !== "string" || value.indexOf(HASH) !== NO_OFFSET) {
      return null;
    }
    return value.slice(HASH.length);
  }

  // Names a hex colour whose digit count Qt and a browser read differently.
  function hexFault(digits) {
    if (digits === null) {
      return null;
    }
    if (digits.length === SHORT_HEX || digits.length === LONG_HEX) {
      return null;
    }
    return digits.length === SPLIT_HEX ? SPLIT_HEX_FAULT : ODD_HEX_FAULT;
  }

  function byteOf(text) {
    var found = Number(HEX_MARK + text);
    return isNumber(found) ? found : null;
  }

  // The three channels of a `#rgb` or `#rrggbb` colour, or null for any other.
  function channelsOf(value) {
    var digits = hexDigitsOf(value);
    if (digits === null) {
      return null;
    }
    if (digits.length === SHORT_HEX) {
      var widened = "";
      for (var one = 0; one < digits.length; one += 1) {
        widened += digits.charAt(one) + digits.charAt(one);
      }
      digits = widened;
    }
    if (digits.length !== LONG_HEX) {
      return null;
    }
    var found = [];
    for (var at = 0; at < CHANNELS; at += 1) {
      var from = at * CHANNEL_DIGITS;
      var byte = byteOf(digits.slice(from, from + CHANNEL_DIGITS));
      if (byte === null) {
        return null;
      }
      found.push(byte);
    }
    return found;
  }

  // Converts Qt's alpha byte to the share a browser reads, leaving hex alone.
  function cssColour(value) {
    if (typeof value !== "string" || value.indexOf(RGBA_OPEN) !== NO_OFFSET) {
      return value;
    }
    var close = value.lastIndexOf(RGBA_CLOSE);
    if (close < RGBA_OPEN.length) {
      return value;
    }
    var parts = value.slice(RGBA_OPEN.length, close).split(SEPARATOR);
    if (parts.length !== RGBA_PARTS) {
      return value;
    }
    var alpha = Number(parts[ALPHA_AT]);
    if (!isNumber(alpha) || alpha <= OPAQUE) {
      return value;
    }
    parts[ALPHA_AT] = String(alpha * ALPHA_STEP);
    return RGBA_OPEN + parts.join(SEPARATOR) + RGBA_CLOSE;
  }

  function lengthText(value, unit) {
    var text = String(value);
    return text.indexOf(EXPONENT_MARK) < NO_OFFSET ? text + unit : null;
  }

  // One shadow triple as a `box-shadow` value, in the named colour's channels.
  function shadowValue(parts, colourName) {
    if (!Array.isArray(parts) || parts.length !== SHADOW_PARTS) {
      return null;
    }
    if (!isNumber(parts[OFFSET_AT]) || !isNumber(parts[BLUR_AT])) {
      return null;
    }
    if (typeof parts[SHADOW_ALPHA_AT] !== "string") {
      return null;
    }
    var alpha = byteOf(parts[SHADOW_ALPHA_AT]);
    if (alpha === null) {
      return null;
    }
    var tokens = tokenTable();
    var channels = tokens === null ? null : channelsOf(tokens.token(colourName));
    if (channels === null) {
      return null;
    }
    var offset = lengthText(parts[OFFSET_AT], UNIT_BY_KIND[LENGTH_KIND]);
    var blur = lengthText(parts[BLUR_AT], UNIT_BY_KIND[LENGTH_KIND]);
    if (offset === null || blur === null) {
      return null;
    }
    return (
      lengthText(NO_OFFSET, UNIT_BY_KIND[LENGTH_KIND]) +
      SPACER +
      offset +
      SPACER +
      blur +
      SPACER +
      RGBA_OPEN +
      channels.join(SEPARATOR) +
      SEPARATOR +
      String(alpha * ALPHA_STEP) +
      RGBA_CLOSE
    );
  }

  // Renders one token under its group's kind, recording why it renders nothing.
  function renderOne(name, group, value, colourName) {
    var kind = owns(KIND_BY_GROUP, group) ? KIND_BY_GROUP[group] : null;
    if (kind === null) {
      systemFaults.push(fault(name, UNKNOWN_KIND_FAULT, group));
      return null;
    }
    if (value === undefined) {
      systemFaults.push(fault(name, NO_VALUE_FAULT, group));
      return null;
    }
    if (kind === COLOUR_KIND) {
      if (typeof value !== "string") {
        systemFaults.push(fault(name, NOT_TEXT_FAULT, group));
        return null;
      }
      var digits = hexDigitsOf(value);
      var wrong = hexFault(digits);
      if (wrong !== null) {
        systemFaults.push(fault(name, wrong, value));
      }
      if (digits === null && value.indexOf(RGBA_OPEN) !== NO_OFFSET) {
        systemFaults.push(fault(name, NOT_A_COLOUR_FAULT, value));
      }
      return cssColour(value);
    }
    if (kind === TEXT_KIND) {
      if (typeof value !== "string") {
        systemFaults.push(fault(name, NOT_TEXT_FAULT, group));
        return null;
      }
      return value;
    }
    if (kind === SHADOW_KIND) {
      var shadow = shadowValue(value, colourName);
      if (shadow === null) {
        systemFaults.push(fault(name, SHADOW_SHAPE_FAULT, colourName));
      }
      return shadow;
    }
    if (!owns(UNIT_BY_KIND, kind)) {
      systemFaults.push(fault(name, NO_UNIT_FAULT, kind));
      return null;
    }
    if (!isNumber(value)) {
      systemFaults.push(fault(name, NOT_A_NUMBER_FAULT, group));
      return null;
    }
    var text = lengthText(value, UNIT_BY_KIND[kind]);
    if (text === null) {
      systemFaults.push(fault(name, NOT_PLAIN_FAULT, group));
    }
    return text;
  }

  // Walks the published group lists in order, so nothing depends on bag order.
  function renderAll(colourName) {
    systemFaults = [];
    refusalList = [];
    if (held === null) {
      return;
    }
    var tokens = tokenTable();
    held.order = [];
    held.rendered = {};
    held.groupOf = {};
    if (tokens === null) {
      systemFaults.push(fault(GROUP_NAMES_FIELD, NO_TOKENS_FAULT, null));
      return;
    }
    held.groupNames.forEach(function (group) {
      if (!owns(held.members, group)) {
        systemFaults.push(fault(group, MISSING_FAULT, GROUP_MEMBERS_FIELD));
        return;
      }
      if (!Array.isArray(held.members[group])) {
        systemFaults.push(fault(group, NOT_A_LIST_FAULT, GROUP_MEMBERS_FIELD));
        return;
      }
      held.members[group].forEach(function (name) {
        if (typeof name !== "string") {
          systemFaults.push(fault(String(name), NOT_TEXT_FAULT, group));
          return;
        }
        if (owns(held.groupOf, name)) {
          return;
        }
        held.groupOf[name] = group;
        held.order.push(name);
        var rendered = renderOne(name, group, tokens.token(name), colourName);
        if (rendered !== null) {
          held.rendered[name] = rendered;
        }
      });
    });
  }

  function setDesignSystem(model, colourName) {
    if (!isPlainObject(model)) {
      held = null;
      refusalList = [];
      systemFaults = [fault(GROUP_MEMBERS_FIELD, NOT_AN_OBJECT_FAULT, null)];
      return counts();
    }
    held = {
      groupNames: listField(model, GROUP_NAMES_FIELD),
      members: objectField(model, GROUP_MEMBERS_FIELD),
      aliases: objectField(model, ALIASES_FIELD),
      shadowColour: typeof colourName === "string" ? colourName : null,
      order: [],
      rendered: {},
      groupOf: {}
    };
    renderAll(held.shadowColour);
    return counts();
  }

  // Reuses the one ask for tokens already made, so this adds no round trip.
  function loadDesignSystem(colourName) {
    if (typeof global.acervatorLoadTokens !== "function") {
      setDesignSystem(null, colourName);
      return Promise.resolve(null);
    }
    return global.acervatorLoadTokens().then(function (model) {
      setDesignSystem(model, colourName);
      return model;
    });
  }

  function isLoaded() {
    return held !== null;
  }

  function alphaScale() {
    return ALPHA_SCALE;
  }

  function groupNames() {
    return held === null ? [] : held.groupNames.slice();
  }

  function groupOrder(group) {
    if (held === null || !owns(held.members, group)) {
      return [];
    }
    return Array.isArray(held.members[group]) ? held.members[group].slice() : [];
  }

  function declarationNames() {
    return held === null ? [] : held.order.slice();
  }

  function groupOf(name) {
    if (held === null || !owns(held.groupOf, name)) {
      return undefined;
    }
    return held.groupOf[name];
  }

  function kindOf(name) {
    var group = groupOf(name);
    if (group === undefined || !owns(KIND_BY_GROUP, group)) {
      return undefined;
    }
    return KIND_BY_GROUP[group];
  }

  function value(name) {
    if (held === null || !owns(held.rendered, name)) {
      return undefined;
    }
    return held.rendered[name];
  }

  // The whole declaration text a screen paints with, for one token by name.
  function declaration(name) {
    var found = value(name);
    if (found === undefined) {
      return undefined;
    }
    return cssVariable(name) + DECLARATION_MARK + found;
  }

  // One fresh record per rendered token, in the order the surface published.
  function declarations() {
    var found = [];
    declarationNames().forEach(function (name) {
      if (!owns(held.rendered, name)) {
        return;
      }
      found.push({
        name: name,
        group: held.groupOf[name],
        kind: kindOf(name),
        variable: cssVariable(name),
        reference: cssReference(name),
        value: held.rendered[name],
        text: declaration(name)
      });
    });
    return found;
  }

  // One record per colour whose CSS text differs from the surface's text.
  function conversions() {
    var found = [];
    var tokens = tokenTable();
    if (held === null || tokens === null) {
      return found;
    }
    declarationNames().forEach(function (name) {
      if (kindOf(name) !== COLOUR_KIND || !owns(held.rendered, name)) {
        return;
      }
      var was = tokens.token(name);
      if (was !== held.rendered[name]) {
        found.push({ name: name, from: was, to: held.rendered[name] });
      }
    });
    return found;
  }

  function aliasTarget(name) {
    if (held === null || !owns(held.aliases, name)) {
      return undefined;
    }
    return held.aliases[name];
  }

  // Whether a second name renders exactly what the name it copies renders.
  function aliasAgrees(name) {
    var target = aliasTarget(name);
    if (target === undefined) {
      return false;
    }
    return value(name) !== undefined && value(name) === value(target);
  }

  // Every non-alias name whose rendered text is `wanted`, in published order.
  function carriersOf(wanted) {
    var found = [];
    if (held === null) {
      return found;
    }
    declarationNames().forEach(function (name) {
      if (owns(held.aliases, name) || !owns(held.rendered, name)) {
        return;
      }
      if (held.rendered[name] === wanted) {
        found.push(name);
      }
    });
    return found;
  }

  // Names the one token of the wanted kind carrying `wanted`, refusing any tie.
  function tokenNameFor(wanted, kind) {
    var carriers = carriersOf(wanted);
    if (carriers.length === NO_OFFSET) {
      refusalList.push(refusal(wanted, NO_CARRIER, carriers));
      return undefined;
    }
    if (carriers.length > OPAQUE) {
      refusalList.push(refusal(wanted, SEVERAL_CARRIERS, carriers));
      return undefined;
    }
    if (kindOf(carriers[NO_OFFSET]) !== kind) {
      refusalList.push(refusal(wanted, OTHER_KIND, carriers));
      return undefined;
    }
    return carriers[NO_OFFSET];
  }

  function refusals() {
    return refusalList.slice();
  }

  function faults() {
    return systemFaults.slice();
  }

  // Every published count, each read off the list or bag it counts.
  function counts() {
    return {
      groups: held === null ? 0 : held.groupNames.length,
      declared: held === null ? 0 : held.order.length,
      held: held === null ? 0 : Object.keys(held.rendered).length,
      conversions: conversions().length,
      refusals: refusalList.length,
      faults: systemFaults.length
    };
  }

  // Writes each rendered token onto one element, and names what it wrote.
  function apply(target) {
    var written = [];
    if (held === null || !target || !target.style) {
      return written;
    }
    declarationNames().forEach(function (name) {
      if (!owns(held.rendered, name)) {
        return;
      }
      target.style.setProperty(cssVariable(name), held.rendered[name]);
      written.push(name);
    });
    return written;
  }

  function resolve(colourName) {
    if (held !== null) {
      held.shadowColour = typeof colourName === "string" ? colourName : null;
      renderAll(held.shadowColour);
    }
    return counts();
  }

  function forget() {
    held = null;
    systemFaults = [];
    refusalList = [];
  }

  global.acervatorSetDesignSystem = setDesignSystem;
  global.acervatorLoadDesignSystem = loadDesignSystem;
  global.acervatorDesignSystem = {
    method: METHOD,
    alphaScale: alphaScale,
    cssColour: cssColour,
    cssVariable: cssVariable,
    cssReference: cssReference,
    groupNames: groupNames,
    groupOrder: groupOrder,
    declarationNames: declarationNames,
    declaration: declaration,
    declarations: declarations,
    value: value,
    groupOf: groupOf,
    kindOf: kindOf,
    conversions: conversions,
    aliasTarget: aliasTarget,
    aliasAgrees: aliasAgrees,
    carriersOf: carriersOf,
    tokenNameFor: tokenNameFor,
    refusals: refusals,
    faults: faults,
    counts: counts,
    isLoaded: isLoaded,
    apply: apply,
    resolve: resolve,
    forget: forget
  };
})(window);
