// The Activity Log, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "status_log.lines";

  var WIDGET = "widget";
  var DOCUMENT = "document";
  var LINES = "lines";
  var PAUSED = "paused";
  var BUFFERED = "buffered";
  var BUFFER_CAP = "buffer_cap";
  var DOCUMENT_BLOCKS = "document_blocks";
  var HEALTH = "health";
  var TIMESTAMP_COLOR = "timestamp_color";
  var LEVEL_COLORS = "level_colors";
  var DEFAULT_LEVEL_COLOR = "default_level_color";
  var STAGE_COLORS = "stage_colors";
  var STAGE_DEFAULT_COLOR = "stage_default_color";
  var WIRE_FLOW_COLOR = "wire_flow_color";
  var WIRE_STACK_COLOR = "wire_stack_color";
  var RESUME_MARKER_COLOR = "resume_marker_color";

  var DECLARED_FIELDS = [
    BUFFERED,
    BUFFER_CAP,
    DEFAULT_LEVEL_COLOR,
    DOCUMENT,
    DOCUMENT_BLOCKS,
    HEALTH,
    LEVEL_COLORS,
    PAUSED,
    RESUME_MARKER_COLOR,
    STAGE_COLORS,
    STAGE_DEFAULT_COLOR,
    TIMESTAMP_COLOR,
    WIDGET,
    WIRE_FLOW_COLOR,
    WIRE_STACK_COLOR
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var READ_ONLY = "read_only";
  var MAXIMUM_HEIGHT_PX = "maximum_height_px";
  var PLACEHOLDER_TEXT = "placeholder_text";
  var MAXIMUM_BLOCK_COUNT = "maximum_block_count";

  var STAMP = "stamp";
  var STAMP_TEXT = "stamp_text";
  var TAG = "tag";
  var TEXT = "text";
  var LEVEL = "level";
  var KIND = "kind";
  var COLOR = "color";
  var FONT_SIZE_PX = "font_size_px";
  var BOLD = "bold";
  var ITALIC = "italic";
  var BULLET = "bullet";
  var RED = "r";
  var GREEN = "g";
  var BLUE = "b";
  var CHANNELS = [RED, GREEN, BLUE];

  var PAUSE_BUFFER_SIZE = "pause_buffer_size";
  var LAST_RENDER_AGE_SEC = "last_render_age_sec";
  var TOTAL_RENDERS = "total_renders";
  var RENDER_ERRORS = "render_errors";
  var LAST_RENDER_ERROR = "last_render_error";

  var KIND_TRADE = "trade";
  var KIND_WIRE_FLOW = "wire_flow";
  var KIND_WIRE_STACK = "wire_stack";
  var KIND_PLAIN = "plain";
  var KIND_RESUME = "resume";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var COLOUR_MISMATCH_FAULT = "colour-mismatch";
  var DISAGREES_FAULT = "disagrees";
  var BOTH_EMPHASIS_FAULT = "both-emphasis";
  var UNKNOWN_KIND_FAULT = "unknown-kind";

  var NO_BRIDGE = "the preload bridge is not present";

  var LINE_AT = "line:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var PX = "px";
  var RGB_OPEN = "rgb(";
  var OVERFLOW_AUTO = "auto";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "b";
  var EMPHASIS_TAG = "i";

  var LOG_CLASS = "acervator-status-log";
  var LINE_CLASS = "acervator-status-log-line";
  var STAMP_CLASS = "acervator-status-log-stamp";
  var BODY_CLASS = "acervator-status-log-body";

  var LOG_PART = "log";
  var PLACEHOLDER_PART = "placeholder";
  var LINE_PART = "line";
  var STAMP_PART = "stamp";
  var BODY_PART = "body";
  var TAG_PART = "tag";
  var BULLET_PART = "bullet";
  var MESSAGE_PART = "message";

  var PART_ATTR = "data-part";
  var KIND_ATTR = "data-kind";
  var LEVEL_ATTR = "data-level";
  var INDEX_ATTR = "data-index";
  var STAMP_ATTR = "data-stamp";
  var BOLD_ATTR = "data-bold";
  var ITALIC_ATTR = "data-italic";
  var PAUSED_ATTR = "data-paused";
  var BUFFERED_ATTR = "data-buffered";
  var BUFFER_CAP_ATTR = "data-buffer-cap";
  var BLOCKS_ATTR = "data-document-blocks";
  var DECLARED_LINES_ATTR = "data-declared-lines";
  var HELD_LINES_ATTR = "data-held-lines";
  var READ_ONLY_ATTR = "data-read-only";
  var MAX_BLOCKS_ATTR = "data-maximum-block-count";
  var TOTAL_RENDERS_ATTR = "data-total-renders";
  var RENDER_ERRORS_ATTR = "data-render-errors";
  var LAST_ERROR_ATTR = "data-last-render-error";
  var BUFFER_SIZE_ATTR = "data-pause-buffer-size";
  var RENDER_AGE_ATTR = "data-last-render-age-sec";
  var ARIA_LABEL = "aria-label";
  var ARIA_READONLY = "aria-readonly";

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

  // -- resolving a value through the token and theme modules -----------

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

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableFor(value);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // The surface publishes the stamp colour as three channels, which no
  // design token carries, so it is painted as `rgb`.
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

  // -- the components --------------------------------------------------

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // Qt paints the tag, the bullet and the text in one span, so the emphasis
  // tag wraps all three.
  function bodyTag(line) {
    if (line[BOLD] === true) {
      return STRONG_TAG;
    }
    if (line[ITALIC] === true) {
      return EMPHASIS_TAG;
    }
    return SPAN_TAG;
  }

  function Line(props) {
    var line = props.line;
    var lineProps = { className: LINE_CLASS };
    lineProps[PART_ATTR] = LINE_PART;
    lineProps[INDEX_ATTR] = String(props.at);
    lineProps[KIND_ATTR] = text(line[KIND]);
    lineProps[LEVEL_ATTR] = text(line[LEVEL]);
    lineProps[STAMP_ATTR] = text(line[STAMP]);

    var stampProps = { className: STAMP_CLASS, style: { color: props.stampColour } };
    stampProps[PART_ATTR] = STAMP_PART;

    var bodyProps = {
      className: BODY_CLASS,
      style: { color: colour(line[COLOR]), fontSize: length(line[FONT_SIZE_PX]) }
    };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[BOLD_ATTR] = text(line[BOLD]);
    bodyProps[ITALIC_ATTR] = text(line[ITALIC]);

    var tagProps = {};
    tagProps[PART_ATTR] = TAG_PART;
    var bulletProps = {};
    bulletProps[PART_ATTR] = BULLET_PART;
    var messageProps = {};
    messageProps[PART_ATTR] = MESSAGE_PART;

    // An unstamped line carries no span and no gap, as `notice` appends it.
    var painted = text(line[STAMP_TEXT]);
    var body = element(
      bodyTag(line),
      bodyProps,
      element(SPAN_TAG, tagProps, text(line[TAG])),
      element(SPAN_TAG, bulletProps, text(line[BULLET])),
      element(SPAN_TAG, messageProps, text(line[TEXT]))
    );
    if (painted === EMPTY) {
      return element(DIV_TAG, lineProps, body);
    }
    return element(
      DIV_TAG,
      lineProps,
      element(SPAN_TAG, stampProps, painted),
      GAP,
      body
    );
  }

  function Placeholder(props) {
    var placeholderProps = {};
    placeholderProps[PART_ATTR] = PLACEHOLDER_PART;
    return element(DIV_TAG, placeholderProps, text(props.widget[PLACEHOLDER_TEXT]));
  }

  // `Log` draws nothing for a payload that is not an object.
  function Log(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var widget = objectField(model, WIDGET);
    var health = objectField(model, HEALTH);
    var lines = documentLines(model);
    var stampColour = rgbOf(model[TIMESTAMP_COLOR]);

    var logProps = {
      id: props.id,
      className: LOG_CLASS,
      style: {
        maxHeight: length(widget[MAXIMUM_HEIGHT_PX]),
        overflowY: OVERFLOW_AUTO
      }
    };
    logProps[PART_ATTR] = LOG_PART;
    logProps[ARIA_LABEL] = text(widget[ACCESSIBLE_NAME]);
    logProps[ARIA_READONLY] = text(widget[READ_ONLY]);
    logProps[READ_ONLY_ATTR] = text(widget[READ_ONLY]);
    logProps[MAX_BLOCKS_ATTR] = text(widget[MAXIMUM_BLOCK_COUNT]);
    logProps[PAUSED_ATTR] = text(model[PAUSED]);
    logProps[BUFFERED_ATTR] = text(model[BUFFERED]);
    logProps[BUFFER_CAP_ATTR] = text(model[BUFFER_CAP]);
    logProps[BLOCKS_ATTR] = text(model[DOCUMENT_BLOCKS]);
    logProps[DECLARED_LINES_ATTR] = String(lines.length);
    logProps[HELD_LINES_ATTR] = String(heldLineCount(model));
    logProps[TOTAL_RENDERS_ATTR] = text(health[TOTAL_RENDERS]);
    logProps[RENDER_ERRORS_ATTR] = text(health[RENDER_ERRORS]);
    logProps[LAST_ERROR_ATTR] = text(health[LAST_RENDER_ERROR]);
    logProps[BUFFER_SIZE_ATTR] = text(health[PAUSE_BUFFER_SIZE]);
    logProps[RENDER_AGE_ATTR] = text(health[LAST_RENDER_AGE_SEC]);

    if (!lines.length) {
      return element(
        DIV_TAG,
        logProps,
        element(Placeholder, { widget: widget })
      );
    }
    return element(
      DIV_TAG,
      logProps,
      lines.map(function (line, at) {
        return element(Line, {
          key: String(at),
          at: at,
          line: isPlainObject(line) ? line : {},
          stampColour: stampColour
        });
      })
    );
  }

  // -- what the payload carries, and what it does not ------------------

  function documentLines(model) {
    return listField(objectField(model, DOCUMENT), LINES);
  }

  function heldLineCount(model) {
    return documentLines(model).filter(isPlainObject).length;
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

  // The surface publishes these three twice, so each holds the other.
  function checkAgreement(model) {
    var health = objectField(model, HEALTH);
    var pairs = [
      { field: PAUSED, mine: model[PAUSED], theirs: health[PAUSED] },
      { field: BUFFERED, mine: model[BUFFERED], theirs: health[PAUSE_BUFFER_SIZE] },
      {
        field: DOCUMENT_BLOCKS,
        mine: model[DOCUMENT_BLOCKS],
        theirs: health[DOCUMENT_BLOCKS]
      }
    ];
    pairs.forEach(function (one) {
      if (one.mine !== one.theirs) {
        logFaults.push(fault(HEALTH, one.field, DISAGREES_FAULT, one.theirs));
      }
    });
  }

  // The colour table one kind names, undefined for a kind naming none.
  function allowedTriples(model, line) {
    var kind = line[KIND];
    if (kind === KIND_PLAIN) {
      var levels = objectField(model, LEVEL_COLORS);
      var level = line[LEVEL];
      return [owns(levels, level) ? levels[level] : model[DEFAULT_LEVEL_COLOR]];
    }
    if (kind === KIND_TRADE) {
      var stages = objectField(model, STAGE_COLORS);
      var found = Object.keys(stages).map(function (name) {
        return stages[name];
      });
      found.push(model[STAGE_DEFAULT_COLOR]);
      return found;
    }
    if (kind === KIND_WIRE_FLOW) {
      return [model[WIRE_FLOW_COLOR]];
    }
    if (kind === KIND_WIRE_STACK) {
      return [model[WIRE_STACK_COLOR]];
    }
    if (kind === KIND_RESUME) {
      return [model[RESUME_MARKER_COLOR]];
    }
    return undefined;
  }

  // `default_level_color` publishes the type a channel arrives as.
  function checkChannels(where, model, line) {
    var template = model[DEFAULT_LEVEL_COLOR];
    if (!Array.isArray(template) || !template.length) {
      return;
    }
    var wanted = kindOf(template.slice().shift());
    CHANNELS.forEach(function (name) {
      if (!owns(line, name)) {
        logFaults.push(fault(where, name, MISSING_FAULT, null));
        return;
      }
      if (line[name] === null) {
        logFaults.push(fault(where, name, NULL_FAULT, null));
        return;
      }
      if (kindOf(line[name]) !== wanted) {
        logFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(line[name])));
      }
    });
  }

  function checkColour(where, model, line) {
    var allowed = allowedTriples(model, line);
    if (allowed === undefined) {
      logFaults.push(fault(where, KIND, UNKNOWN_KIND_FAULT, kindOf(line[KIND])));
      return;
    }
    var printed = lineTriple(line);
    var matched = allowed.filter(function (triple) {
      return printedTriple(triple) === printed;
    });
    if (!matched.length) {
      logFaults.push(fault(where, COLOR, COLOUR_MISMATCH_FAULT, printed));
    }
  }

  function checkLines(model) {
    var carried = model[DOCUMENT];
    if (isPlainObject(carried) && !Array.isArray(carried[LINES])) {
      logFaults.push(fault(DOCUMENT, LINES, NOT_A_LIST_FAULT, kindOf(carried[LINES])));
      return;
    }
    documentLines(model).forEach(function (line, at) {
      var where = LINE_AT + String(at);
      if (!isPlainObject(line)) {
        logFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(line)));
        return;
      }
      checkChannels(where, model, line);
      checkColour(where, model, line);
      if (line[BOLD] === true && line[ITALIC] === true) {
        logFaults.push(fault(where, BOLD, BOTH_EMPHASIS_FAULT, null));
      }
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        lines: documentLines(model).length,
        blocks: model[DOCUMENT_BLOCKS]
      },
      held: {
        fields: heldFieldCount(),
        lines: heldLineCount(model),
        blocks: objectField(model, HEALTH)[DOCUMENT_BLOCKS]
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
    checkAgreement(model);
    checkLines(model);
    return report();
  }

  // Keeps the lines already held and adds the batch `model` carries, so the
  // pane spools the way the Qt document does.
  function takeLog(model) {
    if (!isPlainObject(model)) {
      return setLog(model);
    }
    var kept = held === null ? [] : documentLines(held.model).slice();
    var joined = kept.concat(documentLines(model));
    var cap = Number(objectField(model, WIDGET)[MAXIMUM_BLOCK_COUNT]);
    if (cap > 0 && joined.length > cap) {
      joined = joined.slice(joined.length - cap);
    }
    var merged = copyOf(model);
    var carried = {};
    carried[LINES] = joined;
    merged[DOCUMENT] = carried;
    return setLog(merged);
  }

  // One round trip per page, and a failed ask is not remembered. A model
  // already held answers without a second ask, so a redraw keeps its lines.
  function loadLog(params) {
    if (held !== null) {
      return Promise.resolve(held.model);
    }
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

  // -- what the module answers for ---------------------------------------

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function widget() {
    return bag(WIDGET);
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

  function paused() {
    return field(PAUSED);
  }

  function buffered() {
    return field(BUFFERED);
  }

  function bufferCap() {
    return field(BUFFER_CAP);
  }

  function documentBlocks() {
    return field(DOCUMENT_BLOCKS);
  }

  function health() {
    return bag(HEALTH);
  }

  function timestampColor() {
    return field(TIMESTAMP_COLOR);
  }

  function levelColors() {
    return field(LEVEL_COLORS);
  }

  function levelColor(name) {
    var table = held === null ? {} : objectField(held.model, LEVEL_COLORS);
    return owns(table, name) ? table[name] : undefined;
  }

  function defaultLevelColor() {
    return field(DEFAULT_LEVEL_COLOR);
  }

  function stageColors() {
    return field(STAGE_COLORS);
  }

  function stageColor(name) {
    var table = held === null ? {} : objectField(held.model, STAGE_COLORS);
    return owns(table, name) ? table[name] : undefined;
  }

  function stageDefaultColor() {
    return field(STAGE_DEFAULT_COLOR);
  }

  function wireFlowColor() {
    return field(WIRE_FLOW_COLOR);
  }

  function wireStackColor() {
    return field(WIRE_STACK_COLOR);
  }

  function resumeMarkerColor() {
    return field(RESUME_MARKER_COLOR);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
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

  // -- drawing ----------------------------------------------------------

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

  // Every host this module has drawn into, re-drawn from the held model.
  function redraw() {
    roots.forEach(function (pair) {
      renderLog(pair.node, held === null ? null : held.model);
    });
    return roots.length;
  }

  // The pane's own pause, which ``StatusLog.pause`` and ``resume`` set.
  function setPaused(flag) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return global.acervator
      .call(METHOD, { paused: flag === true })
      .then(function (model) {
        loadFault = null;
        setLog(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function forget() {
    held = null;
    logFaults = [];
    loadFault = null;
    asked = null;
  }

  // The Activity Log belongs to the Trading tab, so it names no bridge
  // method and the tab bar gives it no tab of its own.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderLog,
      load: loadLog,
      loadError: loadError
    });
  }

  global.acervatorSetLog = setLog;
  global.acervatorTakeLog = takeLog;
  global.acervatorLoadLog = loadLog;
  global.acervatorLog = {
    method: METHOD,
    take: takeLog,
    Log: Log,
    Line: Line,
    Placeholder: Placeholder,
    widget: widget,
    document: documentOf,
    lines: lines,
    lineAt: lineAt,
    paused: paused,
    buffered: buffered,
    bufferCap: bufferCap,
    documentBlocks: documentBlocks,
    health: health,
    timestampColor: timestampColor,
    levelColors: levelColors,
    levelColor: levelColor,
    defaultLevelColor: defaultLevelColor,
    stageColors: stageColors,
    stageColor: stageColor,
    stageDefaultColor: stageDefaultColor,
    wireFlowColor: wireFlowColor,
    wireStackColor: wireStackColor,
    resumeMarkerColor: resumeMarkerColor,
    declaredFields: declaredFields,
    bodyTag: bodyTag,
    rgbOf: rgbOf,
    colour: colour,
    length: length,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderLog: renderLog,
    redraw: redraw,
    setPaused: setPaused,
    forget: forget
  };
})(window);
