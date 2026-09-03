// Draws the Start All progress dialog from the `start_all_progress.state`
// payload: a headline, a scrollable list of bot lines, and Cancel/Close.
(function (global) {
  "use strict";

  var METHOD = "start_all_progress.state";

  var WIDGET = "widget";
  var LAYOUT = "layout";
  var BUTTON_ROW = "button_row";
  var HEADLINE = "headline";
  var SUBLINE = "subline";
  var BUTTONS = "buttons";
  var ACTIONS = "actions";
  var TOPIC = "topic";
  var PHASES = "phases";
  var EVENT_FIELDS = "event_fields";
  var HEADLINE_TEXT = "headline_text";
  var ITEMS = "items";
  var ITEM_COUNT = "item_count";
  var CANCEL_ENABLED = "cancel_enabled";
  var CLOSE_ENABLED = "close_enabled";
  var CALLS = "calls";
  var DIALOG_SURFACE = "dialog_surface";
  var TEXT_COLOR = "text_color";
  var LIST_SURFACE = "list_surface";
  var LIST_BORDER = "list_border";
  var BUTTON_SURFACE = "button_surface";
  var BUTTON_BORDER = "button_border";
  var BUTTON_HOVER = "button_hover";
  var DISABLED_TEXT = "disabled_text";
  var SUBLINE_COLOR = "subline_color";

  // Every top-level name the start_all_progress.state payload carries.
  var DECLARED_FIELDS = [
    WIDGET,
    LAYOUT,
    BUTTON_ROW,
    HEADLINE,
    SUBLINE,
    BUTTONS,
    ACTIONS,
    TOPIC,
    PHASES,
    EVENT_FIELDS,
    HEADLINE_TEXT,
    ITEMS,
    ITEM_COUNT,
    CANCEL_ENABLED,
    CLOSE_ENABLED,
    CALLS,
    DIALOG_SURFACE,
    TEXT_COLOR,
    LIST_SURFACE,
    LIST_BORDER,
    BUTTON_SURFACE,
    BUTTON_BORDER,
    BUTTON_HOVER,
    DISABLED_TEXT,
    SUBLINE_COLOR
  ];

  var DECLARED_BAGS = [WIDGET, LAYOUT, BUTTON_ROW, HEADLINE, SUBLINE, BUTTONS, ACTIONS];

  var COLOUR_FIELDS = [
    DIALOG_SURFACE,
    TEXT_COLOR,
    LIST_SURFACE,
    LIST_BORDER,
    BUTTON_SURFACE,
    BUTTON_BORDER,
    BUTTON_HOVER,
    DISABLED_TEXT,
    SUBLINE_COLOR
  ];

  var DECLARED_LISTS = [PHASES, EVENT_FIELDS, ITEMS, CALLS].concat(COLOUR_FIELDS);

  var ACCESSIBLE_NAME = "accessible_name";
  var MODAL = "modal";
  var MINIMUM_WIDTH_PX = "minimum_width_px";
  var SIZE_PX = "size_px";

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var ORDER = "order";
  var CHILD_STRETCH = "child_stretch";
  var LEADING_STRETCH = "leading_stretch";

  var POINT_SIZE = "point_size";
  var BOLD = "bold";

  var TEXT_KEY = "text";
  var WORD_WRAP = "word_wrap";
  var ENABLED_KEY = "enabled";

  var CANCEL_NAME = "cancel";
  var CLOSE_NAME = "close";
  var STRETCH_CHILD = "stretch";
  var LIST_CHILD = "list";
  var LAYOUT_CHILDREN = [HEADLINE, SUBLINE, LIST_CHILD, BUTTON_ROW];
  var BUTTON_ROW_CHILDREN = [STRETCH_CHILD, CANCEL_NAME, CLOSE_NAME];

  var CANCEL_CLICKED = "cancel.clicked";
  var CLOSE_CLICKED = "close.clicked";
  var CANCEL_PARAM = "cancel";
  var CLOSE_PARAM = "close";
  var CLOSE_AFTER_CALL = "closeAfter";

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var CHANNEL_FAULT = "channel-mismatch";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var DISAGREES_FAULT = "disagrees";

  var NO_BRIDGE = "the preload bridge is not present";
  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var LEFT = ZERO;
  var TOP = LEFT + STEP;
  var RIGHT = TOP + STEP;
  var BOTTOM = RIGHT + STEP;
  var MARGIN_COUNT = BOTTOM + STEP;
  var WIDTH_INDEX = ZERO;
  var HEIGHT_INDEX = STEP;
  var CALL_NAME_INDEX = ZERO;
  var CALL_VALUE_INDEX = STEP;

  var CHANNEL_NAMES = ["r", "g", "b"];
  var CHANNELS = CHANNEL_NAMES.length;
  var RGB_OPEN = "rgb(";
  var LIST_SPLIT = ", ";
  var CLOSE_PAREN = ")";
  var PX = "px";
  var PT = "pt";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var AUTO = "auto";
  var NORMAL = "normal";
  var NOWRAP = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var ANYWHERE = "anywhere";
  var CENTER = "center";
  var SCROLL = "auto";
  var SOLID_BORDER = "1px solid ";
  var BOLD_WEIGHT = "bold";

  var DIALOG_PART = "dialog";
  var HEADLINE_PART = "headline";
  var SUBLINE_PART = "subline";
  var LIST_PART = LIST_CHILD;
  var LIST_ROW_PART = "list-row";
  var BUTTON_ROW_PART = "button-row";
  var SPACER_PART = "button-spacer";
  var BUTTON_PART = "button";

  var PART_ATTR = "data-part";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var NAME_ATTR = "data-name";
  var ACTION_ATTR = "data-action";
  var TOPIC_ATTR = "data-topic";
  var MODAL_ATTR = "data-modal";
  var ARIA_LABEL = "aria-label";
  var ARIA_DISABLED = "aria-disabled";

  var held = null;
  var dialogFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
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
    Object.keys(bag || {}).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? "null" : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    dialogFaults.push(fault(where, field, kind, detail));
  }

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    var found = text(value);
    return found && found.length ? found : undefined;
  }

  function px(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function pt(value) {
    return value === null || value === undefined ? undefined : String(value) + PT;
  }

  // The published triple painted with no alpha, since this dialog has none.
  function rgbOf(channels) {
    if (!Array.isArray(channels) || channels.length !== CHANNELS) {
      return undefined;
    }
    return RGB_OPEN + channels.join(LIST_SPLIT) + CLOSE_PAREN;
  }

  // Qt writes a margin left-first; CSS padding writes it top-first.
  function marginOf(box) {
    var written = listField(box, MARGINS_PX);
    if (written.length !== MARGIN_COUNT) {
      return undefined;
    }
    return [px(written[TOP]), px(written[RIGHT]), px(written[BOTTOM]), px(written[LEFT])].join(
      " "
    );
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  function heldModel() {
    return held === null ? {} : held.model;
  }

  function actionNamed(model, name) {
    return objectField(model, ACTIONS)[name];
  }

  // Fires the bridge call and records it; the caller re-asks for the new
  // state on its own schedule, matching every other screen in this tree.
  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!hasBridge()) {
      return null;
    }
    return global.acervator.call(METHOD, copyOf(params));
  }

  function cancel() {
    var params = {};
    params[CANCEL_PARAM] = true;
    return dispatch(actionNamed(heldModel(), CANCEL_CLICKED), params);
  }

  function closeDialog() {
    var params = {};
    params[CLOSE_PARAM] = true;
    return dispatch(actionNamed(heldModel(), CLOSE_CLICKED), params);
  }

  // The delay of the newest `closeAfter` call, or undefined if none was made.
  function closeAfterDelay(model) {
    var found;
    listField(model, CALLS).forEach(function (call) {
      if (
        Array.isArray(call) &&
        call[CALL_NAME_INDEX] === CLOSE_AFTER_CALL &&
        typeof call[CALL_VALUE_INDEX] === "number"
      ) {
        found = call[CALL_VALUE_INDEX];
      }
    });
    return found;
  }

  function hooks() {
    return global.React;
  }

  // Mirrors the dialog's own QTimer.singleShot: a delay the surface
  // measured and published, never one this module invents.
  function useCloseAfterTimer(model) {
    var delay = closeAfterDelay(model);
    hooks().useEffect(
      function () {
        if (!hasBridge() || typeof delay !== "number") {
          return undefined;
        }
        var handle = global.setTimeout(closeDialog, delay);
        return function () {
          global.clearTimeout(handle);
        };
      },
      [delay]
    );
  }

  function Headline(props) {
    var model = props.model;
    var bag = objectField(model, HEADLINE);
    var style = {
      margin: ZERO,
      fontWeight: bag[BOLD] ? BOLD_WEIGHT : NORMAL,
      fontSize: pt(bag[POINT_SIZE]),
      color: rgbOf(model[TEXT_COLOR])
    };
    var p = { style: style };
    p[PART_ATTR] = HEADLINE_PART;
    return element(DIV_TAG, p, text(model[HEADLINE_TEXT]));
  }

  function Subline(props) {
    var model = props.model;
    var bag = objectField(model, SUBLINE);
    var style = {
      margin: ZERO,
      whiteSpace: bag[WORD_WRAP] === false ? NOWRAP : NORMAL,
      color: rgbOf(model[SUBLINE_COLOR])
    };
    var p = { style: style };
    p[PART_ATTR] = SUBLINE_PART;
    return element(DIV_TAG, p, text(bag[TEXT_KEY]));
  }

  function ListRow(props) {
    var style = { whiteSpace: PRE_WRAP, overflowWrap: ANYWHERE };
    var p = { style: style };
    p[PART_ATTR] = LIST_ROW_PART;
    p[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, p, text(props.words));
  }

  // Items are an explicit ordered list, never a bag keyed by bot id, so no
  // number-like key can ever be re-sorted by the browser.
  function ListPane(props) {
    var model = props.model;
    var items = listField(model, ITEMS);
    var style = {
      flex: AUTO,
      minHeight: ZERO,
      overflowY: SCROLL,
      background: rgbOf(model[LIST_SURFACE]),
      color: rgbOf(model[TEXT_COLOR]),
      border: SOLID_BORDER + rgbOf(model[LIST_BORDER])
    };
    var p = { style: style };
    p[PART_ATTR] = LIST_PART;
    p[COUNT_ATTR] = text(items.length);
    return element(
      DIV_TAG,
      p,
      items.map(function (words, at) {
        return element(ListRow, { key: String(at), words: words, at: at });
      })
    );
  }

  function handlerFor(name) {
    if (name === CANCEL_NAME) {
      return cancel;
    }
    if (name === CLOSE_NAME) {
      return closeDialog;
    }
    return undefined;
  }

  function clickedActionFor(name) {
    if (name === CANCEL_NAME) {
      return CANCEL_CLICKED;
    }
    if (name === CLOSE_NAME) {
      return CLOSE_CLICKED;
    }
    return undefined;
  }

  // `buttons.<name>.enabled` is the dialog's starting value and never
  // changes; the live enabled state is the top-level field by this name.
  function enabledField(name) {
    return name === CANCEL_NAME ? CANCEL_ENABLED : CLOSE_ENABLED;
  }

  function DialogButton(props) {
    var model = props.model;
    var one = objectField(objectField(model, BUTTONS), props.name);
    var enabled = model[enabledField(props.name)] !== false;
    var style = {
      background: rgbOf(model[BUTTON_SURFACE]),
      border: SOLID_BORDER + rgbOf(model[BUTTON_BORDER]),
      color: enabled ? rgbOf(model[TEXT_COLOR]) : rgbOf(model[DISABLED_TEXT])
    };
    var p = {
      type: BUTTON_TYPE,
      disabled: !enabled,
      style: style,
      onClick: handlerFor(props.name)
    };
    p[PART_ATTR] = BUTTON_PART;
    p[NAME_ATTR] = props.name;
    p[ACTION_ATTR] = text(actionNamed(model, clickedActionFor(props.name)));
    p[ARIA_DISABLED] = text(!enabled);
    return element(BUTTON_TAG, p, text(one[TEXT_KEY]));
  }

  function ButtonSpacer(props) {
    var stretch = props.stretch;
    var style = { flex: typeof stretch === "number" ? stretch : undefined };
    var p = { style: style };
    p[PART_ATTR] = SPACER_PART;
    return element(SPAN_TAG, p, null);
  }

  function ButtonRow(props) {
    var model = props.model;
    var row = objectField(model, BUTTON_ROW);
    var style = { display: FLEX, flexDirection: ROW, alignItems: CENTER };
    var p = { style: style };
    p[PART_ATTR] = BUTTON_ROW_PART;
    return element(
      DIV_TAG,
      p,
      listField(row, ORDER).map(function (name, at) {
        if (name === STRETCH_CHILD) {
          return element(ButtonSpacer, { key: ROW_AT + String(at), stretch: row[LEADING_STRETCH] });
        }
        return element(DialogButton, { key: name, model: model, name: name });
      })
    );
  }

  var CHILD_PARTS = {};
  CHILD_PARTS[HEADLINE] = Headline;
  CHILD_PARTS[SUBLINE] = Subline;
  CHILD_PARTS[LIST_CHILD] = ListPane;
  CHILD_PARTS[BUTTON_ROW] = ButtonRow;

  function childFor(name, at, model) {
    var made = CHILD_PARTS[name];
    if (made === undefined) {
      return null;
    }
    var widget = objectField(model, LAYOUT);
    var stretch = listField(widget, CHILD_STRETCH)[at];
    return element(made, { key: name, model: model, stretch: stretch });
  }

  // Dialog draws nothing for a payload that is not an object.
  function Dialog(props) {
    var model = props.model;
    useCloseAfterTimer(isPlainObject(model) ? model : {});
    if (!isPlainObject(model)) {
      return null;
    }
    var widget = objectField(model, WIDGET);
    var box = objectField(model, LAYOUT);
    var sizes = listField(widget, SIZE_PX);
    var style = {
      display: FLEX,
      flexDirection: COLUMN,
      gap: px(box[SPACING_PX]),
      padding: marginOf(box),
      minWidth: px(widget[MINIMUM_WIDTH_PX]),
      width: px(sizes[WIDTH_INDEX]),
      height: px(sizes[HEIGHT_INDEX]),
      background: rgbOf(model[DIALOG_SURFACE]),
      color: rgbOf(model[TEXT_COLOR])
    };
    var p = { style: style };
    p[PART_ATTR] = DIALOG_PART;
    p[ARIA_LABEL] = label(widget[ACCESSIBLE_NAME]);
    p[MODAL_ATTR] = text(widget[MODAL]);
    p[TOPIC_ATTR] = text(model[TOPIC]);
    return element(
      DIV_TAG,
      p,
      listField(box, ORDER).map(function (name, at) {
        return childFor(name, at, model);
      })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        note(null, name, MISSING_FAULT, null);
      }
    });
  }

  function checkBags(model) {
    DECLARED_BAGS.forEach(function (name) {
      if (owns(model, name) && !isPlainObject(model[name])) {
        note(null, name, NOT_A_BAG_FAULT, kindOf(model[name]));
      }
    });
  }

  function checkLists(model) {
    DECLARED_LISTS.forEach(function (name) {
      if (owns(model, name) && !Array.isArray(model[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(model[name]));
      }
    });
  }

  function checkColours(model) {
    COLOUR_FIELDS.forEach(function (name) {
      var value = model[name];
      if (Array.isArray(value) && value.length !== CHANNELS) {
        note(null, name, CHANNEL_FAULT, value.length);
      }
    });
  }

  function checkButtons(model) {
    var bag = objectField(model, BUTTONS);
    [CANCEL_NAME, CLOSE_NAME].forEach(function (name) {
      if (!isPlainObject(bag[name])) {
        note(name, BUTTONS, NOT_A_BAG_FAULT, kindOf(bag[name]));
        return;
      }
      [TEXT_KEY, ENABLED_KEY].forEach(function (key) {
        if (!owns(bag[name], key)) {
          note(name, BUTTONS, MISSING_FAULT, key);
        }
      });
    });
  }

  function checkLayout(model) {
    var box = objectField(model, LAYOUT);
    var order = listField(box, ORDER);
    var stretch = listField(box, CHILD_STRETCH);
    if (order.length !== stretch.length) {
      note(null, LAYOUT, SHORT_LIST_FAULT, CHILD_STRETCH + PATH_SPLIT + String(stretch.length));
    }
    order.forEach(function (name, at) {
      if (LAYOUT_CHILDREN.indexOf(name) < ZERO) {
        note(ROW_AT + String(at), ORDER, UNKNOWN_NAME_FAULT, name);
      }
    });
    var row = objectField(model, BUTTON_ROW);
    listField(row, ORDER).forEach(function (name, at) {
      if (BUTTON_ROW_CHILDREN.indexOf(name) < ZERO) {
        note(ROW_AT + String(at), BUTTON_ROW, UNKNOWN_NAME_FAULT, name);
      }
    });
  }

  function checkItemCount(model) {
    var items = listField(model, ITEMS);
    if (owns(model, ITEM_COUNT) && model[ITEM_COUNT] !== items.length) {
      note(null, ITEM_COUNT, DISAGREES_FAULT, model[ITEM_COUNT]);
    }
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(model, name);
    }).length;
  }

  function report(model) {
    return {
      declared: { fields: DECLARED_FIELDS.length },
      held: { fields: heldFieldCount(model), items: listField(model, ITEMS).length },
      faults: dialogFaults.slice()
    };
  }

  function setDialog(model) {
    if (!isPlainObject(model)) {
      held = null;
      dialogFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: dialogFaults.slice() };
    }
    held = { model: model };
    dialogFaults = [];
    checkFields(model);
    checkBags(model);
    checkLists(model);
    checkColours(model);
    checkButtons(model);
    checkLayout(model);
    checkItemCount(model);
    return report(model);
  }

  // One round trip per page; `forget()` is what lets a later ask refetch.
  function loadDialog(params) {
    if (asked !== null) {
      return asked;
    }
    if (!hasBridge()) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setDialog(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function payload() {
    return held === null ? {} : copyOf(held.model);
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

  function items() {
    return list(ITEMS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
  }

  function buttons() {
    return bag(BUTTONS);
  }

  function button(name) {
    var found = buttons();
    return owns(found, name) ? found[name] : undefined;
  }

  function closeDelay() {
    return closeAfterDelay(heldModel());
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function sent() {
    return dispatched.slice();
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
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
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return dialogFaults.slice();
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

  // flushSync makes the document current before draw returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  // Qt scrolls the list to the newest line after every progress event.
  function scrollListToEnd(target) {
    var pane = target.querySelector('[' + PART_ATTR + '="' + LIST_PART + '"]');
    if (pane && typeof pane.scrollHeight === "number") {
      pane.scrollTop = pane.scrollHeight;
    }
  }

  function renderDialog(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = payload();
    }
    draw(target, element(Dialog, { model: drawn }));
    scrollListToEnd(target);
    return target;
  }

  function forget() {
    held = null;
    dialogFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetStartAllProgress = setDialog;
  global.acervatorLoadStartAllProgress = loadDialog;
  global.acervatorStartAllProgress = {
    method: METHOD,
    Dialog: Dialog,
    Headline: Headline,
    Subline: Subline,
    ListPane: ListPane,
    ListRow: ListRow,
    ButtonRow: ButtonRow,
    DialogButton: DialogButton,
    payload: payload,
    field: field,
    bag: bag,
    list: list,
    items: items,
    actions: actions,
    action: action,
    buttons: buttons,
    button: button,
    declaredFields: declaredFields,
    cancel: cancel,
    closeDialog: closeDialog,
    closeDelay: closeDelay,
    sent: sent,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderDialog: renderDialog,
    forget: forget
  };
})(window);
