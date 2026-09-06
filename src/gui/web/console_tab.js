// The Console tab, as console_tab_surface.py serves it.
(function (global) {
  "use strict";

  var METHOD = "console.tab";

  var TAB_TITLE = "tab_title";
  var CONTAINER = "container";
  var CONTROL_BAR = "control_bar";
  var CONTROL_BAR_ORDER = "control_bar_order";
  var PAUSE_BUTTON = "pause_button";
  var PAUSE_INDICATOR = "pause_indicator";
  var CLEAR_BUTTON = "clear_button";
  var SIGNAL_BOX = "signal_box";
  var SIGNAL_HEADER = "signal_header";
  var SPLITTER = "splitter";
  var TIMERS = "timers";
  var ACTIONS = "actions";
  var LOG_HANDLER = "log_handler";
  var LOG_PANE = "log_pane";
  var SIGNAL_PANE = "signal_pane";
  var LEDGER = "ledger";

  var DECLARED_FIELDS = [
    ACTIONS,
    CLEAR_BUTTON,
    CONTAINER,
    CONTROL_BAR,
    CONTROL_BAR_ORDER,
    LEDGER,
    LOG_HANDLER,
    LOG_PANE,
    PAUSE_BUTTON,
    PAUSE_INDICATOR,
    SIGNAL_BOX,
    SIGNAL_HEADER,
    SIGNAL_PANE,
    SPLITTER,
    TAB_TITLE,
    TIMERS
  ];

  var SKINNED_FIELDS = [
    CONTROL_BAR,
    PAUSE_BUTTON,
    PAUSE_INDICATOR,
    CLEAR_BUTTON,
    SIGNAL_HEADER,
    LOG_PANE,
    SIGNAL_PANE
  ];

  var PANE_FIELDS = [LOG_PANE, SIGNAL_PANE];

  var TEXT = "text";
  var BLOCKS = "blocks";
  var BLOCK_COUNT = "block_count";
  var IS_EMPTY = "is_empty";
  var MAX_BLOCKS = "max_blocks";
  var READ_ONLY = "read_only";
  var WRAP = "wrap";
  var CENTER_ON_SCROLL = "center_on_scroll";
  var STYLE_SHEET = "style_sheet";
  var CHECKABLE = "checkable";
  var CHECKED = "checked";
  var CHECKED_BACKGROUND = "checked_background";
  var CHECKED_COLOR = "checked_color";
  var CHECKED_BORDER_COLOR = "checked_border_color";
  var HOVER_BACKGROUND = "hover_background";
  var FONT_FAMILY = "font_family";
  var FONT_SIZE_PX = "font_size_px";
  var FONT_POINT_SIZE = "font_point_size";
  var PADDING_PX = "padding_px";
  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var CHILD_STRETCH = "child_stretch";
  var CHILDREN = "children";
  var ORIENTATION = "orientation";
  var STRETCH = "stretch";
  var INTERVAL_MS = "interval_ms";
  var RUNNING = "running";
  var FORMAT = "format";
  var DATEFMT = "datefmt";
  var LOGGERS = "loggers";
  var HANDLER_LEVEL = "handler_level";

  // Each discrete skin field beside the CSS property its own sheet writes.
  var SKIN_PAIRS = [
    { field: "background", property: "background" },
    { field: "color", property: "color" },
    { field: "border", property: "border" },
    { field: "border_top", property: "border-top" },
    { field: "border_bottom", property: "border-bottom" },
    { field: FONT_FAMILY, property: "font-family" }
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var DISAGREES_FAULT = "disagrees";
  var SHORT_LIST_FAULT = "short-list";
  var OVER_CAP_FAULT = "over-cap";

  var NO_BRIDGE = "the preload bridge is not present";

  var PATH_SPLIT = ".";
  var NEWLINE = "\n";
  var EMPTY = "";
  var PX = "px";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";

  var FLEX = "flex";
  var ROW = "row";
  var COLUMN = "column";
  var FLEX_AUTO = "auto";
  var VERTICAL = "vertical";
  var OVERFLOW_AUTO = "auto";
  var NO_WRAP_SPACE = "pre";
  var WRAP_SPACE = "pre-wrap";

  var TAB_CLASS = "acervator-console-tab";
  var BAR_CLASS = "acervator-console-bar";
  var PANE_CLASS = "acervator-console-pane";
  var BLOCK_CLASS = "acervator-console-block";
  var BLOCK_COLORS = "block_colors";
  var RGB_OPEN = "rgb(";
  var COMMA = ",";
  var CLOSE = ")";

  var TAB_PART = "tab";
  var CONTROL_BAR_PART = "control-bar";
  var PAUSE_BUTTON_PART = "pause-button";
  var PAUSE_INDICATOR_PART = "pause-indicator";
  var CLEAR_BUTTON_PART = "clear-button";
  var STRETCH_PART = "stretch";
  var SPLITTER_PART = "splitter";
  var LOG_PANE_PART = "log-pane";
  var SIGNAL_BOX_PART = "signal-box";
  var SIGNAL_HEADER_PART = "signal-header";
  var SIGNAL_PANE_PART = "signal-pane";
  var BLOCK_PART = "block";
  var MACHINERY_PART = "machinery";
  var TIMER_PART = "timer";
  var COUNTER_PART = "counter";
  var LOG_HANDLER_PART = "log-handler";
  var LOGGER_PART = "logger";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var READ_ONLY_ATTR = "data-read-only";
  var WRAP_ATTR = "data-wrap";
  var CENTER_ON_SCROLL_ATTR = "data-center-on-scroll";
  var BLOCK_COLORS_ATTR = "data-block-colors";
  var MAX_BLOCKS_ATTR = "data-max-blocks";
  var DECLARED_BLOCKS_ATTR = "data-declared-blocks";
  var HELD_BLOCKS_ATTR = "data-held-blocks";
  var IS_EMPTY_ATTR = "data-is-empty";
  var FONT_FAMILY_ATTR = "data-font-family";
  var FONT_SIZE_ATTR = "data-font-size-px";
  var FONT_POINT_SIZE_ATTR = "data-font-point-size";
  var PADDING_ATTR = "data-padding-px";
  var CHECKABLE_ATTR = "data-checkable";
  var CHECKED_BACKGROUND_ATTR = "data-checked-background";
  var CHECKED_COLOR_ATTR = "data-checked-color";
  var CHECKED_BORDER_COLOR_ATTR = "data-checked-border-color";
  var HOVER_BACKGROUND_ATTR = "data-hover-background";
  var ORIENTATION_ATTR = "data-orientation";
  var DECLARED_PANES_ATTR = "data-declared-panes";
  var HELD_PANES_ATTR = "data-held-panes";
  var DECLARED_CONTROLS_ATTR = "data-declared-controls";
  var HELD_CONTROLS_ATTR = "data-held-controls";
  var TAB_TITLE_ATTR = "data-tab-title";
  var TIMER_ATTR = "data-timer";
  var INTERVAL_ATTR = "data-interval-ms";
  var RUNNING_ATTR = "data-running";
  var COUNTER_ATTR = "data-counter";
  var VALUE_ATTR = "data-value";
  var FORMAT_ATTR = "data-format";
  var DATEFMT_ATTR = "data-datefmt";
  var HANDLER_LEVEL_ATTR = "data-handler-level";
  var LOGGER_ATTR = "data-logger";
  var ARIA_LABEL = "aria-label";
  var ARIA_READONLY = "aria-readonly";
  var ARIA_PRESSED = "aria-pressed";

  var PAUSE_ACTION = "pause_button.clicked";
  var CLEAR_ACTION = "clear_button.clicked";

  // The surface writes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var consoleFaults = [];
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

  // header_strip.js owns the Qt style sheet parsing this module calls.
  function headerApi(name) {
    var api = global.acervatorHeader;
    return api && typeof api[name] === "function" ? api : null;
  }

  function sheetStyle(sheet) {
    var api = headerApi("styleOf");
    return api === null ? {} : api.styleOf(sheet);
  }

  function sheetDeclarations(sheet) {
    var api = headerApi("declarations");
    return api === null ? [] : api.declarations(sheet);
  }

  function sheetStateRules(sheet) {
    var api = headerApi("stateRules");
    return api === null ? [] : api.stateRules(sheet);
  }

  // The value one sheet writes for `property`, undefined when it writes none.
  function declaredValue(sheet, property) {
    var found;
    sheetDeclarations(sheet).forEach(function (one) {
      if (one.property === property) {
        found = one.value;
      }
    });
    return found;
  }

  // Console lengths carry no single token name, so pixels prints the number.
  function pixels(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }


  function boxStyle(layout, direction) {
    var style = {};
    var margins = listField(layout, MARGINS);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = pixels(margins[at]);
      }
    });
    style.display = FLEX;
    style.flexDirection = direction;
    if (owns(layout, SPACING)) {
      style.gap = pixels(layout[SPACING]);
    }
    return style;
  }

  function stretchAt(layout, field, at) {
    var stretch = listField(layout, field);
    return at < stretch.length ? stretch[at] : undefined;
  }

  function withStretch(style, value) {
    if (value !== undefined) {
      style.flexGrow = value;
    }
    return style;
  }

  // The pane wrap flag chooses pre or pre-wrap for its own blocks.
  function wrapStyle(pane) {
    if (pane[WRAP] === true) {
      return WRAP_SPACE;
    }
    if (pane[WRAP] === false) {
      return NO_WRAP_SPACE;
    }
    return undefined;
  }


  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // A block takes its own colour where the pane published one for it.
  function Block(props) {
    var blockProps = { className: BLOCK_CLASS };
    blockProps[PART_ATTR] = BLOCK_PART;
    blockProps[INDEX_ATTR] = String(props.at);
    if (Array.isArray(props.channels) && props.channels.length) {
      blockProps.style = { color: RGB_OPEN + props.channels.join(COMMA) + CLOSE };
    }
    return element(DIV_TAG, blockProps, text(props.line));
  }

  function Pane(props) {
    var pane = props.pane;
    var lines = listField(pane, BLOCKS);
    var style = sheetStyle(pane[STYLE_SHEET]);
    style.whiteSpace = wrapStyle(pane);
    style.overflow = OVERFLOW_AUTO;
    withStretch(style, props.stretch);

    var paneProps = { className: PANE_CLASS, style: style };
    paneProps[PART_ATTR] = props.part;
    paneProps[ARIA_LABEL] = text(props.label);
    paneProps[ARIA_READONLY] = text(pane[READ_ONLY]);
    paneProps[READ_ONLY_ATTR] = text(pane[READ_ONLY]);
    paneProps[WRAP_ATTR] = text(pane[WRAP]);
    paneProps[BLOCK_COLORS_ATTR] = String(listField(pane, BLOCK_COLORS).length);
    paneProps[CENTER_ON_SCROLL_ATTR] = text(pane[CENTER_ON_SCROLL]);
    paneProps[MAX_BLOCKS_ATTR] = text(pane[MAX_BLOCKS]);
    paneProps[DECLARED_BLOCKS_ATTR] = text(pane[BLOCK_COUNT]);
    paneProps[HELD_BLOCKS_ATTR] = String(lines.length);
    paneProps[IS_EMPTY_ATTR] = text(pane[IS_EMPTY]);
    paneProps[FONT_FAMILY_ATTR] = text(pane[FONT_FAMILY]);
    paneProps[FONT_SIZE_ATTR] = text(pane[FONT_SIZE_PX]);
    paneProps[FONT_POINT_SIZE_ATTR] = text(pane[FONT_POINT_SIZE]);
    paneProps[PADDING_ATTR] = text(pane[PADDING_PX]);

    return element(
      DIV_TAG,
      paneProps,
      lines.map(function (line, at) {
        return element(Block, {
          key: String(at),
          at: at,
          line: line,
          channels: listField(pane, BLOCK_COLORS)[at]
        });
      })
    );
  }

  function PaneButton(props) {
    var button = props.button;
    var style = withStretch(sheetStyle(button[STYLE_SHEET]), props.stretch);
    var buttonProps = { className: BAR_CLASS, style: style, type: BUTTON_TYPE };
    buttonProps[PART_ATTR] = props.part;
    buttonProps[SLOT_ATTR] = props.slot;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[CHECKABLE_ATTR] = text(button[CHECKABLE]);
    buttonProps[ARIA_PRESSED] = text(button[CHECKED]);
    buttonProps[CHECKED_BACKGROUND_ATTR] = text(button[CHECKED_BACKGROUND]);
    buttonProps[CHECKED_COLOR_ATTR] = text(button[CHECKED_COLOR]);
    buttonProps[CHECKED_BORDER_COLOR_ATTR] = text(button[CHECKED_BORDER_COLOR]);
    buttonProps[HOVER_BACKGROUND_ATTR] = text(button[HOVER_BACKGROUND]);
    buttonProps[FONT_FAMILY_ATTR] = text(button[FONT_FAMILY]);
    buttonProps[FONT_SIZE_ATTR] = text(button[FONT_SIZE_PX]);
    buttonProps[PADDING_ATTR] = text(button[PADDING_PX]);
    return element(BUTTON_TAG, buttonProps, text(button[TEXT]));
  }

  function PauseIndicator(props) {
    var indicator = props.indicator;
    var indicatorProps = {
      className: BAR_CLASS,
      style: sheetStyle(indicator[STYLE_SHEET])
    };
    indicatorProps[PART_ATTR] = PAUSE_INDICATOR_PART;
    indicatorProps[SLOT_ATTR] = PAUSE_INDICATOR;
    indicatorProps[FONT_FAMILY_ATTR] = text(indicator[FONT_FAMILY]);
    indicatorProps[FONT_SIZE_ATTR] = text(indicator[FONT_SIZE_PX]);
    indicatorProps[PADDING_ATTR] = text(indicator[PADDING_PX]);
    return element(SPAN_TAG, indicatorProps, text(indicator[TEXT]));
  }

  function barSlot(model, slot, at) {
    var bar = objectField(model, CONTROL_BAR);
    var stretch = stretchAt(bar, CHILD_STRETCH, at);
    if (slot === STRETCH) {
      var spacerProps = { key: String(at), style: { flex: FLEX_AUTO } };
      spacerProps[PART_ATTR] = STRETCH_PART;
      spacerProps[SLOT_ATTR] = STRETCH;
      return element(DIV_TAG, spacerProps, null);
    }
    if (slot === PAUSE_INDICATOR) {
      return element(PauseIndicator, {
        key: slot,
        indicator: objectField(model, PAUSE_INDICATOR)
      });
    }
    if (slot === PAUSE_BUTTON || slot === CLEAR_BUTTON) {
      var actions = objectField(model, ACTIONS);
      return element(PaneButton, {
        key: slot,
        slot: slot,
        part: slot === PAUSE_BUTTON ? PAUSE_BUTTON_PART : CLEAR_BUTTON_PART,
        action: slot === PAUSE_BUTTON ? actions[PAUSE_ACTION] : actions[CLEAR_ACTION],
        button: objectField(model, slot),
        stretch: stretch
      });
    }
    return null;
  }

  function ControlBar(props) {
    var model = props.model;
    var bar = objectField(model, CONTROL_BAR);
    var style = sheetStyle(bar[STYLE_SHEET]);
    var box = boxStyle(bar, ROW);
    Object.keys(box).forEach(function (name) {
      style[name] = box[name];
    });
    var order = listField(model, CONTROL_BAR_ORDER);
    withStretch(style, props.stretch);
    var barProps = { className: BAR_CLASS, style: style };
    barProps[PART_ATTR] = CONTROL_BAR_PART;
    barProps[DECLARED_CONTROLS_ATTR] = String(order.length);
    barProps[HELD_CONTROLS_ATTR] = String(drawnControls(model).length);
    return element(
      DIV_TAG,
      barProps,
      order.map(function (slot, at) {
        return barSlot(model, slot, at);
      })
    );
  }

  function signalHeaderNode(model, stretch, key) {
    var header = objectField(model, SIGNAL_HEADER);
    var headerProps = {
      key: key,
      style: withStretch(sheetStyle(header[STYLE_SHEET]), stretch)
    };
    headerProps[PART_ATTR] = SIGNAL_HEADER_PART;
    headerProps[FONT_FAMILY_ATTR] = text(header[FONT_FAMILY]);
    headerProps[FONT_SIZE_ATTR] = text(header[FONT_SIZE_PX]);
    headerProps[PADDING_ATTR] = text(header[PADDING_PX]);
    return element(DIV_TAG, headerProps, text(header[TEXT]));
  }

  function signalPaneNode(model, stretch, key) {
    return element(Pane, {
      key: key,
      pane: objectField(model, SIGNAL_PANE),
      part: SIGNAL_PANE_PART,
      label: objectField(model, SIGNAL_HEADER)[TEXT],
      stretch: stretch
    });
  }

  var SIGNAL_BOX_CHILDREN = [signalHeaderNode, signalPaneNode];

  function SignalBox(props) {
    var model = props.model;
    var box = objectField(model, SIGNAL_BOX);
    var boxProps = { style: withStretch(boxStyle(box, COLUMN), props.stretch) };
    boxProps[PART_ATTR] = SIGNAL_BOX_PART;
    boxProps[SLOT_ATTR] = SIGNAL_BOX;
    return element(
      DIV_TAG,
      boxProps,
      SIGNAL_BOX_CHILDREN.map(function (make, at) {
        return make(model, stretchAt(box, CHILD_STRETCH, at), String(at));
      })
    );
  }

  function splitterSlot(model, slot, at) {
    var stretch = stretchAt(objectField(model, SPLITTER), STRETCH, at);
    if (slot === LOG_PANE) {
      return element(Pane, {
        key: slot,
        pane: objectField(model, LOG_PANE),
        part: LOG_PANE_PART,
        label: model[TAB_TITLE],
        stretch: stretch
      });
    }
    if (slot === SIGNAL_BOX) {
      return element(SignalBox, { key: slot, model: model, stretch: stretch });
    }
    return null;
  }

  function Splitter(props) {
    var model = props.model;
    var splitter = objectField(model, SPLITTER);
    var children = listField(splitter, CHILDREN);
    var stacked = splitter[ORIENTATION] === VERTICAL ? COLUMN : ROW;
    var splitterProps = { style: withStretch(boxStyle({}, stacked), props.stretch) };
    splitterProps[PART_ATTR] = SPLITTER_PART;
    splitterProps[ORIENTATION_ATTR] = text(splitter[ORIENTATION]);
    splitterProps[DECLARED_PANES_ATTR] = String(children.length);
    splitterProps[HELD_PANES_ATTR] = String(drawnPanes(model).length);
    splitterProps.style.overflow = OVERFLOW_AUTO;
    return element(
      DIV_TAG,
      splitterProps,
      children.map(function (slot, at) {
        return splitterSlot(model, slot, at);
      })
    );
  }

  function Machinery(props) {
    var model = props.model;
    var timers = objectField(model, TIMERS);
    var ledger = objectField(model, LEDGER);
    var handler = objectField(model, LOG_HANDLER);

    var machineryProps = { hidden: true };
    machineryProps[PART_ATTR] = MACHINERY_PART;

    var handlerProps = {};
    handlerProps[PART_ATTR] = LOG_HANDLER_PART;
    handlerProps[FORMAT_ATTR] = text(handler[FORMAT]);
    handlerProps[DATEFMT_ATTR] = text(handler[DATEFMT]);
    handlerProps[HANDLER_LEVEL_ATTR] = text(handler[HANDLER_LEVEL]);

    return element(
      DIV_TAG,
      machineryProps,
      Object.keys(timers).map(function (name) {
        var timer = objectField(timers, name);
        var timerProps = { key: name };
        timerProps[PART_ATTR] = TIMER_PART;
        timerProps[TIMER_ATTR] = name;
        timerProps[INTERVAL_ATTR] = text(timer[INTERVAL_MS]);
        timerProps[RUNNING_ATTR] = text(timer[RUNNING]);
        return element(DIV_TAG, timerProps, null);
      }),
      Object.keys(ledger).map(function (name) {
        var counterProps = { key: name };
        counterProps[PART_ATTR] = COUNTER_PART;
        counterProps[COUNTER_ATTR] = name;
        counterProps[VALUE_ATTR] = text(ledger[name]);
        return element(DIV_TAG, counterProps, null);
      }),
      element(
        DIV_TAG,
        handlerProps,
        listField(handler, LOGGERS).map(function (name, at) {
          var loggerProps = { key: String(at) };
          loggerProps[PART_ATTR] = LOGGER_PART;
          loggerProps[INDEX_ATTR] = String(at);
          loggerProps[LOGGER_ATTR] = text(name);
          return element(DIV_TAG, loggerProps, null);
        })
      )
    );
  }

  var CONTAINER_CHILDREN = [ControlBar, Splitter];

  // `Tab` draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var container = objectField(model, CONTAINER);
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: boxStyle(container, COLUMN)
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[TAB_TITLE_ATTR] = text(model[TAB_TITLE]);
    tabProps[ARIA_LABEL] = text(model[TAB_TITLE]);
    return element(
      DIV_TAG,
      tabProps,
      CONTAINER_CHILDREN.map(function (Part, at) {
        return element(Part, {
          key: String(at),
          model: model,
          stretch: stretchAt(container, CHILD_STRETCH, at)
        });
      }),
      element(Machinery, { model: model })
    );
  }


  function drawnControls(model) {
    return listField(model, CONTROL_BAR_ORDER).filter(function (slot) {
      return slot === STRETCH || isPlainObject(model[slot]);
    });
  }

  function drawnPanes(model) {
    return listField(objectField(model, SPLITTER), CHILDREN).filter(function (slot) {
      return isPlainObject(model[slot]);
    });
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        consoleFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        consoleFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // Each element's own sheet writes the value its discrete field repeats.
  function checkSkin(model) {
    SKINNED_FIELDS.forEach(function (name) {
      var skinned = model[name];
      if (!isPlainObject(skinned)) {
        return;
      }
      SKIN_PAIRS.forEach(function (pair) {
        var written = declaredValue(skinned[STYLE_SHEET], pair.property);
        if (written === undefined) {
          return;
        }
        if (!owns(skinned, pair.field)) {
          consoleFaults.push(fault(name, pair.field, MISSING_FAULT, null));
          return;
        }
        var carried = skinned[pair.field];
        if (carried === null) {
          consoleFaults.push(fault(name, pair.field, NULL_FAULT, null));
          return;
        }
        if (kindOf(carried) !== kindOf(written)) {
          consoleFaults.push(
            fault(name, pair.field, WRONG_TYPE_FAULT, kindOf(carried))
          );
          return;
        }
        if (carried !== written) {
          consoleFaults.push(fault(name, pair.field, DISAGREES_FAULT, written));
        }
      });
    });
  }

  // Each pane publishes its buffer four ways, so each one holds the others.
  function checkPanes(model) {
    PANE_FIELDS.forEach(function (name) {
      var pane = model[name];
      if (!isPlainObject(pane)) {
        return;
      }
      if (!Array.isArray(pane[BLOCKS])) {
        consoleFaults.push(fault(name, BLOCKS, NOT_A_LIST_FAULT, kindOf(pane[BLOCKS])));
        return;
      }
      var lines = pane[BLOCKS];
      var joined = lines.join(NEWLINE);
      if (pane[TEXT] !== joined) {
        consoleFaults.push(fault(name, TEXT, DISAGREES_FAULT, joined));
      }
      if (lines.length && pane[BLOCK_COUNT] !== lines.length) {
        consoleFaults.push(fault(name, BLOCK_COUNT, DISAGREES_FAULT, lines.length));
      }
      if (pane[IS_EMPTY] !== !lines.length) {
        consoleFaults.push(fault(name, IS_EMPTY, DISAGREES_FAULT, !lines.length));
      }
      var cap = pane[MAX_BLOCKS];
      if (typeof cap === "number" && lines.length > cap) {
        consoleFaults.push(fault(name, BLOCKS, OVER_CAP_FAULT, lines.length));
      }
    });
  }

  function checkSlots(model) {
    var order = listField(model, CONTROL_BAR_ORDER);
    order.forEach(function (slot) {
      if (slot !== STRETCH && !isPlainObject(model[slot])) {
        consoleFaults.push(fault(CONTROL_BAR_ORDER, slot, MISSING_FAULT, null));
      }
    });
    var weights = listField(objectField(model, CONTROL_BAR), CHILD_STRETCH);
    if (weights.length < order.length) {
      consoleFaults.push(
        fault(CONTROL_BAR, CHILD_STRETCH, SHORT_LIST_FAULT, weights.length)
      );
    }
    var splitter = objectField(model, SPLITTER);
    var children = listField(splitter, CHILDREN);
    children.forEach(function (slot) {
      if (!isPlainObject(model[slot])) {
        consoleFaults.push(fault(CHILDREN, slot, MISSING_FAULT, null));
      }
    });
    var stretch = listField(splitter, STRETCH);
    if (stretch.length < children.length) {
      consoleFaults.push(fault(SPLITTER, STRETCH, SHORT_LIST_FAULT, stretch.length));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function paneBlocks(model, name) {
    return listField(objectField(model, name), BLOCKS).length;
  }

  // `declared` counts what the payload promises, `held` what it carries.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        controls: listField(model, CONTROL_BAR_ORDER).length,
        panes: listField(objectField(model, SPLITTER), CHILDREN).length,
        log_blocks: objectField(model, LOG_PANE)[BLOCK_COUNT],
        signal_blocks: objectField(model, SIGNAL_PANE)[BLOCK_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        controls: drawnControls(model).length,
        panes: drawnPanes(model).length,
        log_blocks: paneBlocks(model, LOG_PANE),
        signal_blocks: paneBlocks(model, SIGNAL_PANE)
      },
      faults: consoleFaults.slice()
    };
  }

  function setConsole(model) {
    if (!isPlainObject(model)) {
      held = null;
      consoleFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: consoleFaults.slice() };
    }
    held = { model: model };
    consoleFaults = [];
    checkFields(model);
    checkSkin(model);
    checkPanes(model);
    checkSlots(model);
    return report();
  }

  // One round trip per page, and a refused ask is not remembered.
  function loadConsole(params) {
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
        setConsole(model);
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

  function tabTitle() {
    return field(TAB_TITLE);
  }

  function container() {
    return bag(CONTAINER);
  }

  function controlBar() {
    return bag(CONTROL_BAR);
  }

  function controlBarOrder() {
    return list(CONTROL_BAR_ORDER);
  }

  function pauseButton() {
    return bag(PAUSE_BUTTON);
  }

  function pauseIndicator() {
    return bag(PAUSE_INDICATOR);
  }

  function clearButton() {
    return bag(CLEAR_BUTTON);
  }

  function signalBox() {
    return bag(SIGNAL_BOX);
  }

  function signalHeader() {
    return bag(SIGNAL_HEADER);
  }

  function splitter() {
    return bag(SPLITTER);
  }

  function timers() {
    return bag(TIMERS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function logHandler() {
    return bag(LOG_HANDLER);
  }

  function logPane() {
    return bag(LOG_PANE);
  }

  function signalPane() {
    return bag(SIGNAL_PANE);
  }

  function ledger() {
    return bag(LEDGER);
  }

  function timer(name) {
    var table = held === null ? {} : objectField(held.model, TIMERS);
    return owns(table, name) ? table[name] : undefined;
  }

  function action(name) {
    var table = held === null ? {} : objectField(held.model, ACTIONS);
    return owns(table, name) ? table[name] : undefined;
  }

  function counter(name) {
    var table = held === null ? {} : objectField(held.model, LEDGER);
    return owns(table, name) ? table[name] : undefined;
  }

  function logBlocks() {
    return held === null ? [] : listField(objectField(held.model, LOG_PANE), BLOCKS);
  }

  function signalBlocks() {
    return held === null ? [] : listField(objectField(held.model, SIGNAL_PANE), BLOCKS);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function skinPairs() {
    return SKIN_PAIRS.slice();
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
    return consoleFaults.slice();
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

  function renderTab(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: payload }));
  }

  function forget() {
    held = null;
    consoleFaults = [];
    loadFault = null;
    asked = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadConsole,
      loadError: loadError
    });
  }

  global.acervatorSetConsole = setConsole;
  global.acervatorLoadConsole = loadConsole;
  global.acervatorConsole = {
    method: METHOD,
    Tab: Tab,
    ControlBar: ControlBar,
    Splitter: Splitter,
    SignalBox: SignalBox,
    Pane: Pane,
    Block: Block,
    PaneButton: PaneButton,
    PauseIndicator: PauseIndicator,
    Machinery: Machinery,
    tabTitle: tabTitle,
    container: container,
    controlBar: controlBar,
    controlBarOrder: controlBarOrder,
    pauseButton: pauseButton,
    pauseIndicator: pauseIndicator,
    clearButton: clearButton,
    signalBox: signalBox,
    signalHeader: signalHeader,
    splitter: splitter,
    timers: timers,
    timer: timer,
    actions: actions,
    action: action,
    logHandler: logHandler,
    logPane: logPane,
    signalPane: signalPane,
    ledger: ledger,
    counter: counter,
    logBlocks: logBlocks,
    signalBlocks: signalBlocks,
    declaredFields: declaredFields,
    skinPairs: skinPairs,
    declarations: sheetDeclarations,
    stateRules: sheetStateRules,
    styleOf: sheetStyle,
    declaredValue: declaredValue,
    pixels: pixels,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
