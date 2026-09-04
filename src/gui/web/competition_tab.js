// The Proof of Accumulation tab, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "competition_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALIGNMENT = "alignment";
  var AWARD_COLUMNS = "award_columns";
  var AWARD_COLUMN_COUNT = "award_column_count";
  var BUS_TOPICS = "bus_topics";
  var CALLS = "calls";
  var COLORS = "colors";
  var CONNECT_BUTTON_ENABLED = "connect_button_enabled";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var IDENTITY_PANEL = "identity_panel";
  var INFO_WORD_WRAP = "info_word_wrap";
  var INNER_SPACING = "inner_spacing";
  var LEADERBOARD_COLUMNS = "leaderboard_columns";
  var LEADERBOARD_COLUMN_COUNT = "leaderboard_column_count";
  var LEADERBOARD_PANEL = "leaderboard_panel";
  var NETWORK_LINES = "network_lines";
  var RELAY_FIELD_ENABLED = "relay_field_enabled";
  var SECTION_ACCESSIBLE_NAME = "section_accessible_name";
  var SECTION_MARGINS = "section_margins";
  var SECTION_NAMES = "section_names";
  var SECTION_SPACING = "section_spacing";
  var STYLES = "styles";
  var SUPPLY_PANEL = "supply_panel";
  var TEXTS = "texts";
  var TIER_COLORS = "tier_colors";
  var TIER_FALLBACK_COLOR = "tier_fallback_color";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var WALLET_BALANCE = "wallet_balance";
  var WALLET_PANEL = "wallet_panel";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ALIGNMENT,
    AWARD_COLUMNS,
    AWARD_COLUMN_COUNT,
    BUS_TOPICS,
    CALLS,
    COLORS,
    CONNECT_BUTTON_ENABLED,
    CONTENT_MARGINS,
    CONTENT_SPACING,
    IDENTITY_PANEL,
    INFO_WORD_WRAP,
    INNER_SPACING,
    LEADERBOARD_COLUMNS,
    LEADERBOARD_COLUMN_COUNT,
    LEADERBOARD_PANEL,
    NETWORK_LINES,
    RELAY_FIELD_ENABLED,
    SECTION_ACCESSIBLE_NAME,
    SECTION_MARGINS,
    SECTION_NAMES,
    SECTION_SPACING,
    STYLES,
    SUPPLY_PANEL,
    TEXTS,
    TIER_COLORS,
    TIER_FALLBACK_COLOR,
    TIMERS,
    TIMER_DELAYS_MS,
    WALLET_BALANCE,
    WALLET_PANEL
  ];

  var HELD = "held";
  var SHORT_TEXT = "short_text";
  var SHORT_STYLE = "short_style";
  var FULL_TEXT = "full_text";
  var FULL_STYLE = "full_style";
  var EMPTY_TEXT = "empty_text";

  var BALANCE_TEXT = "balance_text";
  var BALANCE_STYLE = "balance_style";
  var ROWS = "rows";
  var MAX_HEIGHT = "max_height";

  var LABEL_TEXT = "label_text";
  var LABEL_STYLE = "label_style";
  var VALUE_TEXT = "value_text";
  var VALUE_STYLE = "value_style";

  var CELL_TEXT = "text";
  var CELL_COLOR = "color";

  var TITLE = "title";
  var SUBTITLE = "subtitle";
  var NO_IDENTITY = "no_identity";
  var DOT = "dot";
  var NOT_CONNECTED = "not_connected";
  var RELAY_LABEL = "relay_label";
  var RELAY_URL = "relay_url";
  var CONNECT_BUTTON = "connect_button";
  var NETWORK_LINE_JOIN = "network_line_join";

  var SECTION = "section";
  var SEPARATOR = "separator";
  var STATUS = "status";
  var INFO = "info";
  var URL_LABEL = "url_label";
  var RELAY_FIELD = "relay_field";
  var MONO = "mono";
  var VALUE = "value";
  var SUPPLY_VALUE = "supply_value";
  var LABEL = "label";

  // The surface names its "no colour" reading in the colors bag.
  var NO_COLOR = "none";

  // The five panels, in the order the tab stacks them.
  var PANEL_ORDER = [
    IDENTITY_PANEL,
    WALLET_PANEL,
    SUPPLY_PANEL,
    LEADERBOARD_PANEL,
    NETWORK_LINES
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var SHORT_LIST_FAULT = "short-list";
  var UNNAMED_FAULT = "unnamed";
  var NOT_CSS_FAULT = "not-css";

  var NO_BRIDGE = "the preload bridge is not present";

  var ROW_AT = "row:";
  var COLON = ":";
  var SEMICOLON = ";";
  var EMPTY = "";

  var TAB_CLASS = "acervator-competition-tab";
  var HEADER_CLASS = "acervator-competition-header";
  var SCROLL_CLASS = "acervator-competition-scroll";
  var SECTION_CLASS = "acervator-competition-section";
  var TABLE_CLASS = "acervator-competition-table";

  var TAB_PART = "competition-tab";
  var HEADER_PART = "header";
  var TITLE_PART = "title";
  var SUBTITLE_PART = "subtitle";
  var SEPARATOR_PART = "separator";
  var SCROLL_PART = "scroll";
  var SECTION_PART = "section";
  var SECTION_TITLE_PART = "section-title";
  var IDENTITY_PART = "identity";
  var WALLET_PART = "wallet";
  var SUPPLY_PART = "supply";
  var LEADERBOARD_PART = "leaderboard";
  var NETWORK_PART = "network";
  var BALANCE_PART = "balance";
  var TABLE_PART = "table";
  var HEAD_PART = "table-head";
  var ROW_PART = "table-row";
  var CELL_PART = "table-cell";
  var COLUMN_PART = "supply-column";
  var EMPTY_PART = "empty";
  var STATUS_PART = "status";
  var INFO_PART = "info";
  var RELAY_PART = "relay";

  var PART_ATTR = "data-part";
  var AT_ATTR = "data-at";
  var NAME_ATTR = "data-name";
  var PATH_ATTR = "data-path";
  var ROWS_ATTR = "data-rows";
  var ENABLED_ATTR = "data-enabled";
  var ARIA_LABEL = "aria-label";

  var DIV = "div";
  var SPAN = "span";
  var TABLE = "table";
  var THEAD = "thead";
  var TBODY = "tbody";
  var TR = "tr";
  var TH = "th";
  var TD = "td";
  var INPUT = "input";
  var BUTTON = "button";
  var HR = "hr";
  var GROUP_ROLE = "group";

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var AUTO = "auto";
  var CENTER = "center";
  var WRAP_ON = "normal";
  var WRAP_OFF = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var BLOCK = "block";
  var SPREAD = "space-between";
  var PX = "px";

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var tabFaults = [];
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
    Object.keys(bag).forEach(function (name) {
      found[name] = bag[name];
    });
    return found;
  }

  function holds(items, value) {
    return items.some(function (one) {
      return one === value;
    });
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

  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function marginStyle(model, field) {
    var style = {};
    var margins = listField(model, field);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = pixels(margins[at]);
      }
    });
    return style;
  }

  // sheetApi answers null when acervatorHeader is absent, so styleOf paints nothing.
  function sheetApi() {
    var api = global.acervatorHeader;
    var usable =
      api &&
      typeof api.styleOf === "function" &&
      typeof api.declarations === "function";
    return usable ? api : null;
  }

  function styleOf(sheet) {
    var api = sheetApi();
    return api === null ? {} : api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === null ? [] : api.declarations(sheet);
  }

  // A Qt group box writes its title in a `::title` rule the base block omits.
  function stateRules(sheet) {
    var api = sheetApi();
    if (api === null || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  function stateStyle(sheet) {
    var found = stateRules(sheet);
    return found.length ? styleOf(found[0].body) : {};
  }

  // Every property of one sheet that styleOf paints nothing from.
  function unpaintable(sheet) {
    var found = [];
    declarations(sheet).forEach(function (one) {
      var alone = one.property + COLON + one.value + SEMICOLON;
      if (!Object.keys(styleOf(alone)).length) {
        found.push(one.property);
      }
    });
    return found;
  }

  function styleNamed(model, name) {
    return styleOf(objectField(model, STYLES)[name]);
  }

  function textNamed(model, name) {
    return objectField(model, TEXTS)[name];
  }

  // A cell paints its own colour only when the surface published one.
  function cellStyle(model, cell) {
    var style = {};
    var none = objectField(model, COLORS)[NO_COLOR];
    var colour = cell[CELL_COLOR];
    if (typeof colour === "string" && colour !== EMPTY && colour !== none) {
      style.color = colour;
    }
    if (cell[ALIGNMENT] === model[ALIGNMENT]) {
      style.textAlign = CENTER;
    }
    return style;
  }

  function cellObject(cell) {
    return isPlainObject(cell) ? cell : {};
  }

  function rowsOf(panel) {
    return listField(panel, ROWS).filter(function (one) {
      return Array.isArray(one);
    });
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tabFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A table row must carry one cell for each column header the surface names.
  function checkTable(where, panel, columnCount) {
    rowsOf(panel).forEach(function (one, at) {
      if (one.length !== columnCount) {
        tabFaults.push(fault(where + ROW_AT + String(at), ROWS, SHORT_LIST_FAULT, one.length));
      }
      one.forEach(function (cell) {
        if (!isPlainObject(cell)) {
          tabFaults.push(fault(where + ROW_AT + String(at), ROWS, WRONG_TYPE_FAULT, kindOf(cell)));
        }
      });
    });
  }

  // Every tier colour a wallet cell paints must be one the surface published.
  function checkTierColours(model) {
    var named = objectField(model, TIER_COLORS);
    var allowed = Object.keys(named).map(function (name) {
      return named[name];
    });
    allowed.push(model[TIER_FALLBACK_COLOR]);
    allowed.push(objectField(model, COLORS)[NO_COLOR]);
    rowsOf(objectField(model, WALLET_PANEL)).forEach(function (one, at) {
      one.forEach(function (cell) {
        var colour = cellObject(cell)[CELL_COLOR];
        if (colour !== undefined && !holds(allowed, colour)) {
          tabFaults.push(fault(WALLET_PANEL + ROW_AT + String(at), CELL_COLOR, UNNAMED_FAULT, colour));
        }
      });
    });
  }

  // A Qt-only paint reaches no CSS property, so the renderer would drop it.
  function checkStyles(model) {
    var sheets = objectField(model, STYLES);
    Object.keys(sheets).forEach(function (name) {
      unpaintable(sheets[name]).forEach(function (property) {
        tabFaults.push(fault(STYLES, name, NOT_CSS_FAULT, property));
      });
    });
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function heldRowTotal(model) {
    return (
      rowsOf(objectField(model, WALLET_PANEL)).length +
      rowsOf(objectField(model, LEADERBOARD_PANEL)).length
    );
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        panels: PANEL_ORDER.length,
        sections: listField(model, SECTION_NAMES).length
      },
      held: {
        fields: heldFieldCount(model),
        panels: PANEL_ORDER.filter(function (name) {
          return owns(model, name);
        }).length,
        rows: heldRowTotal(model)
      },
      faults: tabFaults.slice()
    };
  }

  function setCompetitionTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: model };
    tabFaults = [];
    checkFields(model);
    checkTable(WALLET_PANEL, objectField(model, WALLET_PANEL), model[AWARD_COLUMN_COUNT]);
    checkTable(
      LEADERBOARD_PANEL,
      objectField(model, LEADERBOARD_PANEL),
      model[LEADERBOARD_COLUMN_COUNT]
    );
    checkTierColours(model);
    checkStyles(model);
    return report();
  }

  // loadCompetitionTab asks once per page and clears asked when the call is refused.
  function loadCompetitionTab(params) {
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
        setCompetitionTab(model);
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

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Cell(props) {
    var cell = cellObject(props.cell);
    var cellProps = {
      className: TABLE_CLASS,
      style: cellStyle(props.model, cell)
    };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[AT_ATTR] = text(props.at);
    return element(props.tag, cellProps, text(cell[CELL_TEXT]));
  }

  function HeaderRow(props) {
    var rowProps = {};
    rowProps[PART_ATTR] = HEAD_PART;
    return element(
      TR,
      rowProps,
      props.columns.map(function (one, at) {
        var headProps = { className: TABLE_CLASS, key: String(at) };
        headProps[PART_ATTR] = CELL_PART;
        headProps[AT_ATTR] = String(at);
        return element(TH, headProps, text(one));
      })
    );
  }

  function CellTable(props) {
    var tableProps = { className: TABLE_CLASS, style: props.style };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[NAME_ATTR] = props.name;
    tableProps[ROWS_ATTR] = String(props.rows.length);
    var body = props.rows.map(function (one, at) {
      var rowProps = { key: String(at) };
      rowProps[PART_ATTR] = ROW_PART;
      rowProps[AT_ATTR] = String(at);
      return element(
        TR,
        rowProps,
        one.map(function (cell, column) {
          return element(Cell, {
            cell: cell,
            model: props.model,
            tag: TD,
            at: column,
            key: String(column)
          });
        })
      );
    });
    return element(
      TABLE,
      tableProps,
      element(THEAD, null, element(HeaderRow, { columns: props.columns })),
      element(TBODY, null, body)
    );
  }

  function EmptyLine(props) {
    var lineProps = { className: SECTION_CLASS };
    lineProps[PART_ATTR] = EMPTY_PART;
    lineProps[NAME_ATTR] = props.name;
    return element(DIV, lineProps, text(props.text));
  }

  function Section(props) {
    var model = props.model;
    var style = styleNamed(model, SECTION);
    var margins = marginStyle(model, SECTION_MARGINS);
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.gap = pixels(model[SECTION_SPACING]);
    Object.keys(margins).forEach(function (side) {
      style[side] = margins[side];
    });
    var sectionProps = { className: SECTION_CLASS, role: GROUP_ROLE, style: style };
    sectionProps[PART_ATTR] = SECTION_PART;
    sectionProps[NAME_ATTR] = props.name;
    sectionProps[ARIA_LABEL] = text(model[SECTION_ACCESSIBLE_NAME]);
    var titleProps = { style: stateStyle(objectField(model, STYLES)[SECTION]) };
    titleProps[PART_ATTR] = SECTION_TITLE_PART;
    titleProps[NAME_ATTR] = props.name;
    return element(
      DIV,
      sectionProps,
      element(DIV, titleProps, text(props.title)),
      props.children
    );
  }

  function IdentityPanel(props) {
    var model = props.model;
    var panel = objectField(model, IDENTITY_PANEL);
    if (!panel[HELD]) {
      return element(EmptyLine, {
        name: IDENTITY_PART,
        text: panel[EMPTY_TEXT] === undefined ? textNamed(model, NO_IDENTITY) : panel[EMPTY_TEXT]
      });
    }
    var rowProps = { style: { display: FLEX, flexDirection: ROW, gap: pixels(model[SECTION_SPACING]) } };
    rowProps[PART_ATTR] = IDENTITY_PART;
    var shortProps = { style: styleOf(panel[SHORT_STYLE]) };
    shortProps[NAME_ATTR] = VALUE;
    var fullProps = { style: styleOf(panel[FULL_STYLE]) };
    fullProps[NAME_ATTR] = MONO;
    return element(
      DIV,
      rowProps,
      element(SPAN, shortProps, text(panel[SHORT_TEXT])),
      element(SPAN, fullProps, text(panel[FULL_TEXT]))
    );
  }

  function WalletPanel(props) {
    var model = props.model;
    var panel = objectField(model, WALLET_PANEL);
    var rows = rowsOf(panel);
    var walletProps = { style: { display: FLEX, flexDirection: COLUMN, gap: pixels(model[SECTION_SPACING]) } };
    walletProps[PART_ATTR] = WALLET_PART;
    walletProps[PATH_ATTR] = text(panel.path);
    var balanceProps = { style: styleOf(panel[BALANCE_STYLE]) };
    balanceProps[PART_ATTR] = BALANCE_PART;
    var tail = rows.length
      ? element(CellTable, {
          model: model,
          name: WALLET_PART,
          columns: listField(model, AWARD_COLUMNS),
          rows: rows,
          style: { maxHeight: pixels(panel[MAX_HEIGHT]), overflowY: AUTO, display: BLOCK }
        })
      : element(EmptyLine, { name: WALLET_PART, text: panel[EMPTY_TEXT] });
    return element(
      DIV,
      walletProps,
      element(DIV, balanceProps, text(panel[BALANCE_TEXT])),
      tail
    );
  }

  function SupplyColumn(props) {
    var column = isPlainObject(props.column) ? props.column : {};
    var columnProps = {
      style: { display: FLEX, flexDirection: COLUMN, textAlign: CENTER }
    };
    columnProps[PART_ATTR] = COLUMN_PART;
    columnProps[AT_ATTR] = String(props.at);
    columnProps[NAME_ATTR] = text(column[LABEL_TEXT]);
    var labelProps = { style: styleOf(column[LABEL_STYLE]) };
    labelProps[NAME_ATTR] = LABEL;
    var valueProps = { style: styleOf(column[VALUE_STYLE]) };
    valueProps[NAME_ATTR] = SUPPLY_VALUE;
    return element(
      DIV,
      columnProps,
      element(DIV, labelProps, text(column[LABEL_TEXT])),
      element(DIV, valueProps, text(column[VALUE_TEXT]))
    );
  }

  function SupplyPanel(props) {
    var model = props.model;
    var panelProps = {
      style: { display: FLEX, flexDirection: ROW, gap: pixels(model[SECTION_SPACING]) }
    };
    panelProps[PART_ATTR] = SUPPLY_PART;
    return element(
      DIV,
      panelProps,
      listField(model, SUPPLY_PANEL).map(function (one, at) {
        return element(SupplyColumn, { column: one, at: at, key: String(at) });
      })
    );
  }

  function LeaderboardPanel(props) {
    var model = props.model;
    var panel = objectField(model, LEADERBOARD_PANEL);
    var rows = rowsOf(panel);
    var panelProps = {};
    panelProps[PART_ATTR] = LEADERBOARD_PART;
    panelProps[PATH_ATTR] = text(panel.path);
    return element(
      DIV,
      panelProps,
      rows.length
        ? element(CellTable, {
            model: model,
            name: LEADERBOARD_PART,
            columns: listField(model, LEADERBOARD_COLUMNS),
            rows: rows,
            style: {}
          })
        : element(EmptyLine, { name: LEADERBOARD_PART, text: panel[EMPTY_TEXT] })
    );
  }

  function NetworkPanel(props) {
    var model = props.model;
    var join = textNamed(model, NETWORK_LINE_JOIN);
    var panelProps = {
      style: { display: FLEX, flexDirection: COLUMN, gap: pixels(model[SECTION_SPACING]) }
    };
    panelProps[PART_ATTR] = NETWORK_PART;
    var statusProps = {
      style: { display: FLEX, flexDirection: ROW, gap: pixels(model[SECTION_SPACING]) }
    };
    statusProps[PART_ATTR] = STATUS_PART;
    var infoStyle = styleNamed(model, INFO);
    infoStyle.whiteSpace = model[INFO_WORD_WRAP] ? PRE_WRAP : WRAP_OFF;
    var infoProps = { style: infoStyle };
    infoProps[PART_ATTR] = INFO_PART;
    var relayProps = {
      style: { display: FLEX, flexDirection: ROW, gap: pixels(model[SECTION_SPACING]) }
    };
    relayProps[PART_ATTR] = RELAY_PART;
    var fieldProps = {
      className: SECTION_CLASS,
      readOnly: true,
      disabled: !model[RELAY_FIELD_ENABLED],
      value: text(textNamed(model, RELAY_URL)),
      onChange: function () {},
      style: styleNamed(model, RELAY_FIELD)
    };
    fieldProps[NAME_ATTR] = RELAY_URL;
    fieldProps[ENABLED_ATTR] = String(Boolean(model[RELAY_FIELD_ENABLED]));
    var buttonProps = {
      type: BUTTON,
      disabled: !model[CONNECT_BUTTON_ENABLED],
      style: styleNamed(model, CONNECT_BUTTON)
    };
    buttonProps[NAME_ATTR] = CONNECT_BUTTON;
    buttonProps[ENABLED_ATTR] = String(Boolean(model[CONNECT_BUTTON_ENABLED]));
    return element(
      DIV,
      panelProps,
      element(
        DIV,
        statusProps,
        element(SPAN, { style: styleNamed(model, DOT) }, text(textNamed(model, DOT))),
        element(SPAN, { style: styleNamed(model, STATUS) }, text(textNamed(model, NOT_CONNECTED)))
      ),
      element(DIV, infoProps, list(NETWORK_LINES).join(typeof join === "string" ? join : EMPTY)),
      element(
        DIV,
        relayProps,
        element(SPAN, { style: styleNamed(model, URL_LABEL) }, text(textNamed(model, RELAY_LABEL))),
        element(INPUT, fieldProps),
        element(BUTTON, buttonProps, text(textNamed(model, CONNECT_BUTTON)))
      )
    );
  }

  var PANEL_BODIES = [
    IdentityPanel,
    WalletPanel,
    SupplyPanel,
    LeaderboardPanel,
    NetworkPanel
  ];

  function CompetitionTab(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var style = marginStyle(model, CONTENT_MARGINS);
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.gap = pixels(model[CONTENT_SPACING]);
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = text(model[ACCESSIBLE_NAME]);
    var headerProps = {
      className: HEADER_CLASS,
      style: { display: FLEX, flexDirection: ROW, justifyContent: SPREAD }
    };
    headerProps[PART_ATTR] = HEADER_PART;
    var titleProps = { style: styleNamed(model, TITLE) };
    titleProps[PART_ATTR] = TITLE_PART;
    var subtitleProps = { style: styleNamed(model, SUBTITLE) };
    subtitleProps[PART_ATTR] = SUBTITLE_PART;
    var separatorProps = { style: styleNamed(model, SEPARATOR) };
    separatorProps[PART_ATTR] = SEPARATOR_PART;
    var scrollProps = {
      className: SCROLL_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN,
        gap: pixels(model[INNER_SPACING]),
        overflowY: AUTO,
        whiteSpace: WRAP_ON
      }
    };
    scrollProps[PART_ATTR] = SCROLL_PART;
    var names = listField(model, SECTION_NAMES);
    var sections = PANEL_BODIES.map(function (body, at) {
      return element(
        Section,
        { model: model, name: PANEL_ORDER[at], title: names[at], key: String(at) },
        element(body, { model: model })
      );
    });
    return element(
      DIV,
      tabProps,
      element(
        DIV,
        headerProps,
        element(SPAN, titleProps, text(textNamed(model, TITLE))),
        element(SPAN, subtitleProps, text(textNamed(model, SUBTITLE)))
      ),
      element(HR, separatorProps),
      element(DIV, scrollProps, sections)
    );
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

  // flushSync makes the document current before draw returns.
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
    return draw(target, element(CompetitionTab, { model: payload }));
  }

  function faults() {
    return tabFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetCompetitionTab = setCompetitionTab;
  global.acervatorLoadCompetitionTab = loadCompetitionTab;
  global.acervatorCompetitionTab = {
    method: METHOD,
    CompetitionTab: CompetitionTab,
    Section: Section,
    CellTable: CellTable,
    Cell: Cell,
    EmptyLine: EmptyLine,
    IdentityPanel: IdentityPanel,
    WalletPanel: WalletPanel,
    SupplyPanel: SupplyPanel,
    SupplyColumn: SupplyColumn,
    LeaderboardPanel: LeaderboardPanel,
    NetworkPanel: NetworkPanel,
    accessibleName: function () {
      return field(ACCESSIBLE_NAME);
    },
    sectionNames: function () {
      return list(SECTION_NAMES);
    },
    texts: function () {
      return bag(TEXTS);
    },
    styles: function () {
      return bag(STYLES);
    },
    colors: function () {
      return bag(COLORS);
    },
    tierColors: function () {
      return bag(TIER_COLORS);
    },
    identityPanel: function () {
      return bag(IDENTITY_PANEL);
    },
    walletPanel: function () {
      return bag(WALLET_PANEL);
    },
    supplyPanel: function () {
      return list(SUPPLY_PANEL);
    },
    leaderboardPanel: function () {
      return bag(LEADERBOARD_PANEL);
    },
    networkLines: function () {
      return list(NETWORK_LINES);
    },
    walletBalance: function () {
      return field(WALLET_BALANCE);
    },
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    panelOrder: function () {
      return PANEL_ORDER.slice();
    },
    cellStyle: cellStyle,
    styleOf: styleOf,
    stateStyle: stateStyle,
    declarations: declarations,
    unpaintable: unpaintable,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
