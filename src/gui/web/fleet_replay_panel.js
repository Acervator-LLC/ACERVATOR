// The Simulator's Fleet Replay panel, drawn from what its Python surface publishes.
(function (global) {
  "use strict";

  var METHOD = "fleet_replay_panel.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var HOST_KIND = "gate_host_kind";
  var OUTER = "outer";
  var HEADER = "header";
  var BUTTONS = "buttons";
  var FULL_EVALUATION = "full_evaluation";
  var STATUS = "status";
  var FLEET_TABLE = "fleet_table";
  var PROGRESS = "progress";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS_RUNNING = "timers_running";
  var REFRESH_EVERY_N = "visual_refresh_every_n_candles";
  var BUS_TOPICS = "bus_topics";
  var SIGNALS = "signals";
  var SIGNALS_EMITTED = "signals_emitted";
  var ACTIONS = "actions";
  var CONNECTIONS_AT_BUILD = "connections_at_build";
  var COLUMNS_INDEX = "columns_index";
  var STAT_FIELD_NAMES = "stat_field_names";
  var STAT_FIELDS = "stat_fields";
  var LAMP_ROWS_DRAWN = "gate_rows_drawn";
  var CHART_SYMBOLS = "chart_symbols";
  var CHART_CLEARED = "chart_cleared";
  var VOTING_BOT_LIST = "voting_bot_list";
  var REFRESH_EVERY = "visual_refresh_every";
  var CHART_BARS = "chart_bars";
  var CHART_MARKERS = "chart_markers";
  var VOTING_ROWS = "voting_rows";
  var BOT_STATUSES = "bot_statuses";
  var CONFIGS = "configs";
  var YTD_TRADE_COUNT = "ytd_trade_count";
  var ACTIVITY_LINES = "activity_lines";
  var PERFORMANCE_LINES = "performance_lines";
  var TELEMETRY = "telemetry";
  var PINS = "pins";
  var PIN_NAMES = "pin_names";
  var PINS_WITH_DURATION = "pins_with_duration";
  var TEXTS = "texts";
  var FORMATS = "formats";
  var NUMBERS = "numbers";
  var KEYS = "keys";
  var DEFAULTS = "defaults";
  var SPENDABLE_CURRENCIES = "spendable_currencies";
  var TELEMETRY_NAMES = "telemetry_names";
  var SKIP_REASONS = "skip_reasons";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var STEPS = "steps";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME, ACTIONS, ACTIVITY_LINES, BOT_STATUSES, BUS_TOPICS, BUTTONS,
    CALLS, CALL_NAMES, CHART_BARS, CHART_CLEARED, CHART_MARKERS, CHART_SYMBOLS,
    COLUMNS_INDEX, CONFIGS, CONNECTIONS_AT_BUILD, DEFAULTS, FLEET_TABLE,
    FORMATS, FULL_EVALUATION, HEADER, HOST_KIND, KEYS, LAMP_ROWS_DRAWN, NUMBERS,
    OUTER, PERFORMANCE_LINES, PINS, PINS_WITH_DURATION, PIN_NAMES, PROGRESS,
    REFRESH_EVERY, REFRESH_EVERY_N, SIGNALS, SIGNALS_EMITTED, SKIP_REASONS,
    SPENDABLE_CURRENCIES, STATUS, STAT_FIELDS, STAT_FIELD_NAMES, STEPS,
    TELEMETRY, TELEMETRY_NAMES, TEXTS, TIMERS, TIMERS_RUNNING, TIMER_DELAYS_MS,
    VOTING_BOT_LIST, VOTING_ROWS, YTD_TRADE_COUNT
  ];

  var BAG_FIELDS = [
    ACTIONS, BUTTONS, COLUMNS_INDEX, DEFAULTS, FLEET_TABLE, FORMATS,
    FULL_EVALUATION, HEADER, KEYS, NUMBERS, OUTER, PROGRESS, SKIP_REASONS,
    STATUS, STAT_FIELDS, TELEMETRY, TELEMETRY_NAMES, TEXTS, TIMERS,
    TIMERS_RUNNING
  ];

  var LIST_FIELDS = [
    ACTIVITY_LINES, BOT_STATUSES, BUS_TOPICS, CALLS, CALL_NAMES, CHART_BARS,
    CHART_MARKERS, CHART_SYMBOLS, CONFIGS, PERFORMANCE_LINES, PINS,
    PINS_WITH_DURATION, PIN_NAMES, SIGNALS, SIGNALS_EMITTED,
    SPENDABLE_CURRENCIES, STAT_FIELD_NAMES, STEPS, TIMER_DELAYS_MS,
    VOTING_BOT_LIST, VOTING_ROWS
  ];

  var COUNT_FIELDS = [
    CHART_CLEARED, CONNECTIONS_AT_BUILD, LAMP_ROWS_DRAWN, REFRESH_EVERY,
    REFRESH_EVERY_N, YTD_TRADE_COUNT
  ];

  // REFRESH_EVERY is null until a replay starts, so a null there is not a fault.
  var NULLABLE = {};
  NULLABLE[REFRESH_EVERY] = true;

  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var ENABLED = "enabled";
  var CHECKED = "checked";
  var STYLE_SHEET = "style_sheet";
  var TITLE = "title";
  var TITLE_STYLE = "title_style";
  var SUBTITLE = "subtitle";
  var SUBTITLE_STYLE = "subtitle_style";
  var SUBTITLE_WORD_WRAP = "subtitle_word_wrap";
  var WORD_WRAP = "word_wrap";
  var MARGIN_PX = "margin_px";
  var SPACING_PX = "spacing_px";
  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var ALTERNATING = "alternating_row_colors";
  var EDIT_TRIGGERS = "edit_triggers";
  var RESIZE_MODE = "header_resize_mode";
  var STRETCH_LAST = "stretch_last_section";
  var TABLE_STRETCH = "table_stretch";
  var DRAIN = "drain";
  var SKIPS = "skips";
  var EXCEPTIONS = "exceptions";
  var SYMBOL = "symbol";
  var TARGET = "target";
  var TRADES = "trades";

  var LOAD = "load";
  var FETCH = "fetch";
  var RESET = "reset";
  var START = "start";
  var STOP = "stop";

  // The surface publishes the five buttons as a bag, so this module names their order.
  var LOAD_ROW_BUTTONS = [LOAD, FETCH, RESET];
  var RUN_ROW_BUTTONS = [START, STOP];

  var HEADER_FIELDS = [
    STYLE_SHEET, SUBTITLE, SUBTITLE_STYLE, SUBTITLE_WORD_WRAP, TITLE, TITLE_STYLE
  ];
  var BUTTON_FIELDS = [TEXT, TOOLTIP];
  var SWITCH_FIELDS = [CHECKED, TEXT, TOOLTIP];
  var LABEL_FIELDS = [STYLE_SHEET, TEXT];
  var OUTER_FIELDS = [MARGIN_PX, SPACING_PX];
  var TIMER_NAMES = [DRAIN, PROGRESS];
  var TELEMETRY_FIELDS = [CALLS, EXCEPTIONS, SKIPS];
  var TABLE_FIELDS = [
    ALTERNATING, COLUMNS, COLUMN_COUNT, EDIT_TRIGGERS, RESIZE_MODE, ROWS,
    ROW_COUNT, STRETCH_LAST, TABLE_STRETCH, TITLE, TOOLTIP
  ];
  var COLUMN_KEYS = [SYMBOL, TARGET, TRADES];

  var LOAD_ACTION = "load_button.clicked";
  var FETCH_ACTION = "fetch_button.clicked";
  var RESET_ACTION = "reset_button.clicked";
  var START_ACTION = "start_button.clicked";
  var STOP_ACTION = "stop_button.clicked";
  var PROGRESS_TICK = "progress_timer.timeout";
  var DRAIN_TICK = "drain_timer.timeout";

  var BUTTON_ACTION = {};
  BUTTON_ACTION[LOAD] = LOAD_ACTION;
  BUTTON_ACTION[FETCH] = FETCH_ACTION;
  BUTTON_ACTION[RESET] = RESET_ACTION;
  BUTTON_ACTION[START] = START_ACTION;
  BUTTON_ACTION[STOP] = STOP_ACTION;

  var TIMER_ACTION = {};
  TIMER_ACTION[PROGRESS] = PROGRESS_TICK;
  TIMER_ACTION[DRAIN] = DRAIN_TICK;

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var ORDER_FAULT = "order-mismatch";
  var COUNT_FAULT = "count-mismatch";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var NOT_PLAIN_FAULT = "not-plain-data";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var GAP = " ";
  var HASH = "#";
  var COLON = ":";
  var SEMICOLON = ";";
  var COMMA = ",";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var RGB = "rgb";
  var RGBA_OPEN = "rgba(";
  var HEX_ARGB = "AARRGGBB";
  var MARKUP_OPEN = "<";
  var PX = "px";
  var PATH_SPLIT = ".";
  var ROW_AT = "row:";
  var BUTTON_AT = "button:";

  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var GRID = "grid";
  var FLEX_NONE = "none";
  var FLEX_AUTO = "auto";
  var HIDDEN = "hidden";
  var NO_WRAP = "nowrap";
  var WRAPPED = "normal";
  var NO_SELECT = "none";
  var MAX_CONTENT = "max-content";
  var CENTRED = "center";

  var PANEL_PART = "fleet-replay";
  var HEADER_PART = "header";
  var TITLE_PART = "title";
  var SUBTITLE_PART = "subtitle";
  var LOAD_ROW_PART = "load-row";
  var RUN_ROW_PART = "run-row";
  var BUTTON_PART = "button";
  var SWITCH_PART = "switch";
  var SPACER_PART = "spacer";
  var STATUS_PART = "status";
  var GROUP_PART = "fleet-group";
  var GROUP_TITLE_PART = "group-title";
  var TABLE_PART = "fleet-table";
  var HEAD_ROW_PART = "head-row";
  var HEAD_CELL_PART = "head-cell";
  var BODY_PART = "body";
  var BODY_ROW_PART = "body-row";
  var BODY_CELL_PART = "body-cell";
  var PROGRESS_PART = "progress";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NTH_ATTR = "data-nth";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var ACTION_ATTR = "data-action";
  var CHECKED_ATTR = "data-checked";
  var ENABLED_ATTR = "data-enabled";
  var HOST_KIND_ATTR = "data-host-kind";
  var ALTERNATING_ATTR = "data-alternating";
  var EDIT_TRIGGERS_ATTR = "data-edit-triggers";
  var RESIZE_MODE_ATTR = "data-resize-mode";
  var DECLARED_ROWS_ATTR = "data-declared-rows";
  var HELD_ROWS_ATTR = "data-held-rows";
  var TIMER_ATTR = "data-timers";
  var ARIA_LABEL = "aria-label";

  var STEPS_PARAM = "steps";
  var ACTION_PARAM = "action";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var CHANNELS = RGB.length;

  // Qt hands an alpha byte, so ALPHA_SCALE is the ceiling one CSS fraction needs.
  var ALPHA_CEILING = "0xff";
  var ALPHA_SCALE = Number(ALPHA_CEILING);
  var ALPHA_FRACTION = Math.pow(ALPHA_SCALE, -ONE);

  var held = null;
  var panelFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
  var wanted = null;
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

  function note(where, field, kind, detail) {
    panelFaults.push(fault(where, field, kind, detail));
  }

  // text answers undefined so an attribute stays off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    return typeof value === STRING_KIND && value.length ? value : undefined;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function sheetApi() {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return undefined;
    }
    return api;
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.stateRules(sheet);
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // rgbaFields returns one rgba value's channels, its alpha last.
  function rgbaFields(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return [];
    }
    return String(parts.shift()).split(CLOSE).shift().split(COMMA);
  }

  function byteAlpha(value) {
    var fields = rgbaFields(value);
    if (fields.length <= CHANNELS) {
      return false;
    }
    var alpha = String(fields[CHANNELS]).trim();
    return alpha.length > ZERO && !carries(alpha, DOT) && !carries(alpha, PERCENT);
  }

  // qtColour names why CSS would read one value as a different colour.
  function qtColour(value) {
    return hexWord(value).length === HEX_ARGB.length ? HEX_ARGB : undefined;
  }

  // scaledAlpha rewrites one rgba value's alpha byte as the fraction CSS reads.
  function scaledAlpha(value) {
    var fields = rgbaFields(value);
    var alpha = Number(String(fields[CHANNELS]).trim()) * ALPHA_FRACTION;
    var head = fields.slice(ZERO, CHANNELS).map(function (one) {
      return String(one).trim();
    });
    return RGBA_OPEN + head.concat([String(alpha)]).join(COMMA) + CLOSE;
  }

  function usableValue(value) {
    return byteAlpha(value) ? scaledAlpha(value) : value;
  }

  // keptSheet drops each declaration CSS would read as a different colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) === undefined) {
        kept.push(one.property + COLON + usableValue(one.value));
      }
    });
    return kept.join(SEMICOLON);
  }

  // Colours paint plainly here: one token group carries them all, so no rule
  // tells the names apart.
  function styleOf(sheet) {
    var api = sheetApi();
    var style = {};
    if (api === undefined) {
      return style;
    }
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        return;
      }
      var value = String(usableValue(one.value));
      var names = Object.keys(api.styleOf(String(one.property) + COLON + GAP + value));
      if (!names.length) {
        return;
      }
      style[names[ZERO]] = value;
    });
    return style;
  }

  function pixels(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  function boxStyle(way, margin, spacing) {
    var style = { display: FLEX, flexDirection: way };
    if (margin !== undefined) {
      style.padding = pixels(margin);
    }
    if (spacing !== undefined) {
      style.gap = pixels(spacing);
    }
    return style;
  }

  // labelStyle refuses a drag over the text and wraps only when told.
  function labelStyle(sheet, wraps) {
    var style = styleOf(sheet);
    style.whiteSpace = wraps === true ? WRAPPED : NO_WRAP;
    style.overflow = HIDDEN;
    style.userSelect = NO_SELECT;
    style.flex = FLEX_NONE;
    return style;
  }

  function dispatch(action, params) {
    dispatched.push({ action: action, params: copyOf(params) });
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    var sent = copyOf(params);
    sent[ACTION_PARAM] = action;
    return global.acervator.call(METHOD, sent);
  }

  // stepFor answers the step name the surface maps one action onto.
  function stepFor(model, action) {
    var found = objectField(model, ACTIONS);
    return owns(found, action) ? found[action] : undefined;
  }

  function askedFullEvaluation(model) {
    if (wanted !== null) {
      return wanted;
    }
    return objectField(model, FULL_EVALUATION)[CHECKED] === true;
  }

  function take(model, action) {
    var step = stepFor(model, action);
    var params = {};
    params[STEPS_PARAM] = step === undefined ? [] : [step];
    params[FULL_EVALUATION] = askedFullEvaluation(model);
    return dispatch(action, params);
  }

  function Spacer(props) {
    var spacerProps = { style: { flex: FLEX_AUTO } };
    spacerProps[PART_ATTR] = SPACER_PART;
    spacerProps[KEY_ATTR] = props.slot;
    return element(DIV_TAG, spacerProps, null);
  }

  function Caption(props) {
    var captionProps = { style: labelStyle(props.sheet, props.wraps) };
    captionProps[PART_ATTR] = props.part;
    captionProps[TITLE] = label(props.tooltip);
    return element(SPAN_TAG, captionProps, text(props.text));
  }

  function Button(props) {
    var one = props.button;
    var live = one[ENABLED] !== false;
    var buttonProps = {
      style: { flex: FLEX_NONE, whiteSpace: NO_WRAP },
      disabled: !live,
      type: BUTTON_TAG
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[KEY_ATTR] = props.name;
    buttonProps[ACTION_ATTR] = props.action;
    buttonProps[ENABLED_ATTR] = text(live);
    buttonProps[TITLE] = label(one[TOOLTIP]);
    buttonProps.onClick = function () {
      take(props.model, props.action);
    };
    return element(BUTTON_TAG, buttonProps, text(one[TEXT]));
  }

  function Switch(props) {
    var one = objectField(props.model, FULL_EVALUATION);
    var on = askedFullEvaluation(props.model);
    var switchProps = {
      style: { flex: FLEX_NONE, whiteSpace: NO_WRAP, userSelect: NO_SELECT },
      type: BUTTON_TAG
    };
    switchProps[PART_ATTR] = SWITCH_PART;
    switchProps[CHECKED_ATTR] = text(on);
    switchProps[TITLE] = label(one[TOOLTIP]);
    switchProps.onClick = function () {
      wanted = !on;
      props.onPick(wanted);
    };
    return element(BUTTON_TAG, switchProps, text(one[TEXT]));
  }

  function buttonNodes(model, names) {
    var bag = objectField(model, BUTTONS);
    var drawn = [];
    names.forEach(function (name) {
      if (!isPlainObject(bag[name])) {
        return;
      }
      drawn.push(
        element(Button, {
          key: name,
          name: name,
          button: bag[name],
          action: BUTTON_ACTION[name],
          model: model
        })
      );
    });
    return drawn;
  }

  function LoadRow(props) {
    var model = props.model;
    var status = objectField(model, STATUS);
    var rowProps = { style: boxStyle(ROW, undefined, undefined) };
    rowProps.style.flex = FLEX_NONE;
    rowProps.style.alignItems = CENTRED;
    rowProps[PART_ATTR] = LOAD_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      buttonNodes(model, LOAD_ROW_BUTTONS),
      element(Switch, { key: SWITCH_PART, model: model, onPick: props.onPick }),
      element(Spacer, { key: SPACER_PART, slot: LOAD_ROW_PART }),
      element(Caption, {
        key: STATUS_PART,
        part: STATUS_PART,
        sheet: status[STYLE_SHEET],
        text: status[TEXT]
      })
    );
  }

  function RunRow(props) {
    var rowProps = { style: boxStyle(ROW, undefined, undefined) };
    rowProps.style.flex = FLEX_NONE;
    rowProps.style.alignItems = CENTRED;
    rowProps[PART_ATTR] = RUN_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(Spacer, { key: SPACER_PART, slot: RUN_ROW_PART }),
      buttonNodes(props.model, RUN_ROW_BUTTONS)
    );
  }

  function HeaderBox(props) {
    var one = objectField(props.model, HEADER);
    var headerProps = { style: styleOf(one[STYLE_SHEET]) };
    headerProps.style.display = FLEX;
    headerProps.style.flexDirection = COLUMN;
    headerProps.style.flex = FLEX_NONE;
    headerProps[PART_ATTR] = HEADER_PART;
    return element(
      DIV_TAG,
      headerProps,
      element(Caption, {
        key: TITLE_PART,
        part: TITLE_PART,
        sheet: one[TITLE_STYLE],
        text: one[TITLE]
      }),
      element(Caption, {
        key: SUBTITLE_PART,
        part: SUBTITLE_PART,
        sheet: one[SUBTITLE_STYLE],
        wraps: one[SUBTITLE_WORD_WRAP],
        text: one[SUBTITLE]
      })
    );
  }

  // rowNames pairs each row's symbol with how many earlier rows carry it.
  function rowNames(model) {
    var seen = {};
    return listField(objectField(model, FLEET_TABLE), ROWS).map(function (row) {
      var name = String(Array.isArray(row) ? row[ZERO] : kindOf(row));
      var nth = owns(seen, name) ? seen[name] + ONE : ZERO;
      seen[name] = nth;
      return [name, nth];
    });
  }

  function columnNames(model) {
    return listField(objectField(model, FLEET_TABLE), COLUMNS).map(function (one) {
      return String(one);
    });
  }

  function HeadCell(props) {
    var cellProps = { style: { whiteSpace: NO_WRAP, userSelect: NO_SELECT } };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    cellProps[KEY_ATTR] = props.name;
    cellProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, cellProps, text(props.name));
  }

  function BodyCell(props) {
    var cellProps = { style: { whiteSpace: NO_WRAP, overflow: HIDDEN } };
    cellProps[PART_ATTR] = BODY_CELL_PART;
    cellProps[KEY_ATTR] = props.name;
    cellProps[NTH_ATTR] = text(props.nth);
    cellProps[COLUMN_ATTR] = props.column;
    return element(DIV_TAG, cellProps, text(props.value));
  }

  function BodyRow(props) {
    var rowProps = { style: { display: GRID, gridTemplateColumns: props.template } };
    rowProps[PART_ATTR] = BODY_ROW_PART;
    rowProps[KEY_ATTR] = props.name;
    rowProps[NTH_ATTR] = text(props.nth);
    rowProps[INDEX_ATTR] = text(props.at);
    return element(
      DIV_TAG,
      rowProps,
      props.columns.map(function (column, at) {
        return element(BodyCell, {
          key: column,
          name: props.name,
          nth: props.nth,
          column: column,
          value: Array.isArray(props.row) ? props.row[at] : undefined
        });
      })
    );
  }

  // columnTemplate sizes each column to its widest cell, the last one able to stretch.
  function columnTemplate(table, columns) {
    var widths = columns.map(function () {
      return MAX_CONTENT;
    });
    if (table[STRETCH_LAST] === true && widths.length) {
      widths[widths.length - ONE] = FLEX_AUTO;
    }
    return widths.join(GAP);
  }

  function FleetTable(props) {
    var model = props.model;
    var table = objectField(model, FLEET_TABLE);
    var columns = columnNames(model);
    var template = columnTemplate(table, columns);
    var names = rowNames(model);
    var rows = listField(table, ROWS);
    var tableProps = {
      style: { display: FLEX, flexDirection: COLUMN, overflow: FLEX_AUTO }
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[TITLE] = label(table[TOOLTIP]);
    tableProps[ALTERNATING_ATTR] = text(table[ALTERNATING]);
    tableProps[EDIT_TRIGGERS_ATTR] = text(table[EDIT_TRIGGERS]);
    tableProps[RESIZE_MODE_ATTR] = text(table[RESIZE_MODE]);
    tableProps[DECLARED_ROWS_ATTR] = text(table[ROW_COUNT]);
    tableProps[HELD_ROWS_ATTR] = text(rows.length);
    var headProps = { style: { display: GRID, gridTemplateColumns: template } };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    var bodyProps = { style: { display: FLEX, flexDirection: COLUMN } };
    bodyProps[PART_ATTR] = BODY_PART;
    return element(
      DIV_TAG,
      tableProps,
      element(
        DIV_TAG,
        headProps,
        columns.map(function (name, at) {
          return element(HeadCell, { key: name, name: name, at: at });
        })
      ),
      element(
        DIV_TAG,
        bodyProps,
        rows.map(function (row, at) {
          return element(BodyRow, {
            key: String(at),
            at: at,
            name: names[at][ZERO],
            nth: names[at][ONE],
            row: row,
            columns: columns,
            template: template
          });
        })
      )
    );
  }

  function FleetGroup(props) {
    var table = objectField(props.model, FLEET_TABLE);
    var groupProps = { style: { display: FLEX, flexDirection: COLUMN } };
    groupProps.style.flexGrow = table[TABLE_STRETCH];
    groupProps.style.flexBasis = ZERO;
    groupProps.style.overflow = HIDDEN;
    groupProps[PART_ATTR] = GROUP_PART;
    return element(
      DIV_TAG,
      groupProps,
      element(Caption, {
        key: GROUP_TITLE_PART,
        part: GROUP_TITLE_PART,
        sheet: undefined,
        text: table[TITLE]
      }),
      element(FleetTable, { key: TABLE_PART, model: props.model })
    );
  }

  function Panel(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var outer = objectField(model, OUTER);
    var progress = objectField(model, PROGRESS);
    var running = objectField(model, TIMERS_RUNNING);
    var panelProps = { style: boxStyle(COLUMN, outer[MARGIN_PX], outer[SPACING_PX]) };
    panelProps.style.flex = FLEX_AUTO;
    panelProps.style.overflow = HIDDEN;
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[ARIA_LABEL] = text(model[ACCESSIBLE_NAME]);
    panelProps[HOST_KIND_ATTR] = text(model[HOST_KIND]);
    panelProps[TIMER_ATTR] = TIMER_NAMES.filter(function (name) {
      return running[name] === true;
    }).join(COMMA);
    return element(
      DIV_TAG,
      panelProps,
      element(HeaderBox, { key: HEADER_PART, model: model }),
      element(LoadRow, { key: LOAD_ROW_PART, model: model, onPick: props.onPick }),
      element(FleetGroup, { key: GROUP_PART, model: model }),
      element(Caption, {
        key: PROGRESS_PART,
        part: PROGRESS_PART,
        sheet: progress[STYLE_SHEET],
        wraps: progress[WORD_WRAP],
        text: progress[TEXT]
      }),
      element(RunRow, { key: RUN_ROW_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        note(null, field, MISSING_FAULT, null);
        return;
      }
      if (model[field] === null && !owns(NULLABLE, field)) {
        note(null, field, NULL_FAULT, null);
      }
    });
    BAG_FIELDS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        note(null, field, NOT_AN_OBJECT_FAULT, kindOf(model[field]));
      }
    });
    LIST_FIELDS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        note(null, field, NOT_A_LIST_FAULT, kindOf(model[field]));
      }
    });
    COUNT_FIELDS.forEach(function (field) {
      if (!owns(model, field) || (model[field] === null && owns(NULLABLE, field))) {
        return;
      }
      if (typeof model[field] !== NUMBER_KIND) {
        note(null, field, WRONG_TYPE_FAULT, kindOf(model[field]));
      }
    });
  }

  function checkShape(where, bag, names, kinds) {
    if (!isPlainObject(bag)) {
      note(where, null, NOT_AN_OBJECT_FAULT, kindOf(bag));
      return;
    }
    names.forEach(function (name) {
      if (!owns(bag, name)) {
        note(where, name, MISSING_FAULT, null);
        return;
      }
      if (bag[name] === null) {
        note(where, name, NULL_FAULT, null);
        return;
      }
      if (owns(kinds, name) && typeof bag[name] !== kinds[name]) {
        note(where, name, WRONG_TYPE_FAULT, kindOf(bag[name]));
      }
    });
  }

  var FIELD_KINDS = {};
  FIELD_KINDS[TEXT] = STRING_KIND;
  FIELD_KINDS[TOOLTIP] = STRING_KIND;
  FIELD_KINDS[TITLE] = STRING_KIND;
  FIELD_KINDS[SUBTITLE] = STRING_KIND;
  FIELD_KINDS[STYLE_SHEET] = STRING_KIND;
  FIELD_KINDS[TITLE_STYLE] = STRING_KIND;
  FIELD_KINDS[SUBTITLE_STYLE] = STRING_KIND;
  FIELD_KINDS[SUBTITLE_WORD_WRAP] = BOOLEAN_KIND;
  FIELD_KINDS[CHECKED] = BOOLEAN_KIND;
  FIELD_KINDS[MARGIN_PX] = NUMBER_KIND;
  FIELD_KINDS[SPACING_PX] = NUMBER_KIND;
  FIELD_KINDS[COLUMN_COUNT] = NUMBER_KIND;
  FIELD_KINDS[ROW_COUNT] = NUMBER_KIND;
  FIELD_KINDS[TABLE_STRETCH] = NUMBER_KIND;
  FIELD_KINDS[ALTERNATING] = BOOLEAN_KIND;
  FIELD_KINDS[STRETCH_LAST] = BOOLEAN_KIND;
  FIELD_KINDS[EDIT_TRIGGERS] = STRING_KIND;
  FIELD_KINDS[RESIZE_MODE] = STRING_KIND;

  function checkParts(model) {
    checkShape(OUTER, objectField(model, OUTER), OUTER_FIELDS, FIELD_KINDS);
    checkShape(HEADER, objectField(model, HEADER), HEADER_FIELDS, FIELD_KINDS);
    checkShape(STATUS, objectField(model, STATUS), LABEL_FIELDS, FIELD_KINDS);
    checkShape(PROGRESS, objectField(model, PROGRESS), LABEL_FIELDS, FIELD_KINDS);
    checkShape(
      FULL_EVALUATION,
      objectField(model, FULL_EVALUATION),
      SWITCH_FIELDS,
      FIELD_KINDS
    );
    checkShape(FLEET_TABLE, objectField(model, FLEET_TABLE), TABLE_FIELDS, FIELD_KINDS);
    checkShape(TIMERS, objectField(model, TIMERS), TIMER_NAMES, {});
    checkShape(TIMERS_RUNNING, objectField(model, TIMERS_RUNNING), TIMER_NAMES, {});
    checkShape(TELEMETRY, objectField(model, TELEMETRY), TELEMETRY_FIELDS, {});
    checkShape(COLUMNS_INDEX, objectField(model, COLUMNS_INDEX), COLUMN_KEYS, {});
    var bag = objectField(model, BUTTONS);
    LOAD_ROW_BUTTONS.concat(RUN_ROW_BUTTONS).forEach(function (name) {
      checkShape(BUTTON_AT + name, bag[name], BUTTON_FIELDS, FIELD_KINDS);
    });
  }

  function checkTable(model) {
    var table = objectField(model, FLEET_TABLE);
    var columns = listField(table, COLUMNS);
    var rows = listField(table, ROWS);
    if (table[COLUMN_COUNT] !== columns.length) {
      note(FLEET_TABLE, COLUMNS, COUNT_FAULT, columns.length);
    }
    if (table[ROW_COUNT] !== rows.length) {
      note(FLEET_TABLE, ROWS, COUNT_FAULT, rows.length);
    }
    rows.forEach(function (row, at) {
      var where = ROW_AT + String(at);
      if (!Array.isArray(row)) {
        note(where, ROWS, NOT_A_LIST_FAULT, kindOf(row));
        return;
      }
      if (row.length !== columns.length) {
        note(where, ROWS, COUNT_FAULT, row.length);
      }
      row.forEach(function (cell, column) {
        if (cell !== null && typeof cell !== STRING_KIND) {
          note(
            where + PATH_SPLIT + String(column),
            ROWS,
            WRONG_TYPE_FAULT,
            kindOf(cell)
          );
        }
      });
    });
  }

  function checkOrder(model) {
    var names = listField(model, STAT_FIELD_NAMES);
    var carried = Object.keys(objectField(model, STAT_FIELDS));
    if (carried.length && carried.length !== names.length) {
      note(null, STAT_FIELDS, ORDER_FAULT, carried.length);
    } else {
      carried.forEach(function (name, at) {
        if (names[at] !== name) {
          note(STAT_FIELDS + PATH_SPLIT + String(at), STAT_FIELDS, ORDER_FAULT, name);
        }
      });
    }
    var delays = listField(model, TIMER_DELAYS_MS);
    var timers = objectField(model, TIMERS);
    if (delays.length !== TIMER_NAMES.length) {
      note(null, TIMER_DELAYS_MS, COUNT_FAULT, delays.length);
      return;
    }
    TIMER_NAMES.forEach(function (name) {
      if (delays.indexOf(timers[name]) < ZERO) {
        note(name, TIMER_DELAYS_MS, ORDER_FAULT, delays.join(COMMA));
      }
    });
  }

  function checkNames(model) {
    var known = listField(model, CALL_NAMES);
    listField(model, CALLS).forEach(function (call, at) {
      var where = CALLS + PATH_SPLIT + String(at);
      if (!Array.isArray(call)) {
        note(where, CALLS, NOT_A_LIST_FAULT, kindOf(call));
        return;
      }
      if (known.indexOf(call[ZERO]) < ZERO) {
        note(where, CALLS, UNKNOWN_NAME_FAULT, kindOf(call[ZERO]));
      }
    });
    var pinned = listField(model, PIN_NAMES);
    listField(model, PINS).forEach(function (pin, at) {
      var where = PINS + PATH_SPLIT + String(at);
      if (!Array.isArray(pin)) {
        note(where, PINS, NOT_A_LIST_FAULT, kindOf(pin));
        return;
      }
      if (pinned.indexOf(pin[ZERO]) < ZERO) {
        note(where, PINS, UNKNOWN_NAME_FAULT, kindOf(pin[ZERO]));
      }
    });
    var found = objectField(model, ACTIONS);
    LOAD_ROW_BUTTONS.concat(RUN_ROW_BUTTONS).forEach(function (name) {
      if (!owns(found, BUTTON_ACTION[name])) {
        note(BUTTON_AT + name, ACTIONS, MISSING_FAULT, BUTTON_ACTION[name]);
      }
    });
    TIMER_NAMES.forEach(function (name) {
      if (!owns(found, TIMER_ACTION[name])) {
        note(name, ACTIONS, MISSING_FAULT, TIMER_ACTION[name]);
      }
    });
  }

  function paints(property, value) {
    var api = sheetApi();
    if (api === undefined) {
      return false;
    }
    var alone = String(property) + COLON + GAP + String(value);
    return Boolean(Object.keys(api.styleOf(alone)).length);
  }

  function checkSheet(where, sheet) {
    declarations(sheet).forEach(function (one) {
      var why = qtColour(one.value);
      if (why !== undefined) {
        note(where, STYLE_SHEET, QT_COLOUR_FAULT, why);
        return;
      }
      if (!paints(one.property, usableValue(one.value))) {
        note(where, STYLE_SHEET, NOT_CSS_FAULT, one.property);
      }
    });
  }

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      note(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null);
      return;
    }
    var one = objectField(model, HEADER);
    checkSheet(HEADER, one[STYLE_SHEET]);
    checkSheet(TITLE_PART, one[TITLE_STYLE]);
    checkSheet(SUBTITLE_PART, one[SUBTITLE_STYLE]);
    checkSheet(STATUS, objectField(model, STATUS)[STYLE_SHEET]);
    checkSheet(PROGRESS, objectField(model, PROGRESS)[STYLE_SHEET]);
  }

  // drawnText answers each drawn string beside the name of its element.
  function drawnText(model) {
    var found = [];
    var one = objectField(model, HEADER);
    found.push([TITLE_PART, one[TITLE]]);
    found.push([SUBTITLE_PART, one[SUBTITLE]]);
    found.push([STATUS_PART, objectField(model, STATUS)[TEXT]]);
    found.push([PROGRESS_PART, objectField(model, PROGRESS)[TEXT]]);
    var table = objectField(model, FLEET_TABLE);
    found.push([GROUP_TITLE_PART, table[TITLE]]);
    listField(table, COLUMNS).forEach(function (name, at) {
      found.push([HEAD_CELL_PART + PATH_SPLIT + String(at), name]);
    });
    listField(table, ROWS).forEach(function (row, at) {
      if (!Array.isArray(row)) {
        return;
      }
      row.forEach(function (cell, column) {
        found.push([
          BODY_CELL_PART + PATH_SPLIT + String(at) + PATH_SPLIT + String(column),
          cell
        ]);
      });
    });
    var bag = objectField(model, BUTTONS);
    LOAD_ROW_BUTTONS.concat(RUN_ROW_BUTTONS).forEach(function (name) {
      found.push([BUTTON_AT + name, objectField(bag, name)[TEXT]]);
    });
    found.push([SWITCH_PART, objectField(model, FULL_EVALUATION)[TEXT]]);
    return found;
  }

  // checkMarkup names a tag a Qt label would read as formatting.
  function checkMarkup(model) {
    drawnText(model).forEach(function (pair) {
      var body = pair[ONE];
      if (typeof body === STRING_KIND && carries(body, MARKUP_OPEN)) {
        note(pair[ZERO], TEXT, MARKUP_FAULT, MARKUP_OPEN);
      }
    });
  }

  // checkPlainData names a value the bridge could not carry back.
  function checkPlainData(model) {
    function descend(path, value) {
      if (value === null) {
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          descend(path + PATH_SPLIT + String(at), one);
        });
        return;
      }
      if (isPlainObject(value)) {
        Object.keys(value).forEach(function (name) {
          descend(path ? path + PATH_SPLIT + name : name, value[name]);
        });
        return;
      }
      var kind = typeof value;
      if (kind !== STRING_KIND && kind !== NUMBER_KIND && kind !== BOOLEAN_KIND) {
        note(path, null, NOT_PLAIN_FAULT, kind);
        return;
      }
      if (kind === NUMBER_KIND && !isFinite(value)) {
        note(path, null, NOT_PLAIN_FAULT, String(value));
      }
    }
    descend(EMPTY, model);
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report() {
    var model = held.model;
    var table = objectField(model, FLEET_TABLE);
    var bag = objectField(model, BUTTONS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: table[ROW_COUNT],
        columns: table[COLUMN_COUNT],
        buttons: LOAD_ROW_BUTTONS.length + RUN_ROW_BUTTONS.length
      },
      held: {
        fields: heldFieldCount(model),
        rows: listField(table, ROWS).length,
        columns: listField(table, COLUMNS).length,
        buttons: LOAD_ROW_BUTTONS.concat(RUN_ROW_BUTTONS).filter(function (name) {
          return isPlainObject(bag[name]);
        }).length
      },
      faults: panelFaults.slice()
    };
  }

  function setPanel(model) {
    wanted = null;
    if (!isPlainObject(model)) {
      held = null;
      panelFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: panelFaults.slice() };
    }
    held = { model: model };
    panelFaults = [];
    checkFields(model);
    checkParts(model);
    checkTable(model);
    checkOrder(model);
    checkNames(model);
    checkSheets(model);
    checkMarkup(model);
    checkPlainData(model);
    return report();
  }

  function loadPanel(params) {
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
        setPanel(model);
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

  function buttons() {
    return bag(BUTTONS);
  }

  function buttonOrder() {
    return LOAD_ROW_BUTTONS.concat(RUN_ROW_BUTTONS);
  }

  function fleetTable() {
    return bag(FLEET_TABLE);
  }

  function tableRows() {
    return held === null ? [] : listField(objectField(held.model, FLEET_TABLE), ROWS);
  }

  function rowOrder() {
    return held === null ? [] : rowNames(held.model);
  }

  function columnOrder() {
    return held === null ? [] : columnNames(held.model);
  }

  // rowsNamed answers every row one symbol names, each with its ordinal.
  function rowsNamed(name) {
    var rows = tableRows();
    var found = [];
    rowOrder().forEach(function (pair, at) {
      if (pair[ZERO] === name) {
        found.push([pair[ONE], rows[at]]);
      }
    });
    return found;
  }

  function collidingNames() {
    var seen = {};
    var found = [];
    rowOrder().forEach(function (pair) {
      var name = pair[ZERO];
      if (owns(seen, name)) {
        if (found.indexOf(name) < ZERO) {
          found.push(name);
        }
        return;
      }
      seen[name] = true;
    });
    return found;
  }

  function labels() {
    return held === null ? [] : drawnText(held.model);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function actionNames() {
    return buttonOrder()
      .map(function (name) {
        return BUTTON_ACTION[name];
      })
      .concat(
        TIMER_NAMES.map(function (name) {
          return TIMER_ACTION[name];
        })
      );
  }

  // tick hands one timer's action to the bridge, because no clock runs here.
  function tick(name) {
    if (held === null || !owns(TIMER_ACTION, name)) {
      return null;
    }
    return take(held.model, TIMER_ACTION[name]);
  }

  function press(name) {
    if (held === null || !owns(BUTTON_ACTION, name)) {
      return null;
    }
    return take(held.model, BUTTON_ACTION[name]);
  }

  function fullEvaluation() {
    return held === null ? undefined : askedFullEvaluation(held.model);
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

  function callNames() {
    return list(CALL_NAMES);
  }

  function calls() {
    return list(CALLS);
  }

  function pins() {
    return list(PINS);
  }

  function statFieldNames() {
    return list(STAT_FIELD_NAMES);
  }

  function statFields() {
    return bag(STAT_FIELDS);
  }

  function method() {
    return METHOD;
  }

  function alphaScale() {
    return ALPHA_SCALE;
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function declaredNames() {
    return DECLARED_FIELDS.concat(
      HEADER_FIELDS,
      SWITCH_FIELDS,
      LABEL_FIELDS,
      OUTER_FIELDS,
      TABLE_FIELDS,
      TELEMETRY_FIELDS,
      TIMER_NAMES,
      COLUMN_KEYS,
      buttonOrder(),
      actionNames(),
      [ENABLED, WORD_WRAP]
    );
  }

  function drawnParts() {
    return [
      PANEL_PART, HEADER_PART, TITLE_PART, SUBTITLE_PART, LOAD_ROW_PART,
      BUTTON_PART, SWITCH_PART, SPACER_PART, STATUS_PART, GROUP_PART,
      GROUP_TITLE_PART, TABLE_PART, HEAD_ROW_PART, HEAD_CELL_PART, BODY_PART,
      BODY_ROW_PART, BODY_CELL_PART, PROGRESS_PART, RUN_ROW_PART
    ];
  }

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
    return panelFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function sent() {
    return dispatched.slice();
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

  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderPanel(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    function again() {
      draw(target, element(Panel, { model: payload, onPick: again }));
    }
    again();
    return target;
  }

  function forget() {
    held = null;
    panelFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
    wanted = null;
  }

  global.acervatorSetFleetReplay = setPanel;
  global.acervatorLoadFleetReplay = loadPanel;
  global.acervatorFleetReplay = {
    method: method,
    Panel: Panel,
    HeaderBox: HeaderBox,
    LoadRow: LoadRow,
    RunRow: RunRow,
    Button: Button,
    Switch: Switch,
    FleetGroup: FleetGroup,
    FleetTable: FleetTable,
    Caption: Caption,
    field: field,
    buttons: buttons,
    buttonOrder: buttonOrder,
    fleetTable: fleetTable,
    tableRows: tableRows,
    rowOrder: rowOrder,
    rowsNamed: rowsNamed,
    collidingNames: collidingNames,
    columnOrder: columnOrder,
    labels: labels,
    actions: actions,
    actionNames: actionNames,
    press: press,
    tick: tick,
    fullEvaluation: fullEvaluation,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    callNames: callNames,
    calls: calls,
    pins: pins,
    statFieldNames: statFieldNames,
    statFields: statFields,
    alphaScale: alphaScale,
    declaredFields: declaredFields,
    declaredNames: declaredNames,
    drawnParts: drawnParts,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    keptSheet: keptSheet,
    qtColour: qtColour,
    scaledAlpha: scaledAlpha,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    sent: sent,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
