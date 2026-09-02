// The Simulator's header stat strip, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "sim_stat_strip.state";

  var WIDGET = "widget";
  var LAYOUT = "layout";
  var ITEMS = "items";
  var ORDER = "order";
  var CELLS = "cells";
  var PLACEHOLDER = "placeholder";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var METHOD_FIELD = "method";

  var DECLARED_FIELDS = [
    ACTIONS,
    BUS_TOPICS,
    CALL_NAMES,
    CELLS,
    ITEMS,
    LAYOUT,
    METHOD_FIELD,
    ORDER,
    PLACEHOLDER,
    TIMERS,
    TIMER_DELAYS_MS,
    WIDGET
  ];

  var OBJECT_NAME = "object_name";
  var ACCESSIBLE_NAME = "accessible_name";
  var FRAME_SHAPE = "frame_shape";
  var FIELD = "field";
  var LABEL = "label";
  var LABEL_STYLE = "label_style";
  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";

  // CELL_FIELDS names every value one published cell carries.
  var CELL_FIELDS = [
    ACCESSIBLE_NAME,
    FIELD,
    FRAME_SHAPE,
    LABEL,
    LABEL_STYLE,
    STYLE_SHEET,
    TEXT
  ];

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var CELL_MARGINS_PX = "cell_margins_px";
  var CELL_SPACING_PX = "cell_spacing_px";

  var KIND = "kind";
  var CELL = "cell";
  var STRETCH = "stretch";

  // DRAWN_KINDS names the two item kinds the strip draws.
  var DRAWN_KINDS = {};
  DRAWN_KINDS[CELL] = true;
  DRAWN_KINDS[STRETCH] = true;

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var UNKNOWN_KIND_FAULT = "unknown-kind";
  var UNKNOWN_FIELD_FAULT = "unknown-field";
  var ORDER_FAULT = "order-mismatch";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var CELL_AT = "cell:";
  var ITEM_AT = "item:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  // DECLARATION_SPLIT rejoins one declaration's property and value.
  var DECLARATION_SPLIT = ": ";
  var PX = "px";

  // PADDING_SIDES holds the left, top, right, bottom order the surface publishes.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var FLEX = "flex";
  var ROW = "row";
  // FLEX_NONE keeps a cell at its own width, as a Qt layout keeps a QLabel.
  var FLEX_NONE = "none";
  // FLEX_AUTO grows the trailing spacer without naming a factor.
  var FLEX_AUTO = "auto";
  // A Qt QLabel never wraps, so NO_WRAP and CLIPPED cut the text instead.
  var NO_WRAP = "nowrap";
  var CLIPPED = "hidden";
  // Qt QLabel text cannot be dragged over, so NO_SELECT refuses the drag.
  var NO_SELECT = "none";

  var STRIP_PART = "strip";
  var CELL_PART = "cell";
  var CAPTION_PART = "caption";
  var VALUE_PART = "value";
  var STRETCH_PART = "stretch";

  var PART_ATTR = "data-part";
  var KIND_ATTR = "data-kind";
  var FIELD_ATTR = "data-field";
  var FRAME_SHAPE_ATTR = "data-frame-shape";
  var DECLARED_CELLS_ATTR = "data-declared-cells";
  var HELD_CELLS_ATTR = "data-held-cells";
  var ARIA_LABEL = "aria-label";

  var held = null;
  var stripFaults = [];
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

  // text returns undefined so an attribute stays off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // sheetApi finds acervatorHeader, which owns the Qt sheet grammar.
  function sheetApi() {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return undefined;
    }
    return api;
  }

  function styleOf(sheet) {
    var api = sheetApi();
    return api === undefined ? {} : api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.stateRules(sheet);
  }

  // length writes plain pixels, because the only token carrying six means a radius.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  function marginStyle(layout, field) {
    var style = {};
    var margins = listField(layout, field);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(layout, marginField, spacingField) {
    var style = marginStyle(layout, marginField);
    style.display = FLEX;
    style.flexDirection = ROW;
    if (owns(layout, spacingField)) {
      style.gap = length(layout[spacingField]);
    }
    return style;
  }

  // asLabel cuts one text the way a Qt QLabel cuts it, never wrapping.
  function asLabel(style) {
    style.whiteSpace = NO_WRAP;
    style.overflow = CLIPPED;
    style.userSelect = NO_SELECT;
    style.flex = FLEX_NONE;
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function cellOf(model, field) {
    var found;
    listField(model, CELLS).forEach(function (one) {
      if (isPlainObject(one) && one[FIELD] === field) {
        found = one;
      }
    });
    return found;
  }

  // StatCell draws one field's caption beside its value.
  function StatCell(props) {
    var one = props.cell;
    if (!isPlainObject(one)) {
      return null;
    }
    var layout = objectField(props.model, LAYOUT);
    var cellProps = {
      style: boxStyle(layout, CELL_MARGINS_PX, CELL_SPACING_PX)
    };
    cellProps.style.flex = FLEX_NONE;
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[KIND_ATTR] = CELL;
    cellProps[FIELD_ATTR] = text(one[FIELD]);
    cellProps[FRAME_SHAPE_ATTR] = text(one[FRAME_SHAPE]);
    cellProps[ARIA_LABEL] = text(one[ACCESSIBLE_NAME]);

    var captionProps = { style: asLabel(styleOf(one[LABEL_STYLE])) };
    captionProps[PART_ATTR] = CAPTION_PART;
    var valueProps = { style: asLabel(styleOf(one[STYLE_SHEET])) };
    valueProps[PART_ATTR] = VALUE_PART;
    return element(
      "div",
      cellProps,
      element("span", captionProps, text(one[LABEL])),
      element("span", valueProps, text(one[TEXT]))
    );
  }

  function stretchNode(at) {
    var spacerProps = { key: String(at), style: { flex: FLEX_AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[KIND_ATTR] = STRETCH;
    return element("div", spacerProps, null);
  }

  // isDrawn tests one item's kind without building a React element.
  function isDrawn(item) {
    return isPlainObject(item) && owns(DRAWN_KINDS, item[KIND]);
  }

  function itemNode(model, item, at) {
    if (!isDrawn(item)) {
      return null;
    }
    if (item[KIND] === STRETCH) {
      return stretchNode(at);
    }
    return element(StatCell, {
      key: String(at),
      model: model,
      cell: cellOf(model, item[FIELD])
    });
  }

  function drawnCells(model) {
    return listField(model, ITEMS).filter(function (item) {
      return isDrawn(item) && item[KIND] === CELL && cellOf(model, item[FIELD]);
    });
  }

  // Strip draws nothing for a model that is not an object.
  function Strip(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var layout = objectField(model, LAYOUT);
    var widget = objectField(model, WIDGET);
    var items = listField(model, ITEMS);

    var stripProps = {
      id: text(widget[OBJECT_NAME]),
      style: boxStyle(layout, MARGINS_PX, SPACING_PX)
    };
    stripProps[PART_ATTR] = STRIP_PART;
    stripProps[ARIA_LABEL] = text(widget[ACCESSIBLE_NAME]);
    stripProps[DECLARED_CELLS_ATTR] = String(listField(model, ORDER).length);
    stripProps[HELD_CELLS_ATTR] = String(drawnCells(model).length);
    return element(
      "div",
      stripProps,
      items.map(function (item, at) {
        return itemNode(model, item, at);
      })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        stripFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        stripFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // wantedKind is the placeholder's own type, or undefined with none published.
  function wantedKind(model) {
    if (!owns(model, PLACEHOLDER) || model[PLACEHOLDER] === null) {
      return undefined;
    }
    return kindOf(model[PLACEHOLDER]);
  }

  // checkCells holds every cell value against the published placeholder.
  function checkCells(model) {
    var wanted = wantedKind(model);
    listField(model, CELLS).forEach(function (one, at) {
      var where = CELL_AT + String(at);
      if (!isPlainObject(one)) {
        stripFaults.push(fault(where, CELLS, WRONG_TYPE_FAULT, kindOf(one)));
        return;
      }
      CELL_FIELDS.forEach(function (name) {
        if (!owns(one, name)) {
          stripFaults.push(fault(where, name, MISSING_FAULT, null));
          return;
        }
        if (one[name] === null) {
          stripFaults.push(fault(where, name, NULL_FAULT, null));
          return;
        }
        if (wanted !== undefined && kindOf(one[name]) !== wanted) {
          stripFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(one[name])));
        }
      });
    });
  }

  // checkOrder pairs the published order with the cells beside it.
  function checkOrder(model) {
    var order = listField(model, ORDER);
    var carried = listField(model, CELLS).map(function (one) {
      return isPlainObject(one) ? one[FIELD] : kindOf(one);
    });
    if (order.length !== carried.length) {
      stripFaults.push(fault(null, ORDER, ORDER_FAULT, carried.length));
      return;
    }
    order.forEach(function (name, at) {
      if (carried[at] !== name) {
        stripFaults.push(
          fault(ORDER + PATH_SPLIT + String(at), ORDER, ORDER_FAULT, carried[at])
        );
      }
    });
  }

  function checkItems(model) {
    listField(model, ITEMS).forEach(function (item, at) {
      var where = ITEM_AT + String(at);
      if (!isDrawn(item)) {
        var kind = isPlainObject(item) ? item[KIND] : kindOf(item);
        stripFaults.push(fault(where, KIND, UNKNOWN_KIND_FAULT, kind));
        return;
      }
      if (item[KIND] === CELL && cellOf(model, item[FIELD]) === undefined) {
        stripFaults.push(fault(where, FIELD, UNKNOWN_FIELD_FAULT, kindOf(item[FIELD])));
      }
    });
  }

  // paints reports whether styleOf keeps one declaration.
  function paints(one) {
    var alone = String(one.property) + DECLARATION_SPLIT + String(one.value);
    return Boolean(Object.keys(styleOf(alone)).length);
  }

  function checkSheet(where, sheet) {
    declarations(sheet).forEach(function (one) {
      if (!paints(one)) {
        stripFaults.push(fault(where, STYLE_SHEET, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      stripFaults.push(fault(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null));
      return;
    }
    listField(model, CELLS).forEach(function (one, at) {
      if (!isPlainObject(one)) {
        return;
      }
      checkSheet(CELL_AT + String(at), one[LABEL_STYLE]);
      checkSheet(CELL_AT + String(at), one[STYLE_SHEET]);
    });
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        cells: listField(model, ORDER).length,
        items: listField(model, ITEMS).length
      },
      held: {
        fields: heldFieldCount(model),
        cells: drawnCells(model).length,
        items: listField(model, ITEMS).filter(isDrawn).length
      },
      faults: stripFaults.slice()
    };
  }

  function setStrip(model) {
    if (!isPlainObject(model)) {
      held = null;
      stripFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: stripFaults.slice() };
    }
    held = { model: model };
    stripFaults = [];
    checkFields(model);
    checkCells(model);
    checkOrder(model);
    checkItems(model);
    checkSheets(model);
    return report();
  }

  // loadStrip asks once and forgets a refused ask.
  function loadStrip(params) {
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
        setStrip(model);
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

  function widget() {
    return bag(WIDGET);
  }

  function layout() {
    return bag(LAYOUT);
  }

  function items() {
    return list(ITEMS);
  }

  function order() {
    return list(ORDER);
  }

  function cells() {
    return list(CELLS);
  }

  // cell answers only for a field the published cells name.
  function cell(name) {
    return held === null ? undefined : cellOf(held.model, name);
  }

  function placeholder() {
    return field(PLACEHOLDER);
  }

  function actions() {
    return bag(ACTIONS);
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

  function method() {
    return field(METHOD_FIELD);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  // kinds reports the JavaScript type of every payload value by dotted path.
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
    return stripFaults.slice();
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

  // draw runs flushSync so the document is current when it returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderStrip(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Strip, { model: payload }));
  }

  function forget() {
    held = null;
    stripFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSimStrip = setStrip;
  global.acervatorLoadSimStrip = loadStrip;
  global.acervatorSimStrip = {
    method: METHOD,
    Strip: Strip,
    StatCell: StatCell,
    widget: widget,
    layout: layout,
    items: items,
    order: order,
    cells: cells,
    cell: cell,
    placeholder: placeholder,
    actions: actions,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    callNames: callNames,
    methodName: method,
    declaredFields: declaredFields,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderStrip: renderStrip,
    forget: forget
  };
})(window);
