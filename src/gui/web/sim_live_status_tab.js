// The Simulator's fork of live_status_tab.js under the Simulator's names;
// it answers the sim_live_status_tab.state payload the Sim window pushes.
// The live bot Status tab, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "sim_live_status_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var CONTAINER = "container";
  var STATS_GROUP = "stats_group";
  var STATS_FORM = "stats_form";
  var ROWS = "rows";
  var ROW_COUNT = "row_count";
  var STRETCH_SHOWN = "stretch_shown";
  var LABELS = "labels";
  var FORMATS = "formats";
  var TEXTS = "texts";
  var COLORS = "colors";
  var THRESHOLDS = "thresholds";
  var WORD_WRAP = "word_wrap";
  var ATTRIBUTES = "attributes";
  var KEYS = "keys";
  var DEFAULTS = "defaults";
  var NO_STATS = "no_stats";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ATTRIBUTES,
    BUS_TOPICS,
    CALLS,
    CALL_NAMES,
    COLORS,
    CONTAINER,
    DEFAULTS,
    FORMATS,
    KEYS,
    LABELS,
    NO_STATS,
    ROWS,
    ROW_COUNT,
    STATS_FORM,
    STATS_GROUP,
    STRETCH_SHOWN,
    TEXTS,
    THRESHOLDS,
    TIMERS,
    TIMER_DELAYS_MS,
    WORD_WRAP
  ];

  // The surface publishes no_stats as null, so a null there is its value.
  var NULLABLE_FIELDS = [NO_STATS];

  var LABEL = "label";
  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var TOOLTIP = "tooltip";

  // One row of the Statistics form, in the order the surface writes it.
  var ROW_CELLS = [LABEL, TEXT, STYLE_SHEET, TOOLTIP, WORD_WRAP];

  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var MARGINS_PX = "margins_px";
  var HORIZONTAL_SPACING_PX = "horizontal_spacing_px";
  var VERTICAL_SPACING_PX = "vertical_spacing_px";
  var FIELD_GROWS = "field_grows";
  var ROWS_WRAP = "rows_wrap";
  var TITLE = "title";
  var SHOWN = "shown";
  var CONFIGURED = "configured";
  var NO_PRICE = "no_price";
  var NO_STYLE = "no_style";
  var NO_TOOLTIP = "no_tooltip";
  var OTHER_ROWS = "other_rows";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var SHORT_LIST_FAULT = "short-list";
  var UNNAMED_FAULT = "unnamed";

  var NO_BRIDGE = "the preload bridge is not present";

  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var SEMICOLON = ";";
  var COLON = ":";
  var EMPTY = "";

  var TAB_CLASS = "acervator-status-tab";
  var GROUP_CLASS = "acervator-status-group";
  var TITLE_CLASS = "acervator-status-title";
  var FORM_CLASS = "acervator-status-form";
  var ROW_CLASS = "acervator-status-row";
  var ROW_LABEL_CLASS = "acervator-status-row-label";
  var ROW_VALUE_CLASS = "acervator-status-row-value";
  var STRETCH_CLASS = "acervator-status-stretch";

  var TAB_PART = "tab";
  var GROUP_PART = "stats-group";
  var TITLE_PART = "group-title";
  var FORM_PART = "form";
  var ROW_PART = "row";
  var ROW_LABEL_PART = "row-label";
  var ROW_VALUE_PART = "row-value";
  var STRETCH_PART = "stretch";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var AT_ATTR = "data-at";
  var CONFIGURED_ATTR = "data-configured";
  var MARGINS_ATTR = "data-margins-set";
  var GROWS_ATTR = "data-field-grows";
  var ROWS_WRAP_ATTR = "data-rows-wrap";
  var WRAP_ATTR = "data-word-wrap";
  var DECLARED_ROWS_ATTR = "data-declared-rows";
  var HELD_ROWS_ATTR = "data-held-rows";
  var ARIA_LABEL = "aria-label";

  var DIV = "div";
  var SPAN = "span";
  var SECTION = "section";
  var GROUP_ROLE = "group";

  var FLEX = "flex";
  var COLUMN = "column";
  var FLEX_AUTO = "auto";
  var PX = "px";
  var WRAP_ON = "normal";
  var WRAP_OFF = "nowrap";

  var GRID = "grid";
  // CONTENTS drops a row's own box so its label and value join the form grid.
  var CONTENTS = "contents";
  // GROWING_COLUMNS lets the value column absorb the width left over.
  var GROWING_COLUMNS = "max-content auto";
  var NATURAL_COLUMNS = "max-content max-content";

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var statusFaults = [];
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

  // label returns undefined for an empty tooltip, so the title attribute stays off.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // pixels writes spacing_px straight, because the token carrying it names a radius.
  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function marginStyle(bag, name) {
    var style = {};
    var margins = listField(bag, name);
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

  function stateRules(sheet) {
    var api = sheetApi();
    if (api === null || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  // variableFor asks acervatorWidgets, which names the single token carrying a value.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
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


  function rowObject(cells) {
    var found = {};
    ROW_CELLS.forEach(function (name, at) {
      found[name] = at < cells.length ? cells[at] : undefined;
    });
    return found;
  }

  function rowList(model) {
    return listField(model, ROWS).filter(function (one) {
      return Array.isArray(one);
    });
  }

  // The published value whose type each row cell is held against.
  function cellDefaults(model) {
    var texts = objectField(model, TEXTS);
    var wrap = objectField(model, WORD_WRAP);
    var found = {};
    found[TEXT] = texts[NO_PRICE];
    found[STYLE_SHEET] = texts[NO_STYLE];
    found[TOOLTIP] = texts[NO_TOOLTIP];
    found[WORD_WRAP] = wrap[OTHER_ROWS];
    return found;
  }

  function publishedLabels(model) {
    var named = objectField(model, LABELS);
    return Object.keys(named).map(function (name) {
      return named[name];
    });
  }


  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        statusFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && !holds(NULLABLE_FIELDS, field)) {
        statusFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkRowCount(model) {
    var declared = model[ROW_COUNT];
    var rows = listField(model, ROWS);
    if (typeof declared === "number" && declared !== rows.length) {
      statusFaults.push(fault(ROWS, ROW_COUNT, SHORT_LIST_FAULT, rows.length));
    }
  }

  function checkCells(where, cells, defaults) {
    ROW_CELLS.forEach(function (name) {
      var against = defaults[name];
      if (against === undefined || cells[name] === undefined) {
        return;
      }
      if (typeof cells[name] !== typeof against) {
        statusFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(cells[name])));
      }
    });
  }

  function checkRows(model) {
    var defaults = cellDefaults(model);
    var named = publishedLabels(model);
    listField(model, ROWS).forEach(function (one, at) {
      var where = ROW_AT + String(at);
      if (!Array.isArray(one)) {
        statusFaults.push(fault(where, ROWS, WRONG_TYPE_FAULT, kindOf(one)));
        return;
      }
      if (one.length < ROW_CELLS.length) {
        statusFaults.push(fault(where, ROWS, SHORT_LIST_FAULT, one.length));
      }
      var cells = rowObject(one);
      checkCells(where, cells, defaults);
      if (!holds(named, cells[LABEL])) {
        statusFaults.push(fault(where, LABEL, UNNAMED_FAULT, text(cells[LABEL])));
      }
      unpaintable(cells[STYLE_SHEET]).forEach(function (property) {
        statusFaults.push(fault(where, STYLE_SHEET, NOT_CSS_FAULT, property));
      });
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function heldCellTotal(model) {
    var cells = [];
    rowList(model).forEach(function (one) {
      cells = cells.concat(one);
    });
    return cells.length;
  }

  function report() {
    var model = held.model;
    var rows = listField(model, ROWS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: model[ROW_COUNT],
        cells: rows.length * ROW_CELLS.length
      },
      held: {
        fields: heldFieldCount(),
        rows: rows.length,
        cells: heldCellTotal(model)
      },
      faults: statusFaults.slice()
    };
  }

  function setLiveStatus(model) {
    if (!isPlainObject(model)) {
      held = null;
      statusFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: statusFaults.slice() };
    }
    held = { model: model };
    statusFaults = [];
    checkFields(model);
    checkRowCount(model);
    checkRows(model);
    return report();
  }

  // loadLiveStatus asks once per page and clears asked when the call is refused.
  function loadLiveStatus(params) {
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
        setLiveStatus(model);
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

  function accessibleName() {
    return field(ACCESSIBLE_NAME);
  }

  function container() {
    return bag(CONTAINER);
  }

  function statsGroup() {
    return bag(STATS_GROUP);
  }

  function statsForm() {
    return bag(STATS_FORM);
  }

  function rows() {
    return list(ROWS);
  }

  function rowCount() {
    return field(ROW_COUNT);
  }

  function stretchShown() {
    return field(STRETCH_SHOWN);
  }

  function labels() {
    return bag(LABELS);
  }

  function formats() {
    return bag(FORMATS);
  }

  function texts() {
    return bag(TEXTS);
  }

  function colors() {
    return bag(COLORS);
  }

  function thresholds() {
    return bag(THRESHOLDS);
  }

  function wordWrap() {
    return bag(WORD_WRAP);
  }

  function attributes() {
    return bag(ATTRIBUTES);
  }

  function keys() {
    return bag(KEYS);
  }

  function defaults() {
    return bag(DEFAULTS);
  }

  function noStats() {
    return field(NO_STATS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelaysMs() {
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

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function rowCells() {
    return ROW_CELLS.slice();
  }

  // Every drawn row's label, in the order the surface published them.
  function rowLabels() {
    return held === null
      ? []
      : rowList(held.model).map(function (one) {
          return rowObject(one)[LABEL];
        });
  }

  // The row the surface labelled name, undefined when no row carries it.
  function row(name) {
    var found;
    if (held === null) {
      return found;
    }
    rowList(held.model).forEach(function (one) {
      var cells = rowObject(one);
      if (cells[LABEL] === name && found === undefined) {
        found = cells;
      }
    });
    return found;
  }

  // The label the surface published under name, own names only.
  function labelFor(name) {
    var named = held === null ? {} : objectField(held.model, LABELS);
    return owns(named, name) ? named[name] : undefined;
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
    return statusFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }


  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function StatRow(props) {
    var cells = props.cells;
    var style = styleOf(cells[STYLE_SHEET]);
    style.whiteSpace = cells[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    var rowProps = { className: ROW_CLASS, style: { display: CONTENTS } };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[KEY_ATTR] = text(cells[LABEL]);
    rowProps[AT_ATTR] = text(props.at);
    var labelProps = {
      className: ROW_LABEL_CLASS,
      style: { whiteSpace: props.rowsWrap ? WRAP_ON : WRAP_OFF }
    };
    labelProps[PART_ATTR] = ROW_LABEL_PART;
    labelProps[KEY_ATTR] = text(cells[LABEL]);
    var valueProps = {
      className: ROW_VALUE_CLASS,
      style: style,
      title: label(cells[TOOLTIP])
    };
    valueProps[PART_ATTR] = ROW_VALUE_PART;
    valueProps[KEY_ATTR] = text(cells[LABEL]);
    valueProps[WRAP_ATTR] = text(cells[WORD_WRAP]);
    return element(
      DIV,
      rowProps,
      element(SPAN, labelProps, text(cells[LABEL])),
      element(SPAN, valueProps, text(cells[TEXT]))
    );
  }

  // Qt lays the rows out as a QFormLayout, so the labels share one column.
  function formStyle(form) {
    var style = marginStyle(form, MARGINS_PX);
    style.display = GRID;
    style.gridTemplateColumns = form[FIELD_GROWS] ? GROWING_COLUMNS : NATURAL_COLUMNS;
    style.columnGap = pixels(form[HORIZONTAL_SPACING_PX]);
    style.rowGap = pixels(form[VERTICAL_SPACING_PX]);
    return style;
  }

  function StatsForm(props) {
    var model = props.model;
    var form = objectField(model, STATS_FORM);
    var formProps = { className: FORM_CLASS, style: formStyle(form) };
    formProps[PART_ATTR] = FORM_PART;
    formProps[CONFIGURED_ATTR] = text(form[CONFIGURED]);
    formProps[GROWS_ATTR] = text(form[FIELD_GROWS]);
    formProps[ROWS_WRAP_ATTR] = text(form[ROWS_WRAP]);
    formProps[DECLARED_ROWS_ATTR] = text(model[ROW_COUNT]);
    formProps[HELD_ROWS_ATTR] = text(listField(model, ROWS).length);
    var drawn = rowList(model).map(function (one, at) {
      return element(StatRow, {
        cells: rowObject(one),
        at: at,
        rowsWrap: form[ROWS_WRAP],
        key: String(at)
      });
    });
    return element(DIV, formProps, drawn);
  }

  function StatsGroup(props) {
    var model = props.model;
    var group = objectField(model, STATS_GROUP);
    var groupProps = {
      className: GROUP_CLASS,
      role: GROUP_ROLE,
      hidden: !group[SHOWN]
    };
    groupProps[PART_ATTR] = GROUP_PART;
    groupProps[ARIA_LABEL] = label(group[TITLE]);
    var titleProps = { className: TITLE_CLASS };
    titleProps[PART_ATTR] = TITLE_PART;
    return element(
      SECTION,
      groupProps,
      element(DIV, titleProps, text(group[TITLE])),
      element(StatsForm, { model: model })
    );
  }

  function Stretch(props) {
    var stretchProps = {
      className: STRETCH_CLASS,
      style: { flex: FLEX_AUTO },
      hidden: !props.model[STRETCH_SHOWN]
    };
    stretchProps[PART_ATTR] = STRETCH_PART;
    return element(DIV, stretchProps);
  }

  function StatusTab(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var box = objectField(model, CONTAINER);
    var style = { display: FLEX, flexDirection: COLUMN };
    if (owns(box, SPACING_PX)) {
      style.gap = pixels(box[SPACING_PX]);
    }
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[MARGINS_ATTR] = text(box[MARGINS_SET]);
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(
      DIV,
      tabProps,
      element(StatsGroup, { model: model, key: GROUP_PART }),
      element(Stretch, { model: model, key: STRETCH_PART })
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
    return draw(target, element(StatusTab, { model: payload }));
  }

  function forget() {
    held = null;
    statusFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSimLiveStatus = setLiveStatus;
  global.acervatorLoadSimLiveStatus = loadLiveStatus;
  global.acervatorSimLiveStatus = {
    method: METHOD,
    StatusTab: StatusTab,
    StatsGroup: StatsGroup,
    StatsForm: StatsForm,
    StatRow: StatRow,
    Stretch: Stretch,
    accessibleName: accessibleName,
    container: container,
    statsGroup: statsGroup,
    statsForm: statsForm,
    rows: rows,
    rowCount: rowCount,
    stretchShown: stretchShown,
    labels: labels,
    formats: formats,
    texts: texts,
    colors: colors,
    thresholds: thresholds,
    wordWrap: wordWrap,
    attributes: attributes,
    keys: keys,
    defaults: defaults,
    noStats: noStats,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    busTopics: busTopics,
    callNames: callNames,
    calls: calls,
    declaredFields: declaredFields,
    rowCells: rowCells,
    rowLabels: rowLabels,
    row: row,
    labelFor: labelFor,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    unpaintable: unpaintable,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
