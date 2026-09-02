(function (global) {
  "use strict";

  // METHOD names the wire_canvas.state call this sheet is drawn from.
  var METHOD = "wire_canvas.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ALIGNMENT = "alignment";
  var ALPHA_UNIT = "alpha_unit";
  var BOT_CENTERS = "bot_centers";
  var BOT_CENTER_ORDER = "bot_center_order";
  var CALLS = "calls";
  var CURSOR = "cursor";
  var DRAWING_CALLS = "drawing_calls";
  var FONT = "font";
  var DRAW_CALL_NAMES = "draw_call_names";
  var NAME = "name";
  var NO_BRUSH = "no_brush";
  var OPACITY = "opacity";
  var PAINT_BRANCHES = "paint_branches";
  var PAINT_BRANCH_NAMES = "paint_branch_names";
  var PENS = "pens";
  var SOURCE_ID = "source_id";
  var STYLE_SHEET = "style_sheet";
  var TAB = "tab";
  var TARGET_ID = "target_id";
  var THEME = "theme";
  var WIRES = "wires";
  var WEIGHT_VALUE = "weight_value";
  var WIRE_ORDER = "wire_order";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    "actions",
    ALIGNMENT,
    "arrow",
    "attributes",
    "badge",
    "bus_topics",
    "buttons",
    CALLS,
    CURSOR,
    "cursors",
    "curve",
    "defaults",
    "drag",
    DRAWING_CALLS,
    DRAW_CALL_NAMES,
    "event_kinds",
    FONT,
    "formats",
    "glow",
    OPACITY,
    PAINT_BRANCHES,
    PAINT_BRANCH_NAMES,
    PENS,
    "pulse",
    "render_hint",
    "route_names",
    "signals",
    STYLE_SHEET,
    TAB,
    THEME,
    "timer_delays_ms",
    "timers"
  ];

  var SET_OPACITY = "set_opacity";
  var SET_PEN = "set_pen";
  var SET_BRUSH = "set_brush";
  var SET_GRADIENT_BRUSH = "set_gradient_brush";
  var SET_FONT = "set_font";
  var DRAW_PATH = "draw_path";
  var DRAW_ELLIPSE = "draw_ellipse";
  var DRAW_POLYGON = "draw_polygon";
  var DRAW_ROUNDED_RECT = "draw_rounded_rect";
  var DRAW_TEXT = "draw_text";
  var DRAW_LINE = "draw_line";

  // MOUNT_OPS are the operations no CSS box takes: a curve, a rotated
  // triangle, a sloped line.
  var MOUNT_OPS = [DRAW_PATH, DRAW_POLYGON, DRAW_LINE];

  var WIRE_DRAWN = "wire.drawn";
  var WIRE_SKIPPED = "wire.skipped";
  var DRAG_BRANCHES = ["drag.disconnect", "drag.connect", "drag.loose"];

  var SHEET_PART = "wire-sheet";
  var MOUNT_PART = "wire-mount";
  var WIRE_PART = "wire";
  var PULSE_PART = "pulse";
  var BADGE_PART = "badge";
  var LABEL_PART = "badge-label";

  var MOUNT_LABEL = "wire overlay canvas";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var INDEX_ATTR = "data-index";
  var SOURCE_ATTR = "data-source";
  var TARGET_ATTR = "data-target";
  var OPS_ATTR = "data-ops";
  var DRAG_ATTR = "data-drag";
  var BRANCH_ATTR = "data-branch";
  var LABEL_ATTR = "aria-label";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var ABSOLUTE = "absolute";
  var RELATIVE = "relative";
  var FLEX = "flex";
  var CENTRE = "center";
  var NONE = "none";
  var NOWRAP = "nowrap";
  var PX = "px";
  var PT = "pt";
  var RGBA_OPEN = "rgba(";
  var GRADIENT_OPEN = "radial-gradient(";
  var CLOSE = ")";
  var COMMA_SPACE = ", ";
  var SPACE = " ";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";

  var RADIUS_GROUPS = ["radii"];
  var WEIGHT_GROUPS = ["weights"];
  var FAMILY_GROUPS = ["font_families"];

  var NOT_AN_OBJECT_FAULT = "not_an_object";
  var MISSING_FAULT = "missing";
  var WRONG_KIND_FAULT = "wrong_kind";
  var QT_COLOUR_FAULT = "qt_colour";
  var UNEVEN_CORNER_FAULT = "uneven_corner";
  var OFF_CENTRE_FAULT = "off_centre";
  var SHORT_GROUP_FAULT = "short_group";
  var NOT_LOADED_FAULT = "not_loaded";
  var NULL_FAULT = "null";

  var NO_BRIDGE = "no_bridge";

  var held = null;
  var wireFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

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

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function record(where, field, kind, detail) {
    wireFaults.push(fault(where, field, kind, detail));
  }

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function inList(list, value) {
    return Boolean(
      list.filter(function (one) {
        return one === value;
      }).length
    );
  }

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function px(value) {
    return isNumber(value) ? String(value) + PX : undefined;
  }

  // rgba turns one published colour list into CSS, scaling its byte
  // alpha by the unit the surface publishes beside it.
  function rgba(model, parts) {
    var values = Array.isArray(parts) ? parts.slice() : [];
    if (!values.length) {
      return undefined;
    }
    var alpha = values.pop();
    var unit = objectField(model, THEME)[ALPHA_UNIT];
    var opacity = isNumber(unit) && isNumber(alpha) ? alpha * unit : alpha;
    return (
      RGBA_OPEN +
      values.join(COMMA_SPACE) +
      COMMA_SPACE +
      String(opacity) +
      CLOSE
    );
  }

  // qtColour asks the Bot Swarm tab why CSS would read one written
  // colour as a different one.
  function qtColour(value) {
    var api = global.acervatorBotSwarm;
    if (!api || typeof api.qtColour !== "function") {
      record(THEME, null, NOT_LOADED_FAULT, kindOf(api));
      return undefined;
    }
    return api.qtColour(value);
  }

  // colourOf refuses a written colour CSS reads as another, and answers
  // a published list of four numbers as CSS.
  function colourOf(model, where, value) {
    if (typeof value === "string") {
      var why = qtColour(value);
      if (why !== undefined) {
        record(where, null, QT_COLOUR_FAULT, value);
        return undefined;
      }
      return value;
    }
    if (!Array.isArray(value)) {
      if (value !== null && value !== undefined) {
        record(where, null, WRONG_KIND_FAULT, kindOf(value));
      }
      return undefined;
    }
    return rgba(model, value);
  }

  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  function inGroups(name, groups) {
    var api = global.acervatorTokens;
    if (!api || typeof api.group !== "function") {
      return false;
    }
    return Boolean(
      groups.filter(function (one) {
        return owns(api.group(one), name);
      }).length
    );
  }

  // The token name for `value`, only from a group meaning the same thing.
  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function scaled(value, groups) {
    if (!isNumber(value)) {
      return undefined;
    }
    var name = variableInGroups(value, groups);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // A weight and a family are plain, so the token replaces the value alone.
  function through(value, groups) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, groups);
    if (name === undefined) {
      return String(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // styleOf asks the header strip to read one Qt sheet, which drops
  // any colour CSS reads differently.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      record(STYLE_SHEET, null, NOT_LOADED_FAULT, kindOf(api));
      return {};
    }
    return api.styleOf(sheet);
  }

  function callsOf(model) {
    return listField(model, DRAWING_CALLS).map(function (one) {
      return Array.isArray(one) ? one.slice() : [];
    });
  }

  function point(value) {
    var parts = Array.isArray(value) ? value.slice() : [];
    return { x: parts.shift(), y: parts.shift() };
  }

  function rect(value) {
    var parts = Array.isArray(value) ? value.slice() : [];
    return {
      x: parts.shift(),
      y: parts.shift(),
      width: parts.shift(),
      height: parts.shift()
    };
  }

  // programme walks the operations once, keeping the pen, brush,
  // gradient and font each drawing operation is made under.
  function programme(model) {
    var pen = null;
    var brush = null;
    var gradient = null;
    var font = null;
    var opacity;
    var dots = [];
    var plates = [];
    var labels = [];
    var mount = [];
    callsOf(model).forEach(function (call) {
      var name = call.shift();
      if (name === SET_OPACITY) {
        opacity = call.shift();
        return;
      }
      if (name === SET_PEN) {
        pen = call.shift();
        return;
      }
      if (name === SET_BRUSH) {
        brush = call.shift();
        gradient = null;
        return;
      }
      if (name === SET_GRADIENT_BRUSH) {
        gradient = {
          centre: point(call.shift()),
          radius: call.shift(),
          stops: call.shift()
        };
        brush = null;
        return;
      }
      if (name === SET_FONT) {
        font = { family: call.shift(), size: call.shift(), weight: call.shift() };
        return;
      }
      if (name === DRAW_ELLIPSE) {
        dots.push({
          centre: point(call.shift()),
          radiusX: call.shift(),
          radiusY: call.shift(),
          gradient: gradient
        });
        return;
      }
      if (name === DRAW_ROUNDED_RECT) {
        plates.push({
          box: rect(call.shift()),
          cornerX: call.shift(),
          cornerY: call.shift(),
          brush: brush
        });
        return;
      }
      if (name === DRAW_TEXT) {
        labels.push({
          box: rect(call.shift()),
          align: call.shift(),
          written: call.shift(),
          pen: pen,
          font: font
        });
        return;
      }
      if (inList(MOUNT_OPS, name)) {
        mount.push(name);
      }
    });
    return {
      opacity: opacity,
      dots: dots,
      plates: plates,
      labels: labels,
      mount: mount
    };
  }

  // drawnWires pairs each drawn branch with its wire, so a skipped wire
  // shifts none of the others.
  function drawnWires(model) {
    var wires = listField(objectField(model, TAB), WIRES).slice();
    var names = listField(objectField(model, TAB), WIRE_ORDER).slice();
    var found = [];
    var seen = [];
    listField(model, PAINT_BRANCHES).forEach(function (branch) {
      if (branch !== WIRE_DRAWN && branch !== WIRE_SKIPPED) {
        return;
      }
      var at = seen.length;
      seen.push(branch);
      var wire = wires.shift();
      var key = names.shift();
      if (branch !== WIRE_DRAWN) {
        return;
      }
      found.push({
        at: at,
        key: key,
        source: isPlainObject(wire) ? wire[SOURCE_ID] : undefined,
        target: isPlainObject(wire) ? wire[TARGET_ID] : undefined
      });
    });
    return found;
  }

  // dragBranch names which of the three colours the loose end is drawn in.
  function dragBranch(model) {
    var found;
    listField(model, PAINT_BRANCHES).forEach(function (branch) {
      if (inList(DRAG_BRANCHES, branch)) {
        found = branch;
      }
    });
    return found;
  }

  // groups pairs each wire with the dot, plate and label it drew.
  function groups(model) {
    var drawn = programme(model);
    var wires = drawnWires(model);
    return wires.map(function (wire, at) {
      if (at >= drawn.dots.length || at >= drawn.plates.length) {
        record(WIRE_PART, wire.key, SHORT_GROUP_FAULT, at);
      }
      return {
        wire: wire,
        dot: drawn.dots[at],
        plate: drawn.plates[at],
        label: drawn.labels[at]
      };
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function dressed(part, props) {
    var dress = props;
    dress[PART_ATTR] = part;
    return dress;
  }

  // Pulse is the travelling dot, a round box carrying the same falloff
  // the gradient describes.
  function Pulse(props) {
    var dot = props.dot;
    if (!isPlainObject(dot)) {
      return null;
    }
    var style = { position: ABSOLUTE, pointerEvents: NONE };
    style.left = px(dot.centre.x - dot.radiusX);
    style.top = px(dot.centre.y - dot.radiusY);
    style.width = px(dot.radiusX + dot.radiusX);
    style.height = px(dot.radiusY + dot.radiusY);
    style.borderRadius = px(dot.radiusX);
    var falloff = isPlainObject(dot.gradient) ? dot.gradient : null;
    if (falloff !== null) {
      if (falloff.centre.x !== dot.centre.x || falloff.centre.y !== dot.centre.y) {
        record(PULSE_PART, null, OFF_CENTRE_FAULT, falloff.centre);
      }
      var stops = (Array.isArray(falloff.stops) ? falloff.stops : []).map(
        function (one) {
          var stop = Array.isArray(one) ? one.slice() : [];
          var at = stop.shift();
          var colour = colourOf(props.model, PULSE_PART, stop.shift());
          var away = isNumber(at) && isNumber(falloff.radius) ? at * falloff.radius : at;
          return String(colour) + SPACE + String(px(away));
        }
      );
      if (stops.length) {
        style.background = GRADIENT_OPEN + stops.join(COMMA_SPACE) + CLOSE;
      }
    }
    return element(DIV_TAG, dressed(PULSE_PART, { key: PULSE_PART, style: style }));
  }

  // Badge is the plate behind the share percentage, with the label inside.
  function Badge(props) {
    var plate = props.plate;
    var label = props.label;
    if (!isPlainObject(plate)) {
      return null;
    }
    var style = { position: ABSOLUTE, boxSizing: "border-box" };
    style.left = px(plate.box.x);
    style.top = px(plate.box.y);
    style.width = px(plate.box.width);
    style.height = px(plate.box.height);
    if (plate.cornerX !== plate.cornerY) {
      record(BADGE_PART, null, UNEVEN_CORNER_FAULT, plate.cornerY);
    }
    style.borderRadius = scaled(plate.cornerX, RADIUS_GROUPS);
    style.backgroundColor = colourOf(props.model, BADGE_PART, plate.brush);
    var centred =
      isPlainObject(label) && label.align === objectField(props.model, ALIGNMENT)[NAME];
    if (centred) {
      style.display = FLEX;
      style.alignItems = CENTRE;
      style.justifyContent = CENTRE;
    }
    return element(
      DIV_TAG,
      dressed(BADGE_PART, { key: BADGE_PART, style: style }),
      Label({ model: props.model, label: label })
    );
  }

  // Label is the share percentage as characters, never as markup.
  function Label(props) {
    var label = props.label;
    if (!isPlainObject(label)) {
      return null;
    }
    var font = isPlainObject(label.font) ? label.font : {};
    var style = { whiteSpace: NOWRAP, pointerEvents: NONE };
    style.color = colourOf(props.model, LABEL_PART, label.pen);
    style.fontFamily = through(font.family, FAMILY_GROUPS);
    style.fontSize = isNumber(font.size) ? String(font.size) + PT : undefined;
    style.fontWeight = through(
      objectField(props.model, FONT)[WEIGHT_VALUE],
      WEIGHT_GROUPS
    );
    return element(
      SPAN_TAG,
      dressed(LABEL_PART, { key: LABEL_PART, style: style }),
      text(label.written)
    );
  }

  function Wire(props) {
    var group = props.group;
    var style = { position: ABSOLUTE, pointerEvents: NONE };
    var wireProps = dressed(WIRE_PART, { key: String(props.at), style: style });
    wireProps[KEY_ATTR] = text(group.wire.key);
    wireProps[SOURCE_ATTR] = text(group.wire.source);
    wireProps[TARGET_ATTR] = text(group.wire.target);
    wireProps[INDEX_ATTR] = String(group.wire.at);
    return element(
      DIV_TAG,
      wireProps,
      Pulse({ model: props.model, dot: group.dot }),
      Badge({ model: props.model, plate: group.plate, label: group.label })
    );
  }

  // Mount is the named place for the curves, the arrows and the loose end.
  function Mount(props) {
    var model = props.model;
    var mountProps = dressed(MOUNT_PART, {
      key: MOUNT_PART,
      style: { position: ABSOLUTE, pointerEvents: NONE }
    });
    mountProps[SLOT_ATTR] = MOUNT_PART;
    mountProps[LABEL_ATTR] = MOUNT_LABEL;
    mountProps[OPS_ATTR] = String(programme(model).mount.length);
    mountProps[DRAG_ATTR] = text(dragBranch(model));
    return element(DIV_TAG, mountProps, null);
  }

  function Sheet(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var style = styleOf(model[STYLE_SHEET]);
    style.position = RELATIVE;
    var drawn = programme(model);
    if (isNumber(drawn.opacity)) {
      style.opacity = String(drawn.opacity);
    }
    var sheetProps = dressed(SHEET_PART, { style: style });
    sheetProps[SLOT_ATTR] = SHEET_PART;
    sheetProps[LABEL_ATTR] = text(model[ACCESSIBLE_NAME]);
    sheetProps[BRANCH_ATTR] = listField(model, PAINT_BRANCHES).join(COMMA_SPACE);
    var drawnGroups = groups(model).map(function (group, at) {
      return Wire({ model: model, group: group, at: at });
    });
    drawnGroups.push(Mount({ model: model }));
    return element(DIV_TAG, sheetProps, drawnGroups);
  }

  function model() {
    return held === null ? null : held.model;
  }

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function unreachable() {
    if (held === null) {
      return DECLARED_FIELDS.slice();
    }
    return DECLARED_FIELDS.filter(function (name) {
      return !owns(held.model, name);
    });
  }

  function counts() {
    var payload = model();
    return {
      declared: DECLARED_FIELDS.length,
      held: DECLARED_FIELDS.length - unreachable().length,
      wires: listField(objectField(payload, TAB), WIRES).length,
      drawn: drawnWires(payload).length,
      operations: listField(payload, DRAWING_CALLS).length,
      mounted: programme(payload).mount.length
    };
  }

  // wireNames reads the list the surface publishes beside the wires.
  function wireNames() {
    return listField(objectField(model(), TAB), WIRE_ORDER).slice();
  }

  // botOrder reads the published list, because a bag keyed by a number
  // arrives in numeric order.
  function botOrder() {
    var tab = objectField(model(), TAB);
    if (!Array.isArray(tab[BOT_CENTER_ORDER])) {
      record(TAB, BOT_CENTER_ORDER, MISSING_FAULT, kindOf(tab[BOT_CENTER_ORDER]));
      return [];
    }
    return tab[BOT_CENTER_ORDER].slice();
  }

  function botCentre(name) {
    var centres = objectField(objectField(model(), TAB), BOT_CENTERS);
    return owns(centres, name) ? centres[name] : undefined;
  }

  // wireAt answers the drawn values of one wire by its published name.
  function wireAt(name) {
    var found;
    groups(model()).forEach(function (group) {
      if (group.wire.key === name) {
        found = group;
      }
    });
    return found === undefined ? undefined : {
      key: found.wire.key,
      source: found.wire.source,
      target: found.wire.target,
      at: found.wire.at,
      written: isPlainObject(found.label) ? found.label.written : undefined,
      centre: isPlainObject(found.dot) ? found.dot.centre : undefined,
      box: isPlainObject(found.plate) ? found.plate.box : undefined
    };
  }

  function branchNames() {
    return listField(model(), PAINT_BRANCH_NAMES).slice();
  }

  function operationNames() {
    return listField(model(), DRAW_CALL_NAMES).slice();
  }

  function mountedOps() {
    return programme(model()).mount.slice();
  }

  function cssOps() {
    var drawn = programme(model());
    return {
      dots: drawn.dots.length,
      plates: drawn.plates.length,
      labels: drawn.labels.length
    };
  }

  function noBrush() {
    return objectField(model(), PENS)[NO_BRUSH];
  }

  function cursor() {
    return field(CURSOR);
  }

  function routed() {
    return listField(model(), CALLS).slice();
  }

  function tokens() {
    var payload = model();
    var drawn = programme(payload);
    var plate = drawn.plates.slice().shift();
    var label = drawn.labels.slice().shift();
    var font = isPlainObject(label) && isPlainObject(label.font) ? label.font : {};
    return {
      corner: variableInGroups(
        isPlainObject(plate) ? plate.cornerX : undefined,
        RADIUS_GROUPS
      ),
      family: variableInGroups(font.family, FAMILY_GROUPS),
      weight: variableInGroups(objectField(payload, FONT)[WEIGHT_VALUE], WEIGHT_GROUPS)
    };
  }

  function faults() {
    return wireFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function checkFields(model) {
    unreachable().forEach(function (name) {
      record(null, name, MISSING_FAULT, kindOf(model[name]));
    });
  }

  function setWireCanvas(model) {
    wireFaults = [];
    if (!isPlainObject(model)) {
      held = null;
      wireFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: wireFaults.slice() };
    }
    held = { model: model };
    checkFields(model);
    botOrder();
    return { counts: counts(), faults: wireFaults.slice() };
  }

  // loadWireCanvas asks once per page, and a failed ask is not remembered.
  function loadWireCanvas(params) {
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
        setWireCanvas(model);
        return model;
      })
      .catch(function (why) {
        loadFault = String(why);
        asked = null;
        return null;
      });
    return asked;
  }

  function rootFor(target) {
    var found;
    roots.forEach(function (pair) {
      if (pair.node === target) {
        found = pair.root;
      }
    });
    if (found === undefined) {
      found = global.ReactDOM.createRoot(target);
      roots.push({ node: target, root: found });
    }
    return found;
  }

  // `flushSync` makes the document current before `draw` returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderSheet(target, given) {
    var payload = isPlainObject(given) ? given : model();
    return draw(target, element(Sheet, { model: payload }));
  }

  function forget() {
    held = null;
    wireFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetWireCanvas = setWireCanvas;
  global.acervatorLoadWireCanvas = loadWireCanvas;
  global.acervatorWireCanvas = {
    method: METHOD,
    Sheet: Sheet,
    Wire: Wire,
    Pulse: Pulse,
    Badge: Badge,
    Label: Label,
    Mount: Mount,
    field: field,
    declaredFields: declaredFields,
    unreachable: unreachable,
    counts: counts,
    wireNames: wireNames,
    wireAt: wireAt,
    botOrder: botOrder,
    botCentre: botCentre,
    branchNames: branchNames,
    operationNames: operationNames,
    mountedOps: mountedOps,
    cssOps: cssOps,
    dragBranch: function () {
      return dragBranch(model());
    },
    noBrush: noBrush,
    cursor: cursor,
    routed: routed,
    tokens: tokens,
    rgba: function (parts) {
      return rgba(model(), parts);
    },
    qtColour: qtColour,
    styleOf: styleOf,
    variableFor: variableFor,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderSheet: renderSheet,
    forget: forget
  };
})(window);
