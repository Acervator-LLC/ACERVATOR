// The header stat strip, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "header.strip";

  var CENTRAL_LAYOUT = "central_layout";
  var TOP_ROW = "top_row";
  var TOP_ROW_ORDER = "top_row_order";
  var WIDTH_BUDGET = "width_budget";
  var BUDGET_SLOTS = "slots";
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
    VISIBLE,
    WIDTH_BUDGET
  ];

  var KEY = "key";
  var LABEL = "label";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var FIELD_ID = "field_id";
  var MASKED = "masked";
  var STYLE_SHEET = "style_sheet";
  var INITIAL_TEXT = "initial_text";
  var INITIAL_STYLE = "initial_style";
  var LABEL_STYLE = "label_style";
  var CLICKABLE = "clickable";
  var CURSOR = "cursor";
  var SOURCE_KEY = "source_key";
  var FORMAT = "format";
  var COLUMNS = "columns";
  var LAYOUT = "layout";
  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var CHILD_STRETCH = "child_stretch";
  var COLUMN_SPACING_PX = "column_spacing_px";
  var FRAME_SHAPE = "frame_shape";
  var LABEL_ALIGN = "label_align";
  var MINIMUM_WIDTH = "minimum_width_px";
  var GROUP_SPACING = "group_spacing_px";
  var CHECKED = "checked";
  var WINDOW_TITLE = "window_title";
  var MODE = "mode";
  var BUTTONS = "buttons";
  var CLASS_KEY = "class";
  var NEXT_MODE = "next_mode";
  var MODE_PARAM_FIELD = "mode_param";
  var SIDE = "side_px";
  var GRID_ROWS = "grid_rows";
  var GRID_COLUMNS = "grid_columns";
  var SEGMENT_ROW = "row";
  var SEGMENT_COLUMN = "grid_column";
  var SEGMENT_SPAN = "column_span";

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

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var PX = "px";

  var SEMICOLON = ";";
  var COLON = ":";
  var CHECKED_STATE = ":checked";
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

  var STRIP_CLASS = "acervator-header-strip";
  var TOP_ROW_CLASS = "acervator-header-top-row";
  var SPENDABLE_CLASS = "acervator-header-spendable";
  var CARD_CLASS = "acervator-header-card";
  var DOT_CLASS = "acervator-header-dot";
  var MODE_CLASS = "acervator-header-mode";
  var MODE_GROUP_CLASS = "acervator-header-class-group";
  var GROUP_LABEL = "Asset class group";

  var STRIP_PART = "strip";
  var TOP_ROW_PART = "top-row";
  var DOT_PART = "privacy-dot";
  var COUNTER_PART = "counter";
  var COUNTER_LABEL_PART = "counter-label";
  var COUNTER_VALUE_PART = "counter-value";
  var HIDDEN_CARD_PART = "hidden-card";
  var MODE_BUTTON_PART = "mode-button";

  var SPENDABLE_MODULE = "spendable_profits";
  var STAT_CARD_MODULE = "dashboard_stat_card";
  var STAT_CARD_API = "acervatorStatCard";
  var LOAD_SPENDABLE = "acervatorLoadProfits";

  // The request one card is built from, on the stat card surface's own terms.
  var CARD_LABEL_PARAM = "label";
  var CARD_VALUE_PARAM = "value";
  var CARD_FIELD_ID_PARAM = "field_id";
  var CARD_CLICKABLE_PARAM = "clickable";

  var PART_ATTR = "data-part";
  var CHILD_ATTR = "data-child-module";
  var COLUMNS_ATTR = "data-columns";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var FIELD_ID_ATTR = "data-field-id";
  var MASKED_ATTR = "data-masked";
  var CLICKABLE_ATTR = "data-clickable";
  var ACTION_ATTR = "data-action";
  var FRAME_SHAPE_ATTR = "data-frame-shape";
  var MODE_ATTR = "data-mode";
  var CLASS_ATTR = "data-asset-class";
  var FORMAT_ATTR = "data-format";
  var SOURCE_KEY_ATTR = "data-source-key";
  var LABEL_PROPERTY_ATTR = "data-label-property";
  var VALUE_PROPERTY_ATTR = "data-value-property";
  var WINDOW_TITLE_ATTR = "data-window-title";
  var DECLARED_SLOTS_ATTR = "data-declared-slots";
  var HELD_SLOTS_ATTR = "data-held-slots";
  var ARIA_PRESSED = "aria-pressed";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

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

  // A row or column of the square, each track an equal share and none sized
  // by the class name it holds.
  function tracks(count) {
    return "repeat(" + String(count) + ", minmax(0, 1fr))";
  }

  // A grid row, column or span arrives as a whole number and never a token.
  function cell(value, floor) {
    var read = Number(value);
    var least = floor === undefined ? 0 : floor;
    if (!isFinite(read) || read < least) {
      return least;
    }
    return Math.floor(read);
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

  // `styleOf` reads a base block, so the accent the active segment fills
  // with reaches the page through this and nothing else.
  function checkedStyle(sheet) {
    var found = {};
    stateRules(sheet).forEach(function (block) {
      if (carries(block.selector, CHECKED_STATE)) {
        found = styleOf(block.body);
      }
    });
    return found;
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

  // Every top row slot declares a floor, so a long amount cannot widen the
  // row past the pane and push the class group off its right edge.
  function slotFloor(model, slot) {
    var budget = objectField(model, WIDTH_BUDGET);
    var slots = objectField(budget, BUDGET_SLOTS);
    return owns(slots, slot) ? slots[slot] : undefined;
  }

  // A slot never spills: it shrinks to its floor and clips what will not fit.
  function withFloor(style, floor) {
    if (floor !== undefined) {
      style.minWidth = length(floor);
      style.overflow = "hidden";
    }
    return style;
  }

  function stretchOf(layout, at) {
    var stretch = listField(layout, CHILD_STRETCH);
    return at < stretch.length ? stretch[at] : undefined;
  }

  function firstStretch(layout) {
    return listField(layout, CHILD_STRETCH).slice().shift();
  }

  // A stretch of zero draws the slot at its own width; a stretch above zero
  // divides what the zero slots leave, as the QHBoxLayout stretch does.
  function withStretch(style, stretch) {
    if (stretch !== undefined) {
      style.flexGrow = stretch;
      style.flexShrink = 1;
      style.flexBasis = stretch > 0 ? 0 : "auto";
    }
    return style;
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

  // The space renderSpendable draws spendable_profits.js into.
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
    withStretch(style, props.stretch);
    withFloor(style, props.floor);
    var panelProps = { className: SPENDABLE_CLASS, style: style };
    panelProps[PART_ATTR] = SPENDABLE;
    panelProps[SLOT_ATTR] = SPENDABLE;
    panelProps[FRAME_SHAPE_ATTR] = text(layout[FRAME_SHAPE]);
    panelProps[COLUMNS_ATTR] = String(listField(model, COLUMNS).length);
    return element("div", panelProps, null);
  }

  // The space mountCounters draws one dashboard_stat_card.js card into.
  function CounterCard(props) {
    var model = props.model;
    var card = props.card;
    var layout = objectField(model, CARD_LAYOUT);
    var style = boxStyle(layout, COLUMN, MARGINS, SPACING);
    withAlign(style, layout, LABEL_ALIGN);
    style.cursor = cursorOf(card);
    withStretch(style, props.stretch);
    var cardProps = { className: CARD_CLASS, style: style, title: label(card[TOOLTIP]) };
    cardProps[PART_ATTR] = COUNTER_PART;
    cardProps[SLOT_ATTR] = text(card[KEY]);
    cardProps[KEY_ATTR] = text(card[KEY]);
    cardProps[FIELD_ID_ATTR] = text(card[FIELD_ID]);
    cardProps[FORMAT_ATTR] = text(card[FORMAT]);
    cardProps[SOURCE_KEY_ATTR] = text(card[SOURCE_KEY]);
    cardProps[CLICKABLE_ATTR] = text(card[CLICKABLE]);
    cardProps[FRAME_SHAPE_ATTR] = text(layout[FRAME_SHAPE]);
    cardProps[LABEL_PROPERTY_ATTR] = text(model[CARD_LABEL_PROPERTY]);
    cardProps[VALUE_PROPERTY_ATTR] = text(model[CARD_VALUE_PROPERTY]);
    if (card[CLICKABLE] === true) {
      cardProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[ERRORS_ACTION]);
    }
    return element("div", cardProps, null);
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

  // Asks METHOD for the wing NEXT_MODE names, then redraws.
  function modePressed(button, askedClass) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return Promise.resolve(null);
    }
    var field = text(button[MODE_PARAM_FIELD]);
    // A class button names itself; NEXT_MODE serves a caller holding no class.
    var wing = askedClass === undefined ? text(button[NEXT_MODE]) : askedClass;
    if (field === undefined || wing === undefined) {
      return Promise.resolve(null);
    }
    var asked = {};
    asked[field] = wing;
    return global.acervator.call(METHOD, asked).then(function (model) {
      setHeader(model);
      redraw();
      return model;
    });
  }

  // One segment per asset class, placed at its own grid row and column. The
  // group's element carries the active class, so a reader finds it without
  // walking the segments.
  function ModeButton(props) {
    var model = isPlainObject(props.button) ? props.button : {};
    var action = text(
      isPlainObject(props.actions) ? props.actions[MODE_ACTION] : undefined
    );
    var buttons = listField(model, BUTTONS).map(function (each) {
      var key = text(each[CLASS_KEY]);
      var style = styleOf(each[STYLE_SHEET]);
      if (each[CHECKED]) {
        var fill = checkedStyle(each[STYLE_SHEET]);
        Object.keys(fill).forEach(function (property) {
          style[property] = fill[property];
        });
      }
      // `MINIMUM_WIDTH` equals the track's own width, because `SIDE` is that
      // floor times the columns. The class name elides, as the Qt segment does.
      style.minWidth = length(model[MINIMUM_WIDTH]);
      style.overflow = "hidden";
      style.textOverflow = "ellipsis";
      style.whiteSpace = "nowrap";
      style.gridRow = String(cell(each[SEGMENT_ROW]) + 1);
      style.gridColumn =
        String(cell(each[SEGMENT_COLUMN]) + 1) +
        " / span " +
        String(cell(each[SEGMENT_SPAN], 1));
      var one = {
        key: key,
        className: MODE_CLASS,
        style: style,
        title: label(each[TOOLTIP]),
        type: "button",
        onClick: function () {
          return modePressed(model, key);
        }
      };
      one[PART_ATTR] = MODE_BUTTON_PART;
      one[CLASS_ATTR] = key;
      one[ARIA_PRESSED] = text(each[CHECKED]);
      return element("button", one, text(each[TEXT]));
    });

    // OVERTAKEN, quoted whole:
    //   "Both sides are `SIDE`, the number the Qt widget is fixed to, so a track
    //   is `minmax(0, 1fr)` and no class name widens the square."
    // True today: both sides are `SIDE`, the number the Qt widget is fixed to,
    // and the widest class name is what widens it.
    var side = length(model[SIDE]);
    var groupStyle = {
      display: "grid",
      gap: length(model[GROUP_SPACING]),
      gridTemplateColumns: tracks(cell(model[GRID_COLUMNS], 1)),
      gridTemplateRows: tracks(cell(model[GRID_ROWS], 1)),
      width: side,
      height: side,
      minWidth: side,
      maxWidth: side,
      flexGrow: 0,
      flexShrink: 0,
      alignSelf: "center",
      overflow: "hidden"
    };
    var groupProps = {
      className: MODE_GROUP_CLASS,
      style: groupStyle,
      role: "group",
      "aria-label": GROUP_LABEL
    };
    groupProps[SLOT_ATTR] = MODE_BUTTON;
    groupProps[MODE_ATTR] = text(model[MODE]);
    groupProps[WINDOW_TITLE_ATTR] = text(model[WINDOW_TITLE]);
    groupProps[ACTION_ATTR] = action;
    return element("div", groupProps, buttons);
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
    var floor = slotFloor(model, slot);
    if (slot === SPENDABLE) {
      return element(SpendablePanel, {
        key: slot,
        spendable: model[SPENDABLE],
        stretch: stretch,
        floor: floor
      });
    }
    if (slot === MODE_BUTTON) {
      return element(ModeButton, {
        key: slot,
        button: model[MODE_BUTTON],
        actions: objectField(model, ACTIONS),
        stretch: stretch,
        floor: floor
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
      stretch: stretch,
      floor: floor
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

    var children = [];
    order.forEach(function (slot, at) {
      children.push(slotNode(model, slot, at));
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

  function spaceNamed(target, part, key) {
    if (!target || typeof target.querySelector !== "function") {
      return null;
    }
    var selector = SELECT_OPEN + PART_ATTR + SELECT_IS + part + SELECT_CLOSE;
    if (key !== undefined) {
      selector += SELECT_OPEN + KEY_ATTR + SELECT_IS + key + SELECT_CLOSE;
    }
    return target.querySelector(selector);
  }

  // Draws spendable_profits.js into the SPENDABLE space. The panel host does
  // the drawing, so a module that registers no panel is named on the space
  // rather than leaving it blank.
  function renderSpendable(target, model) {
    var host = global.acervatorPanelHost;
    var space = spaceNamed(target, SPENDABLE);
    if (!host || space === null) {
      return null;
    }
    space.setAttribute(CHILD_ATTR, SPENDABLE_MODULE);
    return host.mount(SPENDABLE_MODULE, space, model) ? space : null;
  }

  function mountSpendable(target) {
    var loader = global[LOAD_SPENDABLE];
    var wait = typeof loader === "function" ? loader({}) : Promise.resolve(null);
    return Promise.resolve(wait).then(function (model) {
      return renderSpendable(target, model) === null ? null : SPENDABLE_MODULE;
    });
  }

  // One counter as the label, value, field_id and clickable a card is built from.
  function cardRequest(card) {
    var asked = {};
    asked[CARD_LABEL_PARAM] = text(card[LABEL]);
    asked[CARD_VALUE_PARAM] = text(card[TEXT]);
    if (text(card[FIELD_ID]) !== undefined) {
      asked[CARD_FIELD_ID_PARAM] = text(card[FIELD_ID]);
    }
    asked[CARD_CLICKABLE_PARAM] = card[CLICKABLE] === true;
    return asked;
  }

  // Draws one dashboard_stat_card.js card into each COUNTERS space.
  function mountCounters(target, model) {
    var api = global[STAT_CARD_API];
    var reachable =
      Boolean(global.acervator) && typeof global.acervator.call === "function";
    if (!api || typeof api.renderCard !== "function" || !reachable) {
      return Promise.resolve([]);
    }
    var drawn = [];
    var chain = Promise.resolve();
    listField(model, COUNTERS).forEach(function (card) {
      var space = spaceNamed(target, COUNTER_PART, text(card[KEY]));
      if (space === null) {
        return;
      }
      chain = chain
        .then(function () {
          return global.acervator.call(api.method, cardRequest(card));
        })
        .then(function (built) {
          space.setAttribute(CHILD_ATTR, STAT_CARD_MODULE);
          api.renderCard(space, built);
          drawn.push(text(card[KEY]));
        });
    });
    return chain.then(function () {
      return drawn;
    });
  }

  // mountSpendable and mountCounters, run together.
  function mountChildren(target, model) {
    return Promise.all([
      mountSpendable(target),
      mountCounters(target, model)
    ]).then(function (drawn) {
      return drawn;
    });
  }

  function renderStrip(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    var shown = draw(target, element(Strip, { model: payload }));
    mountChildren(target, payload);
    return shown;
  }

  // Every host this module has drawn into, re-drawn from the held model.
  function redraw() {
    roots.forEach(function (pair) {
      renderStrip(pair.node, held === null ? null : held.model);
    });
    return roots.length;
  }

  function forget() {
    held = null;
    headerFaults = [];
    loadFault = null;
    asked = null;
  }

  // The shell draws this strip by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere. The strip
  // is chrome, so it takes no tab and stays on screen for every tab.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      kind: global.acervatorPanelHost.chromeKind,
      render: renderStrip,
      load: loadHeader,
      loadError: loadError
    });
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
    renderSpendable: renderSpendable,
    mountSpendable: mountSpendable,
    mountCounters: mountCounters,
    mountChildren: mountChildren,
    cardRequest: cardRequest,
    modePressed: modePressed,
    redraw: redraw,
    forget: forget
  };
})(window);
