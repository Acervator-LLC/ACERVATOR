// Draws the USB hardware key panel from the usb_auth_widget.state payload.
(function (global) {
  "use strict";

  var METHOD = "usb_auth_widget.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var COMBO_INDEX = "combo_index";
  var COMBO_ITEMS = "combo_items";
  var COMBO_MIN_WIDTH = "combo_min_width_px";
  var COMBO_STYLE = "combo_style";
  var CONSTANTS = "constants";
  var DESCRIPTION_STYLE = "description_style";
  var DESCRIPTION_TEXT = "description_text";
  var DRIVE_INFO_STYLE = "drive_info_style";
  var DRIVE_INFO_TEXT = "drive_info_text";
  var DRIVE_LABEL_TEXT = "drive_label_text";
  var EMPTY_STYLE = "empty_style";
  var EMPTY_TEXT = "empty_text";
  var EXPORT_ENABLED = "export_enabled";
  var EXPORT_GROUP_TITLE = "export_group_title";
  var EXPORT_STATUS_STYLE = "export_status_style";
  var EXPORT_STATUS_TEXT = "export_status_text";
  var EXPORT_STYLE = "export_style";
  var EXPORT_TEXT = "export_text";
  var GROUP_STYLE = "group_style";
  var HEADER_STYLE = "header_style";
  var HEADER_TEXT = "header_text";
  var METHOD_FIELD = "method";
  var MODE_DESCRIPTION_STYLE = "mode_description_style";
  var MODE_DESCRIPTION_TEXT = "mode_description_text";
  var MODE_GROUP_TITLE = "mode_group_title";
  var PROGRESS_HEIGHT = "progress_height_px";
  var PROGRESS_RANGE = "progress_range";
  var PROGRESS_STYLE = "progress_style";
  var PROGRESS_TEXT_VISIBLE = "progress_text_visible";
  var PROGRESS_VISIBLE = "progress_visible";
  var REFRESH_ENABLED = "refresh_enabled";
  var REFRESH_STYLE = "refresh_style";
  var REFRESH_TEXT = "refresh_text";
  var REFRESH_WIDTH = "refresh_width_px";
  var ROOT_MARGINS = "root_margins_px";
  var ROOT_SPACING = "root_spacing_px";
  var ROWS = "rows";
  var ROWS_MARGINS = "rows_margins_px";
  var ROWS_SPACING = "rows_spacing_px";
  var SCROLL_MAX_HEIGHT = "scroll_max_height_px";
  var SCROLL_RESIZABLE = "scroll_resizable";
  var SCROLL_STYLE = "scroll_style";
  var VERIFY_STYLE = "verify_style";
  var VERIFY_TEXT = "verify_text";
  var VERIFY_WIDTH = "verify_width_px";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    "answers_left",
    COMBO_INDEX,
    COMBO_ITEMS,
    COMBO_MIN_WIDTH,
    COMBO_STYLE,
    CONSTANTS,
    DESCRIPTION_STYLE,
    DESCRIPTION_TEXT,
    "dialogs",
    DRIVE_INFO_STYLE,
    DRIVE_INFO_TEXT,
    DRIVE_LABEL_TEXT,
    "emitted",
    EMPTY_STYLE,
    EMPTY_TEXT,
    "exchanges",
    EXPORT_ENABLED,
    EXPORT_GROUP_TITLE,
    EXPORT_STATUS_STYLE,
    EXPORT_STATUS_TEXT,
    EXPORT_STYLE,
    EXPORT_TEXT,
    GROUP_STYLE,
    HEADER_STYLE,
    HEADER_TEXT,
    METHOD_FIELD,
    MODE_DESCRIPTION_STYLE,
    MODE_DESCRIPTION_TEXT,
    MODE_GROUP_TITLE,
    PROGRESS_HEIGHT,
    PROGRESS_RANGE,
    PROGRESS_STYLE,
    PROGRESS_TEXT_VISIBLE,
    PROGRESS_VISIBLE,
    REFRESH_ENABLED,
    REFRESH_STYLE,
    REFRESH_TEXT,
    REFRESH_WIDTH,
    ROOT_MARGINS,
    ROOT_SPACING,
    ROWS,
    ROWS_MARGINS,
    ROWS_SPACING,
    "save_refusals",
    "saves",
    SCROLL_MAX_HEIGHT,
    SCROLL_RESIZABLE,
    SCROLL_STYLE,
    "threads",
    "timers",
    "verify_calls",
    VERIFY_STYLE,
    VERIFY_TEXT,
    VERIFY_WIDTH
  ];

  // ROW_FIELDS lists every field one exchange row carries.
  var ROW_FIELDS = [
    ACCESSIBLE_NAME,
    "exchange_id",
    "hardware_mode",
    "lamp",
    "margins_px",
    "name_style",
    "name_text",
    "serial",
    "serial_style",
    "serial_text",
    "style",
    "toggle_checkable",
    "toggle_checked",
    "toggle_style",
    "toggle_text",
    "toggle_width_px"
  ];

  // LAMP_FIELDS lists every field one status lamp carries.
  var LAMP_FIELDS = [
    "colour",
    "exchange_label",
    "paint",
    "size_px",
    "state",
    "tooltip",
    "updates"
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var OPAQUE_ALPHA_FAULT = "alpha-byte";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var PX = "px";
  var SPACE = " ";
  var COMMA = ",";
  var COLON = ":";
  var CLASS_MARK = ".";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";

  var HOST_CLASS = "acervator-usb-auth";
  var PART_ATTR = "data-part";
  var ACTION_ATTR = "data-action";
  var STATE_ATTR = "data-state";
  var ENABLED_ATTR = "data-enabled";
  var CHECKED_ATTR = "data-checked";
  var ROLE_ATTR = "role";

  var HOST_PART = "panel";
  var HEADER_PART = "header";
  var DESCRIPTION_PART = "description";
  var EXPORT_GROUP_PART = "export-group";
  var MODE_GROUP_PART = "mode-group";
  var COMBO_PART = "drive-combo";
  var REFRESH_PART = "refresh";
  var DRIVE_INFO_PART = "drive-info";
  var EXPORT_PART = "export";
  var VERIFY_PART = "verify";
  var PROGRESS_PART = "progress";
  var STATUS_PART = "export-status";
  var SCROLL_PART = "rows-scroll";
  var ROW_PART = "row";
  var LAMP_PART = "lamp";
  var TOGGLE_PART = "toggle";
  var EMPTY_PART = "empty";
  var STYLE_PART = "panel-style";

  // The steps the bridge takes, by the name the payload's action carries.
  var REFRESH_STEP = "refresh";
  var SELECT_STEP = "select";
  var EXPORT_STEP = "export";
  var VERIFY_STEP = "verify";
  var TOGGLE_STEP = "toggle";

  // Qt darkens the lamp's pen by a percentage of its HSV value.
  var DARKER_BASE = 100;
  var HUE_TURN = 360;
  var HUE_SIXTH = 60;
  var CHANNEL_TOP = 255;
  var HEX_RADIX = 16;
  var SHORT_HEX = 3;
  var LONG_HEX = 6;
  var CHANNEL_DIGITS = 2;
  var HEX_MARK = "#";

  // A published alpha above one is Qt's byte, which CSS clamps to opaque.
  var CSS_ALPHA_TOP = 1;
  var RGBA_CALL = /rgba\(([^()]*)\)/g;
  var RGBA_FIELDS = 4;
  var ALPHA_AT = 3;

  var held = null;
  var panelFaults = [];
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

  function text(value) {
    return value === null || value === undefined ? EMPTY : String(value);
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // header_strip.js owns the rule that turns a Qt style sheet into CSS.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  // A selector carrying a colon names a state Qt paints on hover.
  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  // length turns a bare published number into a CSS pixel value.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  // The surface converts Qt's alpha byte before publishing, so a value
  // still carrying a byte here would paint opaque and is reported.
  function alphaBytes(value) {
    var found = [];
    String(value).replace(RGBA_CALL, function (whole, inside) {
      var fields = inside.split(COMMA);
      if (fields.length !== RGBA_FIELDS) {
        return whole;
      }
      var alpha = Number(fields[ALPHA_AT]);
      if (!isNaN(alpha) && alpha > CSS_ALPHA_TOP) {
        found.push(whole);
      }
      return whole;
    });
    return found;
  }

  function hexChannels(colour) {
    var digits = text(colour).trim().replace(HEX_MARK, EMPTY);
    if (digits.length === SHORT_HEX) {
      digits = digits
        .split(EMPTY)
        .map(function (one) {
          return one + one;
        })
        .join(EMPTY);
    }
    if (digits.length !== LONG_HEX) {
      return null;
    }
    var channels = [];
    var at;
    for (at = 0; at < LONG_HEX; at += CHANNEL_DIGITS) {
      var read = parseInt(digits.substr(at, CHANNEL_DIGITS), HEX_RADIX);
      if (isNaN(read)) {
        return null;
      }
      channels.push(read);
    }
    return channels;
  }

  function hexOf(channels) {
    return (
      HEX_MARK +
      channels
        .map(function (one) {
          var written = Math.round(one).toString(HEX_RADIX);
          return written.length < CHANNEL_DIGITS ? "0" + written : written;
        })
        .join(EMPTY)
    );
  }

  function toHsv(channels) {
    var red = channels[0] / CHANNEL_TOP;
    var green = channels[1] / CHANNEL_TOP;
    var blue = channels[2] / CHANNEL_TOP;
    var top = Math.max(red, green, blue);
    var bottom = Math.min(red, green, blue);
    var span = top - bottom;
    var hue = 0;
    if (span !== 0) {
      if (top === red) {
        hue = HUE_SIXTH * (((green - blue) / span) % 6);
      } else if (top === green) {
        hue = HUE_SIXTH * ((blue - red) / span + 2);
      } else {
        hue = HUE_SIXTH * ((red - green) / span + 4);
      }
    }
    if (hue < 0) {
      hue += HUE_TURN;
    }
    return { hue: hue, saturation: top === 0 ? 0 : span / top, value: top };
  }

  function fromHsv(colour) {
    var chroma = colour.value * colour.saturation;
    var sixth = colour.hue / HUE_SIXTH;
    var second = chroma * (1 - Math.abs((sixth % 2) - 1));
    var base = colour.value - chroma;
    var parts = [0, 0, 0];
    if (sixth < 1) {
      parts = [chroma, second, 0];
    } else if (sixth < 2) {
      parts = [second, chroma, 0];
    } else if (sixth < 3) {
      parts = [0, chroma, second];
    } else if (sixth < 4) {
      parts = [0, second, chroma];
    } else if (sixth < 5) {
      parts = [second, 0, chroma];
    } else {
      parts = [chroma, 0, second];
    }
    return parts.map(function (one) {
      return (one + base) * CHANNEL_TOP;
    });
  }

  // Qt's own rule: a factor above 100 divides the HSV value by that
  // percentage, which is how the lamp's pen is drawn beside its fill.
  function darker(colour, percent) {
    var channels = hexChannels(colour);
    var factor = Number(percent);
    if (channels === null || !factor || factor <= 0) {
      return text(colour);
    }
    var hsv = toHsv(channels);
    hsv.value = hsv.value * (DARKER_BASE / factor);
    return hexOf(fromHsv(hsv));
  }

  function bridge() {
    return global.acervator && typeof global.acervator.call === "function"
      ? global.acervator
      : null;
  }

  // Every step goes through the same round trip, so one failed ask
  // leaves the panel showing what it last drew.
  function step(params) {
    var wire = bridge();
    if (wire === null) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return wire
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setPanel(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function refresh() {
    var params = {};
    params[REFRESH_STEP] = true;
    return step(params);
  }

  function select(index) {
    var params = {};
    params[SELECT_STEP] = index;
    return step(params);
  }

  function exportKeys() {
    var params = {};
    params[EXPORT_STEP] = true;
    return step(params);
  }

  function verify() {
    var params = {};
    params[VERIFY_STEP] = true;
    return step(params);
  }

  function toggle(index, checked) {
    var params = {};
    params[TOGGLE_STEP] = [index, checked];
    return step(params);
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadPanel(params) {
    if (asked !== null) {
      return asked;
    }
    var wire = bridge();
    if (wire === null) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = wire
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setPanel(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function checkFields(model, fields, where) {
    fields.forEach(function (field) {
      if (!owns(model, field)) {
        panelFaults.push(fault(where, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        panelFaults.push(fault(where, field, NULL_FAULT, null));
      }
    });
  }

  // A style sheet reaching the page with Qt's byte would paint a solid
  // block where the panel asks for a tint.
  function checkAlpha(model, fields, where) {
    fields.forEach(function (field) {
      if (typeof model[field] !== "string") {
        return;
      }
      alphaBytes(model[field]).forEach(function (call) {
        panelFaults.push(fault(where, field, OPAQUE_ALPHA_FAULT, call));
      });
    });
  }

  function checkLamp(lamp, where) {
    if (!isPlainObject(lamp)) {
      panelFaults.push(fault(where, "lamp", NOT_AN_OBJECT_FAULT, kindOf(lamp)));
      return;
    }
    checkFields(lamp, LAMP_FIELDS, where);
    if (owns(lamp, "colour") && typeof lamp.colour !== "string") {
      panelFaults.push(
        fault(where, "colour", WRONG_TYPE_FAULT, kindOf(lamp.colour))
      );
    }
  }

  function checkRows(model) {
    listField(model, ROWS).forEach(function (row, at) {
      var where = ROWS + "[" + at + "]";
      if (!isPlainObject(row)) {
        panelFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(row)));
        return;
      }
      checkFields(row, ROW_FIELDS, where);
      checkAlpha(row, ["style", "toggle_style"], where);
      checkLamp(row.lamp, where);
    });
  }

  var STYLE_FIELDS = [
    COMBO_STYLE,
    DESCRIPTION_STYLE,
    DRIVE_INFO_STYLE,
    EMPTY_STYLE,
    EXPORT_STATUS_STYLE,
    EXPORT_STYLE,
    GROUP_STYLE,
    HEADER_STYLE,
    MODE_DESCRIPTION_STYLE,
    PROGRESS_STYLE,
    REFRESH_STYLE,
    SCROLL_STYLE,
    VERIFY_STYLE
  ];

  function setPanel(model) {
    if (!isPlainObject(model)) {
      held = null;
      panelFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { held: null, faults: panelFaults.slice() };
    }
    held = { model: model };
    panelFaults = [];
    checkFields(model, DECLARED_FIELDS, null);
    checkAlpha(model, STYLE_FIELDS, null);
    checkRows(model);
    return { held: model, faults: panelFaults.slice() };
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

  function model() {
    return held === null ? null : held.model;
  }

  function constants() {
    return bag(CONSTANTS);
  }

  function rows() {
    return list(ROWS);
  }

  function comboItems() {
    return list(COMBO_ITEMS);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function rowFields() {
    return ROW_FIELDS.slice();
  }

  function faults() {
    return panelFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  // No inline style carries a hover colour, so a state rule becomes a
  // page rule under the part it was published for.
  function stateCss(sheet, part) {
    return stateRules(sheet)
      .map(function (rule) {
        var states = String(rule.selector).split(COLON);
        states.shift();
        return (
          CLASS_MARK +
          HOST_CLASS +
          SPACE +
          "[" +
          PART_ATTR +
          "='" +
          part +
          "']" +
          COLON +
          states.join(COLON) +
          BLOCK_OPEN +
          rule.body +
          BLOCK_CLOSE
        );
      })
      .join(EMPTY);
  }

  function pageCss(model) {
    if (!isPlainObject(model)) {
      return EMPTY;
    }
    return [
      stateCss(model[REFRESH_STYLE], REFRESH_PART),
      stateCss(model[EXPORT_STYLE], EXPORT_PART),
      stateCss(model[VERIFY_STYLE], VERIFY_PART)
    ].join(EMPTY);
  }

  function Lamp(props) {
    var lamp = props.lamp;
    if (!isPlainObject(lamp)) {
      return null;
    }
    var size = Array.isArray(lamp.size_px) ? lamp.size_px : [];
    var pen = null;
    (Array.isArray(lamp.paint) ? lamp.paint : []).forEach(function (one) {
      if (Array.isArray(one) && one[0] === "pen") {
        pen = one;
      }
    });
    var style = {
      width: length(size[0]),
      height: length(size[1]),
      borderRadius: "50%",
      background: text(lamp.colour),
      boxSizing: "border-box"
    };
    if (pen !== null) {
      style.border =
        length(pen[3]) + " solid " + darker(text(pen[1]), pen[2]);
    }
    var props2 = { className: HOST_CLASS + "-lamp", style: style, title: text(lamp.tooltip) };
    props2[PART_ATTR] = LAMP_PART;
    props2[STATE_ATTR] = text(lamp.state);
    return element("span", props2);
  }

  function ExchangeRow(props) {
    var row = props.row;
    var at = props.at;
    if (!isPlainObject(row)) {
      return null;
    }
    var rowProps = {
      className: HOST_CLASS + "-row",
      style: styleOf(row.style),
      key: text(row.exchange_id) || String(at)
    };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps["data-exchange-id"] = text(row.exchange_id);
    rowProps["aria-label"] = text(row[ACCESSIBLE_NAME]);

    var toggleProps = {
      className: HOST_CLASS + "-toggle",
      style: styleOf(row.toggle_style),
      onClick: function () {
        toggle(at, !row.toggle_checked);
      }
    };
    toggleProps[PART_ATTR] = TOGGLE_PART;
    toggleProps[CHECKED_ATTR] = text(row.toggle_checked);
    toggleProps[ROLE_ATTR] = "switch";
    toggleProps["aria-checked"] = row.toggle_checked === true;

    var nameProps = { style: styleOf(row.name_style) };
    nameProps[PART_ATTR] = "row-name";
    var serialProps = { style: styleOf(row.serial_style) };
    serialProps[PART_ATTR] = "row-serial";

    return element(
      "div",
      rowProps,
      element("span", nameProps, text(row.name_text)),
      element("span", serialProps, text(row.serial_text)),
      element(Lamp, { lamp: row.lamp }),
      element("button", toggleProps, text(row.toggle_text))
    );
  }

  function ExportGroup(props) {
    var model = props.model;
    var comboProps = {
      className: HOST_CLASS + "-combo",
      style: styleOf(model[COMBO_STYLE]),
      value: String(model[COMBO_INDEX]),
      onChange: function (change) {
        select(Number(change.target.value));
      }
    };
    comboProps[PART_ATTR] = COMBO_PART;
    if (model[COMBO_MIN_WIDTH] !== null && model[COMBO_MIN_WIDTH] !== undefined) {
      comboProps.style = copyOf(comboProps.style);
      comboProps.style.minWidth = length(model[COMBO_MIN_WIDTH]);
    }

    var options = listField(model, COMBO_ITEMS).map(function (item, at) {
      return element("option", { value: String(at), key: String(at) }, text(item));
    });

    var refreshProps = {
      className: HOST_CLASS + "-button",
      style: styleOf(model[REFRESH_STYLE]),
      disabled: model[REFRESH_ENABLED] === false,
      onClick: refresh
    };
    refreshProps[PART_ATTR] = REFRESH_PART;
    refreshProps[ACTION_ATTR] = REFRESH_STEP;
    refreshProps[ENABLED_ATTR] = text(model[REFRESH_ENABLED]);
    if (model[REFRESH_WIDTH] !== null && model[REFRESH_WIDTH] !== undefined) {
      refreshProps.style = copyOf(refreshProps.style);
      refreshProps.style.width = length(model[REFRESH_WIDTH]);
    }

    var exportProps = {
      className: HOST_CLASS + "-button",
      style: styleOf(model[EXPORT_STYLE]),
      disabled: model[EXPORT_ENABLED] === false,
      onClick: exportKeys
    };
    exportProps[PART_ATTR] = EXPORT_PART;
    exportProps[ACTION_ATTR] = EXPORT_STEP;
    exportProps[ENABLED_ATTR] = text(model[EXPORT_ENABLED]);

    var verifyProps = {
      className: HOST_CLASS + "-button",
      style: styleOf(model[VERIFY_STYLE]),
      onClick: verify
    };
    verifyProps[PART_ATTR] = VERIFY_PART;
    verifyProps[ACTION_ATTR] = VERIFY_STEP;
    if (model[VERIFY_WIDTH] !== null && model[VERIFY_WIDTH] !== undefined) {
      verifyProps.style = copyOf(verifyProps.style);
      verifyProps.style.width = length(model[VERIFY_WIDTH]);
    }

    var progressStyle = styleOf(model[PROGRESS_STYLE]);
    progressStyle = copyOf(progressStyle);
    progressStyle.height = length(model[PROGRESS_HEIGHT]);
    var progressProps = { className: HOST_CLASS + "-progress", style: progressStyle };
    progressProps[PART_ATTR] = PROGRESS_PART;
    progressProps[ROLE_ATTR] = "progressbar";

    var infoProps = { style: styleOf(model[DRIVE_INFO_STYLE]) };
    infoProps[PART_ATTR] = DRIVE_INFO_PART;
    var statusProps = { style: styleOf(model[EXPORT_STATUS_STYLE]) };
    statusProps[PART_ATTR] = STATUS_PART;

    var groupProps = {
      className: HOST_CLASS + "-group",
      style: styleOf(model[GROUP_STYLE])
    };
    groupProps[PART_ATTR] = EXPORT_GROUP_PART;

    return element(
      "fieldset",
      groupProps,
      element("legend", null, text(model[EXPORT_GROUP_TITLE])),
      element("label", null, text(model[DRIVE_LABEL_TEXT])),
      element("select", comboProps, options),
      element("button", refreshProps, text(model[REFRESH_TEXT])),
      element("div", infoProps, text(model[DRIVE_INFO_TEXT])),
      element("button", exportProps, text(model[EXPORT_TEXT])),
      element("button", verifyProps, text(model[VERIFY_TEXT])),
      model[PROGRESS_VISIBLE] === true ? element("div", progressProps) : null,
      element("div", statusProps, text(model[EXPORT_STATUS_TEXT]))
    );
  }

  function ModeGroup(props) {
    var model = props.model;
    var published = listField(model, ROWS);
    var scrollStyle = copyOf(styleOf(model[SCROLL_STYLE]));
    scrollStyle.maxHeight = length(model[SCROLL_MAX_HEIGHT]);
    scrollStyle.overflowY = "auto";

    var scrollProps = { className: HOST_CLASS + "-scroll", style: scrollStyle };
    scrollProps[PART_ATTR] = SCROLL_PART;

    var descProps = { style: styleOf(model[MODE_DESCRIPTION_STYLE]) };
    descProps[PART_ATTR] = "mode-description";

    var emptyProps = { style: styleOf(model[EMPTY_STYLE]) };
    emptyProps[PART_ATTR] = EMPTY_PART;

    var groupProps = {
      className: HOST_CLASS + "-group",
      style: styleOf(model[GROUP_STYLE])
    };
    groupProps[PART_ATTR] = MODE_GROUP_PART;

    return element(
      "fieldset",
      groupProps,
      element("legend", null, text(model[MODE_GROUP_TITLE])),
      element("div", descProps, text(model[MODE_DESCRIPTION_TEXT])),
      element(
        "div",
        scrollProps,
        published.length === 0
          ? element("div", emptyProps, text(model[EMPTY_TEXT]))
          : published.map(function (row, at) {
              return element(ExchangeRow, { row: row, at: at, key: String(at) });
            })
      )
    );
  }

  function Panel(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var hostProps = { className: HOST_CLASS };
    hostProps[PART_ATTR] = HOST_PART;
    hostProps["aria-label"] = text(model[ACCESSIBLE_NAME]);

    var headerProps = { style: styleOf(model[HEADER_STYLE]) };
    headerProps[PART_ATTR] = HEADER_PART;
    var descProps = { style: styleOf(model[DESCRIPTION_STYLE]) };
    descProps[PART_ATTR] = DESCRIPTION_PART;

    var css = pageCss(model);
    var styleProps = {};
    styleProps[PART_ATTR] = STYLE_PART;

    return element(
      "div",
      hostProps,
      css ? element("style", styleProps, css) : null,
      element("h2", headerProps, text(model[HEADER_TEXT])),
      element("p", descProps, text(model[DESCRIPTION_TEXT])),
      element(ExportGroup, { model: model }),
      element(ModeGroup, { model: model })
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

  // `flushSync` makes the document current before `draw` returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderPanel(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Panel, { model: payload }));
  }

  // Every target already drawn into, redrawn from the state now held.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Panel, { model: held === null ? null : held.model }));
    });
  }

  function forget() {
    held = null;
    panelFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetUsbAuth = setPanel;
  global.acervatorLoadUsbAuth = loadPanel;
  global.acervatorUsbAuth = {
    method: METHOD,
    Panel: Panel,
    ExportGroup: ExportGroup,
    ModeGroup: ModeGroup,
    ExchangeRow: ExchangeRow,
    Lamp: Lamp,
    model: model,
    field: field,
    rows: rows,
    comboItems: comboItems,
    constants: constants,
    declaredFields: declaredFields,
    rowFields: rowFields,
    styleOf: styleOf,
    declarations: declarations,
    stateRules: stateRules,
    stateCss: stateCss,
    pageCss: pageCss,
    alphaBytes: alphaBytes,
    darker: darker,
    length: length,
    refresh: refresh,
    select: select,
    exportKeys: exportKeys,
    verify: verify,
    toggle: toggle,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
