// The Console log body, as console_log_surface.py serves it.
(function (global) {
  "use strict";

  var METHOD = "console.log_lines";

  var DOCUMENT = "document";
  var INSERT_TEXT = "insert_text";
  var LINES = "lines";
  var PAUSED = "paused";
  var BUFFERED = "buffered";
  var DROPPED = "dropped";
  var BUFFER_MAX = "buffer_max";
  var FOLLOW_TAIL = "follow_tail";
  var LEVEL_COLORS = "level_colors";
  var LEVEL_HEX = "level_hex";
  var LEVEL_ORDER = "level_order";
  var DEFAULT_LEVEL = "default_level";
  var HIGHLIGHT_COLOR = "highlight_color";
  var HIGHLIGHT_HEX = "highlight_hex";
  var HIGHLIGHT_MARKER = "highlight_marker";

  var DECLARED_FIELDS = [
    BUFFERED,
    BUFFER_MAX,
    DEFAULT_LEVEL,
    DOCUMENT,
    DROPPED,
    FOLLOW_TAIL,
    HIGHLIGHT_COLOR,
    HIGHLIGHT_MARKER,
    HIGHLIGHT_HEX,
    LEVEL_COLORS,
    LEVEL_ORDER,
    LEVEL_HEX,
    PAUSED
  ];

  var TEXT = "text";
  var LEVEL = "level";
  var COLOR = "color";
  var RED = "r";
  var GREEN = "g";
  var BLUE = "b";
  var CHANNELS = [RED, GREEN, BLUE];
  var LINE_FIELDS = [TEXT, LEVEL, COLOR, RED, GREEN, BLUE];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NO_TEMPLATE_FAULT = "no-template";
  var COLOUR_MISMATCH_FAULT = "colour-mismatch";
  var TOKEN_MISMATCH_FAULT = "token-mismatch";
  var HEX_WIDTH_FAULT = "hex-width";
  var DISAGREES_FAULT = "disagrees";
  var OVER_CAP_FAULT = "over-cap";

  var NO_BRIDGE = "the preload bridge is not present";

  var LINE_AT = "line:";
  var PATH_SPLIT = ".";
  var NEWLINE = "\n";
  var EMPTY = "";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var RGB_OPEN = "rgb(";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var LOG_CLASS = "acervator-console-log";
  var LINE_CLASS = "acervator-console-log-line";

  var LOG_PART = "log";
  var LINE_PART = "line";

  var PART_ATTR = "data-part";
  var INDEX_ATTR = "data-index";
  var LEVEL_ATTR = "data-level";
  var COLOR_ATTR = "data-color";
  var PAUSED_ATTR = "data-paused";
  var BUFFERED_ATTR = "data-buffered";
  var DROPPED_ATTR = "data-dropped";
  var BUFFER_MAX_ATTR = "data-buffer-max";
  var FOLLOW_TAIL_ATTR = "data-follow-tail";
  var DECLARED_LINES_ATTR = "data-declared-lines";
  var HELD_LINES_ATTR = "data-held-lines";
  var MARKER_ATTR = "data-highlight-marker";

  var held = null;
  var logFaults = [];
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

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // `shared_widgets.js` owns the one-carrier rule that names a token.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // A colour painted through the one token that carries it, falling
  // back to the value the surface published.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  function rgbOf(triple) {
    if (!Array.isArray(triple)) {
      return undefined;
    }
    return RGB_OPEN + triple.join(VAR_SPLIT) + VAR_CLOSE;
  }

  function printedTriple(triple) {
    return Array.isArray(triple) ? triple.join(VAR_SPLIT) : undefined;
  }

  function lineTriple(line) {
    return CHANNELS.map(function (name) {
      return line[name];
    }).join(VAR_SPLIT);
  }

  function marked(model, line) {
    var marker = model[HIGHLIGHT_MARKER];
    return typeof marker === "string" && String(line[TEXT]).includes(marker);
  }

  function fromTable(model, field, line) {
    var table = objectField(model, field);
    if (owns(table, line[LEVEL])) {
      return table[line[LEVEL]];
    }
    return table[model[DEFAULT_LEVEL]];
  }

  // The marker beats the level, and an unknown level takes the default.
  function expectedToken(model, line) {
    if (marked(model, line)) {
      return model[HIGHLIGHT_HEX];
    }
    return fromTable(model, LEVEL_HEX, line);
  }

  function expectedTriple(model, line) {
    if (marked(model, line)) {
      return model[HIGHLIGHT_COLOR];
    }
    return fromTable(model, LEVEL_COLORS, line);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Line(props) {
    var line = props.line;
    var lineProps = { className: LINE_CLASS, style: { color: colour(line[COLOR]) } };
    lineProps[PART_ATTR] = LINE_PART;
    lineProps[INDEX_ATTR] = String(props.at);
    lineProps[LEVEL_ATTR] = text(line[LEVEL]);
    lineProps[COLOR_ATTR] = text(line[COLOR]);
    return element(SPAN_TAG, lineProps, text(line[TEXT]));
  }

  // Qt holds the batch in one document, so a newline joins the lines
  // and a drag selects across them.
  function children(lines) {
    var found = [];
    lines.forEach(function (line, at) {
      if (found.length) {
        found.push(NEWLINE);
      }
      found.push(
        element(Line, {
          key: String(at),
          at: at,
          line: isPlainObject(line) ? line : {}
        })
      );
    });
    return found;
  }

  // `Log` draws nothing for a payload that is not an object.
  function Log(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var lines = documentLines(model);

    var logProps = { id: props.id, className: LOG_CLASS };
    logProps[PART_ATTR] = LOG_PART;
    logProps[PAUSED_ATTR] = text(model[PAUSED]);
    logProps[BUFFERED_ATTR] = text(model[BUFFERED]);
    logProps[DROPPED_ATTR] = text(model[DROPPED]);
    logProps[BUFFER_MAX_ATTR] = text(model[BUFFER_MAX]);
    logProps[FOLLOW_TAIL_ATTR] = text(model[FOLLOW_TAIL]);
    logProps[MARKER_ATTR] = text(model[HIGHLIGHT_MARKER]);
    logProps[DECLARED_LINES_ATTR] = String(lines.length);
    logProps[HELD_LINES_ATTR] = String(heldLineCount(model));
    return element(DIV_TAG, logProps, children(lines));
  }

  function documentLines(model) {
    return listField(objectField(model, DOCUMENT), LINES);
  }

  function heldLineCount(model) {
    return documentLines(model).filter(isPlainObject).length;
  }

  function joinedText(model) {
    return documentLines(model)
      .map(function (line) {
        return isPlainObject(line) ? String(line[TEXT]) : EMPTY;
      })
      .join(NEWLINE);
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        logFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        logFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // Every level the surface orders must carry a colour and a token.
  function checkTables(model) {
    var colours = objectField(model, LEVEL_COLORS);
    var tokens = objectField(model, LEVEL_HEX);
    listField(model, LEVEL_ORDER).forEach(function (name) {
      if (!owns(colours, name)) {
        logFaults.push(fault(LEVEL_COLORS, name, MISSING_FAULT, null));
      }
      if (!owns(tokens, name)) {
        logFaults.push(fault(LEVEL_HEX, name, MISSING_FAULT, null));
      }
    });
  }

  // The type each line field arrives as, taken from the surface's own
  // published default for that same meaning.
  function templateOf(model) {
    var tokens = objectField(model, LEVEL_HEX);
    var triple = objectField(model, LEVEL_COLORS)[model[DEFAULT_LEVEL]];
    var channel = Array.isArray(triple) ? triple.slice().shift() : undefined;
    var found = {};
    found[TEXT] = objectField(model, DOCUMENT)[INSERT_TEXT];
    found[LEVEL] = model[DEFAULT_LEVEL];
    found[COLOR] = tokens[model[DEFAULT_LEVEL]];
    CHANNELS.forEach(function (name) {
      found[name] = channel;
    });
    return found;
  }

  function templateKinds(model) {
    var template = templateOf(model);
    var found = {};
    LINE_FIELDS.forEach(function (name) {
      found[name] =
        template[name] === undefined || template[name] === null
          ? undefined
          : kindOf(template[name]);
    });
    return found;
  }

  function checkLineTypes(where, wanted, line) {
    LINE_FIELDS.forEach(function (name) {
      if (!owns(line, name)) {
        logFaults.push(fault(where, name, MISSING_FAULT, null));
        return;
      }
      if (line[name] === null) {
        logFaults.push(fault(where, name, NULL_FAULT, null));
        return;
      }
      if (wanted[name] === undefined) {
        logFaults.push(fault(where, name, NO_TEMPLATE_FAULT, null));
        return;
      }
      if (kindOf(line[name]) !== wanted[name]) {
        logFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(line[name])));
      }
    });
  }

  // Qt reads eight hex digits alpha-first and CSS alpha-last, so an
  // odd width is refused.
  function checkHexWidth(where, model, value) {
    var wanted = objectField(model, LEVEL_HEX)[model[DEFAULT_LEVEL]];
    if (typeof wanted !== "string" || typeof value !== "string") {
      return;
    }
    if (value.length !== wanted.length) {
      logFaults.push(fault(where, COLOR, HEX_WIDTH_FAULT, value));
    }
  }

  function checkLineColour(where, model, line) {
    var wantedTriple = printedTriple(expectedTriple(model, line));
    if (wantedTriple !== undefined && lineTriple(line) !== wantedTriple) {
      logFaults.push(fault(where, COLOR, COLOUR_MISMATCH_FAULT, wantedTriple));
    }
    var wantedToken = expectedToken(model, line);
    if (wantedToken !== undefined && line[COLOR] !== wantedToken) {
      logFaults.push(fault(where, COLOR, TOKEN_MISMATCH_FAULT, wantedToken));
    }
    checkHexWidth(where, model, line[COLOR]);
  }

  function checkLines(model) {
    var carried = model[DOCUMENT];
    if (isPlainObject(carried) && !Array.isArray(carried[LINES])) {
      logFaults.push(fault(DOCUMENT, LINES, NOT_A_LIST_FAULT, kindOf(carried[LINES])));
      return;
    }
    var wanted = templateKinds(model);
    documentLines(model).forEach(function (line, at) {
      var where = LINE_AT + String(at);
      if (!isPlainObject(line)) {
        logFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(line)));
        return;
      }
      checkLineTypes(where, wanted, line);
      checkLineColour(where, model, line);
    });
  }

  // Qt writes a leading newline into a pane that already holds text.
  function checkInsertText(model) {
    var carried = objectField(model, DOCUMENT)[INSERT_TEXT];
    var joined = joinedText(model);
    if (carried === joined || carried === NEWLINE + joined) {
      return;
    }
    logFaults.push(fault(DOCUMENT, INSERT_TEXT, DISAGREES_FAULT, joined));
  }

  function checkBuffer(model) {
    if (
      typeof model[BUFFERED] === "number" &&
      typeof model[BUFFER_MAX] === "number" &&
      model[BUFFERED] > model[BUFFER_MAX]
    ) {
      logFaults.push(fault(null, BUFFERED, OVER_CAP_FAULT, model[BUFFERED]));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  // `declared` counts what the payload promises, `held` what it carries.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        lines: documentLines(model).length,
        levels: listField(model, LEVEL_ORDER).length
      },
      held: {
        fields: heldFieldCount(),
        lines: heldLineCount(model),
        levels: Object.keys(objectField(model, LEVEL_COLORS)).length
      },
      faults: logFaults.slice()
    };
  }

  function setLog(model) {
    if (!isPlainObject(model)) {
      held = null;
      logFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: logFaults.slice() };
    }
    held = { model: model };
    logFaults = [];
    checkFields(model);
    checkTables(model);
    checkLines(model);
    checkInsertText(model);
    checkBuffer(model);
    return report();
  }

  // One round trip per page, and a refused ask is not remembered.
  function loadLog(params) {
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
        setLog(model);
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
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function documentOf() {
    return bag(DOCUMENT);
  }

  function lines() {
    return held === null ? [] : documentLines(held.model).slice();
  }

  function lineAt(at) {
    return lines()[at];
  }

  function insertText() {
    return held === null ? undefined : objectField(held.model, DOCUMENT)[INSERT_TEXT];
  }

  function paused() {
    return field(PAUSED);
  }

  function buffered() {
    return field(BUFFERED);
  }

  function dropped() {
    return field(DROPPED);
  }

  function bufferMax() {
    return field(BUFFER_MAX);
  }

  function followTail() {
    return field(FOLLOW_TAIL);
  }

  function levelColors() {
    return field(LEVEL_COLORS);
  }

  function levelColor(name) {
    var table = held === null ? {} : objectField(held.model, LEVEL_COLORS);
    return owns(table, name) ? table[name] : undefined;
  }

  function levelHex() {
    return field(LEVEL_HEX);
  }

  function levelHexOf(name) {
    var table = held === null ? {} : objectField(held.model, LEVEL_HEX);
    return owns(table, name) ? table[name] : undefined;
  }

  function levelOrder() {
    return list(LEVEL_ORDER);
  }

  function defaultLevel() {
    return field(DEFAULT_LEVEL);
  }

  function highlightColor() {
    return field(HIGHLIGHT_COLOR);
  }

  function highlightHex() {
    return field(HIGHLIGHT_HEX);
  }

  function highlightMarker() {
    return field(HIGHLIGHT_MARKER);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function lineFields() {
    return LINE_FIELDS.slice();
  }

  function tokenFor(line) {
    return held === null ? undefined : expectedToken(held.model, line);
  }

  function tripleFor(line) {
    return held === null ? undefined : expectedTriple(held.model, line);
  }

  function templates() {
    return held === null ? {} : templateKinds(held.model);
  }

  // The JavaScript type of every payload value, by dotted path.
  function kinds() {
    var found = {};
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          found[inner] = kindOf(one);
          descend(inner, one);
        });
      }
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return logFaults.slice();
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

  // `flushSync` makes the document current before `draw` returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderLog(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Log, { model: payload }));
  }

  function forget() {
    held = null;
    logFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetConsoleLog = setLog;
  global.acervatorLoadConsoleLog = loadLog;
  global.acervatorConsoleLog = {
    method: METHOD,
    Log: Log,
    Line: Line,
    document: documentOf,
    lines: lines,
    lineAt: lineAt,
    insertText: insertText,
    paused: paused,
    buffered: buffered,
    dropped: dropped,
    bufferMax: bufferMax,
    followTail: followTail,
    levelColors: levelColors,
    levelColor: levelColor,
    levelHex: levelHex,
    levelHexOf: levelHexOf,
    levelOrder: levelOrder,
    defaultLevel: defaultLevel,
    highlightColor: highlightColor,
    highlightHex: highlightHex,
    highlightMarker: highlightMarker,
    declaredFields: declaredFields,
    lineFields: lineFields,
    tokenFor: tokenFor,
    tripleFor: tripleFor,
    templates: templates,
    colour: colour,
    rgbOf: rgbOf,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderLog: renderLog,
    forget: forget
  };
})(window);
