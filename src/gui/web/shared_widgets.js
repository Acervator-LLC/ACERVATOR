// The shared card and table skins, as the Python surface serves them.
//
// Every colour, size, padding, radius, header and column width reaches
// this file over the bridge from
// `src/gui/main_tabs/widgets_package_surface.py`. This file holds no
// skin value of its own. A colour or a size written here would be a
// second source of truth for the card every widget in `src/gui/widgets`
// paints.
//
// Two ways in, matching the pair `design_tokens.js` and
// `theme_engine.js` use. `acervatorLoadWidgets` asks the backend, once
// per page, the way `desktop/renderer/boot.js` asks for its view model.
// `acervatorSetWidgets` takes a payload a caller already holds.
//
// A skin value carried by exactly one design token, or by exactly one
// field of the selected theme, is painted as that CSS variable with the
// surface's own value as the fallback. A value carried by more than one
// token is painted from the surface: binding a text size to a spacing
// step holding the same number would move the text whenever that
// spacing moved.
//
// It reports and it does not repair. A skin the payload omits, a skin
// or a field carrying null where the surface's default is not null, a
// field arriving as a type the surface's default is not, a padding that
// is not the length the surface declares, and a column count that
// disagrees with the headers held are recorded in `faults` and left as
// they arrived. The declared count and the held count are kept apart.
(function (global) {
  "use strict";

  var METHOD = "widgets_package.state";

  var CARD = "card";
  var TABLE = "table";
  var PRESETS = "presets";
  var CARD_FIELDS = "card_fields";
  var CARD_DEFAULTS = "card_defaults";
  var SPEC_FIELDS = "spec_fields";
  var SPEC_DEFAULTS = "spec_defaults";
  var EXPORTED_NAMES = "exported_names";
  var LIMITS = "limits";
  var CALL_NAMES = "call_names";

  // The Qt machinery the surface describes for this package. A React
  // screen paints none of it; it is carried across so that nothing the
  // surface publishes stops at the bridge.
  var MACHINERY_FIELDS = [
    "actions",
    "signals",
    "timers",
    "timer_delays_ms",
    "bus_topics",
    "threads"
  ];

  var SKIN = "skin";
  var LABEL = "label";
  var VALUE = "value";
  var TEXT = "text";
  var CLASS_NAME = "class_name";
  var ACCESSIBLE_NAME = "accessible_name";
  var FRAME_SHAPE = "frame_shape";
  var CALLS = "calls";

  var PADDING = "padding";
  var SPACING = "spacing";
  var SURFACE = "surface";
  var BORDER = "border";
  var RADIUS = "radius";
  var LABEL_COLOR = "label_color";
  var VALUE_COLOR = "value_color";
  var LABEL_SIZE = "label_size";
  var VALUE_SIZE = "value_size";

  var COLUMN_COUNT = "column_count";
  var HEADERS = "headers";
  var RESIZE_MODES = "resize_modes";
  var FIXED_WIDTHS = "fixed_widths";
  var TOOLTIPS = "tooltips";
  var ALTERNATING_ROWS = "alternating_row_colours";
  var SELECTION_BEHAVIOUR = "selection_behaviour";
  var EDIT_TRIGGERS = "edit_triggers";
  var VERTICAL_HEADER = "vertical_header_visible";

  var BORDER_WIDTH_PX = "border_width_px";
  var BORDER_KIND = "border_kind";
  var VALUE_WEIGHT = "value_weight";
  var PADDING_PARTS = "padding_parts";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_TABLE_FAULT = "not-a-table";
  var WRONG_TYPE_FAULT = "wrong-type";
  var PADDING_LENGTH_FAULT = "padding-length";
  var COLUMN_COUNT_FAULT = "column-count";
  var SHORT_LIST_FAULT = "short-list";

  var NO_BRIDGE = "the preload bridge is not present";
  var PRESET_AT = "preset:";

  var CARD_CLASS = "acervator-card";
  var LABEL_CLASS = "acervator-card-label";
  var VALUE_CLASS = "acervator-card-value";
  var TABLE_CLASS = "acervator-table";
  var COLUMN_SCOPE = "col";
  var ARIA_LABEL = "aria-label";

  var CARD_PART_ATTR = "data-card-part";
  var CARD_CLASS_ATTR = "data-card-class";
  var FRAME_SHAPE_ATTR = "data-frame-shape";
  var TABLE_CLASS_ATTR = "data-table-class";
  var DECLARED_COLUMNS_ATTR = "data-declared-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var ALTERNATING_ROWS_ATTR = "data-alternating-rows";
  var SELECTION_ATTR = "data-selection-behaviour";
  var EDIT_TRIGGERS_ATTR = "data-edit-triggers";
  var VERTICAL_HEADER_ATTR = "data-vertical-header-visible";
  var COLUMN_ATTR = "data-column";
  var RESIZE_MODE_ATTR = "data-resize-mode";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length. Not a
  // size: the number it scales always comes from the surface.
  var PX_FACTOR = " * 1px)";
  var PX = "px";

  // The surface publishes a padding in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var widgetFaults = [];
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

  // Attribute and child text. Undefined leaves the attribute off the
  // element rather than writing an empty one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // An accessible name, on the surface's own terms: an empty name leaves
  // the element unnamed rather than announcing nothing.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // -- resolving a value through the token and theme modules -----------

  // The one name in `candidates`, undefined when there is none and when
  // there is more than one.
  function onlyName(candidates) {
    var only;
    var many = false;
    candidates.forEach(function (name) {
      if (only === undefined) {
        only = name;
        return;
      }
      many = true;
    });
    return many ? undefined : only;
  }

  // Every design token carrying `printed`, an alias of another token
  // left out: an alias is one token under a second name, not two.
  function tokenCandidates(printed) {
    var api = global.acervatorTokens;
    var usable =
      api && typeof api.names === "function" && typeof api.token === "function";
    if (!usable) {
      return [];
    }
    return api.names().filter(function (name) {
      var aliased =
        typeof api.aliasTarget === "function" && api.aliasTarget(name) !== undefined;
      if (aliased) {
        return false;
      }
      var carried = api.token(name);
      return carried !== null && carried !== undefined && String(carried) === printed;
    });
  }

  // Every field of the selected theme carrying `printed`.
  function themeCandidates(printed) {
    var api = global.acervatorThemes;
    if (!api || typeof api.painted !== "function") {
      return [];
    }
    var values = api.painted();
    return Object.keys(values).filter(function (field) {
      var carried = values[field];
      return carried !== null && carried !== undefined && String(carried) === printed;
    });
  }

  // The CSS variable name to paint `value` through, undefined when no
  // single token and no single theme field carries it.
  function variableFor(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var printed = String(value);
    var candidates = tokenCandidates(printed);
    if (candidates.length) {
      return onlyName(candidates);
    }
    return onlyName(themeCandidates(printed));
  }

  // A colour, painted through its token where one carries it. The
  // surface's own value is the fallback, so a page that never applied
  // the tokens paints the same colour.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // A CSS length, painted through its token where exactly one carries
  // its number. A token holds a bare number, so the variable is scaled
  // to pixels rather than read as a length.
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

  // -- the styles the components paint with ----------------------------

  function frameStyle(skinValues, limitValues) {
    var style = {};
    var padding = Array.isArray(skinValues[PADDING]) ? skinValues[PADDING] : [];
    PADDING_SIDES.forEach(function (side, at) {
      if (at < padding.length) {
        style[side] = length(padding[at]);
      }
    });
    if (skinValues[SURFACE] === null || skinValues[SURFACE] === undefined) {
      return style;
    }
    style.background = colour(skinValues[SURFACE]);
    style.borderWidth = length(limitValues[BORDER_WIDTH_PX]);
    style.borderStyle = text(limitValues[BORDER_KIND]);
    style.borderColor = colour(skinValues[BORDER]);
    style.borderRadius = length(skinValues[RADIUS]);
    return style;
  }

  // The caption. Qt's column layout puts the skin's spacing between the
  // caption and the amount, which is the caption's bottom margin here.
  function labelStyle(skinValues) {
    return {
      color: colour(skinValues[LABEL_COLOR]),
      fontSize: length(skinValues[LABEL_SIZE]),
      marginBottom: length(skinValues[SPACING])
    };
  }

  function valueStyle(skinValues, limitValues) {
    return {
      color: colour(skinValues[VALUE_COLOR]),
      fontSize: length(skinValues[VALUE_SIZE]),
      fontWeight: text(limitValues[VALUE_WEIGHT])
    };
  }

  function columnStyle(widths, at) {
    var key = String(at);
    return owns(widths, key) ? { width: length(widths[key]) } : {};
  }

  // -- the components --------------------------------------------------

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Card(props) {
    var model = isPlainObject(props.card) ? props.card : {};
    var limitValues = isPlainObject(props.limits) ? props.limits : {};
    var skinValues = objectField(model, SKIN);
    var caption = objectField(model, LABEL);
    var amount = objectField(model, VALUE);

    var frameProps = {
      id: props.id,
      className: CARD_CLASS,
      style: frameStyle(skinValues, limitValues)
    };
    frameProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    frameProps[CARD_CLASS_ATTR] = text(model[CLASS_NAME]);
    frameProps[FRAME_SHAPE_ATTR] = text(model[FRAME_SHAPE]);

    var captionProps = { className: LABEL_CLASS, style: labelStyle(skinValues) };
    captionProps[CARD_PART_ATTR] = LABEL;

    var amountProps = {
      className: VALUE_CLASS,
      style: valueStyle(skinValues, limitValues)
    };
    amountProps[CARD_PART_ATTR] = VALUE;

    return element(
      "div",
      frameProps,
      element("div", captionProps, text(caption[TEXT])),
      element("div", amountProps, text(amount[TEXT]))
    );
  }

  function headerCell(model, header, at) {
    var modes = listField(model, RESIZE_MODES);
    var tips = listField(model, TOOLTIPS);
    var cellProps = {
      key: String(at),
      scope: COLUMN_SCOPE,
      title: at < tips.length ? label(tips[at]) : undefined,
      style: columnStyle(objectField(model, FIXED_WIDTHS), at)
    };
    cellProps[COLUMN_ATTR] = String(at);
    cellProps[RESIZE_MODE_ATTR] = at < modes.length ? text(modes[at]) : undefined;
    return element("th", cellProps, text(header));
  }

  function Table(props) {
    var model = isPlainObject(props.table) ? props.table : {};
    var headerTexts = listField(model, HEADERS);
    var cells = headerTexts.map(function (header, at) {
      return headerCell(model, header, at);
    });

    var tableProps = { id: props.id, className: TABLE_CLASS };
    tableProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    tableProps[TABLE_CLASS_ATTR] = text(model[CLASS_NAME]);
    tableProps[DECLARED_COLUMNS_ATTR] = text(model[COLUMN_COUNT]);
    tableProps[HELD_COLUMNS_ATTR] = String(headerTexts.length);
    tableProps[ALTERNATING_ROWS_ATTR] = text(model[ALTERNATING_ROWS]);
    tableProps[SELECTION_ATTR] = text(model[SELECTION_BEHAVIOUR]);
    tableProps[EDIT_TRIGGERS_ATTR] = text(model[EDIT_TRIGGERS]);
    tableProps[VERTICAL_HEADER_ATTR] = text(model[VERTICAL_HEADER]);

    return element(
      "table",
      tableProps,
      element("thead", null, element("tr", null, cells))
    );
  }

  // -- what the payload carries, and what it does not ------------------

  // The type the surface's own default declares for `field`, undefined
  // where the default is null and declares none. The two colours have no
  // default, so a colour arriving as a number is reported by `types` and
  // raises no fault.
  function declaredKind(field) {
    var defaults = held === null ? {} : held.cardDefaults;
    if (!owns(defaults, field) || defaults[field] === null) {
      return undefined;
    }
    return kindOf(defaults[field]);
  }

  function checkSkin(where, skinValues) {
    if (skinValues === undefined) {
      widgetFaults.push(fault(where, null, MISSING_FAULT, null));
      return;
    }
    if (skinValues === null) {
      widgetFaults.push(fault(where, null, NULL_FAULT, null));
      return;
    }
    if (!isPlainObject(skinValues)) {
      widgetFaults.push(fault(where, null, NOT_A_TABLE_FAULT, kindOf(skinValues)));
      return;
    }
    held.cardFields.forEach(function (field) {
      if (!owns(skinValues, field)) {
        widgetFaults.push(fault(where, field, MISSING_FAULT, null));
      }
    });
    Object.keys(skinValues).forEach(function (field) {
      var wanted = declaredKind(field);
      if (skinValues[field] === null) {
        if (wanted !== undefined) {
          widgetFaults.push(fault(where, field, NULL_FAULT, null));
        }
        return;
      }
      if (wanted !== undefined && kindOf(skinValues[field]) !== wanted) {
        widgetFaults.push(
          fault(where, field, WRONG_TYPE_FAULT, kindOf(skinValues[field]))
        );
      }
    });
    checkPadding(where, skinValues);
  }

  function checkPadding(where, skinValues) {
    var parts = held.limits[PADDING_PARTS];
    if (!Array.isArray(skinValues[PADDING]) || typeof parts !== "number") {
      return;
    }
    if (skinValues[PADDING].length !== parts) {
      widgetFaults.push(
        fault(where, PADDING, PADDING_LENGTH_FAULT, skinValues[PADDING].length)
      );
    }
  }

  // The declared column count is the surface's own number; the held
  // count is the headers that arrived. They are counted apart, so a
  // payload that promises more columns than it carries reads as a
  // difference rather than as a full table.
  function checkTable() {
    var count = held.table[COLUMN_COUNT];
    var headerTexts = listField(held.table, HEADERS);
    if (typeof count === "number" && count !== headerTexts.length) {
      widgetFaults.push(
        fault(TABLE, COLUMN_COUNT, COLUMN_COUNT_FAULT, {
          declared: count,
          held: headerTexts.length
        })
      );
    }
    [RESIZE_MODES, TOOLTIPS].forEach(function (field) {
      var carried = listField(held.table, field).length;
      if (carried < headerTexts.length) {
        widgetFaults.push(fault(TABLE, field, SHORT_LIST_FAULT, carried));
      }
    });
  }

  function heldFieldCount() {
    var skinValues = objectField(held.card, SKIN);
    return held.cardFields.filter(function (field) {
      return owns(skinValues, field);
    }).length;
  }

  function report() {
    return {
      declared: {
        fields: held.cardFields.length,
        columns: held.table[COLUMN_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        columns: listField(held.table, HEADERS).length
      },
      faults: widgetFaults.slice()
    };
  }

  function setWidgets(model) {
    if (!isPlainObject(model)) {
      held = null;
      widgetFaults = [fault(CARD, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: widgetFaults.slice() };
    }
    held = {
      model: model,
      card: objectField(model, CARD),
      table: objectField(model, TABLE),
      presets: objectField(model, PRESETS),
      cardFields: listField(model, CARD_FIELDS),
      cardDefaults: objectField(model, CARD_DEFAULTS),
      specFields: listField(model, SPEC_FIELDS),
      specDefaults: objectField(model, SPEC_DEFAULTS),
      exported: listField(model, EXPORTED_NAMES),
      limits: objectField(model, LIMITS),
      callNames: listField(model, CALL_NAMES)
    };
    widgetFaults = [];
    if (!isPlainObject(model[TABLE])) {
      widgetFaults.push(fault(TABLE, null, NOT_A_TABLE_FAULT, kindOf(model[TABLE])));
    }
    checkSkin(CARD, owns(held.card, SKIN) ? held.card[SKIN] : undefined);
    Object.keys(held.presets).forEach(function (name) {
      checkSkin(PRESET_AT + name, held.presets[name]);
    });
    checkTable();
    return report();
  }

  // Asks the backend once and remembers the request, so several panels
  // on one page cost one round trip. Resolves to null when the bridge is
  // absent or refuses; `loadError` then carries the reason. A failed ask
  // is not remembered, so a later caller reaches a backend that has
  // since started.
  function loadWidgets(params) {
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
        setWidgets(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  // -- readers ----------------------------------------------------------

  function card() {
    return held === null ? {} : copyOf(held.card);
  }

  function table() {
    return held === null ? {} : copyOf(held.table);
  }

  function skin() {
    return held === null ? {} : copyOf(objectField(held.card, SKIN));
  }

  function presetNames() {
    return held === null ? [] : Object.keys(held.presets);
  }

  function presets() {
    return held === null ? {} : copyOf(held.presets);
  }

  function machinery() {
    var found = {};
    if (held === null) {
      return found;
    }
    MACHINERY_FIELDS.forEach(function (field) {
      if (owns(held.model, field)) {
        found[field] = held.model[field];
      }
    });
    return found;
  }

  function preset(name) {
    if (held === null || !owns(held.presets, name)) {
      return undefined;
    }
    return held.presets[name];
  }

  function cardFields() {
    return held === null ? [] : held.cardFields.slice();
  }

  function cardDefaults() {
    return held === null ? {} : copyOf(held.cardDefaults);
  }

  function specFields() {
    return held === null ? [] : held.specFields.slice();
  }

  function specDefaults() {
    return held === null ? {} : copyOf(held.specDefaults);
  }

  function exportedNames() {
    return held === null ? [] : held.exported.slice();
  }

  function limits() {
    return held === null ? {} : copyOf(held.limits);
  }

  function callNames() {
    return held === null ? [] : held.callNames.slice();
  }

  function calls() {
    return held === null ? [] : listField(held.card, CALLS).slice();
  }

  function headers() {
    return held === null ? [] : listField(held.table, HEADERS).slice();
  }

  function declaredColumns() {
    return held === null ? undefined : held.table[COLUMN_COUNT];
  }

  function heldColumns() {
    return held === null ? undefined : listField(held.table, HEADERS).length;
  }

  // The JavaScript type each field of one skin arrived as, null reported
  // apart from object. A caller comparing this against the Python side
  // sees a value that changed shape in transit.
  function types(name) {
    var values = name === undefined ? skin() : preset(name);
    var found = {};
    if (!isPlainObject(values)) {
      return found;
    }
    Object.keys(values).forEach(function (field) {
      found[field] = kindOf(values[field]);
    });
    return found;
  }

  function faults() {
    return widgetFaults.slice();
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

  // Draws `node` into `target` and makes the document current before
  // returning, so a reader that measures right after a draw sees this
  // one and not the last.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function payloadOr(model) {
    if (isPlainObject(model)) {
      return model;
    }
    return held === null ? {} : held.model;
  }

  function renderCard(target, model) {
    var payload = payloadOr(model);
    return draw(
      target,
      element(Card, {
        card: objectField(payload, CARD),
        limits: objectField(payload, LIMITS)
      })
    );
  }

  function renderTable(target, model) {
    var payload = payloadOr(model);
    return draw(target, element(Table, { table: objectField(payload, TABLE) }));
  }

  function forget() {
    held = null;
    widgetFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetWidgets = setWidgets;
  global.acervatorLoadWidgets = loadWidgets;
  global.acervatorWidgets = {
    method: METHOD,
    Card: Card,
    Table: Table,
    card: card,
    table: table,
    skin: skin,
    presetNames: presetNames,
    presets: presets,
    preset: preset,
    machinery: machinery,
    cardFields: cardFields,
    cardDefaults: cardDefaults,
    specFields: specFields,
    specDefaults: specDefaults,
    exportedNames: exportedNames,
    limits: limits,
    callNames: callNames,
    calls: calls,
    headers: headers,
    declaredColumns: declaredColumns,
    heldColumns: heldColumns,
    frameStyle: frameStyle,
    labelStyle: labelStyle,
    valueStyle: valueStyle,
    columnStyle: columnStyle,
    variableFor: variableFor,
    types: types,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderCard: renderCard,
    renderTable: renderTable,
    forget: forget
  };
})(window);
