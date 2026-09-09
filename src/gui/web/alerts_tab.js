// Draws the Notifications and Alerts tab from the alerts_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "alerts_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var BUTTON_NAMES = "button_names";
  var BUTTON_TEXTS = "button_texts";
  var BUTTONS_ENABLED = "buttons_enabled";
  var CHAT_ID = "chat_id";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var ECHO_MODES = "echo_modes";
  var GROUP_TITLES = "group_titles";
  var HISTORY_COLUMNS = "history_columns";
  var HISTORY_ROWS = "history_rows";
  var PANE_MARGINS = "pane_margins";
  var PHONE = "phone";
  var PLACEHOLDERS = "placeholders";
  var ROW_LABELS = "row_labels";
  var RULES_COLUMNS = "rules_columns";
  var RULES_ROWS = "rules_rows";
  var SMS_STATUS_STYLE = "sms_status_style";
  var SMS_STATUS_TEXT = "sms_status_text";
  var SPLITTER_HANDLE_WIDTH = "splitter_handle_width";
  var SPLITTER_SIZES = "splitter_sizes";
  var STATUS_STYLE = "status_style";
  var STATUS_TEXT = "status_text";
  var STYLES = "styles";
  var TELEGRAM_STATUS_STYLE = "telegram_status_style";
  var TELEGRAM_STATUS_TEXT = "telegram_status_text";
  var TOKEN = "token";
  var UNREAD_STYLE = "unread_style";
  var UNREAD_TEXT = "unread_text";
  var WIDGETS = "widgets";

  // READ_FIELDS is every top-level field this file draws from. A field the
  // payload carries for the Qt side alone is not listed and not reported;
  // the surface parity tests hold the payload's whole shape.
  var READ_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    BUTTON_NAMES,
    BUTTON_TEXTS,
    BUTTONS_ENABLED,
    CHAT_ID,
    CONTENT_MARGINS,
    CONTENT_SPACING,
    ECHO_MODES,
    GROUP_TITLES,
    HISTORY_COLUMNS,
    HISTORY_ROWS,
    PANE_MARGINS,
    PHONE,
    PLACEHOLDERS,
    ROW_LABELS,
    RULES_COLUMNS,
    RULES_ROWS,
    SMS_STATUS_STYLE,
    SMS_STATUS_TEXT,
    SPLITTER_HANDLE_WIDTH,
    SPLITTER_SIZES,
    STATUS_STYLE,
    STATUS_TEXT,
    STYLES,
    TELEGRAM_STATUS_STYLE,
    TELEGRAM_STATUS_TEXT,
    TOKEN,
    UNREAD_STYLE,
    UNREAD_TEXT,
    WIDGETS
  ];

  var COLOR = "color";
  var ECHO_MODE = "echo_mode";
  var EMPTY_STYLE = "empty";
  var GROUP_BOX = "group_box";
  var PLACEHOLDER = "placeholder";
  var STRETCH = "stretch";
  var TEXT = "text";
  var TITLE = "title";

  var STYLE_FIELDS = [EMPTY_STYLE, GROUP_BOX];

  var BAG_FIELDS = {};
  BAG_FIELDS[STYLES] = STYLE_FIELDS;

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var NO_BRIDGE = "the preload bridge is not present";

  var PART_ATTR = "data-part";
  var ACTION_ATTR = "data-action";
  var HOVERED_ATTR = "data-hovered";
  var LABEL_ATTR = "aria-label";
  var ROLE_ATTR = "role";
  var DISABLED_ATTR = "aria-disabled";

  var TAB_PART = "alerts-tab";
  var PANE_PART = "alerts-pane";
  var SPLIT_PART = "alerts-split";
  var HANDLE_PART = "alerts-handle";
  var STATUS_PART = "alerts-status";
  var UNREAD_PART = "alerts-unread";
  var GROUP_PART = "alerts-group";
  var GROUP_TITLE_PART = "alerts-group-title";
  var FIELD_ROW_PART = "alerts-field-row";
  var FIELD_LABEL_PART = "alerts-field-label";
  var FIELD_INPUT_PART = "alerts-field-input";
  var NOTE_PART = "alerts-note";
  var BUTTON_PART = "alerts-button";
  var ACK_ROW_PART = "alerts-ack-row";
  var RULES_TABLE_PART = "alerts-rules-table";
  var HISTORY_TABLE_PART = "alerts-history-table";
  var HEAD_CELL_PART = "alerts-head-cell";
  var ROW_PART = "alerts-row";
  var CELL_PART = "alerts-cell";
  var SPACER_PART = "alerts-spacer";

  var TAB_CLASS = "acervator-alerts-tab";

  var DIV_TAG = "div";
  var INPUT_TAG = "input";
  var BUTTON_TAG = "button";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";

  var TEXT_TYPE = "text";
  var PASSWORD_TYPE = "password";
  var BUTTON_TYPE = "button";
  var HOVER_STATE = "hover";

  var EMPTY = "";
  var PX = "px";
  var FULL = "100%";
  var FLEX = "flex";
  var NONE = "none";
  var COLUMN = "column";
  var ROW = "row";
  var CENTER = "center";
  var AUTO = "auto";
  var NOWRAP = "nowrap";
  var COLLAPSE = "collapse";
  var FIXED = "fixed";
  var BORDER_BOX = "border-box";
  var SEPARATOR_ROLE = "separator";
  var VAR_OPEN = "var(--";
  // The comma carries no space, because the space-and-comma spelling is
  // also the string this tab joins a message's channels with.
  var VAR_SPLIT = ",";
  var CLOSE_PAREN = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";

  var ZERO = 0;

  var MARGIN_LEFT = 0;
  var MARGIN_TOP = 1;
  var MARGIN_RIGHT = 2;
  var MARGIN_BOTTOM = 3;

  var TELEGRAM_TITLE_AT = 0;
  var SMS_TITLE_AT = 1;
  var RULES_TITLE_AT = 2;
  var HISTORY_TITLE_AT = 3;

  var TOKEN_LABEL_AT = 0;
  var CHAT_LABEL_AT = 1;
  var PHONE_LABEL_AT = 2;

  var TOKEN_PLACEHOLDER_AT = 0;
  var CHAT_PLACEHOLDER_AT = 1;
  var PHONE_PLACEHOLDER_AT = 2;

  // The echo mode Qt gives a field whose text is not shown back.
  var HIDDEN_ECHO_AT = 1;

  var TEST_BUTTON_AT = 0;
  var SAVE_BUTTON_AT = 1;
  var ACK_BUTTON_AT = 2;

  var LEFT_PANE_AT = 0;
  var RIGHT_PANE_AT = 1;

  var held = null;
  var tabFaults = [];
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

  function copyOf(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function kindOf(value) {
    if (value === null) {
      return NULL_KIND;
    }
    return Array.isArray(value) ? OBJECT_KIND : typeof value;
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // An accessible name the surface left empty stays off the element.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function at(list, index) {
    return Array.isArray(list) && index < list.length ? list[index] : undefined;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  // `shared_widgets.js` owns the one-carrier rule that names a token.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
  function headerApi(name) {
    var api = global.acervatorHeader;
    return api && typeof api[name] === "function" ? api[name] : null;
  }

  function declarations(sheet) {
    var reader = headerApi("declarations");
    return reader === null ? [] : reader(sheet);
  }

  function stateRules(sheet) {
    var reader = headerApi("stateRules");
    return reader === null ? [] : reader(sheet);
  }

  function styleOf(sheet) {
    var reader = headerApi("styleOf");
    return reader === null ? {} : reader(sheet);
  }

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  // The style one named Qt state paints, such as the hover a button carries.
  function stateStyle(sheet, state) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (String(rule.selector).indexOf(state) < ZERO) {
        return;
      }
      merged(found, styleOf(rule.body));
    });
    return found;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function length(value) {
    if (!isNumber(value)) {
      return undefined;
    }
    var name = variableFor(value);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + CLOSE_PAREN + PX_FACTOR
    );
  }

  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + CLOSE_PAREN;
  }

  function marginsOf(margins) {
    return {
      paddingLeft: length(at(margins, MARGIN_LEFT)),
      paddingTop: length(at(margins, MARGIN_TOP)),
      paddingRight: length(at(margins, MARGIN_RIGHT)),
      paddingBottom: length(at(margins, MARGIN_BOTTOM))
    };
  }

  // -- what a press asks the bridge --------------------------------------

  // The action the surface bound to one button, read in the order the
  // surface published its buttons.
  // The first widget node whose `key` carries `value`.
  function nodeWith(model, key, value) {
    var found = listField(model, WIDGETS).filter(function (node) {
      return isPlainObject(node) && node[key] === value;
    });
    return found.length ? found[ZERO] : {};
  }

  // Whether the field carrying `hint` hides what is typed into it.
  function echoHidden(model, hint) {
    var concealed = at(listField(model, ECHO_MODES), HIDDEN_ECHO_AT);
    return nodeWith(model, PLACEHOLDER, hint)[ECHO_MODE] === concealed;
  }

  // The share of its pane the group box titled `title` was given.
  function titleStretch(model, title) {
    return nodeWith(model, TITLE, title)[STRETCH];
  }

  function actionAt(model, index) {
    var actions = objectField(model, ACTIONS);
    var bound = Object.keys(actions);
    return index < bound.length ? actions[bound[index]] : undefined;
  }

  function buttonName(model, index) {
    return at(listField(model, BUTTON_NAMES), index);
  }

  function buttonEnabled(model, index) {
    var name = buttonName(model, index);
    var enabled = objectField(model, BUTTONS_ENABLED);
    return name === undefined || !owns(enabled, name) ? true : enabled[name];
  }

  function buttonStyle(model, index) {
    var name = buttonName(model, index);
    return name === undefined ? undefined : objectField(model, STYLES)[name];
  }

  function dispatch(action, fields) {
    var params = { action: action, fields: fields };
    dispatched.push(copyOf(params));
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    return global.acervator.call(METHOD, copyOf(params));
  }

  // -- one text field ------------------------------------------------------

  function Field(props) {
    var rowProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: NONE
      }
    };
    rowProps[PART_ATTR] = FIELD_ROW_PART;
    var labelProps = { style: { flex: NONE, whiteSpace: NOWRAP } };
    labelProps[PART_ATTR] = FIELD_LABEL_PART;
    var inputProps = {
      type: props.hidden ? PASSWORD_TYPE : TEXT_TYPE,
      value: text(props.value) === undefined ? EMPTY : String(props.value),
      placeholder: text(props.placeholder),
      style: { flex: AUTO, minWidth: String(ZERO) },
      onChange: props.onWrite
    };
    inputProps[PART_ATTR] = FIELD_INPUT_PART;
    inputProps[LABEL_ATTR] = label(props.words);
    return element(
      DIV_TAG,
      rowProps,
      element(DIV_TAG, labelProps, text(props.words)),
      element(INPUT_TAG, inputProps)
    );
  }

  function Note(props) {
    var style = styleOf(props.sheet);
    style.flex = NONE;
    var noteProps = { style: style };
    noteProps[PART_ATTR] = props.part;
    return element(DIV_TAG, noteProps, text(props.words));
  }

  // A Qt button repaints itself under the pointer, which CSS reaches only
  // through a rule, so the hover block is merged in while it is hovered.
  function HoverButton(props) {
    var kept = hooks().useState(false);
    var hovered = kept.shift();
    var setHovered = kept.shift();
    var style = styleOf(props.sheet);
    style.flex = NONE;
    style.whiteSpace = NOWRAP;
    if (hovered === true) {
      merged(style, stateStyle(props.sheet, HOVER_STATE));
    }
    var buttonProps = {
      type: BUTTON_TYPE,
      style: style,
      disabled: props.enabled === false,
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      },
      onClick: props.onPress
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[HOVERED_ATTR] = text(hovered);
    buttonProps[DISABLED_ATTR] = text(props.enabled === false);
    return element(BUTTON_TAG, buttonProps, text(props.words));
  }

  // -- a group box ---------------------------------------------------------

  // A QGroupBox colour paints its title; the widgets inside keep their own.
  function Group(props) {
    var sheet = styleOf(props.sheet);
    var painted = sheet[COLOR];
    delete sheet[COLOR];
    var style = merged(sheet, {
      display: FLEX,
      flexDirection: COLUMN,
      flexGrow: props.stretch,
      minHeight: String(ZERO),
      boxSizing: BORDER_BOX
    });
    var groupProps = { style: style };
    groupProps[PART_ATTR] = GROUP_PART;
    var titleProps = { style: { flex: NONE, color: painted } };
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    return element(
      DIV_TAG,
      groupProps,
      element(DIV_TAG, titleProps, text(props.title)),
      props.children
    );
  }

  function Spacer() {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = SPACER_PART;
    return element(DIV_TAG, spacerProps);
  }

  // -- a table -------------------------------------------------------------

  function HeadCell(props) {
    var cellProps = { scope: COLUMN };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    return element(HEAD_CELL_TAG, cellProps, text(props.words));
  }

  function Cell(props) {
    var cell = isPlainObject(props.cell) ? props.cell : {};
    var painted = colour(cell[COLOR]);
    var cellProps = {
      style: { color: painted === EMPTY ? undefined : painted, textAlign: CENTER }
    };
    cellProps[PART_ATTR] = CELL_PART;
    return element(CELL_TAG, cellProps, text(cell[TEXT]));
  }

  function Row(props) {
    var rowProps = {};
    rowProps[PART_ATTR] = ROW_PART;
    return element(
      ROW_TAG,
      rowProps,
      props.cells.map(function (cell, index) {
        return element(Cell, { key: String(index), cell: cell });
      })
    );
  }

  function Table(props) {
    var tableProps = {
      style: { width: FULL, borderCollapse: COLLAPSE, tableLayout: FIXED }
    };
    tableProps[PART_ATTR] = props.part;
    var headRowProps = {};
    headRowProps[PART_ATTR] = ROW_PART;
    return element(
      DIV_TAG,
      { style: { flex: AUTO, overflow: AUTO, minHeight: String(ZERO) } },
      element(
        TABLE_TAG,
        tableProps,
        element(
          HEAD_TAG,
          null,
          element(
            ROW_TAG,
            headRowProps,
            props.columns.map(function (words, index) {
              return element(HeadCell, { key: String(index), words: words });
            })
          )
        ),
        element(
          BODY_TAG,
          null,
          props.rows.map(function (cells, index) {
            return element(Row, {
              key: String(index),
              cells: Array.isArray(cells) ? cells : []
            });
          })
        )
      )
    );
  }

  // -- the two panes --------------------------------------------------------

  function LeftPane(props) {
    var model = props.model;
    var titles = listField(model, GROUP_TITLES);
    var labels = listField(model, ROW_LABELS);
    var hints = listField(model, PLACEHOLDERS);
    var texts = listField(model, BUTTON_TEXTS);
    var sheet = objectField(model, STYLES)[GROUP_BOX];
    var write = props.onWrite;
    var paneProps = {
      style: merged(
        {
          display: FLEX,
          flexDirection: COLUMN,
          flex: AUTO,
          minWidth: String(ZERO),
          overflow: AUTO
        },
        marginsOf(listField(model, PANE_MARGINS))
      )
    };
    paneProps[PART_ATTR] = PANE_PART;
    return element(
      DIV_TAG,
      paneProps,
      element(Note, {
        part: STATUS_PART,
        words: model[STATUS_TEXT],
        sheet: model[STATUS_STYLE]
      }),
      element(Note, {
        part: UNREAD_PART,
        words: model[UNREAD_TEXT],
        sheet: model[UNREAD_STYLE]
      }),
      element(
        Group,
        { sheet: sheet, title: at(titles, TELEGRAM_TITLE_AT) },
        element(Field, {
          words: at(labels, TOKEN_LABEL_AT),
          placeholder: at(hints, TOKEN_PLACEHOLDER_AT),
          hidden: echoHidden(model, at(hints, TOKEN_PLACEHOLDER_AT)),
          value: model[TOKEN],
          onWrite: function (event) {
            write(TOKEN, event.target.value);
          }
        }),
        element(Field, {
          words: at(labels, CHAT_LABEL_AT),
          placeholder: at(hints, CHAT_PLACEHOLDER_AT),
          hidden: echoHidden(model, at(hints, CHAT_PLACEHOLDER_AT)),
          value: model[CHAT_ID],
          onWrite: function (event) {
            write(CHAT_ID, event.target.value);
          }
        }),
        element(HoverButton, {
          words: at(texts, TEST_BUTTON_AT),
          sheet: buttonStyle(model, TEST_BUTTON_AT),
          enabled: buttonEnabled(model, TEST_BUTTON_AT),
          action: actionAt(model, TEST_BUTTON_AT),
          onPress: props.onTest
        }),
        element(Note, {
          part: NOTE_PART,
          words: model[TELEGRAM_STATUS_TEXT],
          sheet: model[TELEGRAM_STATUS_STYLE]
        })
      ),
      element(
        Group,
        { sheet: sheet, title: at(titles, SMS_TITLE_AT) },
        element(Field, {
          words: at(labels, PHONE_LABEL_AT),
          placeholder: at(hints, PHONE_PLACEHOLDER_AT),
          hidden: echoHidden(model, at(hints, PHONE_PLACEHOLDER_AT)),
          value: model[PHONE],
          onWrite: function (event) {
            write(PHONE, event.target.value);
          }
        }),
        element(Note, {
          part: NOTE_PART,
          words: model[SMS_STATUS_TEXT],
          sheet: model[SMS_STATUS_STYLE]
        })
      ),
      element(HoverButton, {
        words: at(texts, SAVE_BUTTON_AT),
        sheet: buttonStyle(model, SAVE_BUTTON_AT),
        enabled: buttonEnabled(model, SAVE_BUTTON_AT),
        action: actionAt(model, SAVE_BUTTON_AT),
        onPress: props.onSave
      }),
      element(Spacer, null)
    );
  }

  function RightPane(props) {
    var model = props.model;
    var titles = listField(model, GROUP_TITLES);
    var texts = listField(model, BUTTON_TEXTS);
    var sheet = objectField(model, STYLES)[GROUP_BOX];
    var paneProps = {
      style: merged(
        {
          display: FLEX,
          flexDirection: COLUMN,
          flex: AUTO,
          minWidth: String(ZERO)
        },
        marginsOf(listField(model, PANE_MARGINS))
      )
    };
    paneProps[PART_ATTR] = PANE_PART;
    var ackRowProps = {
      style: { display: FLEX, flexDirection: ROW, flex: NONE }
    };
    ackRowProps[PART_ATTR] = ACK_ROW_PART;
    return element(
      DIV_TAG,
      paneProps,
      element(
        Group,
        {
          sheet: sheet,
          title: at(titles, RULES_TITLE_AT),
          stretch: titleStretch(model, at(titles, RULES_TITLE_AT))
        },
        element(Table, {
          part: RULES_TABLE_PART,
          columns: listField(model, RULES_COLUMNS),
          rows: listField(model, RULES_ROWS)
        })
      ),
      element(
        Group,
        {
          sheet: sheet,
          title: at(titles, HISTORY_TITLE_AT),
          stretch: titleStretch(model, at(titles, HISTORY_TITLE_AT))
        },
        element(
          DIV_TAG,
          ackRowProps,
          element(Spacer, null),
          element(HoverButton, {
            words: at(texts, ACK_BUTTON_AT),
            sheet: buttonStyle(model, ACK_BUTTON_AT),
            enabled: buttonEnabled(model, ACK_BUTTON_AT),
            action: actionAt(model, ACK_BUTTON_AT),
            onPress: props.onAcknowledge
          })
        ),
        element(Table, {
          part: HISTORY_TABLE_PART,
          columns: listField(model, HISTORY_COLUMNS),
          rows: listField(model, HISTORY_ROWS)
        })
      )
    );
  }

  // A Qt splitter gives each pane its share of the row and paints a handle
  // between them, so the shares become the flex-grow numbers here.
  function Tab(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var sizes = listField(model, SPLITTER_SIZES);
    var tabProps = {
      className: TAB_CLASS,
      style: merged(
        {
          display: FLEX,
          flexDirection: COLUMN,
          height: FULL,
          gap: length(model[CONTENT_SPACING]),
          boxSizing: BORDER_BOX
        },
        marginsOf(listField(model, CONTENT_MARGINS))
      )
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[LABEL_ATTR] = label(model[ACCESSIBLE_NAME]);
    var splitProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        flex: AUTO,
        minHeight: String(ZERO)
      }
    };
    splitProps[PART_ATTR] = SPLIT_PART;
    var handleProps = {
      style: { flex: NONE, width: length(model[SPLITTER_HANDLE_WIDTH]) }
    };
    handleProps[PART_ATTR] = HANDLE_PART;
    handleProps[ROLE_ATTR] = SEPARATOR_ROLE;
    function write(name, written) {
      var fields = {};
      fields[name] = written;
      dispatch(undefined, fields);
    }
    function press(index) {
      return function () {
        dispatch(actionAt(model, index), undefined);
      };
    }
    return element(
      DIV_TAG,
      tabProps,
      element(
        DIV_TAG,
        splitProps,
        element(
          DIV_TAG,
          {
            style: {
              display: FLEX,
              flexGrow: at(sizes, LEFT_PANE_AT),
              flexBasis: String(ZERO),
              minWidth: String(ZERO)
            }
          },
          element(LeftPane, {
            model: model,
            onWrite: write,
            onTest: press(TEST_BUTTON_AT),
            onSave: press(SAVE_BUTTON_AT)
          })
        ),
        element(DIV_TAG, handleProps),
        element(
          DIV_TAG,
          {
            style: {
              display: FLEX,
              flexGrow: at(sizes, RIGHT_PANE_AT),
              flexBasis: String(ZERO),
              minWidth: String(ZERO)
            }
          },
          element(RightPane, {
            model: model,
            onAcknowledge: press(ACK_BUTTON_AT)
          })
        )
      )
    );
  }

  // -- holding one payload ---------------------------------------------------

  function checkFields(model) {
    READ_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tabFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkBags(model) {
    Object.keys(BAG_FIELDS).forEach(function (where) {
      var bag = objectField(model, where);
      BAG_FIELDS[where].forEach(function (field) {
        if (!owns(bag, field)) {
          tabFaults.push(fault(where, field, MISSING_FAULT, null));
          return;
        }
        if (bag[field] === null) {
          tabFaults.push(fault(where, field, NULL_FAULT, null));
        }
      });
    });
  }

  function nestedPaths() {
    var found = [];
    Object.keys(BAG_FIELDS).forEach(function (where) {
      BAG_FIELDS[where].forEach(function (name) {
        found.push({ where: where, field: name });
      });
    });
    return found;
  }

  function heldNestedPaths(model) {
    return nestedPaths().filter(function (one) {
      return owns(objectField(model, one.where), one.field);
    });
  }

  // Counts what the file must read apart from what the payload carried.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: READ_FIELDS.length,
        nested: nestedPaths().length
      },
      held: {
        fields: READ_FIELDS.filter(function (field) {
          return owns(model, field);
        }).length,
        nested: heldNestedPaths(model).length,
        buttons: listField(model, BUTTON_NAMES).length,
        rows:
          listField(model, RULES_ROWS).length +
          listField(model, HISTORY_ROWS).length
      },
      faults: tabFaults.slice()
    };
  }

  function setTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: model };
    tabFaults = [];
    checkFields(model);
    checkBags(model);
    return report();
  }

  // loadTab asks METHOD once, clearing asked so a refusal retries.
  function loadTab(params) {
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
        setTab(model);
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

  function readNames() {
    return READ_FIELDS.slice();
  }

  function nestedNames(where) {
    return owns(BAG_FIELDS, where) ? BAG_FIELDS[where].slice() : [];
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function accessibleName() {
    return field(ACCESSIBLE_NAME);
  }

  function actionFor(index) {
    return held === null ? undefined : actionAt(held.model, index);
  }

  function rulesRows() {
    return list(RULES_ROWS);
  }

  function historyRows() {
    return list(HISTORY_ROWS);
  }

  function groupTitles() {
    return list(GROUP_TITLES);
  }

  function buttonTexts() {
    return list(BUTTON_TEXTS);
  }

  function calls() {
    return dispatched.slice();
  }

  function kinds() {
    var found = {};
    if (held === null) {
      return found;
    }
    var model = held.model;
    Object.keys(model).forEach(function (name) {
      found[name] = kindOf(model[name]);
    });
    return found;
  }

  function faults() {
    return tabFaults.slice();
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

  function renderTab(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: drawn }));
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetAlertsTab = setTab;
  global.acervatorLoadAlertsTab = loadTab;
  global.acervatorAlertsTab = {
    method: METHOD,
    Tab: Tab,
    LeftPane: LeftPane,
    RightPane: RightPane,
    Group: Group,
    Field: Field,
    Note: Note,
    HoverButton: HoverButton,
    Spacer: Spacer,
    Table: Table,
    Row: Row,
    Cell: Cell,
    HeadCell: HeadCell,
    payload: payload,
    readNames: readNames,
    nestedNames: nestedNames,
    field: field,
    bag: bag,
    accessibleName: accessibleName,
    actionFor: actionFor,
    rulesRows: rulesRows,
    historyRows: historyRows,
    groupTitles: groupTitles,
    buttonTexts: buttonTexts,
    calls: calls,
    stateStyle: stateStyle,
    styleOf: styleOf,
    declarations: declarations,
    stateRules: stateRules,
    variableFor: variableFor,
    colour: colour,
    length: length,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
