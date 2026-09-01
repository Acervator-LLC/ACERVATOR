// The `notification_spool.lines` payload, each line drawn from its own
// `stamp`, `message` and `color`.
(function (global) {
  "use strict";

  var METHOD = "notification_spool.lines";

  var WIDGET = "widget";
  var DOCUMENT = "document";
  var DOCUMENT_BLOCKS = "document_blocks";
  var TIMESTAMP_COLOR = "timestamp_color";
  var LEVEL_COLORS = "level_colors";
  var DEFAULT_LEVEL_COLOR = "default_level_color";

  var DECLARED_FIELDS = [
    DEFAULT_LEVEL_COLOR,
    DOCUMENT,
    DOCUMENT_BLOCKS,
    LEVEL_COLORS,
    TIMESTAMP_COLOR,
    WIDGET
  ];

  var LINES = "lines";
  var ACCESSIBLE_NAME = "accessible_name";
  var READ_ONLY = "read_only";
  var MAX_HEIGHT = "maximum_height_px";
  var PLACEHOLDER = "placeholder_text";
  var MAX_BLOCKS = "maximum_block_count";

  var STAMP = "stamp";
  var MESSAGE = "message";
  var LEVEL = "level";
  var COLOR = "color";
  var CHANNEL_NAMES = ["r", "g", "b"];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var SHORT_LIST_FAULT = "short-list";
  var CHANNEL_FAULT = "channel-mismatch";
  var UNNAMED_LEVEL_FAULT = "unnamed-level";

  var NO_BRIDGE = "the preload bridge is not present";

  var LINE_AT = "line:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var VAR_OPEN = "var(--";
  var LIST_SPLIT = ", ";
  var CLOSE = ")";
  var RGB_OPEN = "rgb(";
  var PX = "px";

  // GAP is the space between one line's stamp span and its message span.
  var GAP = " ";

  var SPOOL_CLASS = "acervator-notification-spool";
  var LINE_CLASS = "acervator-notification-line";

  var SPOOL_PART = "spool";
  var PLACEHOLDER_PART = "placeholder";
  var LINE_PART = "line";
  var STAMP_PART = "stamp";
  var MESSAGE_PART = "message";

  var SCROLL = "auto";
  var WRAP = "anywhere";

  var PART_ATTR = "data-part";
  var LEVEL_ATTR = "data-level";
  var READ_ONLY_ATTR = "data-read-only";
  var MAX_BLOCKS_ATTR = "data-maximum-block-count";
  var BLOCKS_ATTR = "data-document-blocks";
  var ARIA_LABEL = "aria-label";

  var CHANNELS = CHANNEL_NAMES.length;

  var held = null;
  var spoolFaults = [];
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

  // `acervatorWidgets` owns the one-carrier rule; without it every
  // colour paints from the surface.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // A colour painted through the one token that carries it, with the
  // surface's own value as the fallback.
  function paint(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + LIST_SPLIT + String(value) + CLOSE;
  }

  // The surface publishes the stamp colour as three channels, so it is
  // painted from those and reaches no token.
  function rgbOf(channels) {
    if (!Array.isArray(channels) || channels.length !== CHANNELS) {
      return undefined;
    }
    return RGB_OPEN + channels.join(LIST_SPLIT) + CLOSE;
  }

  // `pixels` writes a CSS length from the surface and resolves no token.
  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Line(props) {
    var line = props.line;
    if (!isPlainObject(line)) {
      return null;
    }
    var lineProps = {
      key: props.at,
      className: LINE_CLASS,
      style: { overflowWrap: WRAP }
    };
    lineProps[PART_ATTR] = LINE_PART;
    lineProps[LEVEL_ATTR] = text(line[LEVEL]);

    var stampProps = { style: { color: rgbOf(props.stampColor) } };
    stampProps[PART_ATTR] = STAMP_PART;

    var messageProps = { style: { color: paint(line[COLOR]) } };
    messageProps[PART_ATTR] = MESSAGE_PART;

    return element(
      "div",
      lineProps,
      element("span", stampProps, text(line[STAMP])),
      GAP,
      element("span", messageProps, text(line[MESSAGE]))
    );
  }

  function Spool(props) {
    var model = props.model;
    var widget = objectField(model, WIDGET);
    var lines = listField(objectField(model, DOCUMENT), LINES);
    var stampColor = isPlainObject(model) ? model[TIMESTAMP_COLOR] : undefined;

    var spoolProps = {
      className: SPOOL_CLASS,
      style: { maxHeight: pixels(widget[MAX_HEIGHT]), overflowY: SCROLL }
    };
    spoolProps[PART_ATTR] = SPOOL_PART;
    spoolProps[ARIA_LABEL] = text(widget[ACCESSIBLE_NAME]);
    spoolProps[READ_ONLY_ATTR] = text(widget[READ_ONLY]);
    spoolProps[MAX_BLOCKS_ATTR] = text(widget[MAX_BLOCKS]);
    spoolProps[BLOCKS_ATTR] = isPlainObject(model)
      ? text(model[DOCUMENT_BLOCKS])
      : undefined;

    if (!lines.length) {
      var emptyProps = {};
      emptyProps[PART_ATTR] = PLACEHOLDER_PART;
      return element(
        "div",
        spoolProps,
        element("div", emptyProps, text(widget[PLACEHOLDER]))
      );
    }
    return element(
      "div",
      spoolProps,
      lines.map(function (line, at) {
        return element(Line, { line: line, at: at, stampColor: stampColor });
      })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        spoolFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        spoolFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkChannels(where, field, channels) {
    if (Array.isArray(channels) && channels.length === CHANNELS) {
      return;
    }
    var detail = Array.isArray(channels) ? channels.length : kindOf(channels);
    spoolFaults.push(fault(where, field, SHORT_LIST_FAULT, detail));
  }

  function levelChannels(model, level) {
    var table = objectField(model, LEVEL_COLORS);
    return owns(table, level) ? table[level] : model[DEFAULT_LEVEL_COLOR];
  }

  // A line whose channels disagree with the level table is a message
  // painted in a colour that level never names.
  function checkLines(model) {
    var table = objectField(model, LEVEL_COLORS);
    listField(objectField(model, DOCUMENT), LINES).forEach(function (line, at) {
      var where = LINE_AT + String(at);
      if (!isPlainObject(line)) {
        spoolFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(line)));
        return;
      }
      if (!owns(table, line[LEVEL])) {
        spoolFaults.push(fault(where, LEVEL, UNNAMED_LEVEL_FAULT, text(line[LEVEL])));
      }
      var wanted = levelChannels(model, line[LEVEL]);
      if (!Array.isArray(wanted) || wanted.length !== CHANNELS) {
        return;
      }
      CHANNEL_NAMES.forEach(function (name, channel) {
        if (line[name] !== wanted[channel]) {
          spoolFaults.push(fault(where, name, CHANNEL_FAULT, kindOf(line[name])));
        }
      });
    });
  }

  function checkColours(model) {
    checkChannels(null, TIMESTAMP_COLOR, model[TIMESTAMP_COLOR]);
    checkChannels(null, DEFAULT_LEVEL_COLOR, model[DEFAULT_LEVEL_COLOR]);
    var table = objectField(model, LEVEL_COLORS);
    Object.keys(table).forEach(function (name) {
      checkChannels(LEVEL_COLORS, name, table[name]);
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function report() {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        blocks: held.model[DOCUMENT_BLOCKS]
      },
      held: {
        fields: heldFieldCount(),
        lines: listField(objectField(held.model, DOCUMENT), LINES).length
      },
      faults: spoolFaults.slice()
    };
  }

  function setSpool(model) {
    if (!isPlainObject(model)) {
      held = null;
      spoolFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: spoolFaults.slice() };
    }
    held = { model: model };
    spoolFaults = [];
    checkFields(model);
    checkColours(model);
    checkLines(model);
    return report();
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadSpool(params) {
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
        setSpool(model);
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

  function widget() {
    return held === null ? {} : copyOf(objectField(held.model, WIDGET));
  }

  function document_() {
    return held === null ? {} : copyOf(objectField(held.model, DOCUMENT));
  }

  function lines() {
    return held === null
      ? []
      : listField(objectField(held.model, DOCUMENT), LINES).slice();
  }

  function line(at) {
    var found = lines();
    return at < found.length ? found[at] : undefined;
  }

  function documentBlocks() {
    return field(DOCUMENT_BLOCKS);
  }

  function timestampColour() {
    return held === null ? undefined : held.model[TIMESTAMP_COLOR];
  }

  function levelColours() {
    return held === null ? {} : copyOf(objectField(held.model, LEVEL_COLORS));
  }

  function levelColour(name) {
    var table = levelColours();
    return owns(table, name) ? table[name] : undefined;
  }

  function defaultLevelColour() {
    return field(DEFAULT_LEVEL_COLOR);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function channelNames() {
    return CHANNEL_NAMES.slice();
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
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
    return spoolFaults.slice();
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

  // The Qt pane jumps to the newest line after every notification.
  function scrollToEnd(target) {
    var pane = target.firstChild;
    if (pane && typeof pane.scrollHeight === "number") {
      pane.scrollTop = pane.scrollHeight;
    }
  }

  function renderSpool(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    draw(target, element(Spool, { model: payload }));
    scrollToEnd(target);
    return target;
  }

  function forget() {
    held = null;
    spoolFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSpool = setSpool;
  global.acervatorLoadSpool = loadSpool;
  global.acervatorSpool = {
    method: METHOD,
    Spool: Spool,
    Line: Line,
    widget: widget,
    document: document_,
    lines: lines,
    line: line,
    documentBlocks: documentBlocks,
    timestampColour: timestampColour,
    levelColours: levelColours,
    levelColour: levelColour,
    defaultLevelColour: defaultLevelColour,
    declaredFields: declaredFields,
    channelNames: channelNames,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderSpool: renderSpool,
    forget: forget
  };
})(window);
