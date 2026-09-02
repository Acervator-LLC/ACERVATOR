// Publishes the locust card on the page global, as the surface serves it.
(function (global) {
  "use strict";

  var METHOD = "bot_node.state";

  var METHOD_FIELD = "method";
  var MINIMUM_SIZE_PX = "minimum_size_px";
  var RENDER_HINT = "render_hint";
  var THEME = "theme";
  var STATES = "states";
  var DATA_KEYS = "data_keys";
  var DEFAULTS = "defaults";
  var MOVEMENT = "movement";
  var PARTICLE = "particle";
  var WING = "wing";
  var PULSE_RING = "pulse_ring";
  var GLOW = "glow";
  var ABDOMEN = "abdomen";
  var SEGMENTS = "segments";
  var THORAX = "thorax";
  var HEAD = "head";
  var EYE = "eye";
  var ANTENNA = "antenna";
  var LEGS = "legs";
  var BRACKETS = "brackets";
  var CIRCUIT = "circuit";
  var FONT = "font";
  var LABELS = "labels";
  var PRIVACY = "privacy";
  var TOOLTIP = "tooltip";
  var PATH = "path";
  var PENS = "pens";
  var ALIGNMENT = "alignment";
  var SCALE_DIVISOR = "scale_divisor";
  var STEP_KINDS = "step_kinds";
  var DRAW_CALL_NAMES = "draw_call_names";
  var ROUTE_NAMES = "route_names";
  var PAINT_BRANCH_NAMES = "paint_branch_names";
  var FORMATS = "formats";
  var ACTIONS = "actions";
  var SIGNALS = "signals";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var SCREEN_ELEMENTS = "screen_elements";
  var DRAWING_CALLS = "drawing_calls";
  var PAINT_BRANCHES = "paint_branches";
  var CALLS = "calls";
  var CARD = "card";

  var DECLARED_FIELDS = [
    ABDOMEN,
    ACTIONS,
    ALIGNMENT,
    ANTENNA,
    BRACKETS,
    BUS_TOPICS,
    CALLS,
    CARD,
    CIRCUIT,
    DATA_KEYS,
    DEFAULTS,
    DRAWING_CALLS,
    DRAW_CALL_NAMES,
    EYE,
    FONT,
    FORMATS,
    GLOW,
    HEAD,
    LABELS,
    LEGS,
    METHOD_FIELD,
    MINIMUM_SIZE_PX,
    MOVEMENT,
    PAINT_BRANCHES,
    PAINT_BRANCH_NAMES,
    PARTICLE,
    PATH,
    PENS,
    PRIVACY,
    PULSE_RING,
    RENDER_HINT,
    ROUTE_NAMES,
    SCALE_DIVISOR,
    SCREEN_ELEMENTS,
    SEGMENTS,
    SIGNALS,
    STATES,
    STEP_KINDS,
    THEME,
    THORAX,
    TIMERS,
    TIMER_DELAYS_MS,
    TOOLTIP,
    WING
  ];

  var THEME_KEY = "key";
  var FALLBACK_KEY = "fallback_key";
  var THEME_KEYS = "keys";
  var COLOR_NAMES = "color_names";
  var OPAQUE_ALPHA = "opaque_alpha";
  var TABLE = "table";
  var COLORS = "colors";
  var HEAD_FILLS = "head_fills";

  var THEME_FIELDS = [
    COLORS,
    COLOR_NAMES,
    FALLBACK_KEY,
    HEAD_FILLS,
    OPAQUE_ALPHA,
    TABLE,
    THEME_KEY,
    THEME_KEYS
  ];

  var STATE_NAMES = "names";
  var LEG_COLORS = "leg_colors";
  var LEG_FALLBACK_COLORS = "leg_fallback_colors";
  var IDLE_GREY = "idle_grey";
  var STOPPED_GREY = "stopped_grey";
  var DEFAULT_FIELD = "default";

  var STATE_FIELDS = [
    COLORS,
    DEFAULT_FIELD,
    IDLE_GREY,
    LEG_COLORS,
    LEG_FALLBACK_COLORS,
    STATE_NAMES,
    STOPPED_GREY
  ];

  var WIDTH_PX = "width_px";
  var HEIGHT_PX = "height_px";
  var PHASE = "phase";
  var BOT_DATA = "bot_data";
  var TRADE_PULSES = "trade_pulses";
  var PARTICLES = "particles";
  var ANTENNA_DRIVE = "antenna_drive";
  var THEME_KEY_FIELD = "theme_key";

  var CARD_FIELDS = [
    ANTENNA_DRIVE,
    BOT_DATA,
    HEIGHT_PX,
    MINIMUM_SIZE_PX,
    PARTICLES,
    PHASE,
    THEME_KEY_FIELD,
    TOOLTIP,
    TRADE_PULSES,
    WIDTH_PX
  ];

  var LEFT_PX = "left_px";
  var SYMBOL_TOP_PX = "symbol_top_px";
  var SYMBOL_HEIGHT_PX = "symbol_height_px";
  var PNL_BOTTOM_PX = "pnl_bottom_px";
  var PNL_HEIGHT_PX = "pnl_height_px";
  var BOT_ID_BOTTOM_PX = "bot_id_bottom_px";
  var BOT_ID_HEIGHT_PX = "bot_id_height_px";
  var BOT_ID_COLOR = "bot_id_color";

  var LABEL_FIELDS = [
    BOT_ID_BOTTOM_PX,
    BOT_ID_COLOR,
    BOT_ID_HEIGHT_PX,
    LEFT_PX,
    PNL_BOTTOM_PX,
    PNL_HEIGHT_PX,
    SYMBOL_HEIGHT_PX,
    SYMBOL_TOP_PX
  ];

  var FAMILY = "family";
  var BOLD = "bold";
  var NORMAL = "normal";
  var BOLD_VALUE = "bold_value";
  var NORMAL_VALUE = "normal_value";
  var SYMBOL_SIZE_PT = "symbol_size_pt";
  var PNL_SIZE_PT = "pnl_size_pt";
  var BOT_ID_SIZE_PT = "bot_id_size_pt";

  var FONT_FIELDS = [
    BOLD,
    BOLD_VALUE,
    BOT_ID_SIZE_PT,
    FAMILY,
    NORMAL,
    NORMAL_VALUE,
    PNL_SIZE_PT,
    SYMBOL_SIZE_PT
  ];

  var SOLID_STYLE = "solid_style";
  var NO_PEN_STYLE = "no_pen_style";
  var NO_PEN_WIDTH_PX = "no_pen_width_px";
  var NO_BRUSH = "no_brush";
  var CAP_STYLE = "cap_style";
  var HALF_WIDTH_RATIO = "half_width_ratio";

  var PEN_FIELDS = [
    CAP_STYLE,
    HALF_WIDTH_RATIO,
    NO_BRUSH,
    NO_PEN_STYLE,
    NO_PEN_WIDTH_PX,
    SOLID_STYLE
  ];

  var PEN_STYLE = "pen_style";
  var NAME_FIELD = "name";
  var VALUE_FIELD = "value";
  var TEXT_FIELD = "text";

  var OP_RENDER_HINT = "set_render_hint";
  var OP_FILL_RECT = "fill_rect";
  var OP_SET_PEN = "set_pen";
  var OP_SET_PEN_COLOR = "set_pen_color";
  var OP_SET_BRUSH = "set_brush";
  var OP_RADIAL_BRUSH = "set_radial_brush";
  var OP_LINEAR_BRUSH = "set_linear_brush";
  var OP_SET_FONT = "set_font";
  var OP_DRAW_PATH = "draw_path";
  var OP_DRAW_ELLIPSE = "draw_ellipse";
  var OP_DRAW_LINE = "draw_line";
  var OP_DRAW_TEXT = "draw_text";
  var OP_END = "end";

  var KNOWN_OPS = {};
  [
    OP_RENDER_HINT,
    OP_FILL_RECT,
    OP_SET_PEN,
    OP_SET_PEN_COLOR,
    OP_SET_BRUSH,
    OP_RADIAL_BRUSH,
    OP_LINEAR_BRUSH,
    OP_SET_FONT,
    OP_DRAW_PATH,
    OP_DRAW_ELLIPSE,
    OP_DRAW_LINE,
    OP_DRAW_TEXT,
    OP_END
  ].forEach(function (name) {
    KNOWN_OPS[name] = true;
  });

  var SYMBOL_LABEL = "symbol";
  var PNL_LABEL = "pnl";
  var BOT_ID_LABEL = "bot-id";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var UNKNOWN_OP_FAULT = "unknown-op";
  var UNKNOWN_ALIGN_FAULT = "unknown-align";
  var UNKNOWN_STYLE_FAULT = "unknown-pen-style";
  var QT_COLOUR_FAULT = "qt-colour";
  var COLOUR_SHAPE_FAULT = "colour-shape";
  var NOT_FINITE_FAULT = "not-finite";
  var MARKUP_FAULT = "markup";
  var NO_DIVISOR_FAULT = "no-alpha-divisor";
  var SLANTED_GRADIENT_FAULT = "slanted-gradient";
  var UNKNOWN_LABEL_FAULT = "unknown-label";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var PATH_SPLIT = ".";
  var KEY_SPLIT = ":";
  var HASH = "#";
  var GAP = " ";
  var COMMA = ",";
  var CLOSE = ")";
  var PX = "px";
  var PT = "pt";
  var RGBA_OPEN = "rgba(";
  var CALC_OPEN = "calc(";
  // OVER carries the slash the browser divides with, so none is written here.
  var OVER = " / ";
  var TAG_OPEN = "<";
  var TAG_CLOSE = ">";
  // Qt reads an eight-digit hex alpha first, CSS reads it last.
  var HEX_ARGB = "AARRGGBB";

  var RADIAL_OPEN = "radial-gradient(circle ";
  var LINEAR_OPEN = "linear-gradient(";
  var AT = " at ";
  var TO_BOTTOM = "to bottom";
  var TO_RIGHT = "to right";

  var OBJECT_KIND = "object";
  var STRING_KIND = "string";
  var NUMBER_KIND = "number";

  var ABSOLUTE = "absolute";
  var RELATIVE = "relative";
  var FLEX = "flex";
  var COLUMN_WAY = "column";
  var CENTER = "center";
  var CLIPPED = "hidden";
  var CLIP = "clip";
  var NO_WRAP = "nowrap";
  var NONE = "none";
  var BORDER_BOX = "border-box";
  var SOLID = "solid";
  var RADIUS_HALF = "50%";
  var TRANSPARENT = "transparent";

  var DIV_TAG = "div";

  var CARD_PART = "card";
  var GROUND_PART = "ground";
  var DOT_PART = "dot";
  var RULE_PART = "rule";
  var WORDS_PART = "words";
  var BODY_PART = "body";

  var CARD_SLOT = "locust";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var OP_ATTR = "data-op";
  var AT_ATTR = "data-at";
  var KEY_ATTR = "data-key";
  var LABEL_ATTR = "data-label";
  var OPS_ATTR = "data-ops";
  var PATHS_ATTR = "data-paths";
  var SLOPES_ATTR = "data-slopes";
  var FIRST_ATTR = "data-first";
  var LAST_ATTR = "data-last";
  var CALLS_ATTR = "data-calls";
  var BRANCHES_ATTR = "data-branches";
  var TITLE_ATTR = "title";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;

  var held = null;
  var cardFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === OBJECT_KIND && !Array.isArray(value);
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
    if (value === null) {
      return NULL_FAULT;
    }
    return Array.isArray(value) ? OBJECT_KIND : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    cardFaults.push(fault(where, field, kind, detail));
  }

  // text answers undefined so an attribute stays off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function merged(into, from) {
    Object.keys(from).forEach(function (name) {
      into[name] = from[name];
    });
    return into;
  }

  function isNumber(value) {
    return typeof value === NUMBER_KIND && isFinite(value);
  }

  function at(list, index) {
    return Array.isArray(list) ? list[index] : undefined;
  }

  // pixels writes a plain length, because no design token names a size this card draws.
  function pixels(value) {
    return isNumber(value) ? String(value) + PX : undefined;
  }

  // A points value takes no token, because every token group counts pixels.
  function points(value) {
    return isNumber(value) ? String(value) + PT : undefined;
  }

  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  function hexWord(value) {
    var parts = String(value).split(HASH);
    parts.shift();
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // The reason CSS would read one written value as a different colour.
  function qtColour(value) {
    if (typeof value !== STRING_KIND) {
      return undefined;
    }
    return hexWord(value).length === HEX_ARGB.length ? HEX_ARGB : undefined;
  }

  function alphaDivisor(model) {
    var divisor = objectField(model, THEME)[OPAQUE_ALPHA];
    return isNumber(divisor) && divisor > ZERO ? divisor : undefined;
  }

  // colour turns Qt's four bytes into CSS, dividing alpha in the browser.
  function colour(where, field, value, divisor) {
    if (value === null || value === undefined) {
      return undefined;
    }
    if (qtColour(value) !== undefined) {
      note(where, field, QT_COLOUR_FAULT, String(value));
      return undefined;
    }
    if (!Array.isArray(value) || value.length !== TWO + TWO) {
      note(where, field, COLOUR_SHAPE_FAULT, kindOf(value));
      return undefined;
    }
    var whole = value.filter(isNumber);
    if (whole.length !== value.length) {
      note(where, field, NOT_FINITE_FAULT, String(value));
      return undefined;
    }
    if (divisor === undefined) {
      note(where, field, NO_DIVISOR_FAULT, null);
      return undefined;
    }
    return (
      RGBA_OPEN +
      String(value[ZERO]) +
      COMMA +
      String(value[ONE]) +
      COMMA +
      String(value[TWO]) +
      COMMA +
      CALC_OPEN +
      String(value[THREE]) +
      OVER +
      String(divisor) +
      CLOSE +
      CLOSE
    );
  }

  function stopList(where, stops, divisor, span) {
    var written = [];
    (Array.isArray(stops) ? stops : []).forEach(function (one) {
      var place = at(one, ZERO);
      var paint = colour(where, COLORS, at(one, ONE), divisor);
      if (paint === undefined || !isNumber(place)) {
        return;
      }
      written.push(paint + GAP + pixels(place * span));
    });
    return written;
  }

  // A radial brush becomes one gradient centred where the call centres it.
  function radialBackground(where, call, divisor, box) {
    var centre = at(call, ONE);
    var radius = at(call, TWO);
    if (!Array.isArray(centre) || !isNumber(radius)) {
      note(where, OP_RADIAL_BRUSH, WRONG_TYPE_FAULT, kindOf(radius));
      return undefined;
    }
    var stops = stopList(where, at(call, THREE), divisor, radius);
    if (!stops.length) {
      return undefined;
    }
    return (
      RADIAL_OPEN +
      pixels(radius) +
      AT +
      pixels(at(centre, ZERO) - box.left) +
      GAP +
      pixels(at(centre, ONE) - box.top) +
      COMMA +
      GAP +
      stops.join(COMMA + GAP) +
      CLOSE
    );
  }

  // A linear brush becomes one gradient, refused when its line slants.
  function linearBackground(where, call, divisor) {
    var from = at(call, ONE);
    var to = at(call, TWO);
    if (!Array.isArray(from) || !Array.isArray(to)) {
      note(where, OP_LINEAR_BRUSH, WRONG_TYPE_FAULT, kindOf(from));
      return undefined;
    }
    var flatX = at(from, ZERO) === at(to, ZERO);
    var flatY = at(from, ONE) === at(to, ONE);
    if (!flatX && !flatY) {
      note(where, OP_LINEAR_BRUSH, SLANTED_GRADIENT_FAULT, null);
      return undefined;
    }
    var span = flatX
      ? at(to, ONE) - at(from, ONE)
      : at(to, ZERO) - at(from, ZERO);
    var stops = stopList(where, at(call, THREE), divisor, span);
    if (!stops.length) {
      return undefined;
    }
    return (
      LINEAR_OPEN +
      (flatX ? TO_BOTTOM : TO_RIGHT) +
      COMMA +
      GAP +
      stops.join(COMMA + GAP) +
      CLOSE
    );
  }

  // One drawn element's name, taken from its own numbers, never its place.
  function keyOf(op, numbers) {
    return op + KEY_SPLIT + numbers.join(KEY_SPLIT);
  }

  function markupIn(where, value) {
    var written = String(value);
    if (written.indexOf(TAG_OPEN) >= ZERO && written.indexOf(TAG_CLOSE) >= ZERO) {
      note(where, TEXT_FIELD, MARKUP_FAULT, written);
    }
  }

  // The label one text rectangle carries, matched to the published boxes.
  function labelFor(model, rect, height) {
    var labels = objectField(model, LABELS);
    var top = at(rect, ONE);
    if (top === labels[SYMBOL_TOP_PX]) {
      return SYMBOL_LABEL;
    }
    if (isNumber(height) && top === height - labels[PNL_BOTTOM_PX]) {
      return PNL_LABEL;
    }
    if (isNumber(height) && top === height - labels[BOT_ID_BOTTOM_PX]) {
      return BOT_ID_LABEL;
    }
    return undefined;
  }

  function Ground(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(props.box.left),
      top: pixels(props.box.top),
      width: pixels(props.box.width),
      height: pixels(props.box.height),
      backgroundColor: props.paint
    };
    var groundProps = { style: style };
    groundProps[PART_ATTR] = GROUND_PART;
    groundProps[OP_ATTR] = OP_FILL_RECT;
    groundProps[AT_ATTR] = text(props.at);
    groundProps[KEY_ATTR] = text(props.name);
    return element(DIV_TAG, groundProps, null);
  }

  // Dot draws one ellipse, widened by the pen Qt straddles its edge with.
  function Dot(props) {
    var edge = props.penWidth;
    var style = {
      position: ABSOLUTE,
      boxSizing: BORDER_BOX,
      left: pixels(props.left),
      top: pixels(props.top),
      width: pixels(props.width),
      height: pixels(props.height),
      borderRadius: RADIUS_HALF,
      backgroundColor: props.paint,
      backgroundImage: props.gradient,
      borderStyle: edge > ZERO ? SOLID : NONE,
      borderWidth: pixels(edge),
      borderColor: edge > ZERO ? props.edge : TRANSPARENT
    };
    var dotProps = { style: style };
    dotProps[PART_ATTR] = DOT_PART;
    dotProps[OP_ATTR] = OP_DRAW_ELLIPSE;
    dotProps[AT_ATTR] = text(props.at);
    dotProps[KEY_ATTR] = text(props.name);
    return element(DIV_TAG, dotProps, null);
  }

  // Rule draws one straight line, lengthened by the square cap Qt uses.
  function Rule(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(props.left),
      top: pixels(props.top),
      width: pixels(props.width),
      height: pixels(props.height),
      backgroundColor: props.paint
    };
    var ruleProps = { style: style };
    ruleProps[PART_ATTR] = RULE_PART;
    ruleProps[OP_ATTR] = OP_DRAW_LINE;
    ruleProps[AT_ATTR] = text(props.at);
    ruleProps[KEY_ATTR] = text(props.name);
    return element(DIV_TAG, ruleProps, null);
  }

  // Words draws one text, clipped to its rectangle as Qt clips it.
  function Words(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(props.box.left),
      top: pixels(props.box.top),
      width: pixels(props.box.width),
      height: pixels(props.box.height),
      display: FLEX,
      justifyContent: CENTER,
      alignItems: CENTER,
      whiteSpace: NO_WRAP,
      overflow: CLIPPED,
      textOverflow: CLIP,
      userSelect: NONE,
      color: props.paint,
      fontFamily: props.family,
      fontSize: points(props.size),
      fontWeight: props.weight
    };
    var wordsProps = { style: style };
    wordsProps[PART_ATTR] = WORDS_PART;
    wordsProps[OP_ATTR] = OP_DRAW_TEXT;
    wordsProps[AT_ATTR] = text(props.at);
    wordsProps[KEY_ATTR] = text(props.name);
    wordsProps[LABEL_ATTR] = text(props.label);
    return element(DIV_TAG, wordsProps, text(props.words));
  }

  // Body keeps the place of the curves and slants CSS cannot draw.
  function Body(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(ZERO),
      top: pixels(ZERO),
      width: pixels(props.width),
      height: pixels(props.height)
    };
    var bodyProps = { style: style };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[SLOT_ATTR] = BODY_PART;
    bodyProps[OPS_ATTR] = String(props.paths + props.slopes);
    bodyProps[PATHS_ATTR] = String(props.paths);
    bodyProps[SLOPES_ATTR] = String(props.slopes);
    bodyProps[FIRST_ATTR] = String(props.first);
    bodyProps[LAST_ATTR] = String(props.last);
    return element(DIV_TAG, bodyProps, null);
  }

  // spec keeps one drawn part as a plain value, so counting needs no React.
  function spec(kind, part, props) {
    return { kind: kind, part: part, props: props };
  }

  function boxOf(rect) {
    return {
      left: at(rect, ZERO),
      top: at(rect, ONE),
      width: at(rect, TWO),
      height: at(rect, THREE)
    };
  }

  function newPaint(model) {
    return {
      pen: undefined,
      penWidth: objectField(model, PENS)[NO_PEN_WIDTH_PX],
      brush: undefined,
      gradient: undefined,
      family: undefined,
      size: undefined,
      weight: undefined
    };
  }

  // The card writes three pen styles: plain, dashed on the wings, and none.
  function penStyleOf(model, where, style) {
    var pens = objectField(model, PENS);
    var dashed = objectField(model, WING)[PEN_STYLE];
    if (style === pens[NO_PEN_STYLE] || style === pens[SOLID_STYLE]) {
      return style;
    }
    if (style === dashed) {
      return style;
    }
    note(where, OP_SET_PEN, UNKNOWN_STYLE_FAULT, text(style));
    return style;
  }

  function weightOf(model, where, name) {
    var font = objectField(model, FONT);
    if (name === font[BOLD]) {
      return font[BOLD_VALUE];
    }
    if (name === font[NORMAL]) {
      return font[NORMAL_VALUE];
    }
    note(where, OP_SET_FONT, WRONG_TYPE_FAULT, text(name));
    return undefined;
  }

  function readState(model, call, op, where, paint, divisor) {
    var pens = objectField(model, PENS);
    if (op === OP_SET_PEN) {
      penStyleOf(model, where, at(call, THREE));
      paint.pen = colour(where, OP_SET_PEN, at(call, ONE), divisor);
      paint.penWidth = at(call, TWO);
      return true;
    }
    if (op === OP_SET_PEN_COLOR) {
      paint.pen = colour(where, OP_SET_PEN_COLOR, at(call, ONE), divisor);
      return true;
    }
    if (op === OP_SET_BRUSH) {
      paint.gradient = undefined;
      paint.radial = undefined;
      paint.brush =
        at(call, ONE) === pens[NO_BRUSH]
          ? undefined
          : colour(where, OP_SET_BRUSH, at(call, ONE), divisor);
      return true;
    }
    if (op === OP_LINEAR_BRUSH) {
      paint.brush = undefined;
      paint.radial = undefined;
      paint.gradient = linearBackground(where, call, divisor);
      return true;
    }
    if (op === OP_SET_FONT) {
      paint.family = text(at(call, ONE));
      paint.size = at(call, TWO);
      paint.weight = weightOf(model, where, at(call, THREE));
      return true;
    }
    return false;
  }

  function ellipseNode(model, call, index, paint, divisor) {
    var where = String(index);
    var centre = at(call, ONE);
    var rx = at(call, TWO);
    var ry = at(call, THREE);
    if (!Array.isArray(centre) || !isNumber(rx) || !isNumber(ry)) {
      note(where, OP_DRAW_ELLIPSE, NOT_FINITE_FAULT, kindOf(rx));
      return undefined;
    }
    var cx = at(centre, ZERO);
    var cy = at(centre, ONE);
    if (!isNumber(cx) || !isNumber(cy)) {
      note(where, OP_DRAW_ELLIPSE, NOT_FINITE_FAULT, String(centre));
      return undefined;
    }
    var edge = isNumber(paint.penWidth) ? paint.penWidth : ZERO;
    var half = objectField(model, PENS)[HALF_WIDTH_RATIO];
    var reach = isNumber(half) ? edge * half : ZERO;
    var box = { left: cx - rx - reach, top: cy - ry - reach };
    return spec(Dot, DOT_PART, {
      key: where,
      at: index,
      name: keyOf(OP_DRAW_ELLIPSE, [cx, cy, rx, ry]),
      left: box.left,
      top: box.top,
      width: rx + rx + edge,
      height: ry + ry + edge,
      penWidth: edge,
      edge: paint.pen,
      paint: paint.brush,
      gradient:
        paint.gradient === undefined
          ? radialGradientFor(model, index, paint, box)
          : paint.gradient
    });
  }

  function radialGradientFor(model, index, paint, box) {
    if (paint.radial === undefined) {
      return undefined;
    }
    return radialBackground(String(index), paint.radial, paint.divisor, box);
  }

  function lineNode(model, call, index, paint) {
    var where = String(index);
    var from = at(call, ONE);
    var to = at(call, TWO);
    if (!Array.isArray(from) || !Array.isArray(to)) {
      note(where, OP_DRAW_LINE, NOT_A_LIST_FAULT, kindOf(from));
      return undefined;
    }
    var firstX = at(from, ZERO);
    var firstY = at(from, ONE);
    var lastX = at(to, ZERO);
    var lastY = at(to, ONE);
    if (![firstX, firstY, lastX, lastY].every(isNumber)) {
      note(where, OP_DRAW_LINE, NOT_FINITE_FAULT, String(from) + KEY_SPLIT + String(to));
      return undefined;
    }
    if (firstX !== lastX && firstY !== lastY) {
      return undefined;
    }
    var half = objectField(model, PENS)[HALF_WIDTH_RATIO];
    var wide = isNumber(paint.penWidth) ? paint.penWidth : ZERO;
    var reach = isNumber(half) ? wide * half : ZERO;
    var flatY = firstY === lastY;
    var lowX = Math.min(firstX, lastX);
    var lowY = Math.min(firstY, lastY);
    var runX = Math.abs(lastX - firstX);
    var runY = Math.abs(lastY - firstY);
    return spec(Rule, RULE_PART, {
      key: where,
      at: index,
      name: keyOf(OP_DRAW_LINE, [firstX, firstY, lastX, lastY]),
      left: lowX - reach,
      top: lowY - reach,
      width: flatY ? runX + wide : wide,
      height: flatY ? wide : runY + wide,
      paint: paint.pen
    });
  }

  function textNode(model, call, index, paint) {
    var where = String(index);
    var rect = at(call, ONE);
    var align = at(call, TWO);
    var words = at(call, THREE);
    if (!Array.isArray(rect)) {
      note(where, OP_DRAW_TEXT, NOT_A_LIST_FAULT, kindOf(rect));
      return undefined;
    }
    if (align !== objectField(model, ALIGNMENT)[NAME_FIELD]) {
      note(where, OP_DRAW_TEXT, UNKNOWN_ALIGN_FAULT, text(align));
    }
    markupIn(where, words);
    var label = labelFor(model, rect, objectField(model, CARD)[HEIGHT_PX]);
    if (label === undefined) {
      note(where, OP_DRAW_TEXT, UNKNOWN_LABEL_FAULT, String(at(rect, ONE)));
    }
    return spec(Words, WORDS_PART, {
      key: where,
      at: index,
      label: label,
      name: keyOf(OP_DRAW_TEXT, [at(rect, ZERO), at(rect, ONE), String(words)]),
      box: boxOf(rect),
      words: words,
      paint: paint.pen,
      family: paint.family,
      size: paint.size,
      weight: paint.weight
    });
  }

  // replay walks the drawing calls once, in the order the surface wrote them.
  function replay(model) {
    var calls = listField(model, DRAWING_CALLS);
    var divisor = alphaDivisor(model);
    var card = objectField(model, CARD);
    var paint = newPaint(model);
    paint.divisor = divisor;
    var drawn = [];
    var seen = ZERO;
    var pending = null;
    var counts = { grounds: ZERO, dots: ZERO, rules: ZERO, words: ZERO };
    var deferred = { paths: ZERO, slopes: ZERO };

    function flush() {
      if (pending === null) {
        return;
      }
      drawn.push(
        spec(Body, BODY_PART, {
          key: BODY_PART + PATH_SPLIT + String(pending.first),
          width: card[WIDTH_PX],
          height: card[HEIGHT_PX],
          paths: pending.paths,
          slopes: pending.slopes,
          first: pending.first,
          last: pending.last
        })
      );
      pending = null;
    }

    function defer(index, isPath) {
      if (pending === null) {
        pending = { paths: ZERO, slopes: ZERO, first: index, last: index };
      }
      pending.last = index;
      if (isPath) {
        pending.paths += ONE;
        deferred.paths += ONE;
      } else {
        pending.slopes += ONE;
        deferred.slopes += ONE;
      }
    }

    calls.forEach(function (call, index) {
      var where = String(index);
      if (!Array.isArray(call)) {
        note(where, DRAWING_CALLS, NOT_A_LIST_FAULT, kindOf(call));
        return;
      }
      var op = call[ZERO];
      if (!owns(KNOWN_OPS, String(op))) {
        note(where, DRAWING_CALLS, UNKNOWN_OP_FAULT, text(op));
        return;
      }
      seen += ONE;
      if (op === OP_RADIAL_BRUSH) {
        paint.brush = undefined;
        paint.gradient = undefined;
        paint.radial = call;
        return;
      }
      if (readState(model, call, op, where, paint, divisor)) {
        return;
      }
      if (op === OP_RENDER_HINT || op === OP_END) {
        return;
      }
      if (op === OP_DRAW_PATH) {
        defer(index, true);
        return;
      }
      if (op === OP_DRAW_LINE) {
        var rule = lineNode(model, call, index, paint);
        if (rule === undefined) {
          defer(index, false);
          return;
        }
        flush();
        counts.rules += ONE;
        drawn.push(rule);
        return;
      }
      flush();
      if (op === OP_FILL_RECT) {
        counts.grounds += ONE;
        drawn.push(
          spec(Ground, GROUND_PART, {
            key: where,
            at: index,
            name: keyOf(OP_FILL_RECT, [String(at(call, ONE))]),
            box: boxOf(at(call, ONE)),
            paint: colour(where, OP_FILL_RECT, at(call, TWO), divisor)
          })
        );
        return;
      }
      if (op === OP_DRAW_ELLIPSE) {
        var dot = ellipseNode(model, call, index, paint, divisor);
        if (dot !== undefined) {
          counts.dots += ONE;
          drawn.push(dot);
        }
        return;
      }
      var caption = textNode(model, call, index, paint);
      if (caption !== undefined) {
        counts.words += ONE;
        drawn.push(caption);
      }
    });
    flush();
    return { drawn: drawn, seen: seen, counts: counts, deferred: deferred };
  }

  // Card draws the whole locust, its parts in the order the surface paints.
  function Card(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var card = objectField(model, CARD);
    var least = listField(model, MINIMUM_SIZE_PX);
    var style = {
      position: RELATIVE,
      display: FLEX,
      flexDirection: COLUMN_WAY,
      width: pixels(card[WIDTH_PX]),
      height: pixels(card[HEIGHT_PX]),
      minWidth: pixels(at(least, ZERO)),
      minHeight: pixels(at(least, ONE)),
      overflow: CLIPPED,
      userSelect: NONE
    };
    var found = replay(model);
    var drawn = found.drawn.map(function (one) {
      return element(one.kind, one.props);
    });
    var cardProps = { style: style };
    cardProps[PART_ATTR] = CARD_PART;
    cardProps[SLOT_ATTR] = CARD_SLOT;
    cardProps[TITLE_ATTR] = text(card[TOOLTIP]);
    cardProps[CALLS_ATTR] = String(listField(model, DRAWING_CALLS).length);
    cardProps[BRANCHES_ATTR] = String(listField(model, PAINT_BRANCHES).length);
    return element(DIV_TAG, cardProps, drawn);
  }

  // checkPresent lets the one nullable field stand, because a card with no values writes no tooltip.
  function checkPresent(where, bag, names, nullable) {
    names.forEach(function (name) {
      if (!owns(bag, name)) {
        note(where, name, MISSING_FAULT, null);
        return;
      }
      if (bag[name] === null && name !== nullable) {
        note(where, name, NULL_FAULT, null);
      }
    });
  }

  function checkTopFields(model) {
    checkPresent(null, model, DECLARED_FIELDS);
    if (model[METHOD_FIELD] !== METHOD) {
      note(null, METHOD_FIELD, WRONG_TYPE_FAULT, text(model[METHOD_FIELD]));
    }
  }

  function checkShapes(model) {
    [DRAWING_CALLS, PAINT_BRANCHES, CALLS, MINIMUM_SIZE_PX].forEach(function (name) {
      if (!Array.isArray(model[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(model[name]));
      }
    });
    [THEME, STATES, CARD, LABELS, FONT, PENS, ALIGNMENT].forEach(function (name) {
      if (!isPlainObject(model[name])) {
        note(null, name, NOT_AN_OBJECT_FAULT, kindOf(model[name]));
      }
    });
  }

  function checkGroups(model) {
    checkPresent(THEME, objectField(model, THEME), THEME_FIELDS);
    checkPresent(STATES, objectField(model, STATES), STATE_FIELDS);
    checkPresent(CARD, objectField(model, CARD), CARD_FIELDS, TOOLTIP);
    checkPresent(LABELS, objectField(model, LABELS), LABEL_FIELDS);
    checkPresent(FONT, objectField(model, FONT), FONT_FIELDS);
    checkPresent(PENS, objectField(model, PENS), PEN_FIELDS);
    if (alphaDivisor(model) === undefined) {
      note(THEME, OPAQUE_ALPHA, NO_DIVISOR_FAULT, text(objectField(model, THEME)[OPAQUE_ALPHA]));
    }
  }

  // Every colour table is checked by group and name, never by name alone.
  function checkColourTables(model) {
    var divisor = alphaDivisor(model);
    colourGroups(model).forEach(function (pair) {
      var bag = pair[ONE];
      Object.keys(bag).forEach(function (name) {
        var row = objectField(bag, name);
        Object.keys(row).forEach(function (label) {
          colour(pair[ZERO] + PATH_SPLIT + name, label, row[label], divisor);
        });
      });
    });
  }

  // labelGroups names every group one colour label appears in.
  function labelGroups(model) {
    var found = {};
    colourGroups(model).forEach(function (pair) {
      Object.keys(pair[ONE]).forEach(function (name) {
        Object.keys(objectField(pair[ONE], name)).forEach(function (label) {
          found[label] = (found[label] || []).concat([pair[ZERO] + PATH_SPLIT + name]);
        });
      });
    });
    return found;
  }

  // stateLabels names every state one theme row of the card paints.
  function stateLabels(model) {
    var rows = objectField(objectField(model, STATES), COLORS);
    var found = {};
    Object.keys(rows).forEach(function (name) {
      Object.keys(objectField(rows, name)).forEach(function (label) {
        found[label] = true;
      });
    });
    return found;
  }

  function colourGroups(model) {
    return [
      [THEME, objectField(objectField(model, THEME), TABLE)],
      [STATES, objectField(objectField(model, STATES), COLORS)],
      [LEG_COLORS, objectField(objectField(model, STATES), LEG_COLORS)]
    ];
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(model, name);
    }).length;
  }

  function report(model, found) {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        calls: listField(model, DRAWING_CALLS).length,
        branches: listField(model, PAINT_BRANCHES).length,
        routes: listField(model, CALLS).length,
        themes: listField(objectField(model, THEME), THEME_KEYS).length,
        states: listField(objectField(model, STATES), STATE_NAMES).length
      },
      held: {
        fields: heldFieldCount(model),
        calls: found.seen,
        branches: listField(model, PAINT_BRANCHES).length,
        routes: listField(model, CALLS).length,
        themes: Object.keys(objectField(objectField(model, THEME), TABLE)).length,
        states: Object.keys(stateLabels(model)).length
      },
      drawn: {
        grounds: found.counts.grounds,
        dots: found.counts.dots,
        rules: found.counts.rules,
        words: found.counts.words,
        paths: found.deferred.paths,
        slopes: found.deferred.slopes
      },
      faults: cardFaults.slice()
    };
  }

  function setBotNode(model) {
    if (!isPlainObject(model)) {
      held = null;
      cardFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, drawn: null, faults: cardFaults.slice() };
    }
    held = { model: model };
    cardFaults = [];
    checkTopFields(model);
    checkShapes(model);
    checkGroups(model);
    checkColourTables(model);
    return report(model, replay(model));
  }

  // loadBotNode asks once and forgets a refused ask.
  function loadBotNode(params) {
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
        setBotNode(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : merged({}, objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function card() {
    return bag(CARD);
  }

  function themeColours() {
    return held === null ? {} : merged({}, objectField(objectField(held.model, THEME), COLORS));
  }

  // themeOrder takes its order from the published list, never from the table.
  function themeOrder() {
    return held === null ? [] : listField(objectField(held.model, THEME), THEME_KEYS).slice();
  }

  function colourOrder() {
    return held === null ? [] : listField(objectField(held.model, THEME), COLOR_NAMES).slice();
  }

  function stateOrder() {
    return held === null ? [] : listField(objectField(held.model, STATES), STATE_NAMES).slice();
  }

  function drawingCalls() {
    return list(DRAWING_CALLS);
  }

  function paintBranches() {
    return list(PAINT_BRANCHES);
  }

  function routeCalls() {
    return list(CALLS);
  }

  function colourAt(group, name, label) {
    if (held === null) {
      return undefined;
    }
    var bags = {};
    colourGroups(held.model).forEach(function (pair) {
      bags[pair[ZERO]] = pair[ONE];
    });
    var row = objectField(bags[group] || {}, name);
    return colour(group + PATH_SPLIT + name, label, row[label], alphaDivisor(held.model));
  }

  function nameOf(one) {
    return one.props.name === undefined
      ? BODY_PART + KEY_SPLIT + String(one.props.first)
      : one.props.name;
  }

  function drawnKeys() {
    return drawnParts().map(function (one) {
      return one.name;
    });
  }

  // drawnParts answers each drawn part, its call and the name it answers to.
  function drawnParts() {
    if (held === null) {
      return [];
    }
    return replay(held.model).drawn.map(function (one) {
      return {
        part: one.part,
        at: one.props.at === undefined ? one.props.first : one.props.at,
        name: nameOf(one)
      };
    });
  }

  function labelOrder() {
    if (held === null) {
      return [];
    }
    var found = [];
    replay(held.model).drawn.forEach(function (one) {
      if (one.props.words !== undefined) {
        found.push([text(one.props.label), String(one.props.words)]);
      }
    });
    return found;
  }

  function heldLabelGroups() {
    return held === null ? {} : labelGroups(held.model);
  }

  function deferredCount() {
    return held === null ? { paths: ZERO, slopes: ZERO } : replay(held.model).deferred;
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelays() {
    return list(TIMER_DELAYS_MS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function signals() {
    return list(SIGNALS);
  }

  function screenElements() {
    return list(SCREEN_ELEMENTS);
  }

  function stepKinds() {
    return list(STEP_KINDS);
  }

  function callNames() {
    return list(DRAW_CALL_NAMES);
  }

  function routeNames() {
    return list(ROUTE_NAMES);
  }

  function branchNames() {
    return list(PAINT_BRANCH_NAMES);
  }

  function method() {
    return field(METHOD_FIELD);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function declaredNames() {
    return DECLARED_FIELDS.concat(
      THEME_FIELDS,
      STATE_FIELDS,
      CARD_FIELDS,
      LABEL_FIELDS,
      FONT_FIELDS,
      PEN_FIELDS,
      [NAME_FIELD, PEN_STYLE, VALUE_FIELD, TEXT_FIELD],
      [SYMBOL_LABEL, PNL_LABEL, BOT_ID_LABEL]
    );
  }

  function slots() {
    return [CARD_SLOT];
  }

  function parts() {
    return [CARD_PART, GROUND_PART, DOT_PART, RULE_PART, WORDS_PART, BODY_PART];
  }

  // kinds reports the JavaScript type of every payload value by dotted path.
  function kinds() {
    var found = {};
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, index) {
          var inner = path + PATH_SPLIT + String(index);
          found[inner] = kindOf(one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return cardFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
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

  // draw runs flushSync so the document is current when it answers.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderCard(target, model) {
    var payload = isPlainObject(model) ? model : held === null ? null : held.model;
    return draw(target, element(Card, { model: payload }));
  }

  function forget() {
    held = null;
    cardFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetBotNode = setBotNode;
  global.acervatorLoadBotNode = loadBotNode;
  global.acervatorBotNode = {
    method: METHOD,
    Card: Card,
    Ground: Ground,
    Dot: Dot,
    Rule: Rule,
    Words: Words,
    Body: Body,
    field: field,
    card: card,
    themeColours: themeColours,
    themeOrder: themeOrder,
    colourOrder: colourOrder,
    stateOrder: stateOrder,
    colourAt: colourAt,
    drawingCalls: drawingCalls,
    paintBranches: paintBranches,
    routeCalls: routeCalls,
    drawnKeys: drawnKeys,
    drawnParts: drawnParts,
    labelOrder: labelOrder,
    labelGroups: heldLabelGroups,
    deferredCount: deferredCount,
    actions: actions,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    signals: signals,
    screenElements: screenElements,
    stepKinds: stepKinds,
    callNames: callNames,
    routeNames: routeNames,
    branchNames: branchNames,
    methodName: method,
    declaredFields: declaredFields,
    declaredNames: declaredNames,
    slots: slots,
    parts: parts,
    qtColour: qtColour,
    variableFor: variableFor,
    pixels: pixels,
    points: points,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderCard: renderCard,
    forget: forget
  };
})(window);
