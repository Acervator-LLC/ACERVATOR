// The instance consent modal, as the Python surface serves it. Named for the
// Qt dialog it stands beside; the bridge method it calls keeps its own name.
(function (global) {
  "use strict";

  var METHOD = "instance_consent.state";

  var WIDGET = "widget";
  var LAYOUT = "layout";
  var FACTS_LAYOUT = "facts_layout";
  var BUTTON_ROW = "button_row";
  var HEADLINE_LABEL = "headline_label";
  var DETAIL_LABEL = "detail_label";
  var FACT_LABEL = "fact_label";
  var CONSEQUENCE_LABEL = "consequence_label";
  var FACTS_FRAME = "facts_frame";
  var BUTTONS = "buttons";
  var ACTIONS = "actions";
  var ANSWERS = "answers";
  var BUTTON_ANSWERS = "button_answers";
  var DEFAULT_ANSWER = "default_answer";
  var CLOSED_ANSWER = "closed_answer";
  var BUILD_FAILED_ANSWER = "build_failed_answer";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var FOCUS_ON = "focus_on";
  var HEADLINE_TEXT = "headline_text";
  var DETAIL_TEXT = "detail_text";
  var OWNER_TEXT = "owner_text";
  var THIS_MACHINE_TEXT = "this_machine_text";
  var CONSEQUENCE_TEXT = "consequence_text";
  var BUTTON_BOT_COUNT = "button_bot_count";
  var CONSENTED = "consented";
  var BUILT = "built";
  var RELEASED = "released";
  var CALLS = "calls";
  var SKIN = "skin";

  var DECLARED_FIELDS = [
    ACTIONS,
    ANSWERS,
    BUILD_FAILED_ANSWER,
    BUILT,
    BUTTONS,
    BUTTON_ANSWERS,
    BUTTON_BOT_COUNT,
    BUTTON_ROW,
    CALLS,
    CLOSED_ANSWER,
    CONSEQUENCE_LABEL,
    CONSEQUENCE_TEXT,
    CONSENTED,
    DEFAULT_ANSWER,
    DETAIL_LABEL,
    DETAIL_TEXT,
    FACTS_FRAME,
    FACTS_LAYOUT,
    FACT_LABEL,
    FOCUS_ON,
    HEADLINE_LABEL,
    HEADLINE_TEXT,
    LAYOUT,
    OWNER_TEXT,
    RELEASED,
    SKIN,
    THIS_MACHINE_TEXT,
    TIMERS,
    TIMER_DELAYS_MS,
    WIDGET
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var WINDOW_TITLE = "window_title";
  var MODAL = "modal";
  var MINIMUM_WIDTH_PX = "minimum_width_px";
  var STYLE_SHEET = "style_sheet";

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";

  var OBJECT_NAME = "object_name";
  var WORD_WRAP = "word_wrap";

  var TEXT = "text";
  var ENABLED = "enabled";
  var IS_DEFAULT = "is_default";
  var MINIMUM_HEIGHT_PX = "minimum_height_px";
  var TOOL_TIP = "tool_tip";

  var REFUSE = "refuse";
  var CONSENT = "consent";
  var OWNER = "owner";
  var THIS_MACHINE = "this_machine";

  var SURFACE = "surface";
  var TEXT_HIGH = "text_high";
  var FOCUS_RING = "focus_ring";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var UNSAFE_DEFAULT_FAULT = "unsafe-default";
  var NOT_CSS_FAULT = "not-css";

  var NO_BRIDGE = "the preload bridge is not present";

  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";
  var HASH = "#";
  var COLON = ":";
  var SEMICOLON = ";";
  var EMPTY = "";
  var CHANNEL_SPLIT = ",";
  var RGB_OPEN = "rgb(";
  var RGB_CLOSE = ")";

  var DIALOG_CLASS = "acervator-consent-dialog";
  var FACTS_CLASS = "acervator-consent-facts";
  var ROW_CLASS = "acervator-consent-row";
  var BUTTON_CLASS = "acervator-consent-button";

  var DIALOG_PART = "consent-dialog";
  var HEADLINE_PART = "headline";
  var DETAIL_PART = "detail";
  var FACTS_PART = "facts";
  var FACT_PART = "fact";
  var CONSEQUENCE_PART = "consequence";
  var ROW_PART = "button-row";
  var BUTTON_PART = "button";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var DEFAULT_ATTR = "data-default";
  var ANSWER_ATTR = "data-answer";
  var COUNT_ATTR = "data-bot-count";
  var ARIA_LABEL = "aria-label";
  var ARIA_MODAL = "aria-modal";
  var DIALOG_ROLE = "dialog";

  var DIV = "div";
  var BUTTON = "button";
  var SECTION = "section";

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var END = "flex-end";
  var WRAP_ON = "normal";
  var WRAP_OFF = "nowrap";
  var PX = "px";

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var request = {};
  var consentFaults = [];
  var loadFault = null;
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

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // label returns undefined for an empty tooltip, so the title attribute stays off.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function marginStyle(bag) {
    var style = {};
    var margins = listField(bag, MARGINS_PX);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = pixels(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(bag, direction) {
    var style = marginStyle(bag);
    style.display = FLEX;
    style.flexDirection = direction;
    if (owns(bag, SPACING_PX)) {
      style.gap = pixels(bag[SPACING_PX]);
    }
    return style;
  }

  // -- the skin, as three channels a browser paints ---------------------

  // colour writes one published channel triple as the rgb call CSS reads.
  function colour(model, name) {
    var channels = objectField(model, SKIN)[name];
    if (!Array.isArray(channels) || channels.length !== 3) {
      return undefined;
    }
    return RGB_OPEN + channels.join(CHANNEL_SPLIT) + RGB_CLOSE;
  }

  // -- reading one Qt style sheet, block by block -----------------------

  // Every `selector { body }` of one sheet, in the order it was written.
  function blocks(sheet) {
    var found = [];
    String(sheet === null || sheet === undefined ? EMPTY : sheet)
      .split(BLOCK_CLOSE)
      .forEach(function (chunk) {
        var parts = chunk.split(BLOCK_OPEN);
        var selector = String(parts.shift()).trim();
        if (parts.length && selector) {
          found.push({ selector: selector, body: parts.join(BLOCK_OPEN) });
        }
      });
    return found;
  }

  function sheetApi() {
    var api = global.acervatorHeader;
    var usable =
      api &&
      typeof api.styleOf === "function" &&
      typeof api.declarations === "function";
    return usable ? api : null;
  }

  function styleOf(body) {
    var api = sheetApi();
    return api === null ? {} : api.styleOf(body);
  }

  function declarations(body) {
    var api = sheetApi();
    return api === null ? [] : api.declarations(body);
  }

  // The block that names one object, and the class-wide block above it.
  // Both are found by the object's own name, so no Qt class is written here.
  function styleFor(sheet, objectName) {
    var written = blocks(sheet);
    var own = null;
    written.forEach(function (block) {
      if (block.selector.split(HASH)[1] === objectName) {
        own = block;
      }
    });
    if (own === null) {
      return {};
    }
    var base = own.selector.split(HASH)[0];
    var style = {};
    written.forEach(function (block) {
      if (block.selector === base) {
        style = styleOf(block.body);
      }
    });
    Object.keys(styleOf(own.body)).forEach(function (property) {
      style[property] = styleOf(own.body)[property];
    });
    return style;
  }

  // The one block whose selector names a state, such as the focus ring.
  function focusStyle(sheet) {
    var found = {};
    blocks(sheet).forEach(function (block) {
      if (block.selector.split(COLON).length > 1) {
        found = styleOf(block.body);
      }
    });
    return found;
  }

  // Every property of one block that styleOf paints nothing from.
  function unpaintable(body) {
    var found = [];
    declarations(body).forEach(function (one) {
      var alone = one.property + COLON + one.value + SEMICOLON;
      if (!Object.keys(styleOf(alone)).length) {
        found.push(one.property);
      }
    });
    return found;
  }

  function sheetOf(model) {
    return objectField(model, WIDGET)[STYLE_SHEET];
  }

  // -- what the surface published, held and checked ---------------------

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        consentFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        consentFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // The safe answer must be the one a closed window and a broken build give.
  function checkFailsClosed(model) {
    var answers = objectField(model, BUTTON_ANSWERS);
    [DEFAULT_ANSWER, CLOSED_ANSWER, BUILD_FAILED_ANSWER].forEach(function (field) {
      if (model[field] !== answers[REFUSE]) {
        consentFaults.push(fault(null, field, UNSAFE_DEFAULT_FAULT, model[field]));
      }
    });
  }

  function checkButtons(model) {
    var buttons = objectField(model, BUTTONS);
    [REFUSE, CONSENT].forEach(function (name) {
      var one = objectField(buttons, name);
      if (typeof one[TEXT] !== "string") {
        consentFaults.push(fault(name, TEXT, WRONG_TYPE_FAULT, kindOf(one[TEXT])));
      }
      if (typeof one[ENABLED] !== "boolean") {
        consentFaults.push(fault(name, ENABLED, WRONG_TYPE_FAULT, kindOf(one[ENABLED])));
      }
    });
  }

  function checkStyleSheet(model) {
    blocks(sheetOf(model)).forEach(function (block) {
      unpaintable(block.body).forEach(function (property) {
        consentFaults.push(fault(block.selector, STYLE_SHEET, NOT_CSS_FAULT, property));
      });
    });
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        buttons: 2,
        blocks: blocks(sheetOf(model)).length
      },
      held: {
        fields: DECLARED_FIELDS.filter(function (field) {
          return owns(model, field);
        }).length,
        buttons: Object.keys(objectField(model, BUTTONS)).length,
        skin: Object.keys(objectField(model, SKIN)).length
      },
      answer: model[CONSENTED],
      faults: consentFaults.slice()
    };
  }

  function setInstanceConsent(model) {
    if (!isPlainObject(model)) {
      held = null;
      consentFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, answer: null, faults: consentFaults.slice() };
    }
    held = { model: model };
    consentFaults = [];
    checkFields(model);
    checkFailsClosed(model);
    checkButtons(model);
    checkStyleSheet(model);
    return report();
  }

  // The decision fields a later press re-sends, so the answer keeps its facts.
  function askFor(params) {
    request = isPlainObject(params) ? copyOf(params) : {};
    return request;
  }

  function bridgeCall(params) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setInstanceConsent(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function loadInstanceConsent(params) {
    return bridgeCall(askFor(params));
  }

  // press re-sends the held decision with the button the operator hit.
  // Nothing here decides the answer; the surface does, and this reads it back.
  function press(name) {
    var asked = copyOf(request);
    asked.button = name;
    return bridgeCall(asked);
  }

  // A closed window is not a button, and the surface answers it as a refusal.
  function closeWindow() {
    var asked = copyOf(request);
    asked.closed = true;
    return bridgeCall(asked);
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

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Line(props) {
    var model = props.model;
    var spec = objectField(model, props.spec);
    var style = styleFor(sheetOf(model), spec[OBJECT_NAME]);
    style.whiteSpace = spec[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    var lineProps = { style: style };
    lineProps[PART_ATTR] = props.part;
    lineProps[NAME_ATTR] = text(spec[OBJECT_NAME]);
    return element(DIV, lineProps, text(props.text));
  }

  function Fact(props) {
    var model = props.model;
    var spec = objectField(model, FACT_LABEL);
    var style = styleFor(sheetOf(model), spec[OBJECT_NAME]);
    style.whiteSpace = spec[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    var factProps = { style: style };
    factProps[PART_ATTR] = FACT_PART;
    factProps[NAME_ATTR] = props.name;
    return element(DIV, factProps, text(props.text));
  }

  function Facts(props) {
    var model = props.model;
    var frame = objectField(model, FACTS_FRAME);
    var style = styleFor(sheetOf(model), frame[OBJECT_NAME]);
    Object.keys(boxStyle(objectField(model, FACTS_LAYOUT), COLUMN)).forEach(
      function (property) {
        style[property] = boxStyle(objectField(model, FACTS_LAYOUT), COLUMN)[property];
      }
    );
    var factsProps = { className: FACTS_CLASS, style: style };
    factsProps[PART_ATTR] = FACTS_PART;
    factsProps[NAME_ATTR] = text(frame[OBJECT_NAME]);
    return element(
      SECTION,
      factsProps,
      element(Fact, { model: model, name: OWNER, text: model[OWNER_TEXT], key: OWNER }),
      element(Fact, {
        model: model,
        name: THIS_MACHINE,
        text: model[THIS_MACHINE_TEXT],
        key: THIS_MACHINE
      })
    );
  }

  function Answer(props) {
    var model = props.model;
    var one = objectField(objectField(model, BUTTONS), props.name);
    var style = styleFor(sheetOf(model), props.name);
    style.minHeight = pixels(one[MINIMUM_HEIGHT_PX]);
    if (props.name === model[FOCUS_ON]) {
      Object.keys(focusStyle(sheetOf(model))).forEach(function (property) {
        style[property] = focusStyle(sheetOf(model))[property];
      });
    }
    var buttonProps = {
      className: BUTTON_CLASS,
      type: BUTTON,
      style: style,
      disabled: !one[ENABLED],
      title: label(one[TOOL_TIP]),
      autoFocus: props.name === model[FOCUS_ON],
      onClick: function () {
        press(props.name);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[NAME_ATTR] = props.name;
    buttonProps[DEFAULT_ATTR] = text(one[IS_DEFAULT]);
    buttonProps[ANSWER_ATTR] = text(objectField(model, BUTTON_ANSWERS)[props.name]);
    return element(BUTTON, buttonProps, text(one[TEXT]));
  }

  function ButtonRow(props) {
    var model = props.model;
    var style = boxStyle(objectField(model, BUTTON_ROW), ROW);
    style.justifyContent = END;
    var rowProps = { className: ROW_CLASS, style: style };
    rowProps[PART_ATTR] = ROW_PART;
    return element(
      DIV,
      rowProps,
      element(Answer, { model: model, name: REFUSE, key: REFUSE }),
      element(Answer, { model: model, name: CONSENT, key: CONSENT })
    );
  }

  function ConsentDialog(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var box = objectField(model, WIDGET);
    var style = boxStyle(objectField(model, LAYOUT), COLUMN);
    style.minWidth = pixels(box[MINIMUM_WIDTH_PX]);
    style.background = colour(model, SURFACE);
    style.color = colour(model, TEXT_HIGH);
    style.outlineColor = colour(model, FOCUS_RING);
    var dialogProps = { className: DIALOG_CLASS, role: DIALOG_ROLE, style: style };
    dialogProps[PART_ATTR] = DIALOG_PART;
    dialogProps[ARIA_LABEL] = text(box[ACCESSIBLE_NAME]);
    dialogProps[ARIA_MODAL] = text(box[MODAL]);
    dialogProps[COUNT_ATTR] = text(model[BUTTON_BOT_COUNT]);
    dialogProps[ANSWER_ATTR] = text(model[CONSENTED]);
    dialogProps.title = label(box[WINDOW_TITLE]);
    return element(
      DIV,
      dialogProps,
      element(Line, {
        model: model,
        spec: HEADLINE_LABEL,
        part: HEADLINE_PART,
        text: model[HEADLINE_TEXT],
        key: HEADLINE_PART
      }),
      element(Line, {
        model: model,
        spec: DETAIL_LABEL,
        part: DETAIL_PART,
        text: model[DETAIL_TEXT],
        key: DETAIL_PART
      }),
      element(Facts, { model: model, key: FACTS_PART }),
      element(Line, {
        model: model,
        spec: CONSEQUENCE_LABEL,
        part: CONSEQUENCE_PART,
        text: model[CONSEQUENCE_TEXT],
        key: CONSEQUENCE_PART
      }),
      element(ButtonRow, { model: model, key: ROW_PART })
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

  function renderDialog(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(ConsentDialog, { model: payload }));
  }

  function answer() {
    return field(CONSENTED);
  }

  function faults() {
    return consentFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function forget() {
    held = null;
    request = {};
    consentFaults = [];
    loadFault = null;
  }

  global.acervatorSetInstanceConsent = setInstanceConsent;
  global.acervatorLoadInstanceConsent = loadInstanceConsent;
  global.acervatorInstanceConsent = {
    method: METHOD,
    ConsentDialog: ConsentDialog,
    Line: Line,
    Facts: Facts,
    Fact: Fact,
    ButtonRow: ButtonRow,
    Answer: Answer,
    widget: function () {
      return bag(WIDGET);
    },
    layout: function () {
      return bag(LAYOUT);
    },
    factsLayout: function () {
      return bag(FACTS_LAYOUT);
    },
    buttonRow: function () {
      return bag(BUTTON_ROW);
    },
    buttons: function () {
      return bag(BUTTONS);
    },
    skin: function () {
      return bag(SKIN);
    },
    actions: function () {
      return bag(ACTIONS);
    },
    answers: function () {
      return list(ANSWERS);
    },
    buttonAnswers: function () {
      return bag(BUTTON_ANSWERS);
    },
    calls: function () {
      return list(CALLS);
    },
    timerDelaysMs: function () {
      return list(TIMER_DELAYS_MS);
    },
    focusOn: function () {
      return field(FOCUS_ON);
    },
    botCount: function () {
      return field(BUTTON_BOT_COUNT);
    },
    built: function () {
      return field(BUILT);
    },
    released: function () {
      return field(RELEASED);
    },
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    heldRequest: function () {
      return copyOf(request);
    },
    blocks: blocks,
    styleFor: styleFor,
    focusStyle: focusStyle,
    unpaintable: unpaintable,
    colour: colour,
    press: press,
    closeWindow: closeWindow,
    answer: answer,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderDialog: renderDialog,
    forget: forget
  };
})(window);
