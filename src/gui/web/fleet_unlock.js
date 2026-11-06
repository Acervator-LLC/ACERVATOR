// The unlock screen, as the Python surface serves it. Named for the Qt dialog
// it stands beside; the bridge method it calls keeps its own name.
(function (global) {
  "use strict";

  var METHOD = "fleet_unlock.state";

  var WIDGET = "widget";
  var LAYOUT = "layout";
  var BUTTON_ROW = "button_row";
  var SKIN = "skin";
  var HEADLINE_LABEL = "headline_label";
  var DETAIL_LABEL = "detail_label";
  var FEEDBACK_LABEL = "feedback_label";
  var PHRASE_ROW = "phrase_row";
  var HEADLINE_TEXT = "headline_text";
  var DETAIL_TEXT = "detail_text";
  var FEEDBACK_TEXT = "feedback_text";
  var BUTTONS = "buttons";
  var BUTTON_ANSWERS = "button_answers";
  var ANSWERS = "answers";
  var ACTIONS = "actions";
  var DEFAULT_ANSWER = "default_answer";
  var CLOSED_ANSWER = "closed_answer";
  var BUILD_FAILED_ANSWER = "build_failed_answer";
  var FOCUS_ON = "focus_on";
  var OUTCOME = "outcome";
  var UNLOCKED = "unlocked";

  var DECLARED_FIELDS = [
    ACTIONS,
    ANSWERS,
    BUILD_FAILED_ANSWER,
    BUTTONS,
    BUTTON_ANSWERS,
    BUTTON_ROW,
    CLOSED_ANSWER,
    DEFAULT_ANSWER,
    DETAIL_LABEL,
    DETAIL_TEXT,
    FEEDBACK_LABEL,
    FEEDBACK_TEXT,
    FOCUS_ON,
    HEADLINE_LABEL,
    HEADLINE_TEXT,
    LAYOUT,
    OUTCOME,
    PHRASE_ROW,
    SKIN,
    UNLOCKED,
    WIDGET
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var WINDOW_TITLE = "window_title";
  var MODAL = "modal";
  var MINIMUM_WIDTH_PX = "minimum_width_px";

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";

  var OBJECT_NAME = "object_name";
  var WORD_WRAP = "word_wrap";
  var LABEL = "label";
  var PLACEHOLDER = "placeholder";
  var ECHO_HIDDEN = "echo_hidden";
  var DESCRIPTION = "description";

  var TEXT = "text";
  var ENABLED = "enabled";
  var IS_DEFAULT = "is_default";
  var MINIMUM_HEIGHT_PX = "minimum_height_px";

  var DISMISS = "dismiss";
  var UNLOCK = "unlock";

  var SURFACE = "surface";
  var TEXT_HIGH = "text_high";
  var TEXT_MED = "text_med";
  var HEADLINE_COLOUR = "headline";
  var FEEDBACK_COLOUR = "feedback";
  var INPUT_COLOUR = "input";
  var OUTLINE_COLOUR = "outline";
  var FOCUS_RING = "focus_ring";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var UNSAFE_DEFAULT_FAULT = "unsafe-default";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var CHANNEL_SPLIT = ",";
  var RGB_OPEN = "rgb(";
  var RGB_CLOSE = ")";
  var PX = "px";

  var DIALOG_CLASS = "acervator-unlock-dialog";
  var ROW_CLASS = "acervator-unlock-row";
  var BUTTON_CLASS = "acervator-unlock-button";
  var FIELD_CLASS = "acervator-unlock-field";

  var DIALOG_PART = "unlock-dialog";
  var HEADLINE_PART = "headline";
  var DETAIL_PART = "detail";
  var FEEDBACK_PART = "feedback";
  var FIELD_PART = "phrase";
  var ROW_PART = "button-row";
  var BUTTON_PART = "button";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var DEFAULT_ATTR = "data-default";
  var ANSWER_ATTR = "data-answer";
  var OUTCOME_ATTR = "data-outcome";
  var ARIA_LABEL = "aria-label";
  var ARIA_MODAL = "aria-modal";
  var DIALOG_ROLE = "dialog";

  var DIV = "div";
  var BUTTON = "button";
  var INPUT = "input";
  var LABEL_TAG = "label";
  var SECTION = "section";

  var HIDDEN_TYPE = "password";
  var PLAIN_TYPE = "text";

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var END = "flex-end";
  var WRAP_ON = "normal";
  var WRAP_OFF = "nowrap";

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var request = {};
  var unlockFaults = [];
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

  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  // colour writes one published channel triple as the rgb call CSS reads.
  function colour(model, name) {
    var channels = objectField(model, SKIN)[name];
    if (!Array.isArray(channels) || channels.length !== 3) {
      return undefined;
    }
    return RGB_OPEN + channels.join(CHANNEL_SPLIT) + RGB_CLOSE;
  }

  function marginStyle(bag) {
    var style = {};
    var margins = Array.isArray(bag[MARGINS_PX]) ? bag[MARGINS_PX] : [];
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

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        unlockFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        unlockFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // The sealed answer must be the one a closed window and a broken build give.
  function checkFailsClosed(model) {
    var answers = objectField(model, BUTTON_ANSWERS);
    [DEFAULT_ANSWER, CLOSED_ANSWER, BUILD_FAILED_ANSWER].forEach(function (field) {
      if (model[field] !== answers[DISMISS]) {
        unlockFaults.push(fault(null, field, UNSAFE_DEFAULT_FAULT, model[field]));
      }
    });
  }

  function checkButtons(model) {
    var buttons = objectField(model, BUTTONS);
    [DISMISS, UNLOCK].forEach(function (name) {
      var one = objectField(buttons, name);
      if (typeof one[TEXT] !== "string") {
        unlockFaults.push(fault(name, TEXT, WRONG_TYPE_FAULT, kindOf(one[TEXT])));
      }
      if (typeof one[ENABLED] !== "boolean") {
        unlockFaults.push(
          fault(name, ENABLED, WRONG_TYPE_FAULT, kindOf(one[ENABLED]))
        );
      }
    });
  }

  // The row must hide what is typed in it, on every build.
  function checkEchoHidden(model) {
    var row = objectField(model, PHRASE_ROW);
    if (row[ECHO_HIDDEN] !== true) {
      unlockFaults.push(fault(FIELD_PART, ECHO_HIDDEN, UNSAFE_DEFAULT_FAULT, row[ECHO_HIDDEN]));
    }
  }

  function report() {
    var model = held.model;
    return {
      declared: { fields: DECLARED_FIELDS.length, buttons: 2 },
      held: {
        fields: DECLARED_FIELDS.filter(function (field) {
          return owns(model, field);
        }).length,
        buttons: Object.keys(objectField(model, BUTTONS)).length,
        skin: Object.keys(objectField(model, SKIN)).length
      },
      answer: model[UNLOCKED],
      outcome: model[OUTCOME],
      faults: unlockFaults.slice()
    };
  }

  function setFleetUnlock(model) {
    if (!isPlainObject(model)) {
      held = null;
      unlockFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return {
        declared: null,
        held: null,
        answer: null,
        outcome: null,
        faults: unlockFaults.slice()
      };
    }
    held = { model: model };
    unlockFaults = [];
    checkFields(model);
    checkFailsClosed(model);
    checkButtons(model);
    checkEchoHidden(model);
    return report();
  }

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
        setFleetUnlock(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function loadFleetUnlock(params) {
    return bridgeCall(askFor(params));
  }

  // typed re-sends the row so the surface decides whether the press is live.
  // Nothing here reads or keeps the password; the row's value is sent and dropped.
  function typed(value) {
    var asked = copyOf(request);
    asked.typed = value;
    return bridgeCall(asked);
  }

  function press(name) {
    var asked = copyOf(request);
    asked.button = name;
    return bridgeCall(asked);
  }

  // A closed window is not a button, and the surface answers it as still sealed.
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
    var style = { color: colour(model, props.colour) };
    style.whiteSpace = spec[WORD_WRAP] ? WRAP_ON : WRAP_OFF;
    var lineProps = { style: style };
    lineProps[PART_ATTR] = props.part;
    lineProps[NAME_ATTR] = text(spec[OBJECT_NAME]);
    return element(DIV, lineProps, text(props.text));
  }

  function PhraseRow(props) {
    var model = props.model;
    var spec = objectField(model, PHRASE_ROW);
    var style = {
      background: colour(model, INPUT_COLOUR),
      color: colour(model, TEXT_HIGH),
      borderColor: colour(model, OUTLINE_COLOUR),
      outlineColor: colour(model, FOCUS_RING)
    };
    var inputProps = {
      className: FIELD_CLASS,
      type: spec[ECHO_HIDDEN] ? HIDDEN_TYPE : PLAIN_TYPE,
      placeholder: label(spec[PLACEHOLDER]),
      title: label(spec[DESCRIPTION]),
      style: style,
      autoFocus: model[FOCUS_ON] === FIELD_PART,
      onChange: function (event) {
        typed(event.target.value);
      }
    };
    inputProps[PART_ATTR] = FIELD_PART;
    inputProps[NAME_ATTR] = text(spec[OBJECT_NAME]);
    inputProps[ARIA_LABEL] = text(spec[LABEL]);
    return element(
      LABEL_TAG,
      { style: { color: colour(model, TEXT_MED) } },
      text(spec[LABEL]),
      element(INPUT, inputProps)
    );
  }

  function Answer(props) {
    var model = props.model;
    var one = objectField(objectField(model, BUTTONS), props.name);
    var style = {
      color: colour(model, props.name),
      borderColor: colour(model, props.name),
      outlineColor: colour(model, FOCUS_RING),
      minHeight: pixels(one[MINIMUM_HEIGHT_PX])
    };
    var buttonProps = {
      className: BUTTON_CLASS,
      type: BUTTON,
      style: style,
      disabled: !one[ENABLED],
      title: label(one[DESCRIPTION]),
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
      element(Answer, { model: model, name: DISMISS, key: DISMISS }),
      element(Answer, { model: model, name: UNLOCK, key: UNLOCK })
    );
  }

  function UnlockDialog(props) {
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
    dialogProps[OUTCOME_ATTR] = text(model[OUTCOME]);
    dialogProps[ANSWER_ATTR] = text(model[UNLOCKED]);
    dialogProps.title = label(box[WINDOW_TITLE]);
    return element(
      SECTION,
      dialogProps,
      element(Line, {
        model: model,
        spec: HEADLINE_LABEL,
        colour: HEADLINE_COLOUR,
        part: HEADLINE_PART,
        text: model[HEADLINE_TEXT],
        key: HEADLINE_PART
      }),
      element(Line, {
        model: model,
        spec: DETAIL_LABEL,
        colour: TEXT_HIGH,
        part: DETAIL_PART,
        text: model[DETAIL_TEXT],
        key: DETAIL_PART
      }),
      element(PhraseRow, { model: model, key: FIELD_PART }),
      element(Line, {
        model: model,
        spec: FEEDBACK_LABEL,
        colour: FEEDBACK_COLOUR,
        part: FEEDBACK_PART,
        text: model[FEEDBACK_TEXT],
        key: FEEDBACK_PART
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
    return draw(target, element(UnlockDialog, { model: payload }));
  }

  function answer() {
    return field(UNLOCKED);
  }

  function outcome() {
    return field(OUTCOME);
  }

  function faults() {
    return unlockFaults.slice();
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
    unlockFaults = [];
    loadFault = null;
  }

  global.acervatorSetFleetUnlock = setFleetUnlock;
  global.acervatorLoadFleetUnlock = loadFleetUnlock;
  global.acervatorFleetUnlock = {
    method: METHOD,
    UnlockDialog: UnlockDialog,
    Line: Line,
    PhraseRow: PhraseRow,
    ButtonRow: ButtonRow,
    Answer: Answer,
    widget: function () {
      return bag(WIDGET);
    },
    layout: function () {
      return bag(LAYOUT);
    },
    buttonRow: function () {
      return bag(BUTTON_ROW);
    },
    buttons: function () {
      return bag(BUTTONS);
    },
    phraseRow: function () {
      return bag(PHRASE_ROW);
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
    focusOn: function () {
      return field(FOCUS_ON);
    },
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    heldRequest: function () {
      return copyOf(request);
    },
    colour: colour,
    typed: typed,
    press: press,
    closeWindow: closeWindow,
    answer: answer,
    outcome: outcome,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderDialog: renderDialog,
    forget: forget,
    EMPTY: EMPTY
  };
})(window);
