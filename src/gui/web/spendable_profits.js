// The `spendable_profits.state` payload, drawn as the strip Qt paints.
(function (global) {
  "use strict";

  var METHOD = "spendable_profits.state";

  var FRAME = "frame";
  var ALPHA_SCALE = "alpha_scale";
  var LAYOUT = "layout";
  var SEPARATOR = "separator";
  var ITEMS = "items";
  var ITEM_COUNT = "item_count";
  var ORDER = "order";
  var FIELD_IDS = "field_ids";
  var COLUMN_COUNT = "column_count";
  var COLUMNS = "columns";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var METHOD_FIELD = "method";

  var DECLARED_FIELDS = [
    ACTIONS,
    ALPHA_SCALE,
    BUS_TOPICS,
    CALLS,
    CALL_NAMES,
    COLUMNS,
    COLUMN_COUNT,
    FIELD_IDS,
    FRAME,
    ITEMS,
    ITEM_COUNT,
    LAYOUT,
    METHOD_FIELD,
    ORDER,
    SEPARATOR,
    TIMERS,
    TIMER_DELAYS
  ];

  var KEY = "key";
  var LABEL = "label";
  var LABEL_STYLE = "label_style";
  var LABEL_TOOLTIP = "label_tooltip";
  var FIELD_ID = "field_id";
  var SOURCE_KEY = "source_key";
  var DEFAULT = "default";
  var INITIAL_TEXT = "initial_text";
  var INITIAL_STYLE = "initial_style";
  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var TOOLTIP = "tooltip";
  var DOT = "dot";

  var COLUMN_FIELDS = [
    DEFAULT,
    DOT,
    FIELD_ID,
    INITIAL_STYLE,
    INITIAL_TEXT,
    KEY,
    LABEL,
    LABEL_STYLE,
    LABEL_TOOLTIP,
    SOURCE_KEY,
    STYLE_SHEET,
    TEXT,
    TOOLTIP
  ];

  var FRAME_SHAPE = "frame_shape";
  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var COLUMN_MARGINS = "column_margins_px";
  var RULE_W = "rule_w_px";
  var COLUMN_SPACING = "column_spacing_px";
  var DOT_ALIGN = "dot_align";
  var COLUMN_ALIGN = "column_align";
  var COLUMN_STRETCH = "column_stretch";
  var ALIGN = "align";

  var KIND = "kind";
  var COLUMN = "column";
  var PIXELS = "px";
  var LAYOUT_KIND = "layout";
  var SPACING_KIND = "spacing";
  var SEPARATOR_KIND = "separator";
  var STRETCH_KIND = "stretch";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var COUNT_FAULT = "count";
  var ORDER_FAULT = "order";
  var UNNAMED_COLUMN_FAULT = "unnamed-column";
  var UNNAMED_CALL_FAULT = "unnamed-call";
  var FIELD_ID_FAULT = "field-id";
  var MARKUP_FAULT = "markup";
  var UNKNOWN_KIND_FAULT = "unknown-kind";

  var NO_BRIDGE = "the preload bridge is not present";

  var HOST_CLASS = "acervator-profits";
  var FRAME_PART = "frame";
  var STYLE_PART = "frame-style";
  var COLUMN_PART = "column";
  var LABEL_PART = "column-label";
  var VALUE_PART = "column-value";
  var DOT_PART = "column-dot";
  var SEPARATOR_PART = "separator";
  var SPACER_PART = "spacer";
  var STRETCH_PART = "stretch";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var FIELD_ID_ATTR = "data-field-id";
  var SHAPE_ATTR = "data-frame-shape";

  var EMPTY = "";
  var SPACE = " ";
  var COMMA = ",";
  var COLON = ":";
  var SEMICOLON = ";";
  var DASH = "-";
  var CLASS_MARK = ".";
  var PART_OPEN = "[data-part=";
  var PART_CLOSE = "]";
  var QUOTE = '"';
  var CHILD_SPAN = " span";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";
  var PATH_SPLIT = ".";
  var TAG_OPEN = "<";
  var PERCENT = "%";
  var PX_UNIT = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";

  var RGBA_OPEN = "rgba(";
  var ROUND_OPEN = "(";
  var ROUND_CLOSE = ")";
  var GRADIENT_OPEN = "qlineargradient(";
  var LINEAR_OPEN = "linear-gradient(";
  var STOP_NAME = "stop";

  var FLEX = "flex";
  var ROW = "row";
  var COLUMN_FLOW = "column";
  var CENTRE = "center";
  var FLEX_AUTO = "1 1 auto";
  var NO_SHRINK = "0 0 auto";
  var ZERO_WIDTH = "0";

  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  // The two horizontal alignments the strip's layout numbers name.
  var ALIGNMENT = {
    "hcenter": { alignItems: CENTRE },
    "vcenter": { alignSelf: CENTRE }
  };

  // The published fields that must arrive as a bag, and those as a list.
  var BAG_FIELDS = [ACTIONS, FIELD_IDS, FRAME, LAYOUT, SEPARATOR, TIMERS];
  var LIST_FIELDS = [BUS_TOPICS, CALLS, CALL_NAMES, COLUMNS, ITEMS, ORDER, TIMER_DELAYS];

  // A CSS direction word per signed step between the gradient's corners.
  var DIRECTION_BY_STEP = {
    "1,0": "to right",
    "-1,0": "to left",
    "0,1": "to bottom",
    "0,-1": "to top",
    "1,1": "to bottom right",
    "1,-1": "to top right",
    "-1,1": "to bottom left",
    "-1,-1": "to top left",
    "0,0": "to right"
  };

  var ZERO = 0;
  var ONE = 1;
  var FOUR = 4;
  var PER_CENT = 100;
  var RECIPROCAL = -1;

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
    Object.keys(bag).forEach(function (name) {
      found[name] = bag[name];
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

  // A label the surface leaves empty stays off the element.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function alphaScale() {
    var scale = held === null ? undefined : held.model[ALPHA_SCALE];
    return typeof scale === "number" && scale > ZERO ? scale : ONE;
  }

  // Qt writes the fourth rgba channel over the scale CSS wants a fraction of.
  function rgbaText(inner, scale) {
    var parts = String(inner).split(COMMA);
    if (parts.length === FOUR) {
      parts[FOUR - ONE] = String(Number(parts[FOUR - ONE]) * Math.pow(scale, RECIPROCAL));
    }
    return RGBA_OPEN + parts.join(COMMA) + ROUND_CLOSE;
  }

  function withColours(body, scale) {
    var source = String(body);
    var drawn = EMPTY;
    var at = ZERO;
    while (at < source.length) {
      var start = source.indexOf(RGBA_OPEN, at);
      if (start < ZERO) {
        drawn += source.slice(at);
        return drawn;
      }
      var stop = source.indexOf(ROUND_CLOSE, start);
      if (stop < ZERO) {
        drawn += source.slice(at);
        return drawn;
      }
      drawn += source.slice(at, start);
      drawn += rgbaText(source.slice(start + RGBA_OPEN.length, stop), scale);
      at = stop + ONE;
    }
    return drawn;
  }

  // The index of the `)` closing the `(` at `openAt`, nesting counted.
  function balancedEnd(source, openAt) {
    var depth = ZERO;
    var at = openAt;
    while (at < source.length) {
      if (source.charAt(at) === ROUND_OPEN) {
        depth += ONE;
      }
      if (source.charAt(at) === ROUND_CLOSE) {
        depth -= ONE;
        if (depth === ZERO) {
          return at;
        }
      }
      at += ONE;
    }
    return RECIPROCAL;
  }

  // One argument list, split on the commas outside any nested brackets.
  function topLevelParts(inner) {
    var found = [];
    var carried = EMPTY;
    var depth = ZERO;
    String(inner)
      .split(EMPTY)
      .forEach(function (letter) {
        if (letter === ROUND_OPEN) {
          depth += ONE;
        }
        if (letter === ROUND_CLOSE) {
          depth -= ONE;
        }
        if (letter === COMMA && depth === ZERO) {
          found.push(carried);
          carried = EMPTY;
          return;
        }
        carried += letter;
      });
    found.push(carried);
    return found.map(function (one) {
      return one.trim();
    });
  }

  function stepOf(from, to) {
    return String(Math.sign(Number(to) - Number(from)));
  }

  // `qlineargradient` as the CSS gradient the same corners describe.
  function gradientText(inner, scale) {
    var corners = {};
    var stops = [];
    topLevelParts(inner).forEach(function (part) {
      var head = part.slice(ZERO, part.indexOf(COLON)).trim();
      var tail = part.slice(part.indexOf(COLON) + ONE).trim();
      if (head === STOP_NAME) {
        var at = tail.indexOf(SPACE);
        stops.push({
          at: Number(tail.slice(ZERO, at)) * PER_CENT,
          colour: withColours(tail.slice(at + ONE).trim(), scale)
        });
        return;
      }
      corners[head] = tail;
    });
    var step = stepOf(corners.x1, corners.x2) + COMMA + stepOf(corners.y1, corners.y2);
    var direction = owns(DIRECTION_BY_STEP, step)
      ? DIRECTION_BY_STEP[step]
      : DIRECTION_BY_STEP["0,0"];
    var drawn = stops.map(function (one) {
      return one.colour + SPACE + String(one.at) + PERCENT;
    });
    drawn.unshift(direction);
    return LINEAR_OPEN + drawn.join(VAR_SPLIT) + ROUND_CLOSE;
  }

  function withGradients(body, scale) {
    var source = String(body);
    var start = source.indexOf(GRADIENT_OPEN);
    if (start < ZERO) {
      return withColours(source, scale);
    }
    var open = start + GRADIENT_OPEN.length - ONE;
    var stop = balancedEnd(source, open);
    if (stop < ZERO) {
      return withColours(source, scale);
    }
    return (
      withColours(source.slice(ZERO, start), scale) +
      gradientText(source.slice(open + ONE, stop), scale) +
      withGradients(source.slice(stop + ONE), scale)
    );
  }

  // `shared_widgets.js` names the one token carrying a value.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  function paint(value, scale) {
    var name = variableFor(value);
    if (name !== undefined) {
      return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
    }
    return withGradients(value, scale);
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

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

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

  // Every `property: value` of a sheet's base block, in written order.
  function declarations(sheet) {
    var found = [];
    if (sheet === null || sheet === undefined) {
      return found;
    }
    topLevelParts(baseBody(sheet).split(SEMICOLON).join(COMMA)).forEach(function (one) {
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

  function styleOf(sheet) {
    var scale = alphaScale();
    var style = {};
    declarations(sheet).forEach(function (one) {
      style[camelCase(one.property)] = paint(one.value, scale);
    });
    return style;
  }

  // A hover colour lives in no inline style, so it becomes a page rule.
  function hoverCss(sheet) {
    var scale = alphaScale();
    return stateRules(sheet)
      .map(function (rule) {
        var states = String(rule.selector).split(COLON);
        states.shift();
        var body = declarations(BLOCK_OPEN + rule.body + BLOCK_CLOSE)
          .map(function (one) {
            return one.property + COLON + SPACE + paint(one.value, scale) + SEMICOLON;
          })
          .join(SPACE);
        return (
          CLASS_MARK +
          HOST_CLASS +
          PART_OPEN +
          QUOTE +
          DOT_PART +
          QUOTE +
          PART_CLOSE +
          COLON +
          states.join(COLON) +
          CHILD_SPAN +
          BLOCK_OPEN +
          body +
          BLOCK_CLOSE
        );
      })
      .join(EMPTY);
  }

  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX_UNIT;
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

  function boxStyle(layout, flow, marginField, spacingField) {
    var style = marginStyle(layout, marginField);
    style.display = FLEX;
    style.flexDirection = flow;
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

  // privacy_dot.js draws the dot where the page loads it; header_strip.js
  // paints the bare glyph span otherwise.
  function dotSpan() {
    var own = global.acervatorDot;
    if (own && own.Dot) {
      return own.Dot;
    }
    var api = global.acervatorHeader;
    return api && api.PrivacyDot ? api.PrivacyDot : null;
  }

  function Column(props) {
    var column = isPlainObject(props.column) ? props.column : {};
    var layout = props.layout;
    var span = dotSpan();
    var columnStyle = boxStyle(layout, COLUMN_FLOW, COLUMN_MARGINS, COLUMN_SPACING);
    withAlign(columnStyle, layout, COLUMN_ALIGN);
    // One share of the row each, so the eight columns sit at one pitch.
    if (owns(layout, COLUMN_STRETCH)) {
      columnStyle.flex = String(layout[COLUMN_STRETCH]);
      columnStyle.minWidth = ZERO_WIDTH;
    }
    var columnProps = {
      className: HOST_CLASS,
      style: columnStyle
    };
    columnProps[PART_ATTR] = COLUMN_PART;
    columnProps[KEY_ATTR] = text(column[KEY]);
    columnProps[FIELD_ID_ATTR] = text(column[FIELD_ID]);

    var captionProps = {
      className: HOST_CLASS,
      style: styleOf(column[LABEL_STYLE]),
      title: label(column[LABEL_TOOLTIP])
    };
    captionProps[PART_ATTR] = LABEL_PART;

    var amountProps = {
      className: HOST_CLASS,
      style: styleOf(column[STYLE_SHEET]),
      title: label(column[TOOLTIP])
    };
    amountProps[PART_ATTR] = VALUE_PART;

    var dot = objectField(column, DOT);
    var dotProps = { className: HOST_CLASS, style: withAlign({}, layout, DOT_ALIGN) };
    dotProps[PART_ATTR] = DOT_PART;

    return element(
      "div",
      columnProps,
      element("div", captionProps, text(column[LABEL])),
      element("div", amountProps, text(column[TEXT])),
      element(
        "div",
        dotProps,
        span === null ? text(dot[TEXT]) : element(span, { dot: dot, model: dot })
      )
    );
  }

  function separatorNode(model, at) {
    var separator = objectField(model, SEPARATOR);
    var layout = objectField(model, LAYOUT);
    var style = styleOf(separator[STYLE_SHEET]);
    withAlign(style, layout, ALIGN);
    style.flex = NO_SHRINK;
    style.width = length(layout[RULE_W]);
    style.textAlign = "center";
    var props = { key: SEPARATOR_PART + String(at), className: HOST_CLASS, style: style };
    props[PART_ATTR] = SEPARATOR_PART;
    return element("span", props, text(separator[TEXT]));
  }

  function spacerNode(item, at) {
    var props = {
      key: SPACER_PART + String(at),
      className: HOST_CLASS,
      style: { flex: NO_SHRINK, width: length(item[PIXELS]) }
    };
    props[PART_ATTR] = SPACER_PART;
    return element("div", props, null);
  }

  function stretchNode(at) {
    var props = {
      key: STRETCH_PART + String(at),
      className: HOST_CLASS,
      style: { flex: FLEX_AUTO }
    };
    props[PART_ATTR] = STRETCH_PART;
    return element("div", props, null);
  }

  function columnByName(model, name) {
    var found = null;
    listField(model, COLUMNS).forEach(function (column) {
      if (isPlainObject(column) && column[KEY] === name) {
        found = column;
      }
    });
    return found;
  }

  function itemNode(model, item, at) {
    var layout = objectField(model, LAYOUT);
    if (!isPlainObject(item)) {
      return null;
    }
    if (item[KIND] === SEPARATOR_KIND) {
      return separatorNode(model, at);
    }
    if (item[KIND] === SPACING_KIND) {
      return spacerNode(item, at);
    }
    if (item[KIND] === STRETCH_KIND) {
      return stretchNode(at);
    }
    if (item[KIND] !== LAYOUT_KIND) {
      return null;
    }
    var column = columnByName(model, item[COLUMN]);
    if (column === null) {
      return null;
    }
    return element(Column, {
      key: COLUMN_PART + String(at),
      column: column,
      layout: layout
    });
  }

  function Strip(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var layout = objectField(model, LAYOUT);
    var frame = objectField(model, FRAME);
    var style = styleOf(frame[STYLE_SHEET]);
    var box = boxStyle(layout, ROW, MARGINS, SPACING);
    Object.keys(box).forEach(function (name) {
      style[name] = box[name];
    });
    var frameProps = { className: HOST_CLASS, style: style };
    frameProps[PART_ATTR] = FRAME_PART;
    frameProps[SHAPE_ATTR] = text(frame[FRAME_SHAPE]);

    var css = EMPTY;
    listField(model, COLUMNS).forEach(function (column) {
      if (!css) {
        css = hoverCss(objectField(column, DOT)[STYLE_SHEET]);
      }
    });
    var styleProps = { className: HOST_CLASS };
    styleProps[PART_ATTR] = STYLE_PART;

    var drawn = listField(model, ITEMS).map(function (item, at) {
      return itemNode(model, item, at);
    });
    if (css) {
      drawn.unshift(element("style", styleProps, css));
    }
    return element("div", frameProps, drawn);
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

  // A bag arriving as a scalar would walk as nothing and report nothing.
  function checkShapes(model) {
    BAG_FIELDS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        stripFaults.push(fault(null, field, WRONG_TYPE_FAULT, kindOf(model[field])));
      }
    });
    LIST_FIELDS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        stripFaults.push(fault(null, field, WRONG_TYPE_FAULT, kindOf(model[field])));
      }
    });
  }

  // A count and its list disagreeing would pair a cell with another name.
  function checkCounts(model) {
    if (model[COLUMN_COUNT] !== listField(model, COLUMNS).length) {
      stripFaults.push(
        fault(null, COLUMN_COUNT, COUNT_FAULT, listField(model, COLUMNS).length)
      );
    }
    if (model[ITEM_COUNT] !== listField(model, ITEMS).length) {
      stripFaults.push(
        fault(null, ITEM_COUNT, COUNT_FAULT, listField(model, ITEMS).length)
      );
    }
  }

  // The published order against the column names, name by name.
  function checkOrder(model) {
    var names = listField(model, COLUMNS).map(function (column) {
      return isPlainObject(column) ? column[KEY] : null;
    });
    var order = listField(model, ORDER);
    if (order.length !== names.length) {
      stripFaults.push(fault(ORDER, null, COUNT_FAULT, names.length));
    }
    order.forEach(function (name, at) {
      if (at < names.length && names[at] !== name) {
        stripFaults.push(fault(ORDER, name, ORDER_FAULT, names[at]));
      }
      if (columnByName(model, name) === null) {
        stripFaults.push(fault(ORDER, name, UNNAMED_COLUMN_FAULT, null));
      }
    });
  }

  // A dot hiding one field must sit under the column that field names.
  function checkFieldIds(model) {
    var published = objectField(model, FIELD_IDS);
    listField(model, COLUMNS).forEach(function (column) {
      if (!isPlainObject(column)) {
        return;
      }
      var name = column[KEY];
      if (owns(published, name) && published[name] !== column[FIELD_ID]) {
        stripFaults.push(fault(FIELD_IDS, name, FIELD_ID_FAULT, column[FIELD_ID]));
      }
      var dot = objectField(column, DOT);
      if (owns(dot, FIELD_ID) && dot[FIELD_ID] !== column[FIELD_ID]) {
        stripFaults.push(fault(DOT, name, FIELD_ID_FAULT, dot[FIELD_ID]));
      }
    });
  }

  // Every column field, named where it is absent or carries null.
  function checkColumns(model) {
    listField(model, COLUMNS).forEach(function (column, at) {
      if (!isPlainObject(column)) {
        stripFaults.push(fault(COLUMNS, String(at), NOT_AN_OBJECT_FAULT, kindOf(column)));
        return;
      }
      COLUMN_FIELDS.forEach(function (field) {
        if (!owns(column, field)) {
          stripFaults.push(fault(COLUMNS, field, MISSING_FAULT, column[KEY]));
        }
      });
      if (owns(column, TEXT) && owns(column, INITIAL_TEXT)) {
        if (kindOf(column[TEXT]) !== kindOf(column[INITIAL_TEXT])) {
          stripFaults.push(fault(COLUMNS, TEXT, WRONG_TYPE_FAULT, kindOf(column[TEXT])));
        }
      }
      if (owns(column, STYLE_SHEET) && owns(column, INITIAL_STYLE)) {
        if (kindOf(column[STYLE_SHEET]) !== kindOf(column[INITIAL_STYLE])) {
          stripFaults.push(
            fault(COLUMNS, STYLE_SHEET, WRONG_TYPE_FAULT, kindOf(column[STYLE_SHEET]))
          );
        }
      }
    });
  }

  // A tag in drawn text would reach a QLabel, which reads it as markup.
  function checkMarkup(model) {
    listField(model, COLUMNS).forEach(function (column) {
      if (!isPlainObject(column)) {
        return;
      }
      [TEXT, LABEL, TOOLTIP, LABEL_TOOLTIP].forEach(function (field) {
        var value = column[field];
        if (typeof value === "string" && carries(value, TAG_OPEN)) {
          stripFaults.push(fault(COLUMNS, field, MARKUP_FAULT, column[KEY]));
        }
      });
    });
  }

  // An item kind the strip cannot draw would leave a silent hole.
  function checkItems(model) {
    var kinds = [LAYOUT_KIND, SPACING_KIND, SEPARATOR_KIND, STRETCH_KIND];
    listField(model, ITEMS).forEach(function (item, at) {
      if (!isPlainObject(item)) {
        stripFaults.push(fault(ITEMS, String(at), NOT_AN_OBJECT_FAULT, kindOf(item)));
        return;
      }
      var known = false;
      kinds.forEach(function (one) {
        if (one === item[KIND]) {
          known = true;
        }
      });
      if (!known) {
        stripFaults.push(fault(ITEMS, String(at), UNKNOWN_KIND_FAULT, item[KIND]));
        return;
      }
      if (item[KIND] === LAYOUT_KIND && columnByName(model, item[COLUMN]) === null) {
        stripFaults.push(fault(ITEMS, String(at), UNNAMED_COLUMN_FAULT, item[COLUMN]));
      }
    });
  }

  // A branch the strip took that `call_names` never declared.
  function checkCalls(model) {
    var declared = listField(model, CALL_NAMES);
    listField(model, CALLS).forEach(function (name) {
      var known = false;
      declared.forEach(function (one) {
        if (one === name) {
          known = true;
        }
      });
      if (!known) {
        stripFaults.push(fault(CALLS, name, UNNAMED_CALL_FAULT, null));
      }
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function report() {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        columns: held.model[COLUMN_COUNT],
        items: held.model[ITEM_COUNT],
        calls: listField(held.model, CALL_NAMES).length
      },
      held: {
        fields: heldFieldCount(),
        columns: listField(held.model, COLUMNS).length,
        items: listField(held.model, ITEMS).length,
        calls: listField(held.model, CALLS).length
      },
      faults: stripFaults.slice()
    };
  }

  function setProfits(model) {
    if (!isPlainObject(model)) {
      held = null;
      stripFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: stripFaults.slice() };
    }
    held = { model: model };
    stripFaults = [];
    checkFields(model);
    checkShapes(model);
    checkCounts(model);
    checkOrder(model);
    checkFieldIds(model);
    checkColumns(model);
    checkMarkup(model);
    checkItems(model);
    checkCalls(model);
    return report();
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadProfits(params) {
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
        setProfits(model);
        redraw();
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

  function alphaScaleOf() {
    return field(ALPHA_SCALE);
  }

  function layout() {
    return bag(LAYOUT);
  }

  function separator() {
    return bag(SEPARATOR);
  }

  function items() {
    return list(ITEMS);
  }

  function itemCount() {
    return field(ITEM_COUNT);
  }

  function order() {
    return list(ORDER);
  }

  function fieldIds() {
    return bag(FIELD_IDS);
  }

  function columnCount() {
    return field(COLUMN_COUNT);
  }

  function columns() {
    return list(COLUMNS);
  }

  function column(name) {
    return held === null ? null : columnByName(held.model, name);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelaysMs() {
    return list(TIMER_DELAYS);
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

  function methodName() {
    return field(METHOD_FIELD);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function columnFields() {
    return COLUMN_FIELDS.slice();
  }

  function directionNames() {
    return Object.keys(DIRECTION_BY_STEP);
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

  // Every target already drawn into, redrawn from the state now held.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Strip, { model: held === null ? null : held.model }));
    });
  }

  function forget() {
    held = null;
    stripFaults = [];
    loadFault = null;
    asked = null;
  }

  // header_strip.js draws this strip by its module name; the host reads that
  // name off the script tag running now. It names no bridge method, so the
  // tab bar draws no tab for it.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderStrip,
      load: loadProfits,
      loadError: loadError
    });
  }

  global.acervatorSetProfits = setProfits;
  global.acervatorLoadProfits = loadProfits;
  global.acervatorProfits = {
    method: METHOD,
    Strip: Strip,
    Column: Column,
    styleOf: styleOf,
    hoverCss: hoverCss,
    declarations: declarations,
    stateRules: stateRules,
    withGradients: withGradients,
    frame: frame,
    alphaScale: alphaScaleOf,
    layout: layout,
    separator: separator,
    items: items,
    itemCount: itemCount,
    order: order,
    fieldIds: fieldIds,
    columnCount: columnCount,
    columns: columns,
    column: column,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    busTopics: busTopics,
    callNames: callNames,
    calls: calls,
    methodName: methodName,
    declaredFields: declaredFields,
    columnFields: columnFields,
    directionNames: directionNames,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderStrip: renderStrip,
    forget: forget
  };
})(window);
