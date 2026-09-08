// The header stat card, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "dashboard_stat_card.state";

  var FRAME = "frame";
  var LAYOUT = "layout";
  var LABEL = "label";
  var VALUE = "value";
  var DOT = "dot";
  var ITEMS = "items";
  var LABEL_ROW_ITEMS = "label_row_items";
  var TOOLTIP = "tooltip";
  var CLICKABLE = "clickable";
  var PRIVACY = "privacy";
  var SIGNALS = "signals";
  var CLICKS = "clicks";
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
    CLICKABLE,
    CLICKS,
    DOT,
    FRAME,
    ITEMS,
    LABEL,
    LABEL_ROW_ITEMS,
    LAYOUT,
    METHOD_FIELD,
    PRIVACY,
    SIGNALS,
    TIMERS,
    TIMER_DELAYS_MS,
    TOOLTIP,
    VALUE
  ];

  // NULLABLE_FIELDS holds dot, which is null until a dot is attached.
  var NULLABLE_FIELDS = {};
  NULLABLE_FIELDS[DOT] = true;

  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var ALIGN = "align";
  var PROPERTY = "property";
  var DEFAULT_TEXT = "default_text";
  var FRAME_SHAPE = "frame_shape";

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var LABEL_ROW_MARGINS_PX = "label_row_margins_px";
  var LABEL_ROW_SPACING_PX = "label_row_spacing_px";
  var DOT_ALIGN = "dot_align";

  var KIND = "kind";
  var ROLE = "role";
  var STRETCH = "stretch";
  var LABEL_ROW = "label_row";

  // DRAWN_ROLES names the three item roles StatCard draws.
  var DRAWN_ROLES = {};
  DRAWN_ROLES[LABEL_ROW] = true;
  DRAWN_ROLES[VALUE] = true;
  DRAWN_ROLES[DOT] = true;

  var FIELD_ID = "field_id";
  var MASKED = "masked";
  var IS_CLICKABLE = "is_clickable";
  var CURSOR = "cursor";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var UNKNOWN_ROLE_FAULT = "unknown-role";
  var DOT_MISMATCH_FAULT = "dot-mismatch";
  var MANY_FRAME_RULES_FAULT = "many-frame-rules";
  var NO_FRAME_RULE_FAULT = "no-frame-rule";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var ITEM_AT = "item:";
  var CLASS_MARK = ".";
  var STATE_SPLIT = ":";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";
  // FRAME_SHAPE_SELECTOR names the theme rule QFrame carries its skin in.
  var FRAME_SHAPE_SELECTOR = "frameShape";
  var STATE_STYLE_ID = "acervator-stat-card-states";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  // DECLARATION_SPLIT rejoins the property and value of one declaration.
  var DECLARATION_SPLIT = ": ";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // PX_FACTOR scales a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var PX = "px";

  // PADDING_SIDES holds the left, top, right, bottom order the surface publishes.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  // ALIGNMENT maps each published word to alignItems and justifyContent.
  var ALIGNMENT = {
    hcenter: { alignItems: "center" },
    "hcenter|top": { alignItems: "center", justifyContent: "flex-start" },
    "hcenter|bottom": { alignItems: "center", justifyContent: "flex-end" }
  };

  // CURSOR_BY_NAME maps each published Qt cursor name to a CSS cursor.
  var CURSOR_BY_NAME = { ArrowCursor: "default", PointingHandCursor: "pointer" };

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  // A Qt QLabel never wraps, so NO_WRAP and CLIPPED cut the text instead.
  var NO_WRAP = "nowrap";
  var CLIPPED = "hidden";
  // FLEX_AUTO grows a spacer without naming a factor.
  var FLEX_AUTO = "auto";

  var CARD_CLASS = "acervator-stat-card";
  var LABEL_CLASS = "acervator-stat-card-label";
  var VALUE_CLASS = "acervator-stat-card-value";
  var DOT_CLASS = "acervator-stat-card-dot";

  var CARD_PART = "card";
  var COLUMN_PART = "column";
  var LABEL_ROW_PART = "label-row";
  var LABEL_PART = "label";
  var VALUE_PART = "value";
  var STRETCH_PART = "stretch";
  var DOT_SLOT_PART = "dot-slot";
  var DOT_PART = "privacy-dot";

  var PRIVACY_DOT_MODULE = "privacy_dot";
  var PRIVACY_DOT_API = "acervatorDot";

  var PART_ATTR = "data-part";
  var CHILD_ATTR = "data-child-module";
  var ROLE_ATTR = "data-role";
  var KIND_ATTR = "data-kind";
  var FRAME_SHAPE_ATTR = "data-frame-shape";
  var CLICKABLE_ATTR = "data-clickable";
  var CLICKS_ATTR = "data-clicks";
  var FIELD_ID_ATTR = "data-field-id";
  var MASKED_ATTR = "data-masked";
  var PROPERTY_ATTR = "data-property";
  var DEFAULT_TEXT_ATTR = "data-default-text";
  var DECLARED_ITEMS_ATTR = "data-declared-items";
  var HELD_ITEMS_ATTR = "data-held-items";

  var held = null;
  var cardFaults = [];
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

  // titleOf drops an empty tooltip so no title is written.
  function titleOf(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // variableFor asks acervatorWidgets, which owns the one-carrier rule.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // sheetApi finds acervatorHeader, which owns the Qt sheet grammar.
  function sheetApi() {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return undefined;
    }
    return api;
  }

  // carriesName reports whether text holds name, in either letter case.
  function carriesName(text, name) {
    var parts = String(text).toLowerCase().split(String(name).toLowerCase());
    parts.shift();
    return Boolean(parts.length);
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

  // length wraps a bare token number in calc to make a CSS length.
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

  function boxStyle(layout, direction, marginField, spacingField) {
    var style = marginStyle(layout, marginField);
    style.display = FLEX;
    style.flexDirection = direction;
    if (owns(layout, spacingField)) {
      style.gap = length(layout[spacingField]);
    }
    return style;
  }

  // asLabel cuts one text the way a Qt QLabel cuts it, never wrapping.
  function asLabel(style) {
    style.whiteSpace = NO_WRAP;
    style.overflow = CLIPPED;
    return style;
  }

  // withAlign paints one ALIGNMENT word as a column flex.
  function withAlign(style, word) {
    if (!owns(ALIGNMENT, word)) {
      return style;
    }
    var aligned = ALIGNMENT[word];
    style.display = FLEX;
    style.flexDirection = COLUMN;
    Object.keys(aligned).forEach(function (name) {
      style[name] = aligned[name];
    });
    return style;
  }

  function cursorOf(clickable) {
    var name = clickable[CURSOR];
    return owns(CURSOR_BY_NAME, name) ? CURSOR_BY_NAME[name] : undefined;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function PrivacyDot(props) {
    if (!isPlainObject(props.dot)) {
      return null;
    }
    var dot = props.dot;
    var dotProps = {
      className: DOT_CLASS,
      style: styleOf(dot[STYLE_SHEET]),
      title: titleOf(dot[TOOLTIP])
    };
    dotProps[PART_ATTR] = DOT_PART;
    dotProps[FIELD_ID_ATTR] = text(dot[FIELD_ID]);
    dotProps[MASKED_ATTR] = text(dot[MASKED]);
    return element("span", dotProps, text(dot[TEXT]));
  }

  function stretchNode(item, at) {
    var spacerProps = { key: String(at), style: { flex: FLEX_AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[KIND_ATTR] = STRETCH;
    spacerProps[ROLE_ATTR] = text(isPlainObject(item) ? item[ROLE] : item);
    return element("div", spacerProps, null);
  }

  function labelNode(model, at) {
    var caption = objectField(model, LABEL);
    var captionProps = {
      key: String(at),
      className: LABEL_CLASS,
      style: asLabel(withAlign(styleOf(caption[STYLE_SHEET]), caption[ALIGN]))
    };
    captionProps[PART_ATTR] = LABEL_PART;
    captionProps[ROLE_ATTR] = LABEL;
    captionProps[PROPERTY_ATTR] = text(caption[PROPERTY]);
    return element("div", captionProps, text(caption[TEXT]));
  }

  // LabelRow draws the caption between the published stretch items.
  function LabelRow(props) {
    var model = props.model;
    var layout = objectField(model, LAYOUT);
    var rowProps = {
      style: boxStyle(layout, ROW, LABEL_ROW_MARGINS_PX, LABEL_ROW_SPACING_PX)
    };
    rowProps[PART_ATTR] = LABEL_ROW_PART;
    rowProps[ROLE_ATTR] = LABEL_ROW;
    var drawn = listField(model, LABEL_ROW_ITEMS).map(function (item, at) {
      if (isPlainObject(item) && item[ROLE] === LABEL) {
        return labelNode(model, at);
      }
      return stretchNode(item, at);
    });
    return element("div", rowProps, drawn);
  }

  function valueNode(model, at) {
    var amount = objectField(model, VALUE);
    var amountProps = {
      key: String(at),
      className: VALUE_CLASS,
      style: asLabel(withAlign(styleOf(amount[STYLE_SHEET]), amount[ALIGN]))
    };
    amountProps[PART_ATTR] = VALUE_PART;
    amountProps[ROLE_ATTR] = VALUE;
    amountProps[PROPERTY_ATTR] = text(amount[PROPERTY]);
    amountProps[DEFAULT_TEXT_ATTR] = text(amount[DEFAULT_TEXT]);
    return element("div", amountProps, text(amount[TEXT]));
  }

  // acervatorDot.Dot when privacy_dot.js is loaded, else the local PrivacyDot.
  function dotSpan() {
    var own = global[PRIVACY_DOT_API];
    return own && own.Dot ? own.Dot : PrivacyDot;
  }

  function dotNode(model, item, at) {
    var layout = objectField(model, LAYOUT);
    var word = isPlainObject(item) && owns(item, ALIGN) ? item[ALIGN] : layout[DOT_ALIGN];
    var slotProps = { key: String(at), style: withAlign({}, word) };
    slotProps[PART_ATTR] = DOT_SLOT_PART;
    slotProps[ROLE_ATTR] = DOT;
    var span = dotSpan();
    if (span !== PrivacyDot) {
      slotProps[CHILD_ATTR] = PRIVACY_DOT_MODULE;
    }
    return element(
      "div",
      slotProps,
      element(span, { dot: model[DOT], model: model[DOT] })
    );
  }

  // isDrawn tests the role of one item without building a React element.
  function isDrawn(item) {
    if (!isPlainObject(item)) {
      return false;
    }
    return owns(DRAWN_ROLES, item[ROLE]) || item[KIND] === STRETCH;
  }

  function itemNode(model, item, at) {
    if (!isDrawn(item)) {
      return null;
    }
    if (item[ROLE] === LABEL_ROW) {
      return element(LabelRow, { key: String(at), model: model });
    }
    if (item[ROLE] === VALUE) {
      return valueNode(model, at);
    }
    if (item[ROLE] === DOT) {
      return dotNode(model, item, at);
    }
    return stretchNode(item, at);
  }

  function drawnItems(model) {
    return listField(model, ITEMS).filter(isDrawn);
  }

  // StatCard draws nothing for a model that is not an object.
  function StatCard(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var layout = objectField(model, LAYOUT);
    var frame = objectField(model, FRAME);
    var clickable = objectField(model, CLICKABLE);
    var items = listField(model, ITEMS);

    var cardProps = {
      id: props.id,
      className: CARD_CLASS,
      style: styleOf(frame[STYLE_SHEET]),
      title: titleOf(model[TOOLTIP])
    };
    cardProps.style.cursor = cursorOf(clickable);
    cardProps[PART_ATTR] = CARD_PART;
    cardProps[FRAME_SHAPE_ATTR] = text(frame[FRAME_SHAPE]);
    cardProps[CLICKABLE_ATTR] = text(clickable[IS_CLICKABLE]);
    cardProps[CLICKS_ATTR] = text(model[CLICKS]);
    cardProps[FIELD_ID_ATTR] = text(objectField(model, PRIVACY)[FIELD_ID]);
    cardProps[DECLARED_ITEMS_ATTR] = String(items.length);
    cardProps[HELD_ITEMS_ATTR] = String(drawnItems(model).length);

    var columnProps = {
      style: boxStyle(layout, COLUMN, MARGINS_PX, SPACING_PX)
    };
    columnProps[PART_ATTR] = COLUMN_PART;
    var drawn = items.map(function (item, at) {
      return itemNode(model, item, at);
    });
    return element(
      "div",
      cardProps,
      element("div", columnProps, drawn)
    );
  }

  // themeFrameBody reads the theme rule QFrame paints its skin from.
  function themeFrameBody() {
    var api = global.acervatorThemes;
    var doc = global.document;
    var usable =
      doc &&
      api &&
      typeof api.current === "function" &&
      typeof api.styleSheet === "function";
    if (!usable || api.current() === null || api.current() === undefined) {
      return undefined;
    }
    var sheet = api.styleSheet(api.current());
    if (typeof sheet !== "string") {
      return undefined;
    }
    var bodies = frameBodiesOf(doc, sheet);
    if (!bodies.length) {
      cardFaults.push(fault(FRAME, FRAME_SHAPE, NO_FRAME_RULE_FAULT, null));
      return undefined;
    }
    var first = bodies.shift();
    if (bodies.length) {
      cardFaults.push(
        fault(FRAME, FRAME_SHAPE, MANY_FRAME_RULES_FAULT, bodies.length)
      );
      return undefined;
    }
    return first;
  }

  // frameBodiesOf returns every frameShape rule the theme sheet holds.
  function frameBodiesOf(doc, sheet) {
    var node = doc.createElement("style");
    node.textContent = sheet;
    doc.head.appendChild(node);
    var found = [];
    Array.prototype.slice.call(node.sheet.cssRules).forEach(function (rule) {
      if (
        rule.selectorText &&
        carriesName(rule.selectorText, FRAME_SHAPE_SELECTOR)
      ) {
        found.push(rule.style.cssText);
      }
    });
    node.remove();
    return found;
  }

  // ruleText wraps one declaration body in a class rule.
  function ruleText(className, state, body) {
    return (
      CLASS_MARK +
      className +
      state +
      BLOCK_OPEN +
      body +
      BLOCK_CLOSE
    );
  }

  // hoverRules turns each Qt state rule of one sheet into a class rule.
  function hoverRules(className, sheet) {
    var parts = [];
    stateRules(sheet).forEach(function (rule) {
      var pieces = String(rule.selector).split(STATE_SPLIT);
      pieces.shift();
      if (!pieces.length) {
        return;
      }
      parts.push(
        ruleText(className, STATE_SPLIT + pieces.join(STATE_SPLIT), rule.body)
      );
    });
    return parts.join(EMPTY);
  }

  // paintRules writes the frame skin and the dot hover into one style node.
  function paintRules(model) {
    var doc = global.document;
    if (!doc) {
      return EMPTY;
    }
    var parts = [];
    var frameBody = themeFrameBody();
    if (frameBody !== undefined) {
      parts.push(ruleText(CARD_CLASS, EMPTY, frameBody));
    }
    if (isPlainObject(model) && isPlainObject(model[DOT])) {
      parts.push(hoverRules(DOT_CLASS, model[DOT][STYLE_SHEET]));
    }
    var node = doc.getElementById(STATE_STYLE_ID);
    if (node === null) {
      node = doc.createElement("style");
      node.id = STATE_STYLE_ID;
      doc.head.appendChild(node);
    }
    node.textContent = parts.join(EMPTY);
    return node.textContent;
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        cardFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && !owns(NULLABLE_FIELDS, field)) {
        cardFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // checkAmount holds the amount text against its own default_text.
  function checkAmount(model) {
    var amount = objectField(model, VALUE);
    if (!owns(amount, DEFAULT_TEXT) || amount[DEFAULT_TEXT] === null) {
      return;
    }
    var wanted = kindOf(amount[DEFAULT_TEXT]);
    if (!owns(amount, TEXT)) {
      cardFaults.push(fault(VALUE, TEXT, MISSING_FAULT, null));
      return;
    }
    if (amount[TEXT] === null) {
      cardFaults.push(fault(VALUE, TEXT, NULL_FAULT, null));
      return;
    }
    if (kindOf(amount[TEXT]) !== wanted) {
      cardFaults.push(fault(VALUE, TEXT, WRONG_TYPE_FAULT, kindOf(amount[TEXT])));
    }
  }

  // paints reports whether styleOf keeps one declaration.
  function paints(one) {
    var alone = String(one.property) + DECLARATION_SPLIT + String(one.value);
    return Boolean(Object.keys(styleOf(alone)).length);
  }

  function checkSheet(where, sheet) {
    declarations(sheet).forEach(function (one) {
      if (!paints(one)) {
        cardFaults.push(fault(where, STYLE_SHEET, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      cardFaults.push(fault(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null));
      return;
    }
    checkSheet(FRAME, objectField(model, FRAME)[STYLE_SHEET]);
    checkSheet(LABEL, objectField(model, LABEL)[STYLE_SHEET]);
    checkSheet(VALUE, objectField(model, VALUE)[STYLE_SHEET]);
    if (isPlainObject(model[DOT])) {
      checkSheet(DOT, model[DOT][STYLE_SHEET]);
    }
  }

  function checkItems(model) {
    listField(model, ITEMS).forEach(function (item, at) {
      if (!isDrawn(item)) {
        var role = isPlainObject(item) ? item[ROLE] : kindOf(item);
        cardFaults.push(fault(ITEM_AT + String(at), ROLE, UNKNOWN_ROLE_FAULT, role));
      }
    });
  }

  // checkDot pairs the privacy field_id with the dot beside it.
  function checkDot(model) {
    var named = objectField(model, PRIVACY)[FIELD_ID];
    var attached = isPlainObject(model[DOT]);
    if (named === null || named === undefined) {
      if (attached) {
        cardFaults.push(fault(PRIVACY, FIELD_ID, DOT_MISMATCH_FAULT, MISSING_FAULT));
      }
      return;
    }
    if (!attached) {
      cardFaults.push(fault(DOT, FIELD_ID, DOT_MISMATCH_FAULT, kindOf(model[DOT])));
    }
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
        items: listField(model, ITEMS).length,
        labelRowItems: listField(model, LABEL_ROW_ITEMS).length
      },
      held: {
        fields: heldFieldCount(model),
        items: drawnItems(model).length,
        labelRowItems: listField(model, LABEL_ROW_ITEMS).length
      },
      faults: cardFaults.slice()
    };
  }

  function setStatCard(model) {
    if (!isPlainObject(model)) {
      held = null;
      cardFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: cardFaults.slice() };
    }
    held = { model: model };
    cardFaults = [];
    checkFields(model);
    checkAmount(model);
    checkSheets(model);
    checkItems(model);
    checkDot(model);
    return report();
  }

  // loadStatCard asks once and forgets a refused ask.
  function loadStatCard(params) {
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
        setStatCard(model);
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

  function frame() {
    return bag(FRAME);
  }

  function layout() {
    return bag(LAYOUT);
  }

  function caption() {
    return bag(LABEL);
  }

  function amount() {
    return bag(VALUE);
  }

  function dot() {
    return field(DOT);
  }

  function items() {
    return list(ITEMS);
  }

  function labelRowItems() {
    return list(LABEL_ROW_ITEMS);
  }

  function tooltip() {
    return field(TOOLTIP);
  }

  function clickable() {
    return bag(CLICKABLE);
  }

  function privacy() {
    return bag(PRIVACY);
  }

  function signals() {
    return list(SIGNALS);
  }

  function clicks() {
    return field(CLICKS);
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

  // item answers only for a role the published items name.
  function item(role) {
    var found;
    list(ITEMS).forEach(function (one) {
      if (isPlainObject(one) && one[ROLE] === role) {
        found = one;
      }
    });
    return found;
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
    return cardFaults.slice();
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

  function renderCard(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    paintRules(payload);
    return draw(target, element(StatCard, { model: payload }));
  }

  function forget() {
    held = null;
    cardFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetStatCard = setStatCard;
  global.acervatorLoadStatCard = loadStatCard;
  global.acervatorStatCard = {
    method: METHOD,
    StatCard: StatCard,
    LabelRow: LabelRow,
    PrivacyDot: PrivacyDot,
    frame: frame,
    layout: layout,
    caption: caption,
    amount: amount,
    dot: dot,
    items: items,
    item: item,
    labelRowItems: labelRowItems,
    tooltip: tooltip,
    clickable: clickable,
    privacy: privacy,
    signals: signals,
    clicks: clicks,
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
    variableFor: variableFor,
    paintRules: paintRules,
    hoverRules: hoverRules,
    themeFrameBody: themeFrameBody,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderCard: renderCard,
    forget: forget
  };
})(window);
