// Draws the Launcher screen from the launcher.state payload: a heading,
// a prompt, two large mode cards side by side, and a footer line.
//
// Every word, colour and measurement is a field of the payload. The
// module's own work is reading Qt's style sheets: a Qt sheet names a
// selector and may carry a :hover block, neither of which an inline
// style can hold, so the base declarations are painted inline and the
// hover values are published as custom properties the page can use.
(function (global) {
  "use strict";

  var METHOD = "launcher.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALIGNMENTS = "alignments";
  var BACKGROUND = "background";
  var CALLS = "calls";
  var CARD_HEAD_ORDER = "card_head_order";
  var CARD_TAIL_ORDER = "card_tail_order";
  var CARDS = "cards";
  var CARDS_ROW = "cards_row";
  var COLORS = "colors";
  var FEATURE_SLOT_FORMAT = "feature_slot_format";
  var FOOTER = "footer";
  var HEADING = "heading";
  var HEADING_GAP_PX = "heading_gap_px";
  var MODES = "modes";
  var PROMPT = "prompt";
  var WINDOW = "window";
  var WINDOW_ORDER = "window_order";

  // Every top-level field the screen is drawn from.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ALIGNMENTS,
    BACKGROUND,
    CALLS,
    CARD_HEAD_ORDER,
    CARD_TAIL_ORDER,
    CARDS,
    CARDS_ROW,
    COLORS,
    FEATURE_SLOT_FORMAT,
    FOOTER,
    HEADING,
    HEADING_GAP_PX,
    MODES,
    PROMPT,
    WINDOW,
    WINDOW_ORDER
  ];

  var TITLE = "title";
  var WIDTH_PX = "width_px";
  var HEIGHT_PX = "height_px";
  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var STYLE_SHEET = "style_sheet";
  var TEXT_FIELD = "text";
  var ALIGNMENT_VALUE = "alignment_value";
  var WORD_WRAP = "word_wrap";
  var ORDER = "order";
  var GRADIENT = "gradient";
  var STOPS = "stops";
  var CENTER_VALUE = "center_value";

  var CARD_TYPE_NAME = "type_name";
  var CARD_CURSOR = "cursor";
  var CARD_ICON = "icon";
  var CARD_TITLE = "title";
  var CARD_SUBTITLE = "subtitle";
  var CARD_FEATURES = "features";
  var CARD_BUTTON = "button";
  var CARD_SHADOW = "shadow";
  var CARD_GAP_PX = "gap_px";
  var CARD_CHILD_ORDER = "child_order";
  var CARD_COLOR = "color";
  var CARD_CLICKS = "clicks";
  var CARD_HOVERED = "hovered";

  var SHADOW_BLUR = "blur_radius_px";
  var SHADOW_OFFSET = "offset_px";

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt writes a hover rule as its own selector block. An inline style
  // holds no pseudo-state, so a hover value is published as a custom
  // property and the page's own rule reads it.
  var HOVER_MARK = ":hover";
  var HOVER_PROPERTY = "--launcher-hover-";

  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";
  var RULE_SPLIT = ";";
  var DECLARATION_SPLIT = ":";
  var WORD_SPLIT = "-";
  var EMPTY = "";
  var PX = "px";

  // A gradient stop is published as a share of the run; CSS wants a
  // percentage of it.
  var PERCENT_SCALE = 100;
  var PERCENT = "%";
  var GRADIENT_OPEN = "linear-gradient(";
  var LIST_SPLIT = ", ";
  var CLOSE = ")";
  var SPACE = " ";
  var TO_BOTTOM = "to bottom";

  var CENTRED = "center";
  var LEADING = "left";
  var COLUMN = "column";
  var ROW = "row";
  var FLEX = "flex";
  var WRAP_ON = "anywhere";
  var WRAP_OFF = "normal";
  var POINTER = "pointer";
  var BUTTON_KIND = "button";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var CLICKS_ATTR = "data-clicks";
  var HOVERED_ATTR = "data-hovered";
  var TYPE_ATTR = "data-type";
  var ARIA_LABEL = "aria-label";

  var PART_SCREEN = "screen";
  var PART_HEADING = "heading";
  var PART_PROMPT = "prompt";
  var PART_GAP = "gap";
  var PART_ROW = "cards-row";
  var PART_CARD = "card";
  var PART_ICON = "card-icon";
  var PART_TITLE = "card-title";
  var PART_SUBTITLE = "card-subtitle";
  var PART_FEATURE = "card-feature";
  var PART_BUTTON = "card-button";
  var PART_FOOTER = "footer";

  var held = null;
  var launcherFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function objectField(model, name) {
    return isPlainObject(model) && isPlainObject(model[name]) ? model[name] : {};
  }

  function listField(model, name) {
    return isPlainObject(model) && Array.isArray(model[name]) ? model[name] : [];
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? NOT_AN_OBJECT_FAULT : typeof value;
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function pixels(value) {
    return isNumber(value) ? String(value) + PX : undefined;
  }

  // -- Qt style sheets -------------------------------------------------

  // "font-size" as the "fontSize" a React style object takes.
  function cssName(name) {
    return name
      .split(WORD_SPLIT)
      .map(function (one, at) {
        return at === 0 ? one : one.charAt(0).toUpperCase() + one.slice(1);
      })
      .join(EMPTY);
  }

  function readDeclarations(body, into) {
    body.split(RULE_SPLIT).forEach(function (one) {
      var at = one.indexOf(DECLARATION_SPLIT);
      if (at < 0) {
        return;
      }
      into[cssName(one.slice(0, at).trim())] = one.slice(at + 1).trim();
    });
    return into;
  }

  // One Qt sheet read as the base declarations and the hover ones. A
  // sheet with no selector block is all base. The selector itself is
  // Qt's own class name and reaches no browser.
  function qtSheet(sheet) {
    var found = { base: {}, hover: {} };
    if (typeof sheet !== "string" || sheet === EMPTY) {
      return found;
    }
    if (sheet.indexOf(BLOCK_OPEN) < 0) {
      readDeclarations(sheet, found.base);
      return found;
    }
    var rest = sheet;
    while (rest.indexOf(BLOCK_OPEN) >= 0) {
      var opened = rest.indexOf(BLOCK_OPEN);
      var closed = rest.indexOf(BLOCK_CLOSE, opened);
      if (closed < 0) {
        break;
      }
      var selector = rest.slice(0, opened);
      var body = rest.slice(opened + 1, closed);
      readDeclarations(
        body,
        selector.indexOf(HOVER_MARK) >= 0 ? found.hover : found.base
      );
      rest = rest.slice(closed + 1);
    }
    return found;
  }

  // The hover declarations as the custom properties a page rule reads.
  function hoverProperties(hover) {
    var found = {};
    Object.keys(hover).forEach(function (name) {
      found[HOVER_PROPERTY + name] = hover[name];
    });
    return found;
  }

  // One sheet as the style object an element carries: the base
  // declarations, and the hover ones as custom properties beside them.
  function styleOf(sheet) {
    var read = qtSheet(sheet);
    var found = copyOf(read.base);
    var properties = hoverProperties(read.hover);
    Object.keys(properties).forEach(function (name) {
      found[name] = properties[name];
    });
    return found;
  }

  // -- geometry --------------------------------------------------------

  function alignmentOf(model, value) {
    var named = objectField(model, ALIGNMENTS);
    return value === named[CENTER_VALUE] ? CENTRED : LEADING;
  }

  // The background wash as CSS reads it: the same stops, each at its own
  // share of the run written as a percentage.
  function washOf(model) {
    var stops = listField(objectField(objectField(model, BACKGROUND), GRADIENT), STOPS);
    if (!stops.length) {
      return undefined;
    }
    return (
      GRADIENT_OPEN +
      TO_BOTTOM +
      LIST_SPLIT +
      stops
        .map(function (one) {
          return String(one[1]) + SPACE + String(one[0] * PERCENT_SCALE) + PERCENT;
        })
        .join(LIST_SPLIT) +
      CLOSE
    );
  }

  // The card's drop shadow as CSS reads it. Qt's blur radius and a
  // browser's are not the same measure, so the value is carried as the
  // payload writes it rather than adjusted here.
  function shadowOf(card) {
    var shadow = objectField(card, CARD_SHADOW);
    var offset = Array.isArray(shadow[SHADOW_OFFSET]) ? shadow[SHADOW_OFFSET] : [];
    if (!isNumber(shadow[SHADOW_BLUR])) {
      return undefined;
    }
    return (
      pixels(offset[0]) +
      SPACE +
      pixels(offset[1]) +
      SPACE +
      pixels(shadow[SHADOW_BLUR]) +
      SPACE +
      String(shadow[CARD_COLOR])
    );
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // -- the parts of the screen -----------------------------------------

  function Line(props) {
    var model = props.model;
    var line = objectField(model, props.field);
    var lineProps = {
      style: copyOf(styleOf(line[STYLE_SHEET]))
    };
    lineProps.style.textAlign = alignmentOf(model, line[ALIGNMENT_VALUE]);
    lineProps.style.overflowWrap = line[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    lineProps[PART_ATTR] = props.part;
    lineProps[NAME_ATTR] = props.field;
    return element("div", lineProps, text(line[TEXT_FIELD]));
  }

  function Feature(props) {
    var model = props.model;
    var feature = props.feature;
    var featureProps = {
      key: props.at,
      style: copyOf(styleOf(feature[STYLE_SHEET]))
    };
    featureProps.style.textAlign = alignmentOf(model, feature[ALIGNMENT_VALUE]);
    featureProps.style.overflowWrap = feature[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    featureProps[PART_ATTR] = PART_FEATURE;
    featureProps[NAME_ATTR] = String(props.at);
    return element("div", featureProps, text(feature[TEXT_FIELD]));
  }

  function CardText(props) {
    var model = props.model;
    var part = objectField(props.card, props.field);
    var partProps = { style: copyOf(styleOf(part[STYLE_SHEET])) };
    partProps.style.textAlign = alignmentOf(model, part[ALIGNMENT_VALUE]);
    partProps.style.overflowWrap = part[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    partProps[PART_ATTR] = props.part;
    return element("div", partProps, text(part[TEXT_FIELD]));
  }

  function Card(props) {
    var model = props.model;
    var card = objectField(objectField(model, CARDS), props.name);
    var margins = Array.isArray(card[MARGINS_PX]) ? card[MARGINS_PX] : [];
    var cardProps = { style: copyOf(styleOf(card[STYLE_SHEET])) };
    cardProps.style.display = FLEX;
    cardProps.style.flexDirection = COLUMN;
    cardProps.style.width = pixels(card[WIDTH_PX]);
    cardProps.style.height = pixels(card[HEIGHT_PX]);
    cardProps.style.gap = pixels(card[SPACING_PX]);
    cardProps.style.paddingLeft = pixels(margins[0]);
    cardProps.style.paddingTop = pixels(margins[1]);
    cardProps.style.paddingRight = pixels(margins[2]);
    cardProps.style.paddingBottom = pixels(margins[3]);
    cardProps.style.boxShadow = shadowOf(card);
    cardProps.style.cursor = POINTER;
    cardProps[PART_ATTR] = PART_CARD;
    cardProps[NAME_ATTR] = props.name;
    cardProps[TYPE_ATTR] = text(card[CARD_TYPE_NAME]);
    cardProps[CLICKS_ATTR] = text(card[CARD_CLICKS]);
    cardProps[HOVERED_ATTR] = text(card[CARD_HOVERED]);
    cardProps[ARIA_LABEL] = text(card[ACCESSIBLE_NAME]);

    var button = objectField(card, CARD_BUTTON);
    var buttonProps = {
      type: BUTTON_KIND,
      disabled: true,
      style: styleOf(button[STYLE_SHEET])
    };
    buttonProps[PART_ATTR] = PART_BUTTON;

    var gapProps = { style: { height: pixels(card[CARD_GAP_PX]) } };
    gapProps[PART_ATTR] = PART_GAP;

    return element(
      "div",
      cardProps,
      element(CardText, {
        model: model,
        card: card,
        field: CARD_ICON,
        part: PART_ICON
      }),
      element(CardText, {
        model: model,
        card: card,
        field: CARD_TITLE,
        part: PART_TITLE
      }),
      element(CardText, {
        model: model,
        card: card,
        field: CARD_SUBTITLE,
        part: PART_SUBTITLE
      }),
      element("div", gapProps),
      listField(card, CARD_FEATURES).map(function (one, at) {
        return element(Feature, { key: at, model: model, feature: one, at: at });
      }),
      element("button", buttonProps, text(button[TEXT_FIELD]))
    );
  }

  function Launcher(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var frame = objectField(model, WINDOW);
    var margins = Array.isArray(frame[MARGINS_PX]) ? frame[MARGINS_PX] : [];
    var screenProps = { style: copyOf(styleOf(frame[STYLE_SHEET])) };
    screenProps.style.display = FLEX;
    screenProps.style.flexDirection = COLUMN;
    screenProps.style.width = pixels(frame[WIDTH_PX]);
    screenProps.style.height = pixels(frame[HEIGHT_PX]);
    screenProps.style.gap = pixels(frame[SPACING_PX]);
    screenProps.style.paddingLeft = pixels(margins[0]);
    screenProps.style.paddingTop = pixels(margins[1]);
    screenProps.style.paddingRight = pixels(margins[2]);
    screenProps.style.paddingBottom = pixels(margins[3]);
    screenProps.style.backgroundImage = washOf(model);
    screenProps[PART_ATTR] = PART_SCREEN;
    screenProps[ARIA_LABEL] = text(model[ACCESSIBLE_NAME]);
    screenProps[TYPE_ATTR] = text(frame[TITLE]);

    var gapProps = { style: { height: pixels(model[HEADING_GAP_PX]) } };
    gapProps[PART_ATTR] = PART_GAP;

    var row = objectField(model, CARDS_ROW);
    var rowProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        gap: pixels(row[SPACING_PX]),
        justifyContent: CENTRED
      }
    };
    rowProps[PART_ATTR] = PART_ROW;

    return element(
      "div",
      screenProps,
      element(Line, { model: model, field: HEADING, part: PART_HEADING }),
      element(Line, { model: model, field: PROMPT, part: PART_PROMPT }),
      element("div", gapProps),
      element(
        "div",
        rowProps,
        listField(row, ORDER).map(function (one) {
          return element(Card, { key: one, model: model, name: one });
        })
      ),
      element(Line, { model: model, field: FOOTER, part: PART_FOOTER })
    );
  }

  // -- holding the payload ---------------------------------------------

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        launcherFaults.push(fault(null, name, MISSING_FAULT, null));
      }
    });
  }

  function heldFieldTotal() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function setLauncher(model) {
    if (!isPlainObject(model)) {
      held = null;
      launcherFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: launcherFaults.slice() };
    }
    held = { model: model };
    launcherFaults = [];
    checkFields(model);
    return {
      declared: { fields: DECLARED_FIELDS.length },
      held: {
        fields: heldFieldTotal(),
        cards: listField(objectField(model, CARDS_ROW), ORDER).length
      },
      faults: launcherFaults.slice()
    };
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadLauncher(params) {
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
        setLauncher(model);
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

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function cardNames() {
    return held === null
      ? []
      : listField(objectField(held.model, CARDS_ROW), ORDER).slice();
  }

  function cardOf(name) {
    return held === null ? {} : copyOf(objectField(objectField(held.model, CARDS), name));
  }

  function cardChildOrder(name) {
    return listField(cardOf(name), CARD_CHILD_ORDER).slice();
  }

  function cardStyle(name) {
    return styleOf(cardOf(name)[STYLE_SHEET]);
  }

  function cardHover(name) {
    return qtSheet(cardOf(name)[STYLE_SHEET]).hover;
  }

  function buttonStyle(name) {
    return styleOf(objectField(cardOf(name), CARD_BUTTON)[STYLE_SHEET]);
  }

  function buttonHover(name) {
    return qtSheet(objectField(cardOf(name), CARD_BUTTON)[STYLE_SHEET]).hover;
  }

  function cardShadow(name) {
    return shadowOf(cardOf(name));
  }

  function featureTexts(name) {
    return listField(cardOf(name), CARD_FEATURES).map(function (one) {
      return one[TEXT_FIELD];
    });
  }

  function backgroundWash() {
    return held === null ? undefined : washOf(held.model);
  }

  function alignmentWord(value) {
    return held === null ? undefined : alignmentOf(held.model, value);
  }

  function screenOrder() {
    return held === null ? [] : listField(held.model, WINDOW_ORDER).slice();
  }

  function pressCalls() {
    return held === null ? [] : listField(held.model, CALLS).slice();
  }

  function faults() {
    return launcherFaults.slice();
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

  function renderLauncher(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Launcher, { model: payload }));
  }

  function forget() {
    held = null;
    launcherFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetLauncher = setLauncher;
  global.acervatorLoadLauncher = loadLauncher;
  global.acervatorLauncher = {
    method: METHOD,
    Launcher: Launcher,
    Card: Card,
    CardText: CardText,
    Feature: Feature,
    Line: Line,
    field: field,
    declaredFields: declaredFields,
    cardNames: cardNames,
    cardOf: cardOf,
    cardChildOrder: cardChildOrder,
    cardStyle: cardStyle,
    cardHover: cardHover,
    buttonStyle: buttonStyle,
    buttonHover: buttonHover,
    cardShadow: cardShadow,
    featureTexts: featureTexts,
    backgroundWash: backgroundWash,
    alignmentWord: alignmentWord,
    screenOrder: screenOrder,
    pressCalls: pressCalls,
    hoverPrefix: HOVER_PROPERTY,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderLauncher: renderLauncher,
    forget: forget
  };
})(window);
