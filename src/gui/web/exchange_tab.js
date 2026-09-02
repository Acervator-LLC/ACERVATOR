// One per-exchange screen, drawn from the payload METHOD names.
(function (global) {
  "use strict";
  var METHOD = "exchange_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ADD_BOT_ACCENT = "add_bot_accent";
  var ADD_BOT_LABEL = "add_bot_label";
  var BOT_IDS = "bot_ids";
  var COMMAND_BUTTONS = "command_buttons";
  var COMMAND_PARAM = "command_param";
  var CURRENT_ROW = "current_row";
  var DANGER_COMMAND_LABEL = "danger_command_label";
  var DRAWN = "drawn";
  var DRAWN_ROWS = "drawn_rows";
  var EXCHANGE_ID = "exchange_id";
  var EXCHANGE_NAME = "exchange_name";
  var EXTRACTOR_SECTION_LABEL = "extractor_section_label";
  var EXTRACTOR_SECTION_STYLE = "extractor_section_style";
  var EXTRACTOR_SECTION_VISIBLE = "extractor_section_visible";
  var EXTRACTOR_TABLE = "extractor_table";
  var HAS_SELECTION = "has_selection";
  var HEADER_STRETCH = "header_stretch";
  var KIND = "kind";
  var NEWS_TICKER_BUILT = "news_ticker_built";
  var NEWS_TICKER_STRETCH = "news_ticker_stretch";
  var NEW_BOT_PARAM = "new_bot_param";
  var PINS = "pins";
  var PIN_COMMAND_ROUTED = "pin_command_routed";
  var PIN_EVERY_BOT_DRAWN = "pin_every_bot_drawn";
  var PIN_PRIVACY_APPLIED = "pin_privacy_applied";
  var PIN_PRIVACY_BUTTON = "pin_privacy_button";
  var PIN_SELECTION_SURVIVES = "pin_selection_survives";
  var PRIVACY_FOCUSABLE = "privacy_focusable";
  var PRIVACY_FOCUS_POLICY = "privacy_focus_policy";
  var PRIVACY_LABEL = "privacy_label";
  var PRIVACY_LABEL_OFF = "privacy_label_off";
  var PRIVACY_LABEL_ON = "privacy_label_on";
  var PRIVACY_PARAM = "privacy_param";
  var PRIVACY_STYLE = "privacy_style";
  var PRIVACY_STYLE_OFF = "privacy_style_off";
  var PRIVACY_STYLE_ON = "privacy_style_on";
  var PRIVACY_TOOLTIP = "privacy_tooltip";
  var PULL_RATE_INTERVAL_MS = "pull_rate_interval_ms";
  var PULL_RATE_PARAM = "pull_rate_param";
  var PULL_RATE_STYLE = "pull_rate_style";
  var PULL_RATE_TEXT = "pull_rate_text";
  var PULL_RATE_TOOLTIP = "pull_rate_tooltip";
  var ROW_COUNT = "row_count";
  var SCRUM_SECTION_LABEL = "scrum_section_label";
  var SCRUM_SECTION_STYLE = "scrum_section_style";
  var SCRUM_SECTION_VISIBLE = "scrum_section_visible";
  var SCRUM_TABLE = "scrum_table";
  var SELECTED_BOT_ID = "selected_bot_id";
  var SELECT_EXTRACTOR_PARAM = "select_extractor_param";
  var SELECT_FIRST_MESSAGE = "select_first_message";
  var SELECT_SCRUM_PARAM = "select_scrum_param";
  var SKIN = "skin";
  var STYLE_SHEET = "style_sheet";
  var TABLE_EXTRACTOR = "table_extractor";
  var TABLE_SCRUMMING = "table_scrumming";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";

  var PRIVACY_CLICKED = "privacy_clicked";
  var ADD_BOT_CLICKED = "add_bot_clicked";
  var PULL_RATE_TIMEOUT = "pull_rate_timeout";
  var SCRUM_SELECTION_CHANGED = "scrum_selection_changed";
  var EXTRACTOR_SELECTION_CHANGED = "extractor_selection_changed";
  var COMMAND_CLICKED = "command_clicked";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ADD_BOT_ACCENT,
    ADD_BOT_LABEL,
    "bot_opens",
    "bus_topics",
    "calls",
    "check_numbers",
    "check_state",
    "check_stats",
    "check_symbol",
    "checks_before_first_cell",
    COMMAND_BUTTONS,
    COMMAND_PARAM,
    "commands_sent",
    DANGER_COMMAND_LABEL,
    "default_exchange_id",
    "default_exchange_name",
    "default_table",
    EXCHANGE_ID,
    "exchange_id_param",
    EXCHANGE_NAME,
    "exchange_name_param",
    EXTRACTOR_SECTION_LABEL,
    EXTRACTOR_SECTION_STYLE,
    EXTRACTOR_SECTION_VISIBLE,
    EXTRACTOR_TABLE,
    HEADER_STRETCH,
    "last_clicked_table",
    "logged",
    "logger_name",
    "method",
    "mode_extractor",
    "mode_scrumming",
    "new_bot_asks",
    NEW_BOT_PARAM,
    NEWS_TICKER_BUILT,
    "news_ticker_failed_log",
    "news_ticker_started",
    NEWS_TICKER_STRETCH,
    "no_bot_id",
    "no_every",
    "no_hits",
    "no_mode",
    "no_number",
    "no_selection_bot_id",
    "no_selection_moved",
    "no_selection_row",
    "no_slots",
    "number_fields",
    "percent_scale",
    PIN_COMMAND_ROUTED,
    PIN_EVERY_BOT_DRAWN,
    PIN_PRIVACY_APPLIED,
    PIN_PRIVACY_BUTTON,
    PIN_SELECTION_SURVIVES,
    PINS,
    PRIVACY_FOCUS_POLICY,
    PRIVACY_FOCUSABLE,
    PRIVACY_LABEL,
    PRIVACY_LABEL_OFF,
    PRIVACY_LABEL_ON,
    PRIVACY_PARAM,
    PRIVACY_STYLE,
    PRIVACY_STYLE_OFF,
    PRIVACY_STYLE_ON,
    PRIVACY_TOOLTIP,
    "pull_rate_awaiting_format",
    "pull_rate_full_format",
    "pull_rate_idle_text",
    "pull_rate_initial_text",
    PULL_RATE_INTERVAL_MS,
    PULL_RATE_PARAM,
    PULL_RATE_STYLE,
    PULL_RATE_TEXT,
    PULL_RATE_TOOLTIP,
    "pool_summary_param",
    "refresh_every_s",
    "refusal_types",
    "reset_param",
    "row_checks",
    SCRUM_SECTION_LABEL,
    SCRUM_SECTION_STYLE,
    SCRUM_SECTION_VISIBLE,
    SCRUM_TABLE,
    SELECT_EXTRACTOR_PARAM,
    SELECT_FIRST_MESSAGE,
    "select_first_level",
    SELECT_SCRUM_PARAM,
    SKIN,
    "statuses_param",
    STYLE_SHEET,
    TABLE_EXTRACTOR,
    "table_neither",
    TABLE_SCRUMMING,
    TIMER_DELAYS_MS,
    TIMERS
  ];

  var DECLARED_BAGS = [ACTIONS, EXTRACTOR_TABLE, "row_checks", SCRUM_TABLE, SKIN, TIMERS];

  var DECLARED_LISTS = [
    "bot_opens",
    "bus_topics",
    "calls",
    "checks_before_first_cell",
    COMMAND_BUTTONS,
    "commands_sent",
    "logged",
    "new_bot_asks",
    "number_fields",
    PINS,
    "refusal_types",
    TIMER_DELAYS_MS
  ];

  var TABLE_SLOTS = [SCRUM_TABLE, EXTRACTOR_TABLE];

  var TABLE_FIELDS = [
    BOT_IDS,
    "calls",
    CURRENT_ROW,
    "current_column",
    DRAWN,
    DRAWN_ROWS,
    HAS_SELECTION,
    KIND,
    ROW_COUNT,
    SELECTED_BOT_ID,
    "signals_blocked"
  ];

  var PIN_NAME_FIELDS = [
    PIN_COMMAND_ROUTED,
    PIN_EVERY_BOT_DRAWN,
    PIN_PRIVACY_APPLIED,
    PIN_PRIVACY_BUTTON,
    PIN_SELECTION_SURVIVES
  ];

  var SHEET_FIELDS = [
    EXTRACTOR_SECTION_STYLE,
    PRIVACY_STYLE,
    PRIVACY_STYLE_OFF,
    PRIVACY_STYLE_ON,
    PULL_RATE_STYLE,
    SCRUM_SECTION_STYLE,
    STYLE_SHEET
  ];

  var WORD_FIELDS = [
    ADD_BOT_LABEL,
    EXCHANGE_NAME,
    EXTRACTOR_SECTION_LABEL,
    PRIVACY_LABEL,
    PULL_RATE_TEXT,
    SCRUM_SECTION_LABEL,
    SELECT_FIRST_MESSAGE
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_PLAIN_FAULT = "not-plain";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var DISAGREES_FAULT = "disagrees";

  var NAME_FIELD = "name";
  var TABLE_AT = "table:";
  var BUTTON_AT = "button:";
  var PIN_AT = "pin:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var SEMICOLON = ";";
  var COLON = ":";
  var COMMA = ",";
  var HASH = "#";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";

  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";
  // A markup tag a rich-text QLabel reads as formatting rather than words.
  var MARKUP_OPEN = "<";

  // Only these token groups carry a value a CSS length may borrow.
  var LENGTH_GROUPS = ["spacing", "radii", "target_sizes", "table_columns", "focus"];
  // Only this token group carries a value a font size may borrow.
  var FONT_GROUPS = ["type_scale"];

  var NO_BRIDGE = "the preload bridge is not present";

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var CENTER = "center";
  var NOWRAP = "nowrap";
  var ELLIPSIS = "ellipsis";
  var FULL = "100%";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var BUTTON_TAG = "button";

  var TAB_CLASS = "acervator-exchange-tab";

  var TAB_PART = "exchange-tab";
  var HEADER_PART = "header-row";
  var PRIVACY_PART = "privacy-button";
  var NEWS_TICKER_PART = "news-ticker";
  var STRETCH_PART = "header-stretch";
  var ADD_BOT_PART = "add-bot-button";
  var PULL_RATE_PART = "pull-rate";
  var SCRUM_SECTION_PART = "scrum-section";
  var SCRUM_TABLE_PART = "scrum-table";
  var EXTRACTOR_SECTION_PART = "extractor-section";
  var EXTRACTOR_TABLE_PART = "extractor-table";
  var COMMAND_BAR_PART = "command-bar";
  var COMMAND_BUTTON_PART = "command-button";

  // crypto_news_ticker and extractor_bot_table each fill one space here.
  var EMPTY_SPACES = [NEWS_TICKER_PART, EXTRACTOR_TABLE_PART];

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var KIND_ATTR = "data-kind";
  var ROWS_ATTR = "data-rows";
  var DRAWN_ATTR = "data-drawn";
  var SELECTED_ATTR = "data-selected";
  var HELD_ATTR = "data-held";
  var VISIBLE_ATTR = "data-visible";
  var ACCENT_ATTR = "data-accent";
  var DANGER_ATTR = "data-danger";
  var MASKED_ATTR = "data-masked";
  var FOCUS_ATTR = "data-focus-policy";
  var INTERVAL_ATTR = "data-interval-ms";
  var EXCHANGE_ATTR = "data-exchange";
  var ARIA_LABEL = "aria-label";
  var ARIA_PRESSED = "aria-pressed";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  // NOT_FOCUSABLE is the tab index Qt's NoFocus policy leaves a button with.
  var NOT_FOCUSABLE = ZERO - STEP;

  var held = null;
  var exchangeFaults = [];
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

  // An undefined value leaves the attribute off rather than writing text.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // A label value, on the surface's own terms, with an empty one left off.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // `shared_widgets.js` owns the one-carrier rule that names a token.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // Whether `name` sits in one of `groups`, so its meaning matches.
  function inGroups(name, groups) {
    var api = global.acervatorTokens;
    if (!api || typeof api.group !== "function") {
      return false;
    }
    var matched = groups.filter(function (one) {
      return owns(api.group(one), name);
    });
    return Boolean(matched.length);
  }

  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales that value to a length.
  function scaled(value, groups) {
    if (value === null || value === undefined) {
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

  function length(value) {
    return scaled(value, LENGTH_GROUPS);
  }

  function fontSize(value) {
    return scaled(value, FONT_GROUPS);
  }

  // A colour painted through the one token that carries it.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  function headerStyleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // Whether one value counts its alpha in bytes, as Qt does and CSS does not.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return false;
    }
    var fields = String(parts.shift()).split(CLOSE).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined) {
      return false;
    }
    return !carries(alpha, DOT) && !carries(alpha, PERCENT);
  }

  // The reason CSS would read one value as a different colour.
  function qtColour(value) {
    if (hexWord(value).length === HEX_ARGB.length) {
      return HEX_ARGB;
    }
    if (byteAlpha(value)) {
      return RGBA_OPEN;
    }
    return undefined;
  }

  // The sheet without the declarations CSS would read as another colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) === undefined) {
        kept.push(one.property + COLON + one.value);
      }
    });
    return kept.join(SEMICOLON);
  }

  function styleOf(sheet) {
    return headerStyleOf(keptSheet(sheet));
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!hasBridge()) {
      return null;
    }
    return global.acervator.call(METHOD, copyOf(params));
  }

  function actionNamed(model, name) {
    return objectField(model, ACTIONS)[name];
  }

  function paramNamed(model, field) {
    return isPlainObject(model) ? model[field] : undefined;
  }

  // One request, keyed by the name the surface publishes for that field.
  function request(model, field, value) {
    var params = {};
    params[String(paramNamed(model, field))] = value;
    return params;
  }

  function heldModel() {
    return held === null ? {} : held.model;
  }

  function flipPrivacy() {
    var model = heldModel();
    return dispatch(actionNamed(model, PRIVACY_CLICKED), request(model, PRIVACY_PARAM, true));
  }

  function askNewBot() {
    var model = heldModel();
    return dispatch(actionNamed(model, ADD_BOT_CLICKED), request(model, NEW_BOT_PARAM, true));
  }

  function sendCommand(key) {
    var model = heldModel();
    return dispatch(actionNamed(model, COMMAND_CLICKED), request(model, COMMAND_PARAM, key));
  }

  // One tick of the one-second timer Qt runs on the freshness line.
  function tick() {
    var model = heldModel();
    return dispatch(
      actionNamed(model, PULL_RATE_TIMEOUT),
      request(model, PULL_RATE_PARAM, true)
    );
  }

  function selectScrumRow(row) {
    var model = heldModel();
    return dispatch(
      actionNamed(model, SCRUM_SELECTION_CHANGED),
      request(model, SELECT_SCRUM_PARAM, row)
    );
  }

  function selectExtractorRow(row) {
    var model = heldModel();
    return dispatch(
      actionNamed(model, EXTRACTOR_SELECTION_CHANGED),
      request(model, SELECT_EXTRACTOR_PARAM, row)
    );
  }

  function masking(model) {
    return model[PRIVACY_LABEL] === model[PRIVACY_LABEL_ON];
  }

  function PrivacyButton(props) {
    var model = props.model;
    var buttonProps = {
      className: TAB_CLASS,
      style: styleOf(model[PRIVACY_STYLE]),
      type: BUTTON_TYPE,
      title: label(model[PRIVACY_TOOLTIP]),
      onClick: flipPrivacy
    };
    if (model[PRIVACY_FOCUSABLE] === false) {
      buttonProps.tabIndex = NOT_FOCUSABLE;
    }
    buttonProps[PART_ATTR] = PRIVACY_PART;
    buttonProps[ACTION_ATTR] = text(actionNamed(model, PRIVACY_CLICKED));
    buttonProps[MASKED_ATTR] = text(masking(model));
    buttonProps[FOCUS_ATTR] = text(model[PRIVACY_FOCUS_POLICY]);
    buttonProps[ARIA_PRESSED] = text(masking(model));
    return element(BUTTON_TAG, buttonProps, text(model[PRIVACY_LABEL]));
  }

  // The strip crypto_news_ticker fills; this screen draws none of it.
  function NewsTickerSpace(props) {
    var spaceProps = {
      style: { flex: text(props.model[NEWS_TICKER_STRETCH]), overflow: HIDDEN }
    };
    spaceProps[PART_ATTR] = NEWS_TICKER_PART;
    spaceProps[SLOT_ATTR] = NEWS_TICKER_PART;
    return element(DIV_TAG, spaceProps, null);
  }

  // Qt puts plain space where a strip that would not build was to go.
  function HeaderStretch() {
    var spaceProps = { style: { flex: AUTO } };
    spaceProps[PART_ATTR] = STRETCH_PART;
    return element(DIV_TAG, spaceProps, null);
  }

  function AddBotButton(props) {
    var model = props.model;
    var buttonProps = { className: TAB_CLASS, type: BUTTON_TYPE, onClick: askNewBot };
    buttonProps[PART_ATTR] = ADD_BOT_PART;
    buttonProps[ACTION_ATTR] = text(actionNamed(model, ADD_BOT_CLICKED));
    buttonProps[ACCENT_ATTR] = text(model[ADD_BOT_ACCENT]);
    return element(BUTTON_TAG, buttonProps, text(model[ADD_BOT_LABEL]));
  }

  function Header(props) {
    var model = props.model;
    var rowProps = { style: { display: FLEX, flexDirection: ROW, alignItems: CENTER } };
    rowProps[PART_ATTR] = HEADER_PART;
    var middle =
      model[NEWS_TICKER_BUILT] === true
        ? element(NewsTickerSpace, { key: NEWS_TICKER_PART, model: model })
        : element(HeaderStretch, { key: STRETCH_PART });
    return element(
      DIV_TAG,
      rowProps,
      element(PrivacyButton, { key: PRIVACY_PART, model: model }),
      middle,
      element(AddBotButton, { key: ADD_BOT_PART, model: model })
    );
  }

  function PullRate(props) {
    var model = props.model;
    var lineProps = {
      style: styleOf(model[PULL_RATE_STYLE]),
      title: label(model[PULL_RATE_TOOLTIP])
    };
    lineProps.style.whiteSpace = NOWRAP;
    lineProps.style.overflow = HIDDEN;
    lineProps.style.textOverflow = ELLIPSIS;
    lineProps[PART_ATTR] = PULL_RATE_PART;
    lineProps[ACTION_ATTR] = text(actionNamed(model, PULL_RATE_TIMEOUT));
    lineProps[INTERVAL_ATTR] = text(model[PULL_RATE_INTERVAL_MS]);
    return element(DIV_TAG, lineProps, text(model[PULL_RATE_TEXT]));
  }

  function SectionLabel(props) {
    var labelProps = { style: styleOf(props.sheet), hidden: props.visible !== true };
    labelProps.style.whiteSpace = NOWRAP;
    labelProps[PART_ATTR] = props.part;
    labelProps[VISIBLE_ATTR] = text(props.visible);
    return element(DIV_TAG, labelProps, text(props.words));
  }

  // A named space one bot table draws its own rows into.
  function TableSpace(props) {
    var table = objectField(props.model, props.slot);
    var spaceProps = {
      style: { flex: AUTO, overflow: AUTO, minHeight: length(ZERO) },
      hidden: props.visible !== true
    };
    spaceProps[PART_ATTR] = props.part;
    spaceProps[SLOT_ATTR] = props.slot;
    spaceProps[KIND_ATTR] = text(table[KIND]);
    spaceProps[ROWS_ATTR] = text(table[ROW_COUNT]);
    spaceProps[DRAWN_ATTR] = text(table[DRAWN_ROWS]);
    spaceProps[HELD_ATTR] = String(listField(table, BOT_IDS).length);
    spaceProps[SELECTED_ATTR] = text(table[SELECTED_BOT_ID]);
    spaceProps[INDEX_ATTR] = text(table[CURRENT_ROW]);
    spaceProps[VISIBLE_ATTR] = text(props.visible);
    return element(DIV_TAG, spaceProps, null);
  }

  function CommandButton(props) {
    var pair = Array.isArray(props.pair) ? props.pair.slice() : [];
    var words = pair.shift();
    var key = pair.shift();
    var buttonProps = {
      className: TAB_CLASS,
      type: BUTTON_TYPE,
      onClick: function () {
        sendCommand(key);
      }
    };
    buttonProps[PART_ATTR] = COMMAND_BUTTON_PART;
    buttonProps[KEY_ATTR] = text(key);
    buttonProps[INDEX_ATTR] = String(props.at);
    buttonProps[ACTION_ATTR] = text(actionNamed(props.model, COMMAND_CLICKED));
    buttonProps[DANGER_ATTR] = text(words === props.model[DANGER_COMMAND_LABEL]);
    return element(BUTTON_TAG, buttonProps, text(words));
  }

  function CommandBar(props) {
    var model = props.model;
    var barProps = { style: { display: FLEX, flexDirection: ROW, alignItems: CENTER } };
    barProps[PART_ATTR] = COMMAND_BAR_PART;
    var drawn = listField(model, COMMAND_BUTTONS).map(function (pair, at) {
      return element(CommandButton, {
        key: String(at),
        at: at,
        pair: pair,
        model: model
      });
    });
    return element(DIV_TAG, barProps, drawn);
  }

  // The freshness line follows Qt's timer only where a bridge can answer.
  function usePullRateTimer(model) {
    var wait = model[PULL_RATE_INTERVAL_MS];
    hooks().useEffect(
      function () {
        if (!hasBridge() || typeof wait !== "number") {
          return undefined;
        }
        var handle = global.setInterval(tick, wait);
        return function () {
          global.clearInterval(handle);
        };
      },
      [wait]
    );
  }

  // `Tab` draws nothing for a payload that is not an object.
  function Tab(props) {
    usePullRateTimer(isPlainObject(props.model) ? props.model : {});
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN,
        height: FULL,
        overflow: HIDDEN
      }
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[EXCHANGE_ATTR] = text(model[EXCHANGE_ID]);
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(
      DIV_TAG,
      tabProps,
      element(Header, { key: HEADER_PART, model: model }),
      element(PullRate, { key: PULL_RATE_PART, model: model }),
      element(SectionLabel, {
        key: SCRUM_SECTION_PART,
        part: SCRUM_SECTION_PART,
        sheet: model[SCRUM_SECTION_STYLE],
        words: model[SCRUM_SECTION_LABEL],
        visible: model[SCRUM_SECTION_VISIBLE]
      }),
      element(TableSpace, {
        key: SCRUM_TABLE_PART,
        part: SCRUM_TABLE_PART,
        slot: SCRUM_TABLE,
        model: model,
        visible: model[SCRUM_SECTION_VISIBLE]
      }),
      element(SectionLabel, {
        key: EXTRACTOR_SECTION_PART,
        part: EXTRACTOR_SECTION_PART,
        sheet: model[EXTRACTOR_SECTION_STYLE],
        words: model[EXTRACTOR_SECTION_LABEL],
        visible: model[EXTRACTOR_SECTION_VISIBLE]
      }),
      element(TableSpace, {
        key: EXTRACTOR_TABLE_PART,
        part: EXTRACTOR_TABLE_PART,
        slot: EXTRACTOR_TABLE,
        model: model,
        visible: model[EXTRACTOR_SECTION_VISIBLE]
      }),
      element(CommandBar, { key: COMMAND_BAR_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        exchangeFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        exchangeFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkShapes(model) {
    DECLARED_BAGS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        exchangeFaults.push(
          fault(null, field, NOT_AN_OBJECT_FAULT, kindOf(model[field]))
        );
      }
    });
    DECLARED_LISTS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        exchangeFaults.push(fault(null, field, NOT_A_LIST_FAULT, kindOf(model[field])));
      }
    });
  }

  // A wrong type is named only against the table the surface publishes twice.
  function checkTables(model) {
    var first = objectField(model, SCRUM_TABLE);
    TABLE_SLOTS.forEach(function (slot) {
      var table = objectField(model, slot);
      var where = TABLE_AT + slot;
      TABLE_FIELDS.forEach(function (field) {
        if (!owns(first, field) || first[field] === null) {
          return;
        }
        if (!owns(table, field)) {
          exchangeFaults.push(fault(where, field, MISSING_FAULT, null));
          return;
        }
        if (kindOf(table[field]) !== kindOf(first[field])) {
          exchangeFaults.push(
            fault(where, field, WRONG_TYPE_FAULT, kindOf(table[field]))
          );
        }
      });
      checkOneTable(where, table);
    });
  }

  // The table publishes its rows four ways, so each holds the others.
  function checkOneTable(where, table) {
    var ids = listField(table, BOT_IDS);
    var drawn = listField(table, DRAWN);
    if (owns(table, ROW_COUNT) && drawn.length !== table[ROW_COUNT]) {
      exchangeFaults.push(fault(where, ROW_COUNT, DISAGREES_FAULT, drawn.length));
    }
    if (ids.length !== drawn.length) {
      exchangeFaults.push(fault(where, BOT_IDS, DISAGREES_FAULT, drawn.length));
    }
    var painted = drawn.filter(function (one) {
      return one === true;
    });
    if (owns(table, DRAWN_ROWS) && painted.length !== table[DRAWN_ROWS]) {
      exchangeFaults.push(fault(where, DRAWN_ROWS, DISAGREES_FAULT, painted.length));
    }
    if (table[HAS_SELECTION] === false && table[SELECTED_BOT_ID]) {
      exchangeFaults.push(
        fault(where, SELECTED_BOT_ID, DISAGREES_FAULT, table[HAS_SELECTION])
      );
    }
  }

  // The button words and the button key each name one command.
  function checkCommandButtons(model) {
    listField(model, COMMAND_BUTTONS).forEach(function (pair, at) {
      var where = BUTTON_AT + String(at);
      if (!Array.isArray(pair)) {
        exchangeFaults.push(fault(where, COMMAND_BUTTONS, NOT_A_LIST_FAULT, kindOf(pair)));
        return;
      }
      var counted = pair.slice();
      var words = counted.shift();
      var key = counted.shift();
      if (typeof words !== "string" || typeof key !== "string") {
        exchangeFaults.push(fault(where, COMMAND_BUTTONS, WRONG_TYPE_FAULT, kindOf(key)));
      }
    });
  }

  function checkColours(model) {
    SHEET_FIELDS.forEach(function (field) {
      declarations(model[field]).forEach(function (one) {
        var named = qtColour(one.value);
        if (named !== undefined) {
          exchangeFaults.push(fault(one.property, field, QT_COLOUR_FAULT, named));
        }
      });
    });
  }

  function nameMarkup(where, field, value) {
    if (typeof value === "string" && carries(value, MARKUP_OPEN)) {
      exchangeFaults.push(fault(where, field, MARKUP_FAULT, MARKUP_OPEN));
    }
  }

  // Every word this screen draws, refused as markup before React draws it.
  function checkMarkup(model) {
    WORD_FIELDS.forEach(function (field) {
      nameMarkup(null, field, model[field]);
    });
    listField(model, COMMAND_BUTTONS).forEach(function (pair, at) {
      if (Array.isArray(pair)) {
        nameMarkup(BUTTON_AT + String(at), COMMAND_BUTTONS, pair.slice().shift());
      }
    });
    TABLE_SLOTS.forEach(function (slot) {
      listField(objectField(model, slot), BOT_IDS).forEach(function (one, at) {
        nameMarkup(TABLE_AT + slot, String(at), one);
      });
    });
  }

  // The words and the colours on the Privacy button name one register state.
  function checkPrivacyButton(model) {
    var words = model[PRIVACY_LABEL];
    var painted = model[PRIVACY_STYLE];
    if (words !== model[PRIVACY_LABEL_ON] && words !== model[PRIVACY_LABEL_OFF]) {
      exchangeFaults.push(fault(null, PRIVACY_LABEL, DISAGREES_FAULT, kindOf(words)));
      return;
    }
    var wanted = masking(model) ? model[PRIVACY_STYLE_ON] : model[PRIVACY_STYLE_OFF];
    if (painted !== wanted) {
      exchangeFaults.push(fault(null, PRIVACY_STYLE, DISAGREES_FAULT, masking(model)));
    }
  }

  function checkTimers(model) {
    var timers = objectField(model, TIMERS);
    var delays = listField(model, TIMER_DELAYS_MS);
    var wait = model[PULL_RATE_INTERVAL_MS];
    var named = Object.keys(timers).filter(function (one) {
      return timers[one] === wait;
    });
    if (!named.length) {
      exchangeFaults.push(fault(null, TIMERS, DISAGREES_FAULT, wait));
    }
    var listed = delays.filter(function (one) {
      return one === wait;
    });
    if (!listed.length) {
      exchangeFaults.push(fault(null, TIMER_DELAYS_MS, DISAGREES_FAULT, wait));
    }
  }

  // A pin the screen recorded under a name the payload declares nowhere.
  function heldPinCount(model) {
    var names = PIN_NAME_FIELDS.map(function (field) {
      return model[field];
    });
    var kept = listField(model, PINS).filter(function (one) {
      return (
        isPlainObject(one) &&
        Boolean(
          names.filter(function (name) {
            return name === one[NAME_FIELD];
          }).length
        )
      );
    });
    return kept.length;
  }

  function checkPins(model) {
    listField(model, PINS).forEach(function (one, at) {
      if (!isPlainObject(one)) {
        exchangeFaults.push(fault(PIN_AT + String(at), PINS, NOT_AN_OBJECT_FAULT, kindOf(one)));
      }
    });
    if (heldPinCount(model) !== listField(model, PINS).length) {
      exchangeFaults.push(fault(null, PINS, DISAGREES_FAULT, heldPinCount(model)));
    }
  }

  // Every value this payload carries must be data a JSON line can hold.
  function plainness() {
    var found = [];
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
          descend(path + PATH_SPLIT + name, value[name]);
        });
        return;
      }
      if (typeof value === "object" || typeof value === "function") {
        found.push(path);
      }
    }
    if (held !== null) {
      Object.keys(held.model).forEach(function (name) {
        descend(name, held.model[name]);
      });
    }
    return found;
  }

  function checkPlainData(model) {
    plainness().forEach(function (path) {
      exchangeFaults.push(fault(null, path, NOT_PLAIN_FAULT, kindOf(model[path])));
    });
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function declaredRowCount(model) {
    var total = ZERO;
    TABLE_SLOTS.forEach(function (slot) {
      var count = objectField(model, slot)[ROW_COUNT];
      total = total + (typeof count === "number" ? count : ZERO);
    });
    return total;
  }

  function heldRowCount(model) {
    var total = ZERO;
    TABLE_SLOTS.forEach(function (slot) {
      total = total + listField(objectField(model, slot), BOT_IDS).length;
    });
    return total;
  }

  function heldButtonCount(model) {
    return listField(model, COMMAND_BUTTONS).filter(function (pair) {
      return Array.isArray(pair) && pair.length > STEP;
    }).length;
  }

  function report(model) {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: declaredRowCount(model),
        buttons: listField(model, COMMAND_BUTTONS).length,
        pins: listField(model, PINS).length,
        spaces: EMPTY_SPACES.length
      },
      held: {
        fields: heldFieldCount(model),
        rows: heldRowCount(model),
        buttons: heldButtonCount(model),
        pins: heldPinCount(model),
        spaces: EMPTY_SPACES.length
      },
      faults: exchangeFaults.slice()
    };
  }

  function setExchangeTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      exchangeFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: exchangeFaults.slice() };
    }
    held = { model: model };
    exchangeFaults = [];
    checkFields(model);
    checkShapes(model);
    checkTables(model);
    checkCommandButtons(model);
    checkColours(model);
    checkMarkup(model);
    checkPrivacyButton(model);
    checkTimers(model);
    checkPins(model);
    checkPlainData(model);
    return report(model);
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadExchangeTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!hasBridge()) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setExchangeTab(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function payload() {
    return held === null ? null : held.model;
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function bagNames() {
    return DECLARED_BAGS.slice();
  }

  function listNames() {
    return DECLARED_LISTS.slice();
  }

  function emptySpaces() {
    return EMPTY_SPACES.slice();
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function table(slot) {
    return bag(slot);
  }

  // The bot order comes from the list beside the table, never from a bag.
  function botIds(slot) {
    return listField(objectField(heldModel(), slot), BOT_IDS).map(function (one) {
      return String(one);
    });
  }

  function commandKeys() {
    return list(COMMAND_BUTTONS).map(function (pair) {
      return Array.isArray(pair) ? String(pair.slice().pop()) : undefined;
    });
  }

  function actions() {
    return bag(ACTIONS);
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
  }

  function requestFor(name, value) {
    return request(heldModel(), name, value);
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
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
    return exchangeFaults.slice();
  }

  function sent() {
    return dispatched.slice();
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
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = payload();
    }
    return draw(target, element(Tab, { model: drawn }));
  }

  // `bot_status_table.js` draws its own rows into the space this screen keeps.
  function renderScrumTable(target) {
    var api = global.acervatorBotTable;
    var space = target.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + SCRUM_TABLE_PART + SELECT_CLOSE
    );
    if (!api || typeof api.renderTable !== "function" || space === null) {
      return null;
    }
    return api.renderTable(space);
  }

  function forget() {
    held = null;
    exchangeFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetExchangeTab = setExchangeTab;
  global.acervatorLoadExchangeTab = loadExchangeTab;
  global.acervatorExchangeTab = {
    method: METHOD,
    Tab: Tab,
    Header: Header,
    PrivacyButton: PrivacyButton,
    AddBotButton: AddBotButton,
    NewsTickerSpace: NewsTickerSpace,
    PullRate: PullRate,
    SectionLabel: SectionLabel,
    TableSpace: TableSpace,
    CommandBar: CommandBar,
    CommandButton: CommandButton,
    payload: payload,
    field: field,
    declaredNames: declaredNames,
    bagNames: bagNames,
    listNames: listNames,
    emptySpaces: emptySpaces,
    bag: bag,
    list: list,
    table: table,
    botIds: botIds,
    commandKeys: commandKeys,
    actions: actions,
    action: action,
    requestFor: requestFor,
    flipPrivacy: flipPrivacy,
    askNewBot: askNewBot,
    sendCommand: sendCommand,
    selectScrumRow: selectScrumRow,
    selectExtractorRow: selectExtractorRow,
    tick: tick,
    sent: sent,
    styleOf: styleOf,
    keptSheet: keptSheet,
    declarations: declarations,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    fontSize: fontSize,
    kinds: kinds,
    plainness: plainness,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    renderScrumTable: renderScrumTable,
    forget: forget
  };
})(window);
