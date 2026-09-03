// Draws the Capital Registry table from the capital_registry.rows payload.
(function (global) {
  "use strict";

  var METHOD = "capital_registry.rows";

  var ALT_ROW_COLOR = "alt_row_color";
  var COLUMNS = "columns";
  var COLUMN_TOOLTIPS = "column_tooltips";
  var COLUMN_WIDTHS_PX = "column_widths_px";
  var INITIAL_USD_BOTS = "initial_usd_bots";
  var INITIAL_USD_BY_BOT = "initial_usd_by_bot";
  var ROWS = "rows";
  var ROW_COLOR = "row_color";
  var ROW_COUNT = "row_count";
  var TEXT_COLOR = "text_color";
  var WIDGET = "widget";

  // Every top-level field the capital_registry.rows payload declares.
  var DECLARED_FIELDS = [
    ALT_ROW_COLOR,
    COLUMNS,
    COLUMN_TOOLTIPS,
    COLUMN_WIDTHS_PX,
    INITIAL_USD_BOTS,
    INITIAL_USD_BY_BOT,
    ROWS,
    ROW_COLOR,
    ROW_COUNT,
    TEXT_COLOR,
    WIDGET
  ];

  var DECLARED_BAGS = [
    COLUMN_TOOLTIPS,
    COLUMN_WIDTHS_PX,
    INITIAL_USD_BY_BOT,
    WIDGET
  ];

  var DECLARED_LISTS = [
    ALT_ROW_COLOR,
    COLUMNS,
    INITIAL_USD_BOTS,
    ROWS,
    ROW_COLOR,
    TEXT_COLOR
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var COLUMN_COUNT = "column_count";
  var EDIT_TRIGGERS = "edit_triggers";
  var INITIAL_ROW_COUNT = "initial_row_count";
  var SELECTION_BEHAVIOR = "selection_behavior";
  var STRETCH_LAST_SECTION = "stretch_last_section";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";

  // The widget names as a list, because a bag loses the key order a browser moves.
  var WIDGET_NAMES = [
    ACCESSIBLE_NAME,
    ALTERNATING_ROW_COLORS,
    COLUMN_COUNT,
    EDIT_TRIGGERS,
    INITIAL_ROW_COUNT,
    SELECTION_BEHAVIOR,
    STRETCH_LAST_SECTION,
    VERTICAL_HEADER_VISIBLE
  ];

  // The three channels a published colour carries, named so a short
  // list is reported rather than read as a colour.
  var RED_CHANNEL = "red";
  var GREEN_CHANNEL = "green";
  var BLUE_CHANNEL = "blue";
  var CHANNEL_NAMES = [RED_CHANNEL, GREEN_CHANNEL, BLUE_CHANNEL];

  var PAGE_PART = "capital-registry-page";
  var TAB_PART = "capital-registry-tab";
  var TABLE_PART = "registry-table";
  var HEAD_PART = "table-head";
  var HEAD_ROW_PART = "head-row";
  var HEADER_CELL_PART = "header-cell";
  var BODY_PART = "table-body";
  var REGISTRY_ROW_PART = "registry-row";
  var REGISTRY_CELL_PART = "registry-cell";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var ROW_ATTR = "data-row";
  var BOT_ATTR = "data-bot";
  var COUNT_ATTR = "data-count";
  var ALTERNATE_ATTR = "data-alternate";
  var ALTERNATING_ATTR = "data-alternating";
  var EDIT_ATTR = "data-edit-triggers";
  var SELECTION_ATTR = "data-selection";
  var VERTICAL_ATTR = "data-vertical-header";
  var STRETCH_ATTR = "data-stretch-last";
  var WIDTH_SET_ATTR = "data-width-set";
  var ARIA_LABEL = "aria-label";

  var MISSING_FAULT = "missing";
  var UNKNOWN_FAULT = "unknown";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var DISAGREES_FAULT = "disagrees";
  var SHORT_ROW_FAULT = "short-row";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var SHORT_COLOUR_FAULT = "short-colour";
  var NO_BOT_NAME_FAULT = "no-bot-name";
  var TWO_BOT_NAMES_FAULT = "two-bot-names";
  var NULL_FAULT = "null";
  var NO_BRIDGE = "no-bridge";

  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var DIV_TAG = "div";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var TR_TAG = "tr";
  var TH_TAG = "th";
  var TD_TAG = "td";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var TAB_CLASS = "capital-registry";
  var RGB_OPEN = "rgb(";
  var RGB_SPLIT = ", ";
  var RGB_CLOSE = ")";
  var PX = "px";
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var FIXED = "fixed";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var ELLIPSIS = "ellipsis";
  var NOWRAP = "nowrap";
  var LEFT = "left";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  var HEX_DIGITS = "0123456789abcdefABCDEF";
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;
  var DIGITS = "0123456789";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

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

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function model() {
    return held === null ? null : held.model;
  }

  // Every run opening with the colour mark, including a run inside a hover block.
  function hexRuns(value) {
    var found = [];
    var printed = String(value);
    var at = printed.indexOf(HEX_MARK);
    while (at >= ZERO) {
      var run = HEX_MARK;
      var next = at + STEP;
      while (
        next < printed.length &&
        HEX_DIGITS.indexOf(printed.charAt(next)) >= ZERO
      ) {
        run += printed.charAt(next);
        next += STEP;
      }
      found.push(run);
      at = printed.indexOf(HEX_MARK, next);
    }
    return found;
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return typeof value === "string" && value.length === SWAPPED_LENGTH;
  }

  // True for a key a browser lists before every worded key of the same bag.
  function isReorderedKey(key) {
    var printed = String(key);
    if (!printed.length) {
      return false;
    }
    var digitsOnly = true;
    printed.split(EMPTY).forEach(function (letter) {
      if (DIGITS.indexOf(letter) < ZERO) {
        digitsOnly = false;
      }
    });
    return digitsOnly;
  }

  // header_strip.js owns the rule that turns a Qt style sheet into declarations.
  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  function payload() {
    return held === null ? {} : copyOf(held.model);
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function declaredBags() {
    return DECLARED_BAGS.slice();
  }

  function declaredLists() {
    return DECLARED_LISTS.slice();
  }

  function widgetNames() {
    return WIDGET_NAMES.slice();
  }

  function channelNames() {
    return CHANNEL_NAMES.slice();
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function bag(name) {
    return copyOf(objectField(model(), name));
  }

  function list(name) {
    return listField(model(), name).slice();
  }

  function bagKeys(name) {
    return Object.keys(objectField(model(), name));
  }

  function widgetValue(name) {
    var found = objectField(model(), WIDGET);
    return owns(found, name) ? found[name] : undefined;
  }

  function columns() {
    return listField(model(), COLUMNS).slice();
  }

  function columnCount() {
    return widgetValue(COLUMN_COUNT);
  }

  function columnTooltip(name) {
    var tips = objectField(model(), COLUMN_TOOLTIPS);
    return owns(tips, String(name)) ? tips[String(name)] : undefined;
  }

  function columnWidth(name) {
    var widths = objectField(model(), COLUMN_WIDTHS_PX);
    return owns(widths, String(name)) ? widths[String(name)] : undefined;
  }

  function rows() {
    return listField(model(), ROWS).slice();
  }

  function rowCells(at) {
    var row = rows()[at];
    return Array.isArray(row) ? row.slice() : [];
  }

  function botNames() {
    return listField(model(), INITIAL_USD_BOTS).slice();
  }

  function initialFor(name) {
    var recorded = objectField(model(), INITIAL_USD_BY_BOT);
    return owns(recorded, String(name)) ? recorded[String(name)] : undefined;
  }

  // The bot one row is about, found by the cell naming a recorded bot.
  function identityFor(at) {
    var names = botNames();
    var found = [];
    rowCells(at).forEach(function (cell) {
      if (names.indexOf(String(cell)) >= ZERO) {
        found.push(String(cell));
      }
    });
    return found.length === STEP ? found[ZERO] : undefined;
  }

  function rowIdentities() {
    return rows().map(function (one, at) {
      return identityFor(at);
    });
  }

  function isAlternating() {
    return widgetValue(ALTERNATING_ROW_COLORS) === true;
  }

  // A row takes the alternate ground only while the widget asks for it.
  function alternateAt(at) {
    return isAlternating() && Boolean(at % (STEP + STEP));
  }

  function colourOf(channels) {
    var given = Array.isArray(channels) ? channels : [];
    if (given.length !== CHANNEL_NAMES.length) {
      return undefined;
    }
    return RGB_OPEN + given.join(RGB_SPLIT) + RGB_CLOSE;
  }

  function rowColour() {
    return colourOf(listField(model(), ROW_COLOR));
  }

  function altRowColour() {
    return colourOf(listField(model(), ALT_ROW_COLOR));
  }

  function textColour() {
    return colourOf(listField(model(), TEXT_COLOR));
  }

  function groundAt(at) {
    return alternateAt(at) ? altRowColour() : rowColour();
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        tabFaults.push(fault(null, name, MISSING_FAULT, null));
      }
    });
    Object.keys(found).forEach(function (name) {
      if (DECLARED_FIELDS.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, name, UNKNOWN_FAULT, kindOf(found[name])));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        tabFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(found[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        tabFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(found[name])));
      }
    });
    WIDGET_NAMES.forEach(function (name) {
      if (!owns(objectField(found, WIDGET), name)) {
        tabFaults.push(fault(WIDGET, name, MISSING_FAULT, null));
      }
    });
  }

  function checkCounts(found) {
    var drawn = listField(found, ROWS);
    var named = listField(found, COLUMNS);
    if (found[ROW_COUNT] !== drawn.length) {
      tabFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, found[ROW_COUNT]));
    }
    var declared = objectField(found, WIDGET)[COLUMN_COUNT];
    if (declared !== named.length) {
      tabFaults.push(fault(WIDGET, COLUMN_COUNT, DISAGREES_FAULT, declared));
    }
    drawn.forEach(function (row, at) {
      if (!Array.isArray(row) || row.length !== named.length) {
        tabFaults.push(fault(ROW_AT + String(at), ROWS, SHORT_ROW_FAULT, kindOf(row)));
      }
    });
  }

  // Each drawn row must name one recorded bot, so no row is read by its place.
  function checkIdentities(found) {
    var names = listField(found, INITIAL_USD_BOTS);
    listField(found, ROWS).forEach(function (row, at) {
      var seen = [];
      (Array.isArray(row) ? row : []).forEach(function (cell) {
        if (names.indexOf(String(cell)) >= ZERO) {
          seen.push(String(cell));
        }
      });
      if (!seen.length) {
        tabFaults.push(fault(ROW_AT + String(at), ROWS, NO_BOT_NAME_FAULT, null));
      } else if (seen.length > STEP) {
        tabFaults.push(fault(ROW_AT + String(at), ROWS, TWO_BOT_NAMES_FAULT, seen));
      }
    });
  }

  // The published order must name the same bots the recorded bag holds.
  function checkOrder(found) {
    var named = listField(found, INITIAL_USD_BOTS).map(String);
    var recorded = Object.keys(objectField(found, INITIAL_USD_BY_BOT));
    named.forEach(function (name) {
      if (recorded.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, INITIAL_USD_BOTS, UNKNOWN_FAULT, name));
      }
    });
    recorded.forEach(function (name) {
      if (named.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, INITIAL_USD_BOTS, MISSING_FAULT, name));
      }
    });
  }

  function checkColourList(name, given) {
    if (!Array.isArray(given) || given.length !== CHANNEL_NAMES.length) {
      tabFaults.push(fault(null, name, SHORT_COLOUR_FAULT, kindOf(given)));
    }
  }

  function checkColours(found) {
    [ROW_COLOR, ALT_ROW_COLOR, TEXT_COLOR].forEach(function (name) {
      checkColourList(name, found[name]);
    });
    walkFound(found, function (path, value) {
      if (typeof value !== "string") {
        return;
      }
      hexRuns(value).forEach(function (run) {
        if (isSwappedAlpha(run)) {
          tabFaults.push(fault(path, null, SWAPPED_ALPHA_FAULT, run));
        }
      });
      declarations(value).forEach(function (one) {
        hexRuns(one.value).forEach(function (run) {
          if (isSwappedAlpha(run)) {
            tabFaults.push(fault(path, null, SWAPPED_ALPHA_FAULT, run));
          }
        });
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          tabFaults.push(fault(null, name, REORDERED_KEY_FAULT, key));
        }
      });
    });
  }

  function walkFound(found, visit) {
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          visit(inner, one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        visit(path, node[name]);
        descend(path, node[name]);
      });
    }
    if (isPlainObject(found)) {
      walk(EMPTY, found);
    }
  }

  function walkPayload(visit) {
    if (held !== null) {
      walkFound(held.model, visit);
    }
  }

  function kinds() {
    var found = {};
    walkPayload(function (path, value) {
      found[path] = kindOf(value);
    });
    return found;
  }

  function notPlainData() {
    var found = [];
    walkPayload(function (path, value) {
      var kind = kindOf(value);
      var plain =
        kind === NULL_FAULT ||
        kind === "string" ||
        kind === "number" ||
        kind === "boolean" ||
        isPlainObject(value) ||
        Array.isArray(value);
      if (!plain) {
        found.push({ path: path, kind: kind });
      }
    });
    return found;
  }

  function heldFieldCount(found) {
    var seen = ZERO;
    DECLARED_FIELDS.forEach(function (name) {
      if (owns(found, name)) {
        seen += STEP;
      }
    });
    return seen;
  }

  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: found[ROW_COUNT],
        columns: objectField(found, WIDGET)[COLUMN_COUNT],
        widget: WIDGET_NAMES.length,
        bots: listField(found, INITIAL_USD_BOTS).length
      },
      held: {
        fields: heldFieldCount(found),
        rows: listField(found, ROWS).length,
        columns: listField(found, COLUMNS).length,
        widget: Object.keys(objectField(found, WIDGET)).length,
        bots: Object.keys(objectField(found, INITIAL_USD_BY_BOT)).length
      },
      faults: tabFaults.slice()
    };
  }

  function setTable(found) {
    if (!isPlainObject(found)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: found };
    tabFaults = [];
    checkFields(found);
    checkCounts(found);
    checkIdentities(found);
    checkOrder(found);
    checkColours(found);
    checkBagOrder(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTable(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (found) {
        loadFault = null;
        setTable(found);
        return found;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function HeaderCell(props) {
    var name = props.name;
    var width = columnWidth(name);
    var cellProps = {
      className: TAB_CLASS,
      title: label(columnTooltip(name)),
      style: {
        textAlign: LEFT,
        whiteSpace: NOWRAP,
        overflow: HIDDEN,
        textOverflow: ELLIPSIS,
        width: width === undefined ? AUTO : String(width) + PX
      }
    };
    cellProps[PART_ATTR] = HEADER_CELL_PART;
    cellProps[NAME_ATTR] = text(name);
    cellProps[INDEX_ATTR] = text(props.at);
    cellProps[WIDTH_SET_ATTR] = String(width !== undefined);
    return element(TH_TAG, cellProps, text(name));
  }

  function RegistryRow(props) {
    var names = columns();
    var cells = rowCells(props.at);
    var rowProps = {
      className: TAB_CLASS,
      style: { backgroundColor: groundAt(props.at) }
    };
    rowProps[PART_ATTR] = REGISTRY_ROW_PART;
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[BOT_ATTR] = text(identityFor(props.at));
    rowProps[ALTERNATE_ATTR] = String(alternateAt(props.at));
    rowProps[COUNT_ATTR] = text(cells.length);
    var drawn = names.map(function (name, at) {
      var cellProps = {
        className: TAB_CLASS,
        key: REGISTRY_CELL_PART + String(at),
        style: {
          color: textColour(),
          whiteSpace: NOWRAP,
          overflow: HIDDEN,
          textOverflow: ELLIPSIS
        }
      };
      cellProps[PART_ATTR] = REGISTRY_CELL_PART;
      cellProps[COLUMN_ATTR] = text(name);
      cellProps[ROW_ATTR] = text(props.at);
      cellProps[NAME_ATTR] = text(identityFor(props.at));
      return element(TD_TAG, cellProps, text(cells[at]));
    });
    return element(TR_TAG, rowProps, drawn);
  }

  function RegistryTable(props) {
    var found = props.model;
    if (!isPlainObject(found)) {
      return null;
    }
    var names = columns();
    var tabProps = { className: TAB_CLASS };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[COUNT_ATTR] = text(found[ROW_COUNT]);
    var tableProps = {
      className: TAB_CLASS,
      style: {
        width: FULL,
        borderCollapse: COLLAPSE,
        tableLayout: FIXED,
        backgroundColor: rowColour(),
        color: textColour()
      }
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[ARIA_LABEL] = text(widgetValue(ACCESSIBLE_NAME));
    tableProps[ALTERNATING_ATTR] = String(isAlternating());
    tableProps[EDIT_ATTR] = text(widgetValue(EDIT_TRIGGERS));
    tableProps[SELECTION_ATTR] = text(widgetValue(SELECTION_BEHAVIOR));
    tableProps[VERTICAL_ATTR] = String(widgetValue(VERTICAL_HEADER_VISIBLE));
    tableProps[STRETCH_ATTR] = String(widgetValue(STRETCH_LAST_SECTION));
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_PART;
    var headRowProps = { className: TAB_CLASS };
    headRowProps[PART_ATTR] = HEAD_ROW_PART;
    headRowProps[COUNT_ATTR] = text(names.length);
    var bodyProps = { className: TAB_CLASS };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[COUNT_ATTR] = text(rows().length);
    return element(
      DIV_TAG,
      tabProps,
      element(
        TABLE_TAG,
        tableProps,
        element(
          HEAD_TAG,
          headProps,
          element(
            TR_TAG,
            headRowProps,
            names.map(function (name, at) {
              return element(HeaderCell, {
                key: HEADER_CELL_PART + String(at),
                name: name,
                at: at
              });
            })
          )
        ),
        element(
          BODY_TAG,
          bodyProps,
          rows().map(function (one, at) {
            return element(RegistryRow, {
              key: REGISTRY_ROW_PART + String(at),
              at: at
            });
          })
        )
      )
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

  // A payload given here is set first, so every drawn piece reads one model.
  function renderTable(target, found) {
    if (isPlainObject(found)) {
      setTable(found);
    }
    return draw(target, element(RegistryTable, { model: model() }));
  }

  // The named empty space the window leaves for this table, or root itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== "function") {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === PAGE_PART) {
      return root;
    }
    if (typeof root.querySelector !== "function") {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE
    );
  }

  function fill(root, found) {
    var space = spaceIn(root);
    return space === null ? null : renderTable(space, found);
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

  global.acervatorSetCapitalRegistry = setTable;
  global.acervatorLoadCapitalRegistry = loadTable;
  global.acervatorCapitalRegistry = {
    method: METHOD,
    spacePart: PAGE_PART,
    RegistryTable: RegistryTable,
    RegistryRow: RegistryRow,
    HeaderCell: HeaderCell,
    payload: payload,
    declaredNames: declaredNames,
    declaredBags: declaredBags,
    declaredLists: declaredLists,
    widgetNames: widgetNames,
    channelNames: channelNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    widgetValue: widgetValue,
    columns: columns,
    columnCount: columnCount,
    columnTooltip: columnTooltip,
    columnWidth: columnWidth,
    rows: rows,
    rowCells: rowCells,
    botNames: botNames,
    initialFor: initialFor,
    identityFor: identityFor,
    rowIdentities: rowIdentities,
    isAlternating: isAlternating,
    alternateAt: alternateAt,
    colourOf: colourOf,
    rowColour: rowColour,
    altRowColour: altRowColour,
    textColour: textColour,
    groundAt: groundAt,
    hexRuns: hexRuns,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTable: renderTable,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
