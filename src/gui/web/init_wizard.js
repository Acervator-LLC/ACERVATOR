// Draws the first-run setup wizard from the init_wizard.state payload:
// the display name page, the venue page and the credentials page.
//
// Every word, colour and measurement is a field of the payload. Each
// page draws its children in the order the payload names, so a widget
// added on one side alone is drawn in the wrong place rather than
// silently left out.
(function (global) {
  "use strict";

  var METHOD = "init_wizard.state";

  var API_KEY_ECHO = "api_key_echo";
  var API_KEY_TEXT = "api_key_text";
  var API_SECRET_MAX_HEIGHT_PX = "api_secret_max_height_px";
  var API_SECRET_STYLE = "api_secret_style";
  var API_SECRET_TEXT = "api_secret_text";
  var BUTTON_TAGS = "button_tags";
  var BUTTON_TEXTS = "button_texts";
  var BUTTONS = "buttons";
  var CHECK_TAGS = "check_tags";
  var CHECK_TEXTS = "check_texts";
  var COMBO_TAGS = "combo_tags";
  var ECHO_MODES = "echo_modes";
  var EXCHANGE_INDEX = "exchange_index";
  var EXCHANGE_ITEMS = "exchange_items";
  var FEEDBACK_STYLE = "feedback_style";
  var FEEDBACK_TEXT = "feedback_text";
  var FEEDBACK_WORD_WRAP = "feedback_word_wrap";
  var FRESH_START_CHECKED = "fresh_start_checked";
  var IS_UPGRADE = "is_upgrade";
  var LABEL_TAGS = "label_tags";
  var LABEL_TEXTS = "label_texts";
  var LINE_TAGS = "line_tags";
  var MINIMUM_SIZE_PX = "minimum_size_px";
  var MUTED_PROPERTY = "muted_property";
  var PAGE_ORDERS = "page_orders";
  var PAGE_SUBTITLES = "page_subtitles";
  var PAGE_TITLES = "page_titles";
  var PAGES = "pages";
  var PASSPHRASE_HINT_VISIBLE = "passphrase_hint_visible";
  var PASSPHRASE_HINT_WORD_WRAP = "passphrase_hint_word_wrap";
  var PASSPHRASE_ECHO = "passphrase_echo";
  var PASSPHRASE_LABEL_VISIBLE = "passphrase_label_visible";
  var PASSPHRASE_TEXT = "passphrase_text";
  var PASSPHRASE_VISIBLE = "passphrase_visible";
  var PLACEHOLDERS = "placeholders";
  var SHOW_KEY_CHECKED = "show_key_checked";
  var SKIP_CREDS_CHECKED = "skip_creds_checked";
  var STYLES = "styles";
  var TEXT_TAGS = "text_tags";
  var TOOL_TIPS = "tool_tips";
  var USERNAME_TEXT = "username_text";
  var WELCOME_SPACING_PX = "welcome_spacing_px";
  var WIDGET_NAMES = "widget_names";
  var WINDOW_TITLE = "window_title";

  // Every top-level field the wizard is drawn from. One that never
  // arrives is reported rather than drawn around.
  var DECLARED_FIELDS = [
    API_KEY_ECHO,
    API_KEY_TEXT,
    API_SECRET_MAX_HEIGHT_PX,
    API_SECRET_STYLE,
    API_SECRET_TEXT,
    BUTTON_TAGS,
    BUTTON_TEXTS,
    BUTTONS,
    CHECK_TAGS,
    CHECK_TEXTS,
    COMBO_TAGS,
    ECHO_MODES,
    EXCHANGE_INDEX,
    EXCHANGE_ITEMS,
    FEEDBACK_STYLE,
    FEEDBACK_TEXT,
    FEEDBACK_WORD_WRAP,
    FRESH_START_CHECKED,
    IS_UPGRADE,
    LABEL_TAGS,
    LABEL_TEXTS,
    LINE_TAGS,
    MINIMUM_SIZE_PX,
    MUTED_PROPERTY,
    PAGE_ORDERS,
    PAGE_SUBTITLES,
    PAGE_TITLES,
    PAGES,
    PASSPHRASE_HINT_VISIBLE,
    PASSPHRASE_HINT_WORD_WRAP,
    PASSPHRASE_ECHO,
    PASSPHRASE_LABEL_VISIBLE,
    PASSPHRASE_TEXT,
    PASSPHRASE_VISIBLE,
    PLACEHOLDERS,
    SHOW_KEY_CHECKED,
    SKIP_CREDS_CHECKED,
    STYLES,
    TEXT_TAGS,
    TOOL_TIPS,
    USERNAME_TEXT,
    WELCOME_SPACING_PX,
    WIDGET_NAMES,
    WINDOW_TITLE
  ];

  // The widget names the payload keys its wording by.
  var USERNAME = "username";
  var API_KEY = "api_key";
  var API_SECRET = "api_secret";
  var PASSPHRASE = "passphrase";
  var FRESH_START = "fresh_start";
  var SHOW_KEY = "show_key";
  var SKIP_CREDS = "skip_creds";
  var PASSPHRASE_LABEL = "passphrase_label";
  var PASSPHRASE_HINT = "passphrase_hint";
  var FEEDBACK = "feedback";
  var WELCOME_SPACING = "welcome_spacing";

  var STYLE_HIDDEN_FIELD = "hidden_field";

  var BUTTON_TEXT = "text";
  var BUTTON_TOOL_TIP = "tool_tip";
  var BUTTON_ENABLED = "enabled";
  var BUTTON_STYLE_SHEET = "style_sheet";

  // The echo mode the payload names when a secret field is readable.
  var ECHO_NORMAL_AT = 0;

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var UNKNOWN_WIDGET_FAULT = "unknown-widget";

  var NO_BRIDGE = "the preload bridge is not present";

  var TEXT_INPUT = "text";
  var PASSWORD_INPUT = "password";
  var CHECKBOX_INPUT = "checkbox";
  var BUTTON_KIND = "button";
  var WRAP_ON = "anywhere";
  var WRAP_OFF = "normal";
  var COLUMN = "column";
  var FLEX = "flex";
  var PX = "px";
  var EMPTY = "";

  var RULE_SPLIT = ";";
  var DECLARATION_SPLIT = ":";
  var WORD_SPLIT = "-";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var PAGE_ATTR = "data-page";
  var HIDDEN_ATTR = "hidden";
  var MUTED_ATTR = "data-muted";
  var UPGRADE_ATTR = "data-upgrade";
  var ARIA_LABEL = "aria-label";

  var PART_WIZARD = "wizard";
  var PART_PAGE = "page";
  var PART_TITLE = "page-title";
  var PART_SUBTITLE = "page-subtitle";
  var PART_LABEL = "label";
  var PART_LINE = "line";
  var PART_TEXT = "text";
  var PART_CHECK = "check";
  var PART_BUTTON = "button";
  var PART_COMBO = "combo";
  var PART_SPACING = "spacing";
  var PART_UNKNOWN = "unknown";

  var held = null;
  var wizardFaults = [];
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

  // Undefined leaves an attribute off the element rather than writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function pixels(value) {
    return isNumber(value) ? String(value) + PX : undefined;
  }

  function has(bag, name) {
    return isPlainObject(bag) && owns(bag, name);
  }

  // "font-size" as the "fontSize" a React style object takes.
  function cssName(name) {
    return name
      .split(WORD_SPLIT)
      .map(function (one, at) {
        return at === 0 ? one : one.charAt(0).toUpperCase() + one.slice(1);
      })
      .join(EMPTY);
  }

  // One style sheet the surface publishes as the declarations a browser
  // reads. A Qt sheet may wrap its declarations in a selector block; the
  // block's contents are what the element carries.
  function declarations(sheet) {
    if (typeof sheet !== "string" || sheet === EMPTY) {
      return null;
    }
    var opened = sheet.indexOf(BLOCK_OPEN);
    var body =
      opened < 0 ? sheet : sheet.slice(opened + 1, sheet.lastIndexOf(BLOCK_CLOSE));
    var found = {};
    body.split(RULE_SPLIT).forEach(function (one) {
      var at = one.indexOf(DECLARATION_SPLIT);
      if (at < 0) {
        return;
      }
      found[cssName(one.slice(0, at).trim())] = one.slice(at + 1).trim();
    });
    return found;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // -- the widgets one page holds --------------------------------------

  // A secret field is readable only while the show-credentials switch is
  // on, which the payload reports as the echo mode each field carries.
  function readable(model, name) {
    var modes = listField(model, ECHO_MODES);
    var carried = name === API_KEY ? model[API_KEY_ECHO] : model[PASSPHRASE_ECHO];
    return carried === modes[ECHO_NORMAL_AT];
  }

  var LINE_TEXTS = {};
  LINE_TEXTS[USERNAME] = USERNAME_TEXT;
  LINE_TEXTS[API_KEY] = API_KEY_TEXT;
  LINE_TEXTS[PASSPHRASE] = PASSPHRASE_TEXT;

  var CHECK_STATES = {};
  CHECK_STATES[FRESH_START] = FRESH_START_CHECKED;
  CHECK_STATES[SHOW_KEY] = SHOW_KEY_CHECKED;
  CHECK_STATES[SKIP_CREDS] = SKIP_CREDS_CHECKED;

  var HIDEABLE = {};
  HIDEABLE[PASSPHRASE_LABEL] = PASSPHRASE_LABEL_VISIBLE;
  HIDEABLE[PASSPHRASE] = PASSPHRASE_VISIBLE;
  HIDEABLE[PASSPHRASE_HINT] = PASSPHRASE_HINT_VISIBLE;

  function hiddenHere(model, name) {
    return owns(HIDEABLE, name) ? model[HIDEABLE[name]] === false : false;
  }

  function Label(props) {
    var model = props.model;
    var name = props.name;
    var wraps =
      name === PASSPHRASE_HINT
        ? model[PASSPHRASE_HINT_WORD_WRAP]
        : name === FEEDBACK
          ? model[FEEDBACK_WORD_WRAP]
          : false;
    var labelProps = { style: { overflowWrap: wraps ? WRAP_ON : WRAP_OFF } };
    var painted = name === FEEDBACK ? declarations(model[FEEDBACK_STYLE]) : null;
    if (painted !== null) {
      Object.keys(painted).forEach(function (key) {
        labelProps.style[key] = painted[key];
      });
    }
    labelProps[PART_ATTR] = PART_LABEL;
    labelProps[NAME_ATTR] = name;
    labelProps[HIDDEN_ATTR] = hiddenHere(model, name);
    if (name === PASSPHRASE_HINT) {
      labelProps[MUTED_ATTR] = text(listField(model, MUTED_PROPERTY)[1]);
    }
    var shown =
      name === FEEDBACK
        ? model[FEEDBACK_TEXT]
        : objectField(model, LABEL_TEXTS)[name];
    return element("div", labelProps, text(shown));
  }

  function Line(props) {
    var model = props.model;
    var name = props.name;
    var secret = name !== USERNAME;
    var lineProps = {
      type: secret && !readable(model, name) ? PASSWORD_INPUT : TEXT_INPUT,
      value: text(model[LINE_TEXTS[name]]),
      placeholder: text(objectField(model, PLACEHOLDERS)[name]),
      title: text(objectField(model, TOOL_TIPS)[name]),
      readOnly: true,
      onChange: function () {}
    };
    lineProps[PART_ATTR] = PART_LINE;
    lineProps[NAME_ATTR] = name;
    lineProps[HIDDEN_ATTR] = hiddenHere(model, name);
    return element("input", lineProps);
  }

  // The secret box has no echo mode of its own; Qt hides it by painting
  // the glyphs transparent, and the payload carries the sheet that does.
  function SecretBox(props) {
    var model = props.model;
    var boxProps = {
      value: text(model[API_SECRET_TEXT]),
      placeholder: text(objectField(model, PLACEHOLDERS)[API_SECRET]),
      title: text(objectField(model, TOOL_TIPS)[API_SECRET]),
      readOnly: true,
      onChange: function () {},
      style: declarations(model[API_SECRET_STYLE]) || {}
    };
    boxProps.style.maxHeight = pixels(model[API_SECRET_MAX_HEIGHT_PX]);
    boxProps[PART_ATTR] = PART_TEXT;
    boxProps[NAME_ATTR] = API_SECRET;
    return element("textarea", boxProps);
  }

  function Check(props) {
    var model = props.model;
    var name = props.name;
    var boxProps = {
      type: CHECKBOX_INPUT,
      checked: model[CHECK_STATES[name]] === true,
      title: text(objectField(model, TOOL_TIPS)[name]),
      disabled: true,
      onChange: function () {}
    };
    boxProps[PART_ATTR] = PART_CHECK;
    boxProps[NAME_ATTR] = name;
    var wrapProps = {};
    wrapProps[NAME_ATTR] = name;
    return element(
      "label",
      wrapProps,
      element("input", boxProps),
      text(objectField(model, CHECK_TEXTS)[name])
    );
  }

  function Button(props) {
    var model = props.model;
    var name = props.name;
    var carried = objectField(objectField(model, BUTTONS), name);
    var buttonProps = {
      type: BUTTON_KIND,
      title: text(carried[BUTTON_TOOL_TIP]),
      disabled: carried[BUTTON_ENABLED] === false,
      style: declarations(carried[BUTTON_STYLE_SHEET])
    };
    buttonProps[PART_ATTR] = PART_BUTTON;
    buttonProps[NAME_ATTR] = name;
    return element("button", buttonProps, text(carried[BUTTON_TEXT]));
  }

  function Combo(props) {
    var model = props.model;
    var items = listField(model, EXCHANGE_ITEMS);
    var at = model[EXCHANGE_INDEX];
    var chosen = Array.isArray(items[at]) ? items[at][1] : undefined;
    var comboProps = {
      value: chosen,
      disabled: true,
      onChange: function () {}
    };
    comboProps[PART_ATTR] = PART_COMBO;
    comboProps[NAME_ATTR] = props.name;
    return element(
      "select",
      comboProps,
      items.map(function (one) {
        return element("option", { key: one[1], value: one[1] }, text(one[0]));
      })
    );
  }

  function Spacing(props) {
    var gapProps = { style: { height: pixels(props.model[WELCOME_SPACING_PX]) } };
    gapProps[PART_ATTR] = PART_SPACING;
    gapProps[NAME_ATTR] = props.name;
    return element("div", gapProps);
  }

  // Which drawer one widget name belongs to, read off the payload's own
  // tag lists. A name in no list is drawn as an unknown widget and named
  // as a fault, never left out silently.
  function widgetKind(model, name) {
    if (listField(model, LABEL_TAGS).indexOf(name) >= 0) {
      return PART_LABEL;
    }
    if (listField(model, LINE_TAGS).indexOf(name) >= 0) {
      return PART_LINE;
    }
    if (listField(model, TEXT_TAGS).indexOf(name) >= 0) {
      return PART_TEXT;
    }
    if (listField(model, CHECK_TAGS).indexOf(name) >= 0) {
      return PART_CHECK;
    }
    if (listField(model, BUTTON_TAGS).indexOf(name) >= 0) {
      return PART_BUTTON;
    }
    if (listField(model, COMBO_TAGS).indexOf(name) >= 0) {
      return PART_COMBO;
    }
    if (name === WELCOME_SPACING) {
      return PART_SPACING;
    }
    return PART_UNKNOWN;
  }

  var DRAWERS = {};
  DRAWERS[PART_LABEL] = Label;
  DRAWERS[PART_LINE] = Line;
  DRAWERS[PART_TEXT] = SecretBox;
  DRAWERS[PART_CHECK] = Check;
  DRAWERS[PART_BUTTON] = Button;
  DRAWERS[PART_COMBO] = Combo;
  DRAWERS[PART_SPACING] = Spacing;

  function Widget(props) {
    var kind = widgetKind(props.model, props.name);
    if (!owns(DRAWERS, kind)) {
      var strayProps = {};
      strayProps[PART_ATTR] = PART_UNKNOWN;
      strayProps[NAME_ATTR] = props.name;
      return element("div", strayProps);
    }
    return element(DRAWERS[kind], { model: props.model, name: props.name });
  }

  function Page(props) {
    var model = props.model;
    var name = props.name;
    var order = listField(objectField(model, PAGE_ORDERS), name);
    var pageProps = {};
    pageProps[PART_ATTR] = PART_PAGE;
    pageProps[PAGE_ATTR] = name;
    var titleProps = {};
    titleProps[PART_ATTR] = PART_TITLE;
    var subtitleProps = {};
    subtitleProps[PART_ATTR] = PART_SUBTITLE;
    return element(
      "section",
      pageProps,
      element("h2", titleProps, text(objectField(model, PAGE_TITLES)[name])),
      element("p", subtitleProps, text(objectField(model, PAGE_SUBTITLES)[name])),
      order.map(function (one) {
        return element(Widget, { key: one, model: model, name: one });
      })
    );
  }

  function Wizard(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var size = listField(model, MINIMUM_SIZE_PX);
    var wizardProps = {
      style: {
        display: FLEX,
        flexDirection: COLUMN,
        minWidth: pixels(size[0]),
        minHeight: pixels(size[1])
      }
    };
    wizardProps[PART_ATTR] = PART_WIZARD;
    wizardProps[ARIA_LABEL] = text(model[WINDOW_TITLE]);
    wizardProps[UPGRADE_ATTR] = text(model[IS_UPGRADE]);
    return element(
      "div",
      wizardProps,
      listField(model, PAGES).map(function (one) {
        return element(Page, { key: one, model: model, name: one });
      })
    );
  }

  // -- holding the payload ---------------------------------------------

  // Null is a value the wizard publishes on purpose: the fresh-start
  // switch is absent on a first run and no venue is chosen until one is.
  // A field that never arrives at all is the fault.
  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        wizardFaults.push(fault(null, name, MISSING_FAULT, null));
      }
    });
  }

  // A widget a page asks for that no drawer knows would be drawn empty,
  // which is a control the operator cannot use and cannot see is absent.
  function checkWidgets(model) {
    Object.keys(objectField(model, PAGE_ORDERS)).forEach(function (page) {
      listField(objectField(model, PAGE_ORDERS), page).forEach(function (name) {
        if (widgetKind(model, name) === PART_UNKNOWN) {
          wizardFaults.push(fault(page, name, UNKNOWN_WIDGET_FAULT, null));
        }
      });
    });
  }

  function heldFieldTotal() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function setWizard(model) {
    if (!isPlainObject(model)) {
      held = null;
      wizardFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: wizardFaults.slice() };
    }
    held = { model: model };
    wizardFaults = [];
    checkFields(model);
    checkWidgets(model);
    return {
      declared: { fields: DECLARED_FIELDS.length },
      held: { fields: heldFieldTotal(), pages: listField(model, PAGES).length },
      faults: wizardFaults.slice()
    };
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadWizard(params) {
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
        setWizard(model);
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

  function pageNames() {
    return held === null ? [] : listField(held.model, PAGES).slice();
  }

  function pageOrder(name) {
    return held === null
      ? []
      : listField(objectField(held.model, PAGE_ORDERS), name).slice();
  }

  function kindOfWidget(name) {
    return held === null ? undefined : widgetKind(held.model, name);
  }

  // The drawer picked for every widget this run actually shows. The
  // fresh-start switch is named for both runs but drawn only on an
  // upgrade, so the page orders are what is walked, never every name.
  function widgetKinds() {
    if (held === null) {
      return {};
    }
    var orders = objectField(held.model, PAGE_ORDERS);
    var found = {};
    Object.keys(orders).forEach(function (page) {
      listField(orders, page).forEach(function (name) {
        found[name] = widgetKind(held.model, name);
      });
    });
    return found;
  }

  function hiddenWidgets() {
    if (held === null) {
      return [];
    }
    var model = held.model;
    return Object.keys(HIDEABLE).filter(function (name) {
      return hiddenHere(model, name);
    });
  }

  function secretFieldsReadable() {
    if (held === null) {
      return {};
    }
    var found = {};
    found[API_KEY] = readable(held.model, API_KEY);
    found[PASSPHRASE] = readable(held.model, PASSPHRASE);
    return found;
  }

  function secretBoxStyle() {
    return held === null ? null : declarations(held.model[API_SECRET_STYLE]);
  }

  function hiddenFieldStyle() {
    return held === null
      ? null
      : declarations(objectField(held.model, STYLES)[STYLE_HIDDEN_FIELD]);
  }

  function feedbackStyle() {
    return held === null ? null : declarations(held.model[FEEDBACK_STYLE]);
  }

  function buttonOf(name) {
    return held === null
      ? {}
      : copyOf(objectField(objectField(held.model, BUTTONS), name));
  }

  function exchangeItems() {
    return held === null ? [] : listField(held.model, EXCHANGE_ITEMS).slice();
  }

  function checkState(name) {
    return held === null || !has(CHECK_STATES, name)
      ? undefined
      : held.model[CHECK_STATES[name]];
  }

  function faults() {
    return wizardFaults.slice();
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

  function renderWizard(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Wizard, { model: payload }));
  }

  function forget() {
    held = null;
    wizardFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetWizard = setWizard;
  global.acervatorLoadWizard = loadWizard;
  global.acervatorWizard = {
    method: METHOD,
    Wizard: Wizard,
    Page: Page,
    Widget: Widget,
    Label: Label,
    Line: Line,
    SecretBox: SecretBox,
    Check: Check,
    Button: Button,
    Combo: Combo,
    field: field,
    declaredFields: declaredFields,
    pageNames: pageNames,
    pageOrder: pageOrder,
    kindOfWidget: kindOfWidget,
    widgetKinds: widgetKinds,
    hiddenWidgets: hiddenWidgets,
    secretFieldsReadable: secretFieldsReadable,
    secretBoxStyle: secretBoxStyle,
    hiddenFieldStyle: hiddenFieldStyle,
    feedbackStyle: feedbackStyle,
    buttonOf: buttonOf,
    exchangeItems: exchangeItems,
    checkState: checkState,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderWizard: renderWizard,
    forget: forget
  };
})(window);
