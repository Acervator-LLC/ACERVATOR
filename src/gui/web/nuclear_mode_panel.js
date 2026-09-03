// The Nuclear Mode fleet-soak panel, as its Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "nuclear_mode_panel.state";

  var SCREEN = "screen";
  var STATUS_FIELDS = "status_fields";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var SIGNALS = "signals";
  var BUS_TOPICS = "bus_topics";
  var STEP_NAMES = "step_names";

  var DECLARED_FIELDS = [
    ACTIONS,
    BUS_TOPICS,
    SCREEN,
    SIGNALS,
    STATUS_FIELDS,
    STEP_NAMES,
    TIMERS
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var LAYOUT = "layout";
  var HEADER_CARD = "header_card";
  var FLEET_CARD = "fleet_card";
  var CONFIG_CARD = "config_card";
  var BUTTONS = "buttons";
  var STATUS_CARD = "status_card";
  var TIMER = "timer";

  var SCREEN_FIELDS = [
    ACCESSIBLE_NAME,
    BUTTONS,
    CONFIG_CARD,
    FLEET_CARD,
    HEADER_CARD,
    LAYOUT,
    STATUS_CARD,
    TIMER
  ];

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var ORDER = "order";
  var STYLE = "style";
  var TITLE = "title";
  var SUBTITLE = "subtitle";
  var TEXT = "text";
  var WORD_WRAP = "word_wrap";
  var VISIBLE = "visible";
  var HEADING = "heading";
  var EMPTY_LABEL = "empty";
  var FORM_SPACING_PX = "form_spacing_px";
  var DETAIL = "detail";
  var RELOAD_BUTTON = "reload_button";
  var DETAIL_ROW_LABEL = "detail_row_label";
  var RELOAD_ROW_LABEL = "reload_row_label";
  var ROW_LABEL = "row_label";
  var MINIMUM = "minimum";
  var MAXIMUM = "maximum";
  var SINGLE_STEP = "single_step";
  var VALUE = "value";
  var SUFFIX = "suffix";
  var TOOLTIP = "tooltip";
  var ENABLED = "enabled";
  var SPECIAL_VALUE_TEXT = "special_value_text";
  var CHECKED = "checked";
  var START = "start";
  var STOP = "stop";
  var HORIZONTAL_SPACING_PX = "horizontal_spacing_px";
  var VERTICAL_SPACING_PX = "vertical_spacing_px";
  var COLUMN_STRETCH = "column_stretch";
  var ALIGNMENT = "alignment";
  var LABEL_STYLE = "label_style";
  var VALUE_STYLE = "value_style";
  var CELLS = "cells";
  var LAST_EXCEPTION = "last_exception";
  var VALUES = "values";
  var KEY = "key";
  var LABEL = "label";
  var ROW = "row";
  var COLUMN = "column";
  var COLUMN_SPAN = "column_span";
  var INTERVAL_MS = "interval_ms";
  var RUNNING = "running";

  var LAYOUT_FIELDS = [MARGINS_PX, ORDER, SPACING_PX];
  var HEADER_FIELDS = [SPACING_PX, STYLE, SUBTITLE, TITLE];
  var FLEET_FIELDS = [
    DETAIL,
    DETAIL_ROW_LABEL,
    EMPTY_LABEL,
    FORM_SPACING_PX,
    HEADING,
    MARGINS_PX,
    ORDER,
    RELOAD_BUTTON,
    RELOAD_ROW_LABEL,
    STYLE
  ];
  var CONFIG_FIELDS = [FORM_SPACING_PX, HEADING, MARGINS_PX, ORDER, STYLE];
  var STATUS_CARD_FIELDS = [
    ALIGNMENT,
    CELLS,
    COLUMN_STRETCH,
    HEADING,
    HORIZONTAL_SPACING_PX,
    LABEL_STYLE,
    LAST_EXCEPTION,
    MARGINS_PX,
    STYLE,
    VALUE_STYLE,
    VALUES,
    VERTICAL_SPACING_PX
  ];
  var TIMER_FIELDS = [INTERVAL_MS, RUNNING];
  var BUTTON_FIELDS = [ENABLED, STYLE, TEXT];
  var CELL_FIELDS = [COLUMN, KEY, LABEL, ROW, TEXT];

  // BUTTON_ORDER is the run row's order, which the buttons bag never carries.
  var BUTTON_ORDER = [START, STOP];

  // FLEET_ROW_LABELS names the field each fleet form row takes its label from.
  var FLEET_ROW_LABELS = {};
  FLEET_ROW_LABELS[DETAIL] = DETAIL_ROW_LABEL;
  FLEET_ROW_LABELS[RELOAD_BUTTON] = RELOAD_ROW_LABEL;

  var RELOAD_CLICKED = "reload_button_clicked";
  var START_CLICKED = "start_button_clicked";
  var STOP_CLICKED = "stop_button_clicked";
  var TIMER_TICK = "refresh_timer_tick";

  var BUTTON_ACTIONS = {};
  BUTTON_ACTIONS[START] = START_CLICKED;
  BUTTON_ACTIONS[STOP] = STOP_CLICKED;

  var ACTION_PARAM = "action";

  var ALIGN_LEFT = "AlignLeft";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var UNKNOWN_FIELD_FAULT = "unknown-field";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var REPEATED_KEY_FAULT = "repeated-key";
  var QT_COLOUR_FAULT = "qt-colour";
  var NOT_FINITE_FAULT = "not-finite";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var PATH_SPLIT = ".";
  var SEMICOLON = ";";
  var COLON = ":";
  var COMMA = ",";
  var HASH = "#";
  var GAP = " ";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var DASH = "-";
  var PX = "px";
  var FR = "fr";
  var SPAN_WORD = "span";
  var RGBA_OPEN = "rgba(";
  // Qt reads an eight-digit hex alpha first, CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // HEX_DIGITS holds every hex digit, so its length is the radix parseInt takes.
  var HEX_DIGITS = "0123456789abcdef";
  var FULL_BYTE = "ff";

  var HOVER_STATE = "hover";
  var DISABLED_STATE = "disabled";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var LABEL_TAG = "label";

  var NUMBER_TYPE = "number";
  var TEXT_TYPE = "text";
  var CHECKBOX_TYPE = "checkbox";

  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";

  var FLEX = "flex";
  var GRID = "grid";
  var INLINE_FLEX = "inline-flex";
  var COLUMN_WAY = "column";
  var ROW_WAY = "row";
  var CENTER = "center";
  var START_SIDE = "start";
  var AUTO = "auto";
  var NONE = "none";
  var PRE_WRAP = "pre-wrap";
  var NO_WRAP = "nowrap";
  var BREAK_ANY = "anywhere";
  var CLIPPED = "hidden";

  var PANEL_PART = "panel";
  var HEADER_PART = "header-card";
  var TITLE_PART = "title";
  var SUBTITLE_PART = "subtitle";
  var FLEET_PART = "fleet-card";
  var CONFIG_PART = "config-card";
  var BUTTONS_PART = "buttons";
  var STATUS_PART = "status-card";
  var HEADING_PART = "heading";
  var EMPTY_PART = "empty";
  var FORM_PART = "form";
  var ROW_LABEL_PART = "row-label";
  var FIELD_PART = "field";
  var INPUT_PART = "input";
  var GRID_PART = "grid";
  var CELL_LABEL_PART = "cell-label";
  var CELL_VALUE_PART = "cell-value";
  var SUFFIX_PART = "suffix";
  var CHECK_TEXT_PART = "check-text";
  var BUTTON_PART = "button";
  var PANEL_STRETCH_PART = "panel-stretch";
  var BUTTONS_STRETCH_PART = "buttons-stretch";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var ENABLED_ATTR = "data-enabled";
  var CHECKED_ATTR = "data-checked";
  var RUNNING_ATTR = "data-running";
  var INTERVAL_ATTR = "data-interval-ms";
  var SPAN_ATTR = "data-span";
  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var NAME_ATTR = "data-name";

  var held = null;
  var panelFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
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

  function copyOf(source) {
    var found = {};
    Object.keys(source).forEach(function (name) {
      found[name] = source[name];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function isNumber(value) {
    return typeof value === NUMBER_KIND && isFinite(value);
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    panelFaults.push(fault(where, field, kind, detail));
  }

  // text answers nothing for a missing value, leaving its attribute unwritten.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // tip answers nothing for an empty tooltip, so no title attribute is written.
  function tip(value) {
    return typeof value === STRING_KIND && value.length ? value : undefined;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;

  // ALPHA_SCALE is the widest alpha Qt counts in bytes, read from FULL_BYTE.
  var ALPHA_SCALE = parseInt(FULL_BYTE, HEX_DIGITS.length);

  // cssAlpha turns one Qt alpha byte into the fraction CSS reads.
  function cssAlpha(count) {
    return count * Math.pow(ALPHA_SCALE, -ONE);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function headerApi() {
    return global.acervatorHeader;
  }

  function hasSheetSource() {
    var api = headerApi();
    return Boolean(api && typeof api.styleOf === FUNCTION_KIND);
  }

  function declarations(sheet) {
    var api = headerApi();
    if (!api || typeof api.declarations !== FUNCTION_KIND) {
      return [];
    }
    return api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = headerApi();
    if (!api || typeof api.stateRules !== FUNCTION_KIND) {
      return [];
    }
    return api.stateRules(sheet);
  }

  function headerStyleOf(sheet) {
    var api = headerApi();
    if (!api || typeof api.styleOf !== FUNCTION_KIND) {
      return {};
    }
    return api.styleOf(sheet);
  }

  // variableFor asks acervatorWidgets for the one token carrying a value.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== FUNCTION_KIND) {
      return undefined;
    }
    return api.variableFor(value);
  }

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // The reason CSS would read one written value as a different colour.
  function qtColour(value) {
    return hexWord(value).length === HEX_ARGB.length ? HEX_ARGB : undefined;
  }

  // The four rgba fields of a byte-alpha value, with the text around the call.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return undefined;
    }
    var rest = String(parts.shift());
    var fields = rest.split(CLOSE).shift().split(COMMA);
    if (fields.length !== THREE + ONE) {
      return undefined;
    }
    var alpha = String(fields[THREE]).trim();
    if (carries(alpha, DOT) || carries(alpha, PERCENT)) {
      return undefined;
    }
    var count = Number(alpha);
    if (!isNumber(count)) {
      return undefined;
    }
    return {
      fields: fields,
      alpha: count,
      before: String(value).split(RGBA_OPEN).shift(),
      after: afterFirst(rest, CLOSE).join(CLOSE),
    };
  }

  // cssValue rewrites a Qt rgba so a browser paints the alpha Qt painted.
  function cssValue(value) {
    var found = byteAlpha(value);
    if (found === undefined) {
      return value;
    }
    var head = found.fields.slice(ZERO, THREE).map(function (one) {
      return String(one).trim();
    });
    head.push(String(cssAlpha(found.alpha)));
    return found.before + RGBA_OPEN + head.join(COMMA) + CLOSE + found.after;
  }

  // The sheet without the declaration CSS would read as another colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        return;
      }
      kept.push(one.property + COLON + cssValue(one.value));
    });
    return kept.join(SEMICOLON);
  }

  function styleOf(sheet) {
    return headerStyleOf(keptSheet(sheet));
  }

  // The style a named Qt state paints, `:hover` and `:disabled` alike.
  function stateStyle(sheet, state) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (!carries(rule.selector, state)) {
        return;
      }
      var painted = styleOf(rule.body);
      Object.keys(painted).forEach(function (name) {
        found[name] = painted[name];
      });
    });
    return found;
  }

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  function length(value) {
    return isNumber(value) ? String(value) + PX : undefined;
  }

  // Qt writes its four margins as left, top, right then bottom.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  function marginStyle(bag) {
    var style = {};
    listField(bag, MARGINS_PX).forEach(function (one, at) {
      if (at < PADDING_SIDES.length) {
        style[PADDING_SIDES[at]] = length(one);
      }
    });
    return style;
  }

  function boxStyle(bag, way) {
    var style = marginStyle(bag);
    style.display = FLEX;
    style.flexDirection = way;
    style.gap = length(bag[SPACING_PX]);
    return style;
  }

  // wrapStyle paints a Qt word-wrapped label, whose newlines are its own.
  function wrapStyle(bag) {
    var wraps = bag[WORD_WRAP] === true;
    return {
      whiteSpace: wraps ? PRE_WRAP : NO_WRAP,
      overflowWrap: wraps ? BREAK_ANY : undefined
    };
  }

  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      return null;
    }
    var sent = copyOf(params);
    sent[ACTION_PARAM] = name;
    return global.acervator.call(METHOD, sent);
  }

  function actionName(model, name) {
    var found = objectField(model, ACTIONS);
    return owns(found, name) ? name : undefined;
  }


  function Caption(props) {
    var style = merged(styleOf(props.sheet), wrapStyle(props.bag));
    var captionProps = { style: style };
    captionProps[PART_ATTR] = props.part;
    if (props.name !== undefined) {
      captionProps[NAME_ATTR] = props.name;
    }
    captionProps.hidden = props.hidden === true;
    return element(SPAN_TAG, captionProps, text(props.bag[TEXT]));
  }

  function SheetButton(props) {
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var live = props.bag[ENABLED] !== false;
    var style = styleOf(props.bag[STYLE]);
    style.whiteSpace = NO_WRAP;
    style.flex = NONE;
    if (live && hovered) {
      merged(style, stateStyle(props.bag[STYLE], HOVER_STATE));
    }
    if (!live) {
      merged(style, stateStyle(props.bag[STYLE], DISABLED_STATE));
    }
    var buttonProps = { style: style, disabled: !live, type: BUTTON_TAG };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[NAME_ATTR] = props.name;
    buttonProps[ENABLED_ATTR] = text(live);
    buttonProps[ACTION_ATTR] = props.action;
    buttonProps.onMouseEnter = function () {
      setHovered(true);
    };
    buttonProps.onMouseLeave = function () {
      setHovered(false);
    };
    buttonProps.onClick = function () {
      if (props.action !== undefined) {
        dispatch(props.action, props.params());
      }
    };
    return element(BUTTON_TAG, buttonProps, text(props.bag[TEXT]));
  }

  // SpinField draws a Qt spin box, whose special text stands in at the floor.
  function SpinField(props) {
    var bag = props.bag;
    var live = bag[ENABLED] !== false;
    var special =
      typeof bag[SPECIAL_VALUE_TEXT] === STRING_KIND &&
      bag[VALUE] === bag[MINIMUM];
    var fieldProps = {
      style: {
        display: INLINE_FLEX,
        flexDirection: ROW_WAY,
        alignItems: CENTER
      }
    };
    fieldProps[PART_ATTR] = FIELD_PART;
    fieldProps[NAME_ATTR] = props.name;
    fieldProps[ENABLED_ATTR] = text(live);
    var inputProps = {
      type: special ? TEXT_TYPE : NUMBER_TYPE,
      value: special ? bag[SPECIAL_VALUE_TEXT] : text(bag[VALUE]),
      disabled: !live,
      readOnly: special,
      title: tip(bag[TOOLTIP]),
      onChange: function (event) {
        props.onValue(Number(event.target.value));
      }
    };
    inputProps[PART_ATTR] = INPUT_PART;
    inputProps[NAME_ATTR] = props.name;
    if (!special) {
      inputProps.min = text(bag[MINIMUM]);
      inputProps.max = text(bag[MAXIMUM]);
      inputProps.step = text(bag[SINGLE_STEP]);
    }
    var kids = [element(INPUT_TAG, merged(inputProps, { key: INPUT_PART }))];
    if (typeof bag[SUFFIX] === STRING_KIND && bag[SUFFIX].length) {
      var suffixProps = { style: { whiteSpace: NO_WRAP }, key: SUFFIX_PART };
      suffixProps[PART_ATTR] = SUFFIX_PART;
      suffixProps[NAME_ATTR] = props.name;
      kids.push(element(SPAN_TAG, suffixProps, bag[SUFFIX]));
    }
    return element(DIV_TAG, fieldProps, kids);
  }

  function CheckField(props) {
    var bag = props.bag;
    var live = bag[ENABLED] !== false;
    var labelProps = {
      style: { display: INLINE_FLEX, alignItems: CENTER, gap: length(ONE) }
    };
    labelProps[PART_ATTR] = FIELD_PART;
    labelProps[NAME_ATTR] = props.name;
    labelProps[ENABLED_ATTR] = text(live);
    labelProps[CHECKED_ATTR] = text(bag[CHECKED] === true);
    labelProps.title = tip(bag[TOOLTIP]);
    var inputProps = {
      type: CHECKBOX_TYPE,
      checked: bag[CHECKED] === true,
      disabled: !live,
      onChange: function (event) {
        props.onValue(event.target.checked === true);
      }
    };
    inputProps[PART_ATTR] = INPUT_PART;
    inputProps[NAME_ATTR] = props.name;
    var textProps = { style: { whiteSpace: NO_WRAP } };
    textProps[PART_ATTR] = CHECK_TEXT_PART;
    textProps[NAME_ATTR] = props.name;
    return element(
      LABEL_TAG,
      labelProps,
      element(INPUT_TAG, merged(inputProps, { key: INPUT_PART })),
      element(SPAN_TAG, merged(textProps, { key: CHECK_TEXT_PART }), text(bag[TEXT]))
    );
  }

  function formStyle(card) {
    return {
      display: GRID,
      gridTemplateColumns: [AUTO, String(ONE) + FR].join(GAP),
      gap: length(card[FORM_SPACING_PX]),
      alignItems: CENTER
    };
  }

  function rowLabel(name, value) {
    var labelProps = { style: { whiteSpace: NO_WRAP }, key: name };
    labelProps[PART_ATTR] = ROW_LABEL_PART;
    labelProps[NAME_ATTR] = name;
    return element(SPAN_TAG, labelProps, text(value));
  }

  function captionOf(card, name, part, hidden) {
    return element(Caption, {
      key: part,
      part: part,
      bag: objectField(card, name),
      sheet: objectField(card, name)[STYLE],
      hidden: hidden
    });
  }

  function heading(card) {
    return captionOf(card, HEADING, HEADING_PART, false);
  }

  function HeaderCard(props) {
    var card = objectField(props.model, HEADER_CARD);
    var style = merged(styleOf(card[STYLE]), {
      display: FLEX,
      flexDirection: COLUMN_WAY,
      gap: length(card[SPACING_PX])
    });
    var cardProps = { style: style };
    cardProps[PART_ATTR] = HEADER_PART;
    return element(
      DIV_TAG,
      cardProps,
      captionOf(card, TITLE, TITLE_PART, false),
      captionOf(card, SUBTITLE, SUBTITLE_PART, false)
    );
  }

  function fleetRow(props, card, name) {
    var cells = [rowLabel(name, card[FLEET_ROW_LABELS[name]])];
    if (name === RELOAD_BUTTON) {
      cells.push(
        element(SheetButton, {
          key: name,
          name: name,
          bag: objectField(card, name),
          action: actionName(props.top, RELOAD_CLICKED),
          params: emptyParams
        })
      );
      return cells;
    }
    cells.push(
      element(Caption, {
        key: name,
        part: FIELD_PART,
        name: name,
        bag: objectField(card, name),
        sheet: objectField(card, name)[STYLE]
      })
    );
    return cells;
  }

  function emptyParams() {
    return {};
  }

  function FleetCard(props) {
    var card = objectField(props.model, FLEET_CARD);
    var style = merged(styleOf(card[STYLE]), boxStyle(card, COLUMN_WAY));
    var cardProps = { style: style };
    cardProps[PART_ATTR] = FLEET_PART;
    var names = listField(card, ORDER);
    var rows = names.filter(function (name) {
      return owns(FLEET_ROW_LABELS, name);
    });
    var cells = [];
    rows.forEach(function (name) {
      fleetRow(props, card, name).forEach(function (one) {
        cells.push(one);
      });
    });
    var formProps = { style: formStyle(card), key: FORM_PART };
    formProps[PART_ATTR] = FORM_PART;
    var form = element(DIV_TAG, formProps, cells);
    var placed = false;
    var kids = [];
    names.forEach(function (name) {
      if (owns(FLEET_ROW_LABELS, name)) {
        if (!placed) {
          placed = true;
          kids.push(form);
        }
        return;
      }
      if (name === HEADING) {
        kids.push(heading(card));
        return;
      }
      if (name === EMPTY_LABEL) {
        kids.push(
          captionOf(card, name, EMPTY_PART, objectField(card, name)[VISIBLE] !== true)
        );
      }
    });
    if (!placed) {
      kids.push(form);
    }
    return element(DIV_TAG, cardProps, kids);
  }

  function configRow(props, card, name) {
    var bag = objectField(card, name);
    var shown = copyOf(bag);
    var chosen = props.settings()[name];
    if (chosen !== undefined) {
      shown[owns(bag, CHECKED) ? CHECKED : VALUE] = chosen;
    }
    return [
      rowLabel(name, bag[ROW_LABEL]),
      element(owns(bag, CHECKED) ? CheckField : SpinField, {
        key: name,
        name: name,
        bag: shown,
        onValue: function (value) {
          props.onSetting(name, value);
        }
      })
    ];
  }

  function ConfigCard(props) {
    var card = objectField(props.model, CONFIG_CARD);
    var style = merged(styleOf(card[STYLE]), boxStyle(card, COLUMN_WAY));
    var cardProps = { style: style };
    cardProps[PART_ATTR] = CONFIG_PART;
    var cells = [];
    listField(card, ORDER).forEach(function (name) {
      configRow(props, card, name).forEach(function (one) {
        cells.push(one);
      });
    });
    var formProps = { style: formStyle(card), key: FORM_PART };
    formProps[PART_ATTR] = FORM_PART;
    return element(
      DIV_TAG,
      cardProps,
      heading(card),
      element(DIV_TAG, formProps, cells)
    );
  }

  function ButtonRow(props) {
    var bag = objectField(props.model, BUTTONS);
    var rowProps = {
      style: { display: FLEX, flexDirection: ROW_WAY, alignItems: CENTER }
    };
    rowProps[PART_ATTR] = BUTTONS_PART;
    var kids = BUTTON_ORDER.map(function (name) {
      return element(SheetButton, {
        key: name,
        name: name,
        bag: objectField(bag, name),
        action: actionName(props.top, BUTTON_ACTIONS[name]),
        params: name === START ? props.settings : emptyParams
      });
    });
    var stretchProps = { style: { flex: ONE }, key: BUTTONS_STRETCH_PART };
    stretchProps[PART_ATTR] = BUTTONS_STRETCH_PART;
    kids.push(element(DIV_TAG, stretchProps, null));
    return element(DIV_TAG, rowProps, kids);
  }

  function columnTemplate(card) {
    var parts = listField(card, COLUMN_STRETCH).map(function (one) {
      return isNumber(one) && one > ZERO ? String(one) + FR : AUTO;
    });
    return parts.length ? parts.join(GAP) : AUTO;
  }

  function alignSide(card) {
    return card[ALIGNMENT] === ALIGN_LEFT ? START_SIDE : undefined;
  }

  // drawnCells names the grid rows and the wide last-exception row after them.
  function drawnCells(card) {
    var found = listField(card, CELLS).filter(isPlainObject);
    var wide = objectField(card, LAST_EXCEPTION);
    return owns(wide, KEY) ? found.concat([wide]) : found;
  }

  function statusCell(card, cell, side) {
    var span = isNumber(cell[COLUMN_SPAN]) ? cell[COLUMN_SPAN] : ONE;
    var labelProps = {
      style: merged(
        { whiteSpace: NO_WRAP, justifySelf: side },
        styleOf(card[LABEL_STYLE])
      ),
      key: cell[KEY]
    };
    labelProps.style.gridRowStart = text(cell[ROW] + ONE);
    labelProps.style.gridColumnStart = text(cell[COLUMN] + ONE);
    labelProps[PART_ATTR] = CELL_LABEL_PART;
    labelProps[KEY_ATTR] = cell[KEY];
    labelProps[ROW_ATTR] = text(cell[ROW]);
    labelProps[COLUMN_ATTR] = text(cell[COLUMN]);
    var valueProps = {
      style: merged({ justifySelf: side }, styleOf(card[VALUE_STYLE])),
      key: cell[KEY] + DASH
    };
    merged(valueProps.style, wrapStyle(cell));
    valueProps.style.gridRowStart = text(cell[ROW] + ONE);
    valueProps.style.gridColumnStart = text(cell[COLUMN] + TWO);
    valueProps.style.gridColumnEnd = [SPAN_WORD, String(span)].join(GAP);
    valueProps[PART_ATTR] = CELL_VALUE_PART;
    valueProps[KEY_ATTR] = cell[KEY];
    valueProps[SPAN_ATTR] = text(span);
    return [
      element(SPAN_TAG, labelProps, text(cell[TEXT])),
      element(SPAN_TAG, valueProps, text(objectField(card, VALUES)[cell[KEY]]))
    ];
  }

  function StatusCard(props) {
    var card = objectField(props.model, STATUS_CARD);
    var style = merged(styleOf(card[STYLE]), boxStyle(card, COLUMN_WAY));
    var cardProps = { style: style };
    cardProps[PART_ATTR] = STATUS_PART;
    var gridProps = {
      style: {
        display: GRID,
        gridTemplateColumns: columnTemplate(card),
        columnGap: length(card[HORIZONTAL_SPACING_PX]),
        rowGap: length(card[VERTICAL_SPACING_PX])
      },
      key: GRID_PART
    };
    gridProps[PART_ATTR] = GRID_PART;
    var side = alignSide(card);
    var cells = [];
    drawnCells(card).forEach(function (cell) {
      statusCell(card, cell, side).forEach(function (one) {
        cells.push(one);
      });
    });
    return element(
      DIV_TAG,
      cardProps,
      heading(card),
      element(DIV_TAG, gridProps, cells)
    );
  }

  var CARD_PARTS = {};
  CARD_PARTS[HEADER_CARD] = HeaderCard;
  CARD_PARTS[FLEET_CARD] = FleetCard;
  CARD_PARTS[CONFIG_CARD] = ConfigCard;
  CARD_PARTS[BUTTONS] = ButtonRow;
  CARD_PARTS[STATUS_CARD] = StatusCard;

  // startSettings reads the four run settings Start sends with its click.
  function startSettings(screen) {
    var card = objectField(screen, CONFIG_CARD);
    var found = {};
    listField(card, ORDER).forEach(function (name) {
      var bag = objectField(card, name);
      found[name] = owns(bag, CHECKED) ? bag[CHECKED] === true : bag[VALUE];
    });
    return found;
  }

  // useTick runs the refresh action on the surface's own interval.
  function useTick(model, timer) {
    var action = actionName(model, TIMER_TICK);
    var running = timer[RUNNING] === true;
    var every = timer[INTERVAL_MS];
    hooks().useEffect(
      function () {
        if (!running || action === undefined || !isNumber(every)) {
          return undefined;
        }
        var handle = global.setInterval(function () {
          dispatch(action, {});
        }, every);
        return function () {
          global.clearInterval(handle);
        };
      },
      [running, action, every]
    );
  }

  // Panel draws nothing for a payload that is not an object.
  function Panel(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var screen = objectField(model, SCREEN);
    var timer = objectField(screen, TIMER);
    var kept = hooks().useState(startSettings(screen));
    var chosen = kept.shift();
    var setChosen = kept.shift();
    useTick(model, timer);
    if (!isPlainObject(props.model)) {
      return null;
    }
    var style = boxStyle(objectField(screen, LAYOUT), COLUMN_WAY);
    style.overflow = CLIPPED;
    var panelProps = { style: style };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[NAME_ATTR] = text(screen[ACCESSIBLE_NAME]);
    panelProps[RUNNING_ATTR] = text(timer[RUNNING] === true);
    panelProps[INTERVAL_ATTR] = text(timer[INTERVAL_MS]);
    var shared = {
      model: screen,
      top: model,
      settings: function () {
        return copyOf(chosen);
      },
      onSetting: function (name, value) {
        var next = copyOf(chosen);
        next[name] = value;
        setChosen(next);
      }
    };
    var kids = [];
    listField(objectField(screen, LAYOUT), ORDER).forEach(function (name) {
      if (!owns(CARD_PARTS, name)) {
        return;
      }
      kids.push(element(CARD_PARTS[name], merged(copyOf(shared), { key: name })));
    });
    var stretchProps = { style: { flex: ONE }, key: PANEL_STRETCH_PART };
    stretchProps[PART_ATTR] = PANEL_STRETCH_PART;
    kids.push(element(DIV_TAG, stretchProps, null));
    return element(DIV_TAG, panelProps, kids);
  }


  function checkPresent(where, source, names, optional) {
    names.forEach(function (name) {
      if (!owns(source, name)) {
        note(where, name, MISSING_FAULT, null);
        return;
      }
      if (source[name] === null) {
        note(where, name, NULL_FAULT, null);
      }
    });
    var allowed = names.concat(optional || []);
    Object.keys(source).forEach(function (name) {
      if (allowed.indexOf(name) < ZERO) {
        note(where, name, UNKNOWN_FIELD_FAULT, kindOf(source[name]));
      }
    });
  }

  function checkTop(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        note(null, name, MISSING_FAULT, null);
      }
    });
    [ACTIONS, SCREEN, TIMERS].forEach(function (name) {
      if (!isPlainObject(model[name])) {
        note(null, name, NOT_AN_OBJECT_FAULT, kindOf(model[name]));
      }
    });
    [BUS_TOPICS, SIGNALS, STATUS_FIELDS, STEP_NAMES].forEach(function (name) {
      if (!Array.isArray(model[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(model[name]));
      }
    });
  }

  function checkScreen(model) {
    var screen = objectField(model, SCREEN);
    var card = objectField(screen, CONFIG_CARD);
    checkPresent(SCREEN, screen, SCREEN_FIELDS);
    checkPresent(LAYOUT, objectField(screen, LAYOUT), LAYOUT_FIELDS);
    checkPresent(HEADER_CARD, objectField(screen, HEADER_CARD), HEADER_FIELDS);
    checkPresent(FLEET_CARD, objectField(screen, FLEET_CARD), FLEET_FIELDS);
    checkPresent(CONFIG_CARD, card, CONFIG_FIELDS, listField(card, ORDER));
    checkPresent(STATUS_CARD, objectField(screen, STATUS_CARD), STATUS_CARD_FIELDS);
    checkPresent(TIMER, objectField(screen, TIMER), TIMER_FIELDS);
    BUTTON_ORDER.forEach(function (name) {
      var button = objectField(screen, BUTTONS)[name];
      if (!isPlainObject(button)) {
        note(BUTTONS, name, NOT_AN_OBJECT_FAULT, kindOf(button));
        return;
      }
      checkPresent(BUTTONS + PATH_SPLIT + name, button, BUTTON_FIELDS);
    });
  }

  function checkOrder(model) {
    var screen = objectField(model, SCREEN);
    var fleet = objectField(screen, FLEET_CARD);
    var config = objectField(screen, CONFIG_CARD);
    var status = objectField(screen, STATUS_CARD);
    listField(objectField(screen, LAYOUT), ORDER).forEach(function (name) {
      if (!owns(CARD_PARTS, name)) {
        note(LAYOUT, ORDER, UNKNOWN_NAME_FAULT, text(name));
      }
    });
    listField(fleet, ORDER).forEach(function (name) {
      if (!owns(fleet, name)) {
        note(FLEET_CARD, ORDER, UNKNOWN_NAME_FAULT, text(name));
      }
    });
    listField(config, ORDER).forEach(function (name) {
      if (!isPlainObject(config[name])) {
        note(CONFIG_CARD, ORDER, UNKNOWN_NAME_FAULT, text(name));
      }
    });
    if (status[ALIGNMENT] !== ALIGN_LEFT) {
      note(STATUS_CARD, ALIGNMENT, UNKNOWN_NAME_FAULT, text(status[ALIGNMENT]));
    }
  }

  function checkCells(model) {
    var card = objectField(objectField(model, SCREEN), STATUS_CARD);
    var seen = {};
    drawnCells(card).forEach(function (cell) {
      CELL_FIELDS.forEach(function (name) {
        if (!owns(cell, name)) {
          note(CELLS, name, MISSING_FAULT, text(cell[KEY]));
        }
      });
      if (!isNumber(cell[ROW]) || !isNumber(cell[COLUMN])) {
        note(CELLS, ROW, NOT_FINITE_FAULT, text(cell[KEY]));
      }
      if (owns(seen, cell[KEY])) {
        note(CELLS, KEY, REPEATED_KEY_FAULT, text(cell[KEY]));
      }
      seen[cell[KEY]] = true;
      if (!owns(objectField(card, VALUES), cell[KEY])) {
        note(VALUES, text(cell[KEY]), MISSING_FAULT, null);
      }
    });
  }

  // A colour is written as hex digits or as an rgba call.
  function carriesColour(value) {
    return carries(value, HASH) || carries(value, RGBA_OPEN);
  }

  // Every published style sheet, named by the bag that carries it.
  function sheetNames(model) {
    var screen = objectField(model, SCREEN);
    var found = [];
    [HEADER_CARD, FLEET_CARD, CONFIG_CARD, STATUS_CARD].forEach(function (name) {
      var card = objectField(screen, name);
      Object.keys(card).forEach(function (inner) {
        var value = card[inner];
        if (typeof value === STRING_KIND && carriesColour(value)) {
          found.push({ where: name, field: inner, value: value });
          return;
        }
        if (isPlainObject(value) && typeof value[STYLE] === STRING_KIND) {
          found.push({
            where: name + PATH_SPLIT + inner,
            field: STYLE,
            value: value[STYLE]
          });
        }
      });
    });
    BUTTON_ORDER.forEach(function (name) {
      var button = objectField(objectField(screen, BUTTONS), name);
      if (typeof button[STYLE] === STRING_KIND) {
        found.push({
          where: BUTTONS + PATH_SPLIT + name,
          field: STYLE,
          value: button[STYLE]
        });
      }
    });
    return found;
  }

  function ruleBodies(sheet) {
    var bodies = [sheet];
    stateRules(sheet).forEach(function (block) {
      bodies.push(block.body);
    });
    return bodies;
  }

  function checkColours(model) {
    if (!hasSheetSource()) {
      note(null, STYLE, NO_SHEET_SOURCE_FAULT, null);
      return;
    }
    sheetNames(model).forEach(function (one) {
      ruleBodies(one.value).forEach(function (body) {
        declarations(body).forEach(function (rule) {
          if (qtColour(rule.value) !== undefined) {
            note(one.where, rule.property, QT_COLOUR_FAULT, rule.value);
          }
        });
      });
    });
  }

  function checkTypes(model) {
    var screen = objectField(model, SCREEN);
    var card = objectField(screen, CONFIG_CARD);
    var timer = objectField(screen, TIMER);
    listField(card, ORDER).forEach(function (name) {
      var bag = objectField(card, name);
      if (owns(bag, CHECKED)) {
        if (typeof bag[CHECKED] !== BOOLEAN_KIND) {
          note(name, CHECKED, WRONG_TYPE_FAULT, kindOf(bag[CHECKED]));
        }
        return;
      }
      [MINIMUM, MAXIMUM, VALUE].forEach(function (inner) {
        if (!isNumber(bag[inner])) {
          note(name, inner, NOT_FINITE_FAULT, kindOf(bag[inner]));
        }
      });
    });
    if (!isNumber(timer[INTERVAL_MS])) {
      note(TIMER, INTERVAL_MS, NOT_FINITE_FAULT, kindOf(timer[INTERVAL_MS]));
    }
  }


  function screenBag() {
    return held === null ? {} : objectField(held.model, SCREEN);
  }

  function cardBag(name) {
    return objectField(screenBag(), name);
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function heldNames() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    });
  }

  function screenNames() {
    var screen = screenBag();
    return SCREEN_FIELDS.filter(function (name) {
      return owns(screen, name);
    });
  }

  // Every drawn bag's order, published as a list rather than left to a key walk.
  function orders() {
    var found = {};
    found[LAYOUT] = listField(objectField(screenBag(), LAYOUT), ORDER).slice();
    found[FLEET_CARD] = listField(cardBag(FLEET_CARD), ORDER).slice();
    found[CONFIG_CARD] = listField(cardBag(CONFIG_CARD), ORDER).slice();
    found[BUTTONS] = BUTTON_ORDER.slice();
    found[STATUS_CARD] = drawnCells(cardBag(STATUS_CARD)).map(function (cell) {
      return cell[KEY];
    });
    return found;
  }

  function actions() {
    return held === null ? {} : copyOf(objectField(held.model, ACTIONS));
  }

  function alphaScale() {
    return ALPHA_SCALE;
  }

  // Every byte alpha the module rewrote, by the sheet that carried it.
  function alphaRewrites() {
    var found = [];
    if (held === null) {
      return found;
    }
    sheetNames(held.model).forEach(function (one) {
      declarations(one.value).forEach(function (rule) {
        if (byteAlpha(rule.value) !== undefined) {
          found.push({
            where: one.where,
            property: rule.property,
            written: rule.value,
            painted: cssValue(rule.value)
          });
        }
      });
    });
    return found;
  }

  // Every published value beside the one design token that also carries it.
  function tokenNames() {
    var found = {};
    if (held === null) {
      return found;
    }
    sheetNames(held.model).forEach(function (one) {
      ruleBodies(one.value).forEach(function (body) {
        declarations(body).forEach(function (rule) {
          var name = variableFor(rule.value);
          found[rule.value] = name === undefined ? null : name;
        });
      });
    });
    return found;
  }

  function sent() {
    return dispatched.slice();
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
    function descend(path, value) {
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          found[path + PATH_SPLIT + String(at)] = kindOf(one);
          descend(path + PATH_SPLIT + String(at), one);
        });
        return;
      }
      if (isPlainObject(value)) {
        Object.keys(value).forEach(function (name) {
          found[path + PATH_SPLIT + name] = kindOf(value[name]);
          descend(path + PATH_SPLIT + name, value[name]);
        });
      }
    }
    if (held !== null) {
      Object.keys(held.model).forEach(function (name) {
        found[name] = kindOf(held.model[name]);
        descend(name, held.model[name]);
      });
    }
    return found;
  }

  function report() {
    var screen = screenBag();
    var buttons = objectField(screen, BUTTONS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        screen: SCREEN_FIELDS.length,
        buttons: BUTTON_ORDER.length,
        cards: Object.keys(CARD_PARTS).length
      },
      held: {
        fields: heldNames().length,
        screen: screenNames().length,
        buttons: BUTTON_ORDER.filter(function (name) {
          return isPlainObject(buttons[name]);
        }).length,
        cards: listField(objectField(screen, LAYOUT), ORDER).filter(function (name) {
          return owns(CARD_PARTS, name);
        }).length
      },
      cells: drawnCells(cardBag(STATUS_CARD)).length,
      rows: listField(cardBag(CONFIG_CARD), ORDER).length,
      status_fields:
        held === null ? ZERO : listField(held.model, STATUS_FIELDS).length,
      steps: held === null ? ZERO : listField(held.model, STEP_NAMES).length,
      faults: panelFaults.length
    };
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

  function setPanel(model) {
    dispatched = [];
    if (!isPlainObject(model)) {
      held = null;
      panelFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: panelFaults.slice() };
    }
    held = { model: model };
    panelFaults = [];
    checkTop(model);
    checkScreen(model);
    checkOrder(model);
    checkCells(model);
    checkColours(model);
    checkTypes(model);
    return report();
  }

  function loadPanel(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
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

  function rootFor(target) {
    var found;
    roots.forEach(function (one) {
      if (one.node === target) {
        found = one.root;
      }
    });
    if (found === undefined) {
      found = global.ReactDOM.createRoot(target);
      roots.push({ node: target, root: found });
    }
    return found;
  }

  // draw runs flushSync so the document is current when it returns.
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
    return draw(target, element(Panel, { model: payload }));
  }

  function forget() {
    held = null;
    panelFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetNuclearPanel = setPanel;
  global.acervatorLoadNuclearPanel = loadPanel;
  global.acervatorNuclearPanel = {
    method: METHOD,
    Panel: Panel,
    HeaderCard: HeaderCard,
    FleetCard: FleetCard,
    ConfigCard: ConfigCard,
    ButtonRow: ButtonRow,
    StatusCard: StatusCard,
    SheetButton: SheetButton,
    SpinField: SpinField,
    CheckField: CheckField,
    declaredNames: declaredNames,
    heldNames: heldNames,
    screenNames: screenNames,
    orders: orders,
    actions: actions,
    startSettings: startSettings,
    alphaScale: alphaScale,
    alphaRewrites: alphaRewrites,
    tokenNames: tokenNames,
    qtColour: qtColour,
    byteAlpha: byteAlpha,
    cssValue: cssValue,
    keptSheet: keptSheet,
    styleOf: styleOf,
    stateStyle: stateStyle,
    columnTemplate: columnTemplate,
    drawnCells: drawnCells,
    sent: sent,
    kinds: kinds,
    report: report,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
