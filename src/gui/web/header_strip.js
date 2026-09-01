// The header stat strip, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "header.strip";

  var CENTRAL_LAYOUT = "central_layout";
  var TOP_ROW = "top_row";
  var TOP_ROW_ORDER = "top_row_order";
  var VISIBLE = "visible";
  var ISOLATED_TABS = "isolated_tabs";
  var SPENDABLE = "spendable";
  var CARD_LAYOUT = "card_layout";
  var CARD_LABEL_ROW = "card_label_row";
  var CARD_LABEL_STYLE = "card_label_style";
  var CARD_VALUE_STYLE = "card_value_style";
  var CARD_LABEL_PROPERTY = "card_label_property";
  var CARD_VALUE_PROPERTY = "card_value_property";
  var COUNTERS = "counters";
  var HIDDEN_CARD = "hidden_card";
  var MODE_BUTTON = "mode_button";
  var ACTIONS = "actions";

  var DECLARED_FIELDS = [
    ACTIONS,
    CARD_LABEL_PROPERTY,
    CARD_LABEL_ROW,
    CARD_LABEL_STYLE,
    CARD_LAYOUT,
    CARD_VALUE_PROPERTY,
    CARD_VALUE_STYLE,
    CENTRAL_LAYOUT,
    COUNTERS,
    HIDDEN_CARD,
    ISOLATED_TABS,
    MODE_BUTTON,
    SPENDABLE,
    TOP_ROW,
    TOP_ROW_ORDER,
    VISIBLE
  ];

  var KEY = "key";
  var LABEL = "label";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var DOT = "dot";
  var FIELD_ID = "field_id";
  var MASKED = "masked";
  var STYLE_SHEET = "style_sheet";
  var INITIAL_TEXT = "initial_text";
  var INITIAL_STYLE = "initial_style";
  var LABEL_STYLE = "label_style";
  var LABEL_TOOLTIP = "label_tooltip";
  var CLICKABLE = "clickable";
  var CURSOR = "cursor";
  var SOURCE_KEY = "source_key";
  var FORMAT = "format";
  var COLUMNS = "columns";
  var LAYOUT = "layout";
  var SEPARATOR = "separator";
  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var CHILD_STRETCH = "child_stretch";
  var COLUMN_SPACING_PX = "column_spacing_px";
  var COLUMN_MARGINS = "column_margins_px";
  var COLUMN_SPACING = "column_spacing";
  var FRAME_SHAPE = "frame_shape";
  var LABEL_ALIGN = "label_align";
  var VALUE_ALIGN = "value_align";
  var DOT_ALIGN = "dot_align";
  var SEPARATOR_ALIGN = "separator_align";
  var ORDER = "order";
  var STRETCH = "stretch";
  var MINIMUM_WIDTH = "minimum_width_px";
  var CHECKED = "checked";
  var WINDOW_TITLE = "window_title";
  var MODE = "mode";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var SHORT_LIST_FAULT = "short-list";
  var UNSLOTTED_FAULT = "unslotted";

  var NO_BRIDGE = "the preload bridge is not present";

  var COLUMN_AT = "column:";
  var COUNTER_AT = "counter:";
  var DOT_AT = "dot:";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var PX = "px";

  var SEMICOLON = ";";
  var COLON = ":";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";
  var DASH = "-";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  // The one Qt paint function no stylesheet can run.
  var QT_ONLY = "qlineargradient";

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  // Each alignment word the surface publishes, as CSS paints it.
  var ALIGNMENT = {
    hcenter: { alignItems: "center" },
    vcenter: { alignItems: "center" },
    "hcenter|top": { alignItems: "center", justifyContent: "flex-start" },
    "hcenter|bottom": { alignItems: "center", justifyContent: "flex-end" }
  };

  var CURSOR_BY_NAME = { arrow: "default", pointing_hand: "pointer" };

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  // The CSS shorthand that grows a spacer without naming a factor.
  var FLEX_AUTO = "auto";

  var STRIP_CLASS = "acervator-header-strip";
  var TOP_ROW_CLASS = "acervator-header-top-row";
  var SPENDABLE_CLASS = "acervator-header-spendable";
  var KPI_CLASS = "acervator-header-kpi";
  var CARD_CLASS = "acervator-header-card";
  var DOT_CLASS = "acervator-header-dot";
  var SEPARATOR_CLASS = "acervator-header-separator";
  var MODE_CLASS = "acervator-header-mode";

  var STRIP_PART = "strip";
  var TOP_ROW_PART = "top-row";
  var KPI_COLUMN_PART = "kpi-column";
  var KPI_LABEL_PART = "kpi-label";
  var KPI_VALUE_PART = "kpi-value";
  var DOT_PART = "privacy-dot";
  var SEPARATOR_PART = "separator";
  var COUNTER_PART = "counter";
  var COUNTER_LABEL_PART = "counter-label";
  var COUNTER_VALUE_PART = "counter-value";
  var LABEL_ROW_PART = "label-row";
  var STRETCH_PART = "stretch";
  var HIDDEN_CARD_PART = "hidden-card";
  var MODE_BUTTON_PART = "mode-button";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var FIELD_ID_ATTR = "data-field-id";
  var MASKED_ATTR = "data-masked";
  var CLICKABLE_ATTR = "data-clickable";
  var ACTION_ATTR = "data-action";
  var FRAME_SHAPE_ATTR = "data-frame-shape";
  var MODE_ATTR = "data-mode";
  var FORMAT_ATTR = "data-format";
  var SOURCE_KEY_ATTR = "data-source-key";
  var LABEL_PROPERTY_ATTR = "data-label-property";
  var VALUE_PROPERTY_ATTR = "data-value-property";
  var WINDOW_TITLE_ATTR = "data-window-title";
  var DECLARED_SLOTS_ATTR = "data-declared-slots";
  var HELD_SLOTS_ATTR = "data-held-slots";
  var ARIA_PRESSED = "aria-pressed";

  var ERRORS_ACTION = "errors.clicked";
  var MODE_ACTION = "mode_button.clicked";

  var held = null;
  var headerFaults = [];
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

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // A tooltip, on the surface's own terms: an empty one stays off.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // -- resolving a value through the token and theme modules -----------

  // `shared_widgets.js` owns the one-carrier rule; a page without it
  // paints every value from the surface.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // A value painted through the one token that carries it, with the
  // surface's own value as the fallback.
  function paint(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
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

  // -- reading one Qt style sheet --------------------------------------

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // Every `selector { body }` of one sheet, a braceless sheet read as
  // one body.
  function blocks(sheet) {
    var found = [];
    String(sheet)
      .split(BLOCK_CLOSE)
      .forEach(function (chunk) {
        var parts = chunk.split(BLOCK_OPEN);
        var selector = String(parts.shift()).trim();
        if (!parts.length) {
          if (selector) {
            found.push({ selector: EMPTY, body: chunk });
          }
          return;
        }
        found.push({ selector: selector, body: parts.join(BLOCK_OPEN) });
      });
    return found;
  }

  // A selector carrying a colon names a state Qt paints on hover.
  function stateRules(sheet) {
    return blocks(sheet).filter(function (block) {
      return carries(block.selector, COLON);
    });
  }

  function baseBody(sheet) {
    var bodies = [];
    blocks(sheet).forEach(function (block) {
      if (!carries(block.selector, COLON)) {
        bodies.push(block.body);
      }
    });
    return bodies.join(SEMICOLON);
  }

  // Every `property: value` of a sheet's base block, in the order it
  // was written.
  function declarations(sheet) {
    var found = [];
    if (sheet === null || sheet === undefined) {
      return found;
    }
    baseBody(sheet)
      .split(SEMICOLON)
      .forEach(function (one) {
        var parts = one.split(COLON);
        var property = String(parts.shift()).trim();
        if (!parts.length || !property) {
          return;
        }
        var value = parts.join(COLON).trim();
        if (value) {
          found.push({ property: property, value: value });
        }
      });
    return found;
  }

  function camelCase(property) {
    var words = String(property).split(DASH);
    var head = String(words.shift());
    return (
      head +
      words
        .map(function (word) {
          var letters = word.split(EMPTY);
          var first = String(letters.shift());
          return first.toUpperCase() + letters.join(EMPTY);
        })
        .join(EMPTY)
    );
  }

  // A `qlineargradient` value reaches no stylesheet and is left out.
  function styleOf(sheet) {
    var style = {};
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        return;
      }
      style[camelCase(one.property)] = paint(one.value);
    });
    return style;
  }

  // -- the styles the components paint with ----------------------------

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

  function withAlign(style, layout, field) {
    var word = layout[field];
    if (!owns(layout, field) || !owns(ALIGNMENT, word)) {
      return style;
    }
    var aligned = ALIGNMENT[word];
    Object.keys(aligned).forEach(function (name) {
      style[name] = aligned[name];
    });
    return style;
  }

  function stretchOf(layout, at) {
    var stretch = listField(layout, CHILD_STRETCH);
    return at < stretch.length ? stretch[at] : undefined;
  }

  function firstStretch(layout) {
    return listField(layout, CHILD_STRETCH).slice().shift();
  }

  function cursorOf(card) {
    var name = card[CURSOR];
    return owns(CURSOR_BY_NAME, name) ? CURSOR_BY_NAME[name] : undefined;
  }

  // -- the components --------------------------------------------------

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
      title: label(dot[TOOLTIP])
    };
    dotProps[PART_ATTR] = DOT_PART;
    dotProps[FIELD_ID_ATTR] = text(dot[FIELD_ID]);
    dotProps[MASKED_ATTR] = text(dot[MASKED]);
    return element("span", dotProps, text(dot[TEXT]));
  }

  function KpiColumn(props) {
    var column = props.column;
    var layout = props.layout;
    var columnStyle = boxStyle(layout, COLUMN, COLUMN_MARGINS, COLUMN_SPACING);
    var columnProps = { className: KPI_CLASS, style: columnStyle };
    columnProps[PART_ATTR] = KPI_COLUMN_PART;
    columnProps[KEY_ATTR] = text(column[KEY]);
    columnProps[FIELD_ID_ATTR] = text(column[FIELD_ID]);
    columnProps[FORMAT_ATTR] = text(column[FORMAT]);

    var captionProps = {
      className: KPI_CLASS,
      style: styleOf(column[LABEL_STYLE]),
      title: label(column[LABEL_TOOLTIP])
    };
    captionProps[PART_ATTR] = KPI_LABEL_PART;

    var amountProps = {
      className: KPI_CLASS,
      style: styleOf(column[STYLE_SHEET]),
      title: label(column[TOOLTIP])
    };
    amountProps[PART_ATTR] = KPI_VALUE_PART;

    var dotProps = { style: withAlign({}, layout, DOT_ALIGN) };
    dotProps[PART_ATTR] = DOT_AT + text(column[KEY]);

    return element(
      "div",
      columnProps,
      element("div", captionProps, text(column[LABEL])),
      element("div", amountProps, text(column[TEXT])),
      element("div", dotProps, element(PrivacyDot, { dot: column[DOT] }))
    );
  }

  function separatorNode(model, at) {
    var separator = objectField(model, SEPARATOR);
    var layout = objectField(model, LAYOUT);
    var style = styleOf(separator[STYLE_SHEET]);
    withAlign(style, layout, SEPARATOR_ALIGN);
    var props = { key: SEPARATOR_PART + String(at), className: SEPARATOR_CLASS, style: style };
    props[PART_ATTR] = SEPARATOR_PART;
    return element("span", props, text(separator[TEXT]));
  }

  function SpendablePanel(props) {
    var model = isPlainObject(props.spendable) ? props.spendable : {};
    var layout = objectField(model, LAYOUT);
    var style = styleOf(model[STYLE_SHEET]);
    var box = boxStyle(layout, ROW, MARGINS, SPACING);
    Object.keys(box).forEach(function (name) {
      style[name] = box[name];
    });
    if (owns(layout, COLUMN_SPACING_PX)) {
      style.gap = length(layout[COLUMN_SPACING_PX]);
    }
    if (props.stretch !== undefined) {
      style.flexGrow = props.stretch;
    }
    var panelProps = { className: SPENDABLE_CLASS, style: style };
    panelProps[PART_ATTR] = SPENDABLE;
    panelProps[SLOT_ATTR] = SPENDABLE;
    panelProps[FRAME_SHAPE_ATTR] = text(layout[FRAME_SHAPE]);

    var drawn = [];
    listField(model, COLUMNS).forEach(function (column, at) {
      if (drawn.length) {
        drawn.push(separatorNode(model, at));
      }
      drawn.push(
        element(KpiColumn, {
          key: text(column[KEY]) || String(at),
          column: isPlainObject(column) ? column : {},
          layout: layout
        })
      );
    });
    return element("div", panelProps, drawn);
  }

  // The caption row Qt centres between two flexible spacers.
  function labelRow(model, card) {
    var row = objectField(model, CARD_LABEL_ROW);
    var rowProps = { style: boxStyle(row, ROW, MARGINS, SPACING) };
    rowProps[PART_ATTR] = LABEL_ROW_PART;
    var drawn = listField(row, ORDER).map(function (name, at) {
      if (name !== LABEL) {
        var spacerProps = { key: String(at), style: { flex: FLEX_AUTO } };
        spacerProps[PART_ATTR] = STRETCH_PART;
        return element("div", spacerProps, null);
      }
      var captionProps = {
        key: String(at),
        className: CARD_CLASS,
        style: styleOf(model[CARD_LABEL_STYLE])
      };
      captionProps[PART_ATTR] = COUNTER_LABEL_PART;
      captionProps[LABEL_PROPERTY_ATTR] = text(model[CARD_LABEL_PROPERTY]);
      return element("div", captionProps, text(card[LABEL]));
    });
    return element("div", rowProps, drawn);
  }

  function CounterCard(props) {
    var model = props.model;
    var card = props.card;
    var layout = objectField(model, CARD_LAYOUT);
    var style = boxStyle(layout, COLUMN, MARGINS, SPACING);
    withAlign(style, layout, LABEL_ALIGN);
    style.cursor = cursorOf(card);
    if (props.stretch !== undefined) {
      style.flexGrow = props.stretch;
    }
    var cardProps = { className: CARD_CLASS, style: style, title: label(card[TOOLTIP]) };
    cardProps[PART_ATTR] = COUNTER_PART;
    cardProps[SLOT_ATTR] = text(card[KEY]);
    cardProps[KEY_ATTR] = text(card[KEY]);
    cardProps[FIELD_ID_ATTR] = text(card[FIELD_ID]);
    cardProps[FORMAT_ATTR] = text(card[FORMAT]);
    cardProps[SOURCE_KEY_ATTR] = text(card[SOURCE_KEY]);
    cardProps[CLICKABLE_ATTR] = text(card[CLICKABLE]);
    cardProps[FRAME_SHAPE_ATTR] = text(layout[FRAME_SHAPE]);
    if (card[CLICKABLE] === true) {
      cardProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[ERRORS_ACTION]);
    }

    var amountProps = {
      className: CARD_CLASS,
      style: withAlign(styleOf(model[CARD_VALUE_STYLE]), layout, VALUE_ALIGN)
    };
    amountProps[PART_ATTR] = COUNTER_VALUE_PART;
    amountProps[VALUE_PROPERTY_ATTR] = text(model[CARD_VALUE_PROPERTY]);

    var dotProps = { style: withAlign({}, layout, DOT_ALIGN) };
    dotProps[PART_ATTR] = DOT_AT + text(card[KEY]);

    return element(
      "div",
      cardProps,
      labelRow(model, card),
      element("div", amountProps, text(card[TEXT])),
      element("div", dotProps, element(PrivacyDot, { dot: card[DOT] }))
    );
  }

  function HiddenCard(props) {
    var card = objectField(props.model, HIDDEN_CARD);
    var cardProps = {
      className: CARD_CLASS,
      style: styleOf(props.model[CARD_VALUE_STYLE]),
      hidden: card[VISIBLE] === false,
      title: label(card[TOOLTIP])
    };
    cardProps[PART_ATTR] = HIDDEN_CARD_PART;
    cardProps[KEY_ATTR] = text(card[KEY]);
    cardProps[FIELD_ID_ATTR] = text(card[FIELD_ID]);
    cardProps[FORMAT_ATTR] = text(card[FORMAT]);
    cardProps[SOURCE_KEY_ATTR] = text(card[SOURCE_KEY]);

    var captionProps = {};
    captionProps[PART_ATTR] = COUNTER_LABEL_PART;
    var amountProps = {};
    amountProps[PART_ATTR] = COUNTER_VALUE_PART;

    return element(
      "div",
      cardProps,
      element("span", captionProps, text(card[LABEL])),
      element("span", amountProps, text(card[TEXT]))
    );
  }

  function ModeButton(props) {
    var model = isPlainObject(props.button) ? props.button : {};
    var style = styleOf(model[STYLE_SHEET]);
    style.minWidth = length(model[MINIMUM_WIDTH]);
    if (props.stretch !== undefined) {
      style.flexGrow = props.stretch;
    }
    var buttonProps = {
      className: MODE_CLASS,
      style: style,
      title: label(model[TOOLTIP]),
      type: "button"
    };
    buttonProps[PART_ATTR] = MODE_BUTTON_PART;
    buttonProps[SLOT_ATTR] = MODE_BUTTON;
    buttonProps[MODE_ATTR] = text(model[MODE]);
    buttonProps[WINDOW_TITLE_ATTR] = text(model[WINDOW_TITLE]);
    buttonProps[ACTION_ATTR] = text(
      isPlainObject(props.actions) ? props.actions[MODE_ACTION] : undefined
    );
    buttonProps[ARIA_PRESSED] = text(model[CHECKED]);
    return element("button", buttonProps, text(model[TEXT]));
  }

  function counterFor(model, slot) {
    var found;
    listField(model, COUNTERS).forEach(function (card) {
      if (isPlainObject(card) && card[KEY] === slot) {
        found = card;
      }
    });
    return found;
  }

  function slotNode(model, slot, at) {
    var stretch = stretchOf(objectField(model, TOP_ROW), at);
    if (slot === SPENDABLE) {
      return element(SpendablePanel, {
        key: slot,
        spendable: model[SPENDABLE],
        stretch: stretch
      });
    }
    if (slot === MODE_BUTTON) {
      return element(ModeButton, {
        key: slot,
        button: model[MODE_BUTTON],
        actions: objectField(model, ACTIONS),
        stretch: stretch
      });
    }
    var card = counterFor(model, slot);
    if (card === undefined) {
      return null;
    }
    return element(CounterCard, {
      key: slot,
      model: model,
      card: card,
      stretch: stretch
    });
  }

  function drawnSlots(model) {
    return listField(model, TOP_ROW_ORDER).filter(function (slot) {
      return (
        slot === SPENDABLE ||
        slot === MODE_BUTTON ||
        counterFor(model, slot) !== undefined
      );
    });
  }

  // `Strip` draws nothing for a payload that is not an object.
  function Strip(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var order = listField(model, TOP_ROW_ORDER);
    var topRow = objectField(model, TOP_ROW);
    var central = objectField(model, CENTRAL_LAYOUT);

    var rowProps = {
      className: TOP_ROW_CLASS,
      style: boxStyle(topRow, ROW, MARGINS, SPACING)
    };
    rowProps[PART_ATTR] = TOP_ROW_PART;
    rowProps[DECLARED_SLOTS_ATTR] = String(order.length);
    rowProps[HELD_SLOTS_ATTR] = String(drawnSlots(model).length);
    if (firstStretch(central) !== undefined) {
      rowProps.style.flexGrow = firstStretch(central);
    }

    var stripProps = {
      id: props.id,
      className: STRIP_CLASS,
      style: boxStyle(central, COLUMN, MARGINS, SPACING),
      hidden: model[VISIBLE] === false
    };
    stripProps[PART_ATTR] = STRIP_PART;

    var children = order.map(function (slot, at) {
      return slotNode(model, slot, at);
    });
    return element(
      "div",
      stripProps,
      element("div", rowProps, children),
      element(HiddenCard, { model: model })
    );
  }

  // -- what the payload carries, and what it does not ------------------

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        headerFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        headerFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only where `defaultField` declares one.
  function checkAgainstDefault(where, bag, field, defaultField) {
    if (!owns(bag, defaultField) || bag[defaultField] === null) {
      return;
    }
    var wanted = kindOf(bag[defaultField]);
    if (!owns(bag, field)) {
      headerFaults.push(fault(where, field, MISSING_FAULT, null));
      return;
    }
    if (bag[field] === null) {
      headerFaults.push(fault(where, field, NULL_FAULT, null));
      return;
    }
    if (kindOf(bag[field]) !== wanted) {
      headerFaults.push(fault(where, field, WRONG_TYPE_FAULT, kindOf(bag[field])));
    }
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        headerFaults.push(fault(where, field, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkColumns(model) {
    listField(objectField(model, SPENDABLE), COLUMNS).forEach(function (column, at) {
      if (!isPlainObject(column)) {
        headerFaults.push(
          fault(COLUMN_AT + String(at), null, NOT_AN_OBJECT_FAULT, kindOf(column))
        );
        return;
      }
      var where = COLUMN_AT + String(column[KEY]);
      checkAgainstDefault(where, column, TEXT, INITIAL_TEXT);
      checkAgainstDefault(where, column, STYLE_SHEET, INITIAL_STYLE);
      checkSheet(where, STYLE_SHEET, column[STYLE_SHEET]);
      checkSheet(where, LABEL_STYLE, column[LABEL_STYLE]);
    });
  }

  function checkCounters(model) {
    var order = listField(model, TOP_ROW_ORDER);
    listField(model, COUNTERS).forEach(function (card, at) {
      if (!isPlainObject(card)) {
        headerFaults.push(
          fault(COUNTER_AT + String(at), null, NOT_AN_OBJECT_FAULT, kindOf(card))
        );
        return;
      }
      var where = COUNTER_AT + String(card[KEY]);
      checkAgainstDefault(where, card, TEXT, INITIAL_TEXT);
      var slotted = false;
      order.forEach(function (slot) {
        if (slot === card[KEY]) {
          slotted = true;
        }
      });
      if (!slotted) {
        headerFaults.push(fault(where, KEY, UNSLOTTED_FAULT, null));
      }
    });
  }

  function checkSlots(model) {
    var order = listField(model, TOP_ROW_ORDER);
    var stretch = listField(objectField(model, TOP_ROW), CHILD_STRETCH);
    order.forEach(function (slot) {
      if (
        slot !== SPENDABLE &&
        slot !== MODE_BUTTON &&
        counterFor(model, slot) === undefined
      ) {
        headerFaults.push(fault(TOP_ROW_ORDER, slot, MISSING_FAULT, null));
      }
    });
    if (stretch.length < order.length) {
      headerFaults.push(fault(TOP_ROW, CHILD_STRETCH, SHORT_LIST_FAULT, stretch.length));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function counterSlots(model) {
    return listField(model, TOP_ROW_ORDER).filter(function (slot) {
      return slot !== SPENDABLE && slot !== MODE_BUTTON;
    });
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        slots: listField(model, TOP_ROW_ORDER).length,
        counters: counterSlots(model).length
      },
      held: {
        fields: heldFieldCount(),
        slots: drawnSlots(model).length,
        counters: listField(model, COUNTERS).length
      },
      faults: headerFaults.slice()
    };
  }

  function setHeader(model) {
    if (!isPlainObject(model)) {
      held = null;
      headerFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: headerFaults.slice() };
    }
    held = { model: model };
    headerFaults = [];
    checkFields(model);
    checkColumns(model);
    checkCounters(model);
    checkSlots(model);
    checkAgainstDefault(HIDDEN_CARD, objectField(model, HIDDEN_CARD), TEXT, INITIAL_TEXT);
    checkSheet(SPENDABLE, STYLE_SHEET, objectField(model, SPENDABLE)[STYLE_SHEET]);
    checkSheet(MODE_BUTTON, STYLE_SHEET, objectField(model, MODE_BUTTON)[STYLE_SHEET]);
    return report();
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadHeader(params) {
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
        setHeader(model);
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

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function centralLayout() {
    return bag(CENTRAL_LAYOUT);
  }

  function topRow() {
    return bag(TOP_ROW);
  }

  function topRowOrder() {
    return list(TOP_ROW_ORDER);
  }

  function visible() {
    return field(VISIBLE);
  }

  function isolatedTabs() {
    return list(ISOLATED_TABS);
  }

  function spendable() {
    return bag(SPENDABLE);
  }

  function columns() {
    return held === null ? [] : listField(objectField(held.model, SPENDABLE), COLUMNS);
  }

  function cardLayout() {
    return bag(CARD_LAYOUT);
  }

  function cardLabelRow() {
    return bag(CARD_LABEL_ROW);
  }

  function cardLabelStyle() {
    return field(CARD_LABEL_STYLE);
  }

  function cardValueStyle() {
    return field(CARD_VALUE_STYLE);
  }

  function cardLabelProperty() {
    return field(CARD_LABEL_PROPERTY);
  }

  function cardValueProperty() {
    return field(CARD_VALUE_PROPERTY);
  }

  function counters() {
    return list(COUNTERS);
  }

  function hiddenCard() {
    return bag(HIDDEN_CARD);
  }

  function modeButton() {
    return bag(MODE_BUTTON);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function counter(name) {
    return held === null ? undefined : counterFor(held.model, name);
  }

  function column(name) {
    var found;
    columns().forEach(function (one) {
      if (isPlainObject(one) && one[KEY] === name) {
        found = one;
      }
    });
    return found;
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
    return headerFaults.slice();
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

  // `flushSync` makes the document current before `draw` returns.
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
    headerFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetHeader = setHeader;
  global.acervatorLoadHeader = loadHeader;
  global.acervatorHeader = {
    method: METHOD,
    Strip: Strip,
    SpendablePanel: SpendablePanel,
    CounterCard: CounterCard,
    ModeButton: ModeButton,
    PrivacyDot: PrivacyDot,
    centralLayout: centralLayout,
    topRow: topRow,
    topRowOrder: topRowOrder,
    visible: visible,
    isolatedTabs: isolatedTabs,
    spendable: spendable,
    columns: columns,
    column: column,
    cardLayout: cardLayout,
    cardLabelRow: cardLabelRow,
    cardLabelStyle: cardLabelStyle,
    cardValueStyle: cardValueStyle,
    cardLabelProperty: cardLabelProperty,
    cardValueProperty: cardValueProperty,
    counters: counters,
    counter: counter,
    hiddenCard: hiddenCard,
    modeButton: modeButton,
    actions: actions,
    declaredFields: declaredFields,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderStrip: renderStrip,
    forget: forget
  };
})(window);
