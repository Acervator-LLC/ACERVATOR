// Draws the Local Testnet tab from the testnet_tab.state payload.
//
// Every value drawn here -- titles, columns, colours, style sheets,
// button text and spin ranges -- arrives from
// `src/gui/main_tabs/testnet_tab_surface.py`. The module holds none of
// its own.
//
// The payload carries the tab as a flat node list, each node naming its
// parent, so `Tab` walks that tree instead of writing a layout of its
// own. A node's `kind` chooses the component that draws it.
//
// The bridge handler rewrites every Qt alpha byte as the share CSS
// reads before it publishes, so a colour arriving here is the one a
// browser paints. Nothing here scales an alpha a second time.
(function (global) {
  "use strict";

  var METHOD = "testnet_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALIGNMENT = "alignment";
  var BUS_TOPICS = "bus_topics";
  var CHILDREN_COLLAPSIBLE = "children_collapsible";
  var COLOR = "color";
  var COLUMNS = "columns";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var CURRENT_INDEX = "current_index";
  var DECIMALS = "decimals";
  var ENABLED = "enabled";
  var EVENT_COLORS = "event_colors";
  var EVENT_FALLBACK_COLOR = "event_fallback_color";
  var FIXED_WIDTH = "fixed_width";
  var FORMATS = "formats";
  var HANDLE_WIDTH = "handle_width";
  var ITEMS = "items";
  var KIND = "kind";
  var LOG_LINE = "log_line";
  var LOG_LINES = "log_lines";
  var MAX_HEIGHT = "max_height";
  var MAXIMUM = "maximum";
  var MINIMUM = "minimum";
  var NAME = "name";
  var PARENT = "parent";
  var READ_ONLY = "read_only";
  var REFRESH_INTERVAL_MS = "refresh_interval_ms";
  var ROWS = "rows";
  var STYLE_SHEET = "style_sheet";
  var TEXT = "text";
  var TIER_COLORS = "tier_colors";
  var TIER_FALLBACK_COLOR = "tier_fallback_color";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TITLE = "title";
  var VALUE = "value";
  var WIDGET_CHILDREN = "widget_children";
  var WIDGETS = "widgets";

  // The kinds the payload names, each drawn by its own component.
  var TAB_KIND = "QWidget";
  var ROW_LAYOUT_KIND = "QHBoxLayout";
  var COLUMN_LAYOUT_KIND = "QVBoxLayout";
  var STRETCH_KIND = "stretch";
  var LABEL_KIND = "QLabel";
  var FRAME_KIND = "QFrame";
  var GROUP_KIND = "QGroupBox";
  var SPIN_KIND = "QSpinBox";
  var DOUBLE_SPIN_KIND = "QDoubleSpinBox";
  var COMBO_KIND = "QComboBox";
  var BUTTON_KIND = "QPushButton";
  var SPLITTER_KIND = "QSplitter";
  var TABLE_KIND = "QTableWidget";
  var LOG_KIND = "QTextEdit";

  var DIV_TAG = "div";
  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";

  var NODE_ATTR = "data-node";
  var KIND_ATTR = "data-kind";
  var PART_ATTR = "data-part";
  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var ACTION_ATTR = "data-action";
  var ARIA_LABEL = "aria-label";

  var GROUP_TITLE_PART = "group-title";
  var GROUP_BODY_PART = "group-body";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var HEAD_ROW_PART = "head-row";
  var COLUMN_PART = "column";
  var LOG_PART = "log-line";
  var LOG_STAMP_PART = "log-stamp";
  var LOG_TEXT_PART = "log-text";

  var TAB_CLASS = "acervator-testnet";
  var NUMBER_TYPE = "number";
  var FLEX = "flex";
  var COLUMN_FLOW = "column";
  var ROW_FLOW = "row";
  var NONE = "none";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var FULL = "100%";
  var BORDER_BOX = "border-box";
  var COLLAPSE = "collapse";
  var FIXED = "fixed";
  var CENTER = "center";
  var NOWRAP = "nowrap";
  var PX = "px";
  var DOT = ".";
  var EMPTY = "";
  var STAMP_KEY = "stamp";
  var TEXT_KEY = "text";
  var COLOR_KEY = "color";
  var NO_BRIDGE = "the preload bridge is not present";
  var NOT_AN_OBJECT = "not-an-object";

  var STEP = Number(true);
  var ZERO = Number(EMPTY);

  // The four published margins, left, top, right and bottom in order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  // The alignment word the surface publishes, as the CSS that centres.
  var ALIGNED = { AlignCenter: CENTER };

  var held = null;
  var loadFault = null;
  var asked = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return isPlainObject(bag) && Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(model, field) {
    return owns(model, field) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return owns(model, field) && Array.isArray(model[field]) ? model[field] : [];
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function text(value) {
    return value === null || value === undefined ? EMPTY : String(value);
  }

  function isFilledText(value) {
    return typeof value === "string" && value.length > ZERO;
  }

  function length(value) {
    return typeof value === "number" ? String(value) + PX : undefined;
  }

  // ---- the published table, read back ---------------------------------

  function payload() {
    return held === null ? null : held;
  }

  // The held payload, or an empty table, so a reader never dereferences
  // nothing.
  function loaded() {
    return held === null ? {} : held;
  }

  function isLoaded() {
    return held !== null;
  }

  function loadError() {
    return loadFault;
  }

  function nodes() {
    return listField(held, WIDGETS);
  }

  function nodeNames() {
    return nodes().map(function (one) {
      return one[NAME];
    });
  }

  function node(name) {
    var found = null;
    nodes().forEach(function (one) {
      if (found === null && one[NAME] === name) {
        found = one;
      }
    });
    return found;
  }

  function childrenOf(name) {
    var children = objectField(held, WIDGET_CHILDREN);
    return owns(children, name) ? children[name].slice() : [];
  }

  // The rows key whose name opens the table node's own name, so the
  // pairing follows the payload rather than a table written here.
  function rowsKeyFor(name) {
    var found;
    Object.keys(objectField(held, ROWS)).forEach(function (key) {
      if (found === undefined && text(name).indexOf(key) === ZERO) {
        found = key;
      }
    });
    return found;
  }

  function rowsFor(name) {
    var key = rowsKeyFor(name);
    return key === undefined ? [] : listField(objectField(held, ROWS), key);
  }

  function columnsFor(name) {
    var found = node(name);
    return found === null ? [] : listField(found, COLUMNS);
  }

  function logLines() {
    return listField(held, LOG_LINES);
  }

  // The action the payload names for one node, read off the key whose
  // part before the first dot is that node's name.
  function actionFor(name) {
    var actions = objectField(held, ACTIONS);
    var found;
    Object.keys(actions).forEach(function (key) {
      if (found === undefined && key.split(DOT).shift() === name) {
        found = actions[key];
      }
    });
    return found;
  }

  function actions() {
    return copyOf(objectField(held, ACTIONS));
  }

  function timers() {
    return copyOf(objectField(held, TIMERS));
  }

  function timerDelaysMs() {
    return listField(held, TIMER_DELAYS_MS).slice();
  }

  function refreshIntervalMs() {
    return owns(held, REFRESH_INTERVAL_MS) ? held[REFRESH_INTERVAL_MS] : undefined;
  }

  function busTopics() {
    return listField(held, BUS_TOPICS).slice();
  }

  function colourFrom(field, fallback, name) {
    var table = objectField(held, field);
    if (owns(table, name)) {
      return table[name];
    }
    return owns(held, fallback) ? held[fallback] : undefined;
  }

  function tierColour(name) {
    return colourFrom(TIER_COLORS, TIER_FALLBACK_COLOR, name);
  }

  function eventColour(name) {
    return colourFrom(EVENT_COLORS, EVENT_FALLBACK_COLOR, name);
  }

  // The three pieces of one log line, split on the separators the
  // published `log_line` format itself puts between them.
  function logParts(line) {
    var format = objectField(held, FORMATS)[LOG_LINE];
    if (!isFilledText(format) || !isFilledText(line)) {
      return null;
    }
    var walls = [];
    var rest = format;
    [STAMP_KEY, COLOR_KEY, TEXT_KEY].forEach(function (key) {
      var mark = "{" + key + "}";
      var at = rest.indexOf(mark);
      if (at < ZERO) {
        walls = null;
        return;
      }
      if (walls !== null) {
        walls.push(rest.slice(ZERO, at));
        rest = rest.slice(at + mark.length);
      }
    });
    if (walls === null) {
      return null;
    }
    walls.push(rest);
    var cursor = line;
    var taken = [];
    for (var at = ZERO; at < walls.length; at += STEP) {
      if (cursor.indexOf(walls[at]) !== ZERO) {
        return null;
      }
      cursor = cursor.slice(walls[at].length);
      if (at + STEP < walls.length) {
        var stop = cursor.indexOf(walls[at + STEP]);
        if (stop < ZERO) {
          return null;
        }
        taken.push(cursor.slice(ZERO, stop));
        cursor = cursor.slice(stop);
      }
    }
    var answer = {};
    answer[STAMP_KEY] = taken[ZERO];
    answer[COLOR_KEY] = taken[STEP];
    answer[TEXT_KEY] = taken[STEP + STEP];
    return answer;
  }

  // ---- loading -------------------------------------------------------

  function setTestnetTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      return { loaded: false, fault: NOT_AN_OBJECT };
    }
    held = model;
    return { loaded: true, fault: null };
  }

  function loadTestnetTab(params) {
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
        setTestnetTab(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function forget() {
    held = null;
    loadFault = null;
    asked = null;
  }

  // ---- the styles the components paint with ---------------------------

  // The declared style of one Qt sheet, read through the shared reader
  // so one parser serves every panel.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  function withAlignment(style, word) {
    if (owns(ALIGNED, word)) {
      style.textAlign = ALIGNED[word];
    }
    return style;
  }

  function boxStyle(direction) {
    return {
      display: FLEX,
      flexDirection: direction,
      boxSizing: BORDER_BOX,
      minWidth: ZERO,
      minHeight: ZERO
    };
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function nodeProps(declared, style) {
    var props = { className: TAB_CLASS, style: style };
    props[NODE_ATTR] = text(declared[NAME]);
    props[KIND_ATTR] = text(declared[KIND]);
    return props;
  }

  // ---- the components -------------------------------------------------

  function Children(props) {
    return childrenOf(props.name).map(function (one) {
      return element(Node, { key: one, name: one, onAction: props.onAction });
    });
  }

  function Root(props) {
    var declared = props.declared;
    var style = boxStyle(COLUMN_FLOW);
    style.height = FULL;
    style.overflow = AUTO;
    listField(loaded(), CONTENT_MARGINS).forEach(function (one, at) {
      if (at < PADDING_SIDES.length) {
        style[PADDING_SIDES[at]] = length(one);
      }
    });
    style.gap = length(loaded()[CONTENT_SPACING]);
    var props2 = nodeProps(declared, style);
    props2[ARIA_LABEL] = text(declared[ACCESSIBLE_NAME]);
    return element(DIV_TAG, props2, Children(props));
  }

  function Row(props) {
    var style = boxStyle(ROW_FLOW);
    style.alignItems = CENTER;
    style.gap = length(loaded()[CONTENT_SPACING]);
    return element(DIV_TAG, nodeProps(props.declared, style), Children(props));
  }

  function Column(props) {
    var style = boxStyle(COLUMN_FLOW);
    return element(DIV_TAG, nodeProps(props.declared, style), Children(props));
  }

  function Stretch(props) {
    return element(DIV_TAG, nodeProps(props.declared, { flex: AUTO }), null);
  }

  function TextLabel(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.flex = NONE;
    style.whiteSpace = NOWRAP;
    withAlignment(style, declared[ALIGNMENT]);
    var props2 = nodeProps(declared, style);
    props2[ARIA_LABEL] = text(declared[TEXT]);
    return element(DIV_TAG, props2, text(declared[TEXT]));
  }

  function Separator(props) {
    var style = styleOf(props.declared[STYLE_SHEET]);
    style.flex = NONE;
    return element(DIV_TAG, nodeProps(props.declared, style), null);
  }

  // A group box draws its title above its body, as Qt's frame does.
  function GroupBox(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.display = FLEX;
    style.flexDirection = COLUMN_FLOW;
    style.boxSizing = BORDER_BOX;
    style.minWidth = ZERO;
    var props2 = nodeProps(declared, style);
    props2[ARIA_LABEL] = text(declared[TITLE]);
    var titleProps = { className: TAB_CLASS, style: { flex: NONE } };
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    var bodyProps = { className: TAB_CLASS, style: boxStyle(COLUMN_FLOW) };
    bodyProps[PART_ATTR] = GROUP_BODY_PART;
    return element(
      DIV_TAG,
      props2,
      element(DIV_TAG, titleProps, text(declared[TITLE])),
      element(DIV_TAG, bodyProps, Children(props))
    );
  }

  function NumberBox(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.flex = NONE;
    style.width = length(declared[FIXED_WIDTH]);
    style.boxSizing = BORDER_BOX;
    var props2 = nodeProps(declared, style);
    props2.type = NUMBER_TYPE;
    props2.min = declared[MINIMUM];
    props2.max = declared[MAXIMUM];
    props2.value = text(declared[VALUE]);
    props2.readOnly = true;
    props2[ARIA_LABEL] = text(declared[NAME]);
    if (owns(declared, DECIMALS)) {
      props2[COLUMN_ATTR] = text(declared[DECIMALS]);
    }
    var action = actionFor(declared[NAME]);
    props2[ACTION_ATTR] = text(action);
    props2.onClick = function () {
      if (typeof props.onAction === "function" && action !== undefined) {
        props.onAction(action, declared[VALUE]);
      }
    };
    return element(INPUT_TAG, props2, null);
  }

  function DropList(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.flex = NONE;
    style.width = length(declared[FIXED_WIDTH]);
    style.boxSizing = BORDER_BOX;
    var props2 = nodeProps(declared, style);
    props2.value = text(declared[CURRENT_INDEX]);
    props2.onChange = function () {};
    props2[ARIA_LABEL] = text(declared[NAME]);
    return element(
      SELECT_TAG,
      props2,
      listField(declared, ITEMS).map(function (one, at) {
        return element(OPTION_TAG, { key: String(at), value: String(at) }, text(one));
      })
    );
  }

  function ActionButton(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.flex = NONE;
    var props2 = nodeProps(declared, style);
    var action = actionFor(declared[NAME]);
    props2.disabled = declared[ENABLED] === false;
    props2[ACTION_ATTR] = text(action);
    props2[ARIA_LABEL] = text(declared[TEXT]);
    props2.onClick = function () {
      if (typeof props.onAction === "function" && action !== undefined) {
        props.onAction(action, declared[NAME]);
      }
    };
    return element(BUTTON_TAG, props2, text(declared[TEXT]));
  }

  // The splitter lays its panels side by side, its handle width the gap.
  function Splitter(props) {
    var declared = props.declared;
    var style = boxStyle(ROW_FLOW);
    style.gap = length(declared[HANDLE_WIDTH]);
    var props2 = nodeProps(declared, style);
    props2[ACTION_ATTR] = text(declared[CHILDREN_COLLAPSIBLE]);
    return element(DIV_TAG, props2, Children(props));
  }

  function HeaderCell(props) {
    var cellProps = {
      className: TAB_CLASS,
      style: { textAlign: CENTER, whiteSpace: NOWRAP }
    };
    cellProps[PART_ATTR] = COLUMN_PART;
    cellProps[COLUMN_ATTR] = String(props.at);
    cellProps[ARIA_LABEL] = text(props.name);
    return element(HEAD_CELL_TAG, cellProps, text(props.name));
  }

  function BodyCell(props) {
    var declared = isPlainObject(props.cell) ? props.cell : {};
    var style = { whiteSpace: NOWRAP, overflow: HIDDEN };
    withAlignment(style, declared[ALIGNMENT]);
    if (isFilledText(declared[COLOR])) {
      style.color = declared[COLOR];
    }
    var cellProps = { className: TAB_CLASS, style: style };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[COLUMN_ATTR] = String(props.at);
    cellProps[ARIA_LABEL] = text(props.name);
    return element(CELL_TAG, cellProps, text(declared[TEXT]));
  }

  function DataTable(props) {
    var declared = props.declared;
    var names = listField(declared, COLUMNS);
    var rows = rowsFor(declared[NAME]);
    var style = styleOf(declared[STYLE_SHEET]);
    style.tableLayout = FIXED;
    style.width = FULL;
    style.borderCollapse = COLLAPSE;
    var props2 = nodeProps(declared, style);
    props2[ARIA_LABEL] = text(declared[NAME]);
    var scrollProps = {
      className: TAB_CLASS,
      style: { maxHeight: length(declared[MAX_HEIGHT]), overflow: AUTO, flex: AUTO }
    };
    scrollProps[PART_ATTR] = text(declared[KIND]);
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    return element(
      DIV_TAG,
      scrollProps,
      element(
        TABLE_TAG,
        props2,
        element(
          HEAD_TAG,
          null,
          element(
            ROW_TAG,
            headProps,
            names.map(function (one, at) {
              return element(HeaderCell, { key: String(at), name: one, at: at });
            })
          )
        ),
        element(
          BODY_TAG,
          null,
          rows.map(function (cells, at) {
            var rowProps = { className: TAB_CLASS, key: String(at) };
            rowProps[PART_ATTR] = ROW_PART;
            rowProps[ROW_ATTR] = String(at);
            return element(
              ROW_TAG,
              rowProps,
              (Array.isArray(cells) ? cells : []).map(function (one, column) {
                return element(BodyCell, {
                  key: String(column),
                  cell: one,
                  name: names[column],
                  at: column
                });
              })
            );
          })
        )
      )
    );
  }

  function LogLine(props) {
    var parts = logParts(props.line);
    var lineProps = { className: TAB_CLASS };
    lineProps[PART_ATTR] = LOG_PART;
    lineProps[ROW_ATTR] = String(props.at);
    if (parts === null) {
      return element(DIV_TAG, lineProps, text(props.line));
    }
    var stampProps = { className: TAB_CLASS };
    stampProps[PART_ATTR] = LOG_STAMP_PART;
    var textProps = { className: TAB_CLASS, style: { color: parts[COLOR_KEY] } };
    textProps[PART_ATTR] = LOG_TEXT_PART;
    return element(
      DIV_TAG,
      lineProps,
      element(DIV_TAG, stampProps, text(parts[STAMP_KEY])),
      element(DIV_TAG, textProps, text(parts[TEXT_KEY]))
    );
  }

  function LogPane(props) {
    var declared = props.declared;
    var style = styleOf(declared[STYLE_SHEET]);
    style.maxHeight = length(declared[MAX_HEIGHT]);
    style.overflow = AUTO;
    style.flex = AUTO;
    var props2 = nodeProps(declared, style);
    props2[ACTION_ATTR] = text(declared[READ_ONLY]);
    return element(
      DIV_TAG,
      props2,
      logLines().map(function (one, at) {
        return element(LogLine, { key: String(at), line: one, at: at });
      })
    );
  }

  var DRAWN_BY = {};
  DRAWN_BY[TAB_KIND] = Root;
  DRAWN_BY[ROW_LAYOUT_KIND] = Row;
  DRAWN_BY[COLUMN_LAYOUT_KIND] = Column;
  DRAWN_BY[STRETCH_KIND] = Stretch;
  DRAWN_BY[LABEL_KIND] = TextLabel;
  DRAWN_BY[FRAME_KIND] = Separator;
  DRAWN_BY[GROUP_KIND] = GroupBox;
  DRAWN_BY[SPIN_KIND] = NumberBox;
  DRAWN_BY[DOUBLE_SPIN_KIND] = NumberBox;
  DRAWN_BY[COMBO_KIND] = DropList;
  DRAWN_BY[BUTTON_KIND] = ActionButton;
  DRAWN_BY[SPLITTER_KIND] = Splitter;
  DRAWN_BY[TABLE_KIND] = DataTable;
  DRAWN_BY[LOG_KIND] = LogPane;

  function Node(props) {
    var declared = node(props.name);
    if (declared === null || !owns(DRAWN_BY, declared[KIND])) {
      return null;
    }
    return element(DRAWN_BY[declared[KIND]], {
      declared: declared,
      name: props.name,
      onAction: props.onAction
    });
  }

  function Tab(props) {
    if (held === null) {
      return null;
    }
    return childrenOf(EMPTY).map(function (one) {
      return element(Node, { key: one, name: one, onAction: props.onAction });
    });
  }

  var roots = [];

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
  function draw(target, drawn) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(drawn);
    });
    return target;
  }

  function renderTab(target, model, onAction) {
    if (isPlainObject(model)) {
      setTestnetTab(model);
    }
    return draw(target, element(Tab, { onAction: onAction }));
  }

  global.acervatorSetTestnetTab = setTestnetTab;
  global.acervatorLoadTestnetTab = loadTestnetTab;
  global.acervatorTestnetTab = {
    method: METHOD,
    Tab: Tab,
    Node: Node,
    Root: Root,
    GroupBox: GroupBox,
    DataTable: DataTable,
    LogPane: LogPane,
    ActionButton: ActionButton,
    payload: payload,
    isLoaded: isLoaded,
    loadError: loadError,
    nodeNames: nodeNames,
    node: node,
    childrenOf: childrenOf,
    rowsKeyFor: rowsKeyFor,
    rowsFor: rowsFor,
    columnsFor: columnsFor,
    logLines: logLines,
    logParts: logParts,
    actionFor: actionFor,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    refreshIntervalMs: refreshIntervalMs,
    busTopics: busTopics,
    tierColour: tierColour,
    eventColour: eventColour,
    styleOf: styleOf,
    renderTab: renderTab,
    forget: forget
  };
})(window);
