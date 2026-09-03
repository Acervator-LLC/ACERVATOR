// Draws the Indicator Voting Panel from the indicator_panel.state payload.
(function (global) {
  "use strict";

  var METHOD = "indicator_panel.state";

  var ALPHA_UNIT = "alpha_unit";
  var ARROW_ALPHA = "arrow_alpha";
  var BACKGROUND_ALPHA = "background_alpha";
  var BACKGROUND_RGB = "background_rgb";
  var BARS = "bars";
  var BASELINE_RGB = "baseline_rgb";
  var BODY_RADIUS_PX = "body_radius_px";
  var BORDER_ALPHA = "border_alpha";
  var BORDER_RGB = "border_rgb";
  var CELLS = "cells";
  var COLORS = "colors";
  var CONFIDENCE = "confidence";
  var CONTAINER = "container";
  var DIRECTION = "direction";
  var EMPTY_TEXT = "empty_text";
  var FILL_ALPHA = "fill_alpha";
  var FILL_RGB = "fill_rgb";
  var FRAME_INTERVAL_MS = "frame_interval_ms";
  var GEOMETRY = "geometry";
  var GLOW_ALPHA = "glow_alpha";
  var ARROW_MIN_FRACTION = "arrow_min_fraction";
  var SHINE_MIN_FRACTION = "shine_min_fraction";
  var PERCENT_SCALE = "percent_scale";
  var GRADIENT_ALPHAS = "gradient_alphas";
  var GRADIENT_STOPS = "gradient_stops";
  var HEADER = "header";
  var KIND = "kind";
  var LABEL_RGB = "label_rgb";
  var LERP_FACTOR = "lerp_factor";
  var LOCKS = "locks";
  var MARGINS_PX = "margins_px";
  var MASKED = "masked";
  var MAXIMUM_HEIGHT_PX = "maximum_height_px";
  var MAXIMUM_WIDTH_PX = "maximum_width_px";
  var MINIMUM_HEIGHT_PX = "minimum_height_px";
  var NAME = "name";
  var OPTIONS = "options";
  var OUTLINE_ALPHA = "outline_alpha";
  var PAINT = "paint";
  var PRIVACY = "privacy";
  var RATE_STRIP = "rate_strip";
  var ROWS = "rows";
  var RUNNING = "running";
  var SELECTED_BOT_ID = "selected_bot_id";
  var SELECTOR = "selector";
  var SETTLE_DELTA = "settle_delta";
  var SHINE_END_ALPHA = "shine_end_alpha";
  var SHINE_RGB = "shine_rgb";
  var SHINE_START_ALPHA = "shine_start_alpha";
  var SPACING_PX = "spacing_px";
  var STATE = "state";
  var STALENESS = "staleness";
  var STATUS_TEXT = "status_text";
  var SUMMARY_TEXT = "summary_text";
  var SYMBOLS = "symbols";
  var SYMBOL_TEXT = "symbol_text";
  var TABLES = "tables";
  var TARGETS = "targets";
  var TEXT = "text";
  var TEXT_COLOR = "text_color";
  var TF_LOCK = "tf_lock";
  var TIMEFRAME = "timeframe";
  var TITLES = "titles";
  var TITLE_TEXT = "title_text";
  var TOOLTIP = "tooltip";
  var TOOLTIPS = "tooltips";
  var VALUE = "value";
  var VISIBLE = "visible";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ALPHA_UNIT,
    "alpha_scale",
    BARS,
    "base_kind",
    "bot_timeframes",
    "bus_topics",
    COLORS,
    CONTAINER,
    "direction_symbols",
    "group_colors",
    HEADER,
    "header_tooltips",
    "indicator_cols",
    KIND,
    LOCKS,
    "logger_name",
    "method",
    "no_data",
    PERCENT_SCALE,
    PRIVACY,
    RATE_STRIP,
    "raw_value_indicators",
    "row_a_cols",
    "row_b_cols",
    SELECTED_BOT_ID,
    SELECTOR,
    "selector_placeholder",
    "showing_stored",
    "sim_mode",
    "size_policy",
    STALENESS,
    SUMMARY_TEXT,
    SYMBOL_TEXT,
    TABLES,
    TF_LOCK,
    "timeframe_order",
    "title_heading_property",
    TITLE_TEXT
  ];

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var BODY_CELL_TAG = "td";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var BUTTON_TAG = "button";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var STATE_ATTR = "data-state";
  var ARIA_LABEL = "aria-label";
  var TITLE_ATTR = "title";

  var PANEL_PART = "indicator-panel";
  var HEADER_PART = "indicator-header";
  var TITLE_PART = "indicator-title";
  var SELECTOR_PART = "indicator-bot-selector";
  var DOT_PART = "indicator-privacy-dot";
  var SYMBOL_PART = "indicator-symbol";
  var SUMMARY_PART = "indicator-summary";
  var STALENESS_PART = "indicator-staleness";
  var LOCK_ROW_PART = "indicator-lock-row";
  var LOCK_STATUS_PART = "indicator-lock-status";
  var RATE_PART = "indicator-rate-strip";
  var MINI_PART = "indicator-mini-panel";
  var TABLE_PART = "indicator-table";
  var HEAD_CELL_PART = "indicator-head-cell";
  var BODY_CELL_PART = "indicator-body-cell";
  var BARS_PART = "indicator-bars";
  var BAR_PART = "indicator-bar";
  var BAR_LABEL_PART = "indicator-bar-label";
  var BAR_ARROW_PART = "indicator-bar-arrow";
  var BAR_SHINE_PART = "indicator-bar-shine";
  var BARS_EMPTY_PART = "indicator-bars-empty";
  var LOCKS_PART = "indicator-locks";

  var PX = "px";
  var PERCENT = "%";
  var SPACE = " ";
  var SOLID = "solid";
  var GRADIENT_OPEN = "linear-gradient(to bottom, ";
  var RGBA_OPEN = "rgba(";
  var COMMA_SPACE = ", ";
  var CLOSE = ")";
  var EMPTY = "";
  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var CENTER = "center";
  var RELATIVE = "relative";
  var BOLD = "bold";
  var ZERO = "0";

  var NOT_AN_OBJECT_FAULT = "payload is not an object";
  var MISSING_FIELD_FAULT = "declared field is absent";
  var UNDECLARED_FIELD_FAULT = "field is not declared";
  var ALPHA_FAULT = "alpha byte is outside 0-255";
  var NO_BRIDGE = "no bridge on this page";

  var ALPHA_FLOOR = 0;
  var ALPHA_CEILING = 255;
  var FULL = 1;
  var RGB_CHANNELS = 3;

  var held = null;
  var panelFaults = [];
  var loadFault = null;
  var asked = null;

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

  function text(value) {
    return value === null || value === undefined ? EMPTY : String(value);
  }

  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function number(value, fallback) {
    var found = Number(value);
    return typeof value === "number" && found === found ? found : fallback;
  }

  function copyOf(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }


  // length turns a published number into a CSS pixel value.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  function percentScaleOf(model) {
    return number(isPlainObject(model) ? model[PERCENT_SCALE] : undefined, FULL);
  }

  // A 0-1 fraction as the CSS percentage the payload's own scale names.
  function percent(model, fraction) {
    return String(number(fraction, ALPHA_FLOOR) * percentScaleOf(model)) + PERCENT;
  }

  function whole(model) {
    return percent(model, FULL);
  }

  // -- the one place a Qt colour becomes a CSS colour ------------------

  // Qt's alpha channel is a 0-255 byte and CSS's is a 0-1 fraction, so
  // a published byte is scaled by the payload's own alpha_unit. The Qt
  // style sheets this panel publishes are never copied into CSS.
  function alphaUnitOf(model) {
    return number(isPlainObject(model) ? model[ALPHA_UNIT] : undefined, FULL);
  }

  function cssAlpha(model, byte) {
    return number(byte, ALPHA_CEILING) * alphaUnitOf(model);
  }

  function rgba(model, channels, byte) {
    var parts = Array.isArray(channels) ? channels.slice() : [];
    if (parts.length !== RGB_CHANNELS) {
      return undefined;
    }
    return (
      RGBA_OPEN +
      parts.join(COMMA_SPACE) +
      COMMA_SPACE +
      String(cssAlpha(model, byte)) +
      CLOSE
    );
  }

  function opaque(model, channels) {
    return rgba(model, channels, ALPHA_CEILING);
  }

  // -- reading the payload ---------------------------------------------

  function fault(where, why, found) {
    return { where: where, why: why, found: found };
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        panelFaults.push(fault(name, MISSING_FIELD_FAULT, undefined));
      }
    });
    Object.keys(model).forEach(function (name) {
      if (DECLARED_FIELDS.indexOf(name) < 0) {
        panelFaults.push(fault(name, UNDECLARED_FIELD_FAULT, undefined));
      }
    });
  }

  function checkAlpha(where, byte) {
    var found = number(byte, undefined);
    if (found === undefined) {
      return;
    }
    if (found < ALPHA_FLOOR || found > ALPHA_CEILING) {
      panelFaults.push(fault(where, ALPHA_FAULT, found));
    }
  }

  // Every alpha byte the payload carries, checked against Qt's range so
  // a CSS fraction arriving where a byte belongs is named.
  function checkAlphas(model) {
    checkAlpha(PRIVACY, objectField(model, PRIVACY)[BORDER_ALPHA]);
    checkAlpha(STALENESS, objectField(model, STALENESS)[BACKGROUND_ALPHA]);
    checkAlpha(RATE_STRIP, objectField(model, RATE_STRIP)[BACKGROUND_ALPHA]);
    listField(model, TABLES).forEach(function (table, at) {
      listField(table, ROWS).forEach(function (line) {
        listField(line, CELLS).forEach(function (cell) {
          if (owns(cell, FILL_ALPHA)) {
            checkAlpha(TABLES + String(at), cell[FILL_ALPHA]);
          }
        });
      });
    });
  }

  // -- the components ---------------------------------------------------

  function boxStyle(margins, gap, direction) {
    var style = { display: FLEX, flexDirection: direction };
    var sides = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];
    (Array.isArray(margins) ? margins : []).forEach(function (one, at) {
      if (at < sides.length) {
        style[sides[at]] = length(one);
      }
    });
    if (gap !== undefined && gap !== null) {
      style.gap = length(gap);
    }
    return style;
  }

  function Title(props) {
    var titleProps = { style: { fontWeight: BOLD } };
    titleProps[PART_ATTR] = TITLE_PART;
    return element(SPAN_TAG, titleProps, text(props.model[TITLE_TEXT]));
  }

  function PrivacyDot(props) {
    var model = props.model;
    var dot = objectField(model, PRIVACY);
    var size = length(dot.size_px);
    var style = {
      width: size,
      height: size,
      padding: ZERO,
      borderRadius: length(dot.border_radius_px),
      backgroundColor: text(dot[MASKED] ? dot.masked_color : dot.revealed_color),
      borderColor: rgba(model, dot[BORDER_RGB], dot[BORDER_ALPHA]),
      borderStyle: SOLID,
      borderWidth: length(dot.border_width_px)
    };
    var dotProps = { style: style, onClick: props.onToggle };
    dotProps[PART_ATTR] = DOT_PART;
    dotProps[SLOT_ATTR] = DOT_PART;
    dotProps[STATE_ATTR] = text(dot[STATE]);
    dotProps[TITLE_ATTR] = label(dot[TOOLTIP]);
    dotProps[ARIA_LABEL] = label(dot[TOOLTIP]);
    return element(BUTTON_TAG, dotProps, null);
  }

  function BotSelector(props) {
    var model = props.model;
    var drawn = listField(model, SELECTOR).map(function (one, at) {
      return element(
        OPTION_TAG,
        { key: String(at), value: text(one[VALUE]) },
        text(one[TEXT])
      );
    });
    var selectProps = {
      value: text(model[SELECTED_BOT_ID]),
      onChange: props.onSelect,
      style: { minWidth: length(objectField(model, HEADER).selector_minimum_width_px) }
    };
    selectProps[PART_ATTR] = SELECTOR_PART;
    selectProps[SLOT_ATTR] = SELECTOR_PART;
    return element(SELECT_TAG, selectProps, drawn);
  }

  function HeaderRow(props) {
    var model = props.model;
    var head = objectField(model, HEADER);
    var style = boxStyle(head[MARGINS_PX], undefined, ROW);
    style.alignItems = CENTER;
    var headProps = { style: style };
    headProps[PART_ATTR] = HEADER_PART;
    var symbolProps = {};
    symbolProps[PART_ATTR] = SYMBOL_PART;
    var summaryProps = {};
    summaryProps[PART_ATTR] = SUMMARY_PART;
    var spacer = element(DIV_TAG, { key: PANEL_PART, style: { flex: FULL } }, null);
    return element(DIV_TAG, headProps, [
      element(Title, { key: TITLE_PART, model: model }),
      element(SPAN_TAG, { key: HEADER_PART }, text(head.bot_label_text)),
      element(BotSelector, {
        key: SELECTOR_PART,
        model: model,
        onSelect: props.onSelect
      }),
      element(PrivacyDot, {
        key: DOT_PART,
        model: model,
        onToggle: props.onToggle
      }),
      spacer,
      element(SPAN_TAG, symbolProps, text(model[SYMBOL_TEXT])),
      element(SPAN_TAG, summaryProps, text(model[SUMMARY_TEXT]))
    ]);
  }

  function StalenessBanner(props) {
    var model = props.model;
    var band = objectField(model, STALENESS);
    var bandProps = {
      style: {
        color: text(band[TEXT_COLOR]),
        backgroundColor: rgba(model, band[BACKGROUND_RGB], band[BACKGROUND_ALPHA])
      }
    };
    bandProps[PART_ATTR] = STALENESS_PART;
    bandProps[SLOT_ATTR] = STALENESS_PART;
    bandProps.hidden = band[VISIBLE] !== true;
    bandProps[ARIA_LABEL] = label(band.accessible_name);
    bandProps[TITLE_ATTR] = label(band[TOOLTIP]);
    return element(DIV_TAG, bandProps, text(band[TEXT]));
  }

  function LockRow(props) {
    var model = props.model;
    var lock = objectField(model, TF_LOCK);
    var style = boxStyle(lock[MARGINS_PX], undefined, ROW);
    style.alignItems = CENTER;
    var rowProps = { style: style };
    rowProps[PART_ATTR] = LOCK_ROW_PART;
    var drawn = listField(lock, OPTIONS).map(function (one, at) {
      return element(
        OPTION_TAG,
        { key: String(at), value: text(one[VALUE]) },
        text(one[TEXT])
      );
    });
    var selectProps = {
      value: text(lock[VALUE]),
      onChange: props.onLock,
      style: { maxWidth: length(lock[MAXIMUM_WIDTH_PX]) }
    };
    selectProps[PART_ATTR] = LOCK_ROW_PART;
    selectProps[TITLE_ATTR] = label(lock[TOOLTIP]);
    var statusProps = { style: { color: text(lock.status_color) } };
    statusProps[PART_ATTR] = LOCK_STATUS_PART;
    return element(DIV_TAG, rowProps, [
      element(SPAN_TAG, { key: LOCK_ROW_PART }, text(lock.label_text)),
      element(SELECT_TAG, selectProps, drawn),
      element(DIV_TAG, { key: PANEL_PART, style: { flex: FULL } }, null),
      element(SPAN_TAG, statusProps, text(lock[STATUS_TEXT]))
    ]);
  }

  function RateStrip(props) {
    var model = props.model;
    var strip = objectField(model, RATE_STRIP);
    var stripProps = {
      style: {
        color: text(strip[TEXT_COLOR]),
        backgroundColor: rgba(model, strip[BACKGROUND_RGB], strip[BACKGROUND_ALPHA])
      }
    };
    stripProps[PART_ATTR] = RATE_PART;
    stripProps[SLOT_ATTR] = RATE_PART;
    stripProps[ARIA_LABEL] = label(strip.accessible_name);
    stripProps[TITLE_ATTR] = label(strip[TOOLTIP]);
    return element(DIV_TAG, stripProps, text(strip[TEXT]));
  }

  function HeadCell(props) {
    var cellProps = { style: { textAlign: CENTER } };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    cellProps[TITLE_ATTR] = label(props.tooltip);
    cellProps[ARIA_LABEL] = label(props.title);
    return element(HEAD_CELL_TAG, cellProps, text(props.title));
  }

  function BodyCell(props) {
    var model = props.model;
    var cell = props.cell;
    var style = { textAlign: CENTER };
    if (owns(cell, TEXT_COLOR) && cell[TEXT_COLOR] !== null) {
      style.color = text(cell[TEXT_COLOR]);
    }
    if (owns(cell, FILL_RGB)) {
      style.backgroundColor = rgba(model, cell[FILL_RGB], cell[FILL_ALPHA]);
    }
    if (cell.bold === true) {
      style.fontWeight = BOLD;
    }
    var cellProps = { style: style };
    cellProps[PART_ATTR] = BODY_CELL_PART;
    cellProps[STATE_ATTR] = text(cell[KIND]);
    cellProps[TITLE_ATTR] = label(cell[TOOLTIP]);
    return element(BODY_CELL_TAG, cellProps, text(cell[TEXT]));
  }

  function MiniTable(props) {
    var model = props.model;
    var table = props.table;
    var titles = listField(table, TITLES);
    var tooltips = listField(table, TOOLTIPS);
    var head = element(
      HEAD_TAG,
      { key: HEAD_CELL_PART },
      element(
        ROW_TAG,
        null,
        titles.map(function (title, at) {
          return element(HeadCell, {
            key: String(at),
            title: title,
            tooltip: tooltips[at]
          });
        })
      )
    );
    var body = element(
      BODY_TAG,
      { key: BODY_CELL_PART },
      listField(table, ROWS).map(function (line, at) {
        return element(
          ROW_TAG,
          { key: String(at), style: { height: length(table.row_height_px) } },
          listField(line, CELLS).map(function (cell, column) {
            return element(BodyCell, {
              key: String(column),
              model: model,
              cell: cell
            });
          })
        );
      })
    );
    var tableProps = { style: { width: whole(model) } };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[STATE_ATTR] = text(table[KIND]);
    return element(TABLE_TAG, tableProps, [head, body]);
  }

  function barColour(model, bars, one, byte) {
    var table = objectField(bars, COLORS);
    var channels = table[text(one[DIRECTION])];
    return rgba(model, channels, byte);
  }

  function Bar(props) {
    var model = props.model;
    var bars = props.bars;
    var one = props.bar;
    var paint = objectField(bars, PAINT);
    var shape = objectField(bars, GEOMETRY);
    var stops = listField(paint, GRADIENT_STOPS);
    var alphas = listField(paint, GRADIENT_ALPHAS);
    var faces = stops.map(function (stop, at) {
      return (
        barColour(model, bars, one, alphas[at]) + SPACE + percent(model, stop)
      );
    });
    var filled = Math.min(
      Math.max(number(one[CONFIDENCE], ALPHA_FLOOR), ALPHA_FLOOR),
      FULL
    );
    var style = {
      height: percent(model, filled),
      minHeight: length(shape.min_height_px),
      minWidth: length(shape.min_width_px),
      borderRadius: length(shape[BODY_RADIUS_PX]),
      backgroundImage:
        GRADIENT_OPEN + faces.join(COMMA_SPACE) + CLOSE,
      boxShadow:
        ZERO +
        SPACE +
        ZERO +
        SPACE +
        length(shape.glow_radius_px) +
        SPACE +
        barColour(model, bars, one, paint[GLOW_ALPHA]),
      borderStyle: SOLID,
      borderWidth: length(FULL),
      borderColor: barColour(model, bars, one, paint[OUTLINE_ALPHA]),
      position: RELATIVE
    };
    var barProps = { style: style };
    barProps[PART_ATTR] = BAR_PART;
    barProps[STATE_ATTR] = text(one[DIRECTION]);
    barProps[ARIA_LABEL] = label(text(one[NAME]));
    var drawn = [];
    if (filled >= number(shape[SHINE_MIN_FRACTION], FULL)) {
      var shineProps = {
        key: BAR_SHINE_PART,
        style: {
          height: percent(model, number(shape.shine_fraction, ALPHA_FLOOR)),
          borderRadius: length(shape.shine_radius_px),
          backgroundImage:
            GRADIENT_OPEN +
            rgba(model, paint[SHINE_RGB], paint[SHINE_START_ALPHA]) +
            COMMA_SPACE +
            rgba(model, paint[SHINE_RGB], paint[SHINE_END_ALPHA]) +
            CLOSE
        }
      };
      shineProps[PART_ATTR] = BAR_SHINE_PART;
      drawn.push(element(DIV_TAG, shineProps, null));
    }
    if (filled >= number(shape[ARROW_MIN_FRACTION], FULL)) {
      var arrowProps = {
        key: BAR_ARROW_PART,
        style: {
          color: rgba(model, paint[SHINE_RGB], paint[ARROW_ALPHA]),
          textAlign: CENTER
        }
      };
      arrowProps[PART_ATTR] = BAR_ARROW_PART;
      drawn.push(
        element(
          DIV_TAG,
          arrowProps,
          text(objectField(paint, SYMBOLS)[text(one[DIRECTION])])
        )
      );
    }
    return element(DIV_TAG, barProps, drawn);
  }

  function BarsEmpty(props) {
    var model = props.model;
    var bars = props.bars;
    var paint = objectField(bars, PAINT);
    var emptyProps = {
      style: {
        color: opaque(model, paint.empty_text_rgb),
        textAlign: CENTER,
        alignSelf: CENTER,
        margin: AUTO
      }
    };
    emptyProps[PART_ATTR] = BARS_EMPTY_PART;
    return element(DIV_TAG, emptyProps, text(bars[EMPTY_TEXT]));
  }

  function BarLabel(props) {
    var model = props.model;
    var paint = objectField(props.bars, PAINT);
    var labelProps = {
      style: {
        color: opaque(model, paint[LABEL_RGB]),
        textAlign: CENTER,
        fontWeight: BOLD
      }
    };
    labelProps[PART_ATTR] = BAR_LABEL_PART;
    return element(DIV_TAG, labelProps, text(props.bar[NAME]));
  }

  function BarsPane(props) {
    var model = props.model;
    var bars = props.bars;
    var paint = objectField(bars, PAINT);
    var shape = objectField(bars, GEOMETRY);
    var drawn = listField(bars, BARS);
    var style = boxStyle(
      [
        shape.margin_left_px,
        shape.margin_top_px,
        shape.margin_right_px,
        shape.margin_bottom_px
      ],
      shape.gap_px,
      ROW
    );
    style.backgroundColor = opaque(model, paint[BACKGROUND_RGB]);
    style.minHeight = length(bars[MINIMUM_HEIGHT_PX]);
    style.alignItems = "flex-end";
    style.borderBottomStyle = "solid";
    style.borderBottomWidth = length(FULL);
    style.borderBottomColor = opaque(model, paint[BASELINE_RGB]);
    style.overflow = HIDDEN;
    style.flex = FULL;
    var paneProps = { style: style };
    paneProps[PART_ATTR] = BARS_PART;
    paneProps[SLOT_ATTR] = BARS_PART;
    paneProps[ARIA_LABEL] = label(bars.accessible_name);
    paneProps[TITLE_ATTR] = label(bars[TOOLTIP]);
    if (!drawn.length) {
      return element(
        DIV_TAG,
        paneProps,
        element(BarsEmpty, { key: BARS_EMPTY_PART, model: model, bars: bars })
      );
    }
    return element(
      DIV_TAG,
      paneProps,
      drawn.map(function (one, at) {
        return element(
          DIV_TAG,
          {
            key: String(at),
            style: { display: FLEX, flexDirection: COLUMN, flex: FULL }
          },
          [
            element(Bar, { key: BAR_PART, model: model, bars: bars, bar: one }),
            element(BarLabel, { key: BAR_LABEL_PART, model: model, bars: bars, bar: one })
          ]
        );
      })
    );
  }

  function MiniPanel(props) {
    var style = { display: FLEX, flexDirection: COLUMN, flex: FULL, overflow: HIDDEN };
    var paneProps = { style: style };
    paneProps[PART_ATTR] = MINI_PART;
    return element(DIV_TAG, paneProps, [
      element(MiniTable, {
        key: TABLE_PART,
        model: props.model,
        table: props.table
      }),
      element(BarsPane, { key: BARS_PART, model: props.model, bars: props.bars })
    ]);
  }

  function LocksLine(props) {
    var locks = objectField(props.model, LOCKS);
    var lineProps = {
      style: {
        maxHeight: length(locks[MAXIMUM_HEIGHT_PX]),
        overflow: HIDDEN
      }
    };
    lineProps[PART_ATTR] = LOCKS_PART;
    lineProps[SLOT_ATTR] = LOCKS_PART;
    return element(DIV_TAG, lineProps, text(locks[TEXT]));
  }

  function Panel(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var box = objectField(model, CONTAINER);
    var style = boxStyle(box[MARGINS_PX], box[SPACING_PX], COLUMN);
    style.flex = FULL;
    style.overflow = AUTO;
    var panelProps = { style: style };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[SLOT_ATTR] = PANEL_PART;
    var tables = listField(model, TABLES);
    var bars = listField(model, BARS);
    var minis = tables.map(function (table, at) {
      return element(MiniPanel, {
        key: String(at),
        model: model,
        table: table,
        bars: bars[at]
      });
    });
    var drawn = [
      element(HeaderRow, {
        key: HEADER_PART,
        model: model,
        onSelect: props.onSelect,
        onToggle: props.onToggle
      }),
      element(StalenessBanner, { key: STALENESS_PART, model: model })
    ];
    if (model.sim_mode !== true) {
      drawn.push(element(LockRow, { key: LOCK_ROW_PART, model: model, onLock: props.onLock }));
    }
    drawn.push(element(RateStrip, { key: RATE_PART, model: model }));
    drawn = drawn.concat(minis);
    drawn.push(element(LocksLine, { key: LOCKS_PART, model: model }));
    return element(DIV_TAG, panelProps, drawn);
  }

  // -- the animation, counted in frames --------------------------------

  // One frame of the bar animation. The interval belongs to the payload,
  // so a caller reads the delay rather than timing the result.
  function stepBars(bars) {
    var targets = listField(bars, TARGETS);
    var drawn = listField(bars, BARS);
    var factor = number(bars[LERP_FACTOR], ALPHA_FLOOR);
    var delta = number(bars[SETTLE_DELTA], ALPHA_FLOOR);
    var settled = true;
    targets.forEach(function (target, at) {
      if (at >= drawn.length) {
        return;
      }
      var here = number(drawn[at][CONFIDENCE], ALPHA_FLOOR);
      var there = number(target[CONFIDENCE], ALPHA_FLOOR);
      var gap = there - here;
      if (Math.abs(gap) > delta) {
        drawn[at][CONFIDENCE] = here + gap * factor;
        settled = false;
      } else {
        drawn[at][CONFIDENCE] = there;
      }
      drawn[at][DIRECTION] = target[DIRECTION];
    });
    bars[RUNNING] = !settled;
    return settled;
  }

  function frameInterval(at) {
    var bars = listField(payload(), BARS)[at];
    return isPlainObject(bars) ? bars[FRAME_INTERVAL_MS] : undefined;
  }

  function advance(at, frames) {
    if (held === null) {
      return undefined;
    }
    var bars = listField(held.model, BARS)[at];
    if (!isPlainObject(bars)) {
      return undefined;
    }
    var settled = true;
    var count = number(frames, FULL);
    for (var round = 0; round < count; round += FULL) {
      settled = stepBars(bars);
    }
    return settled;
  }

  // -- what the module answers ------------------------------------------

  function report() {
    return {
      held: held === null ? null : copyOf(held.model),
      faults: panelFaults.slice()
    };
  }

  function setPanel(model) {
    if (!isPlainObject(model)) {
      held = null;
      panelFaults = [fault(null, NOT_AN_OBJECT_FAULT, typeof model)];
      return { held: null, faults: panelFaults.slice() };
    }
    held = { model: model };
    panelFaults = [];
    checkFields(model);
    checkAlphas(model);
    return report();
  }

  // loadPanel asks METHOD once, clearing asked so a refusal retries.
  function loadPanel(params) {
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

  function payload() {
    return held === null ? {} : copyOf(held.model);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function tableAt(at) {
    return listField(payload(), TABLES)[at];
  }

  function rowsOf(at) {
    return listField(tableAt(at), ROWS);
  }

  function cellTexts(at) {
    return rowsOf(at).map(function (line) {
      return listField(line, CELLS).map(function (cell) {
        return cell[TEXT];
      });
    });
  }

  function cellFills(at) {
    return rowsOf(at).map(function (line) {
      return listField(line, CELLS).map(function (cell) {
        if (!owns(cell, FILL_RGB)) {
          return undefined;
        }
        return rgba(payload(), cell[FILL_RGB], cell[FILL_ALPHA]);
      });
    });
  }

  function timeframes(at) {
    return rowsOf(at).map(function (line) {
      return line[TIMEFRAME];
    });
  }

  function titlesOf(at) {
    return listField(tableAt(at), TITLES);
  }

  function barsAt(at) {
    return listField(payload(), BARS)[at];
  }

  function barConfidences(at) {
    return listField(barsAt(at), BARS).map(function (one) {
      return one[CONFIDENCE];
    });
  }

  function colourOf(name, byte) {
    var model = payload();
    return rgba(model, objectField(model, COLORS)[name], byte);
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

  function draw(target, node) {
    var root = global.ReactDOM.createRoot(target);
    root.render(node);
    return root;
  }

  function renderPanel(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(Panel, { model: drawn }));
  }

  function forget() {
    held = null;
    panelFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetIndicatorPanel = setPanel;
  global.acervatorLoadIndicatorPanel = loadPanel;
  global.acervatorIndicatorPanel = {
    method: METHOD,
    Panel: Panel,
    HeaderRow: HeaderRow,
    BotSelector: BotSelector,
    PrivacyDot: PrivacyDot,
    StalenessBanner: StalenessBanner,
    LockRow: LockRow,
    RateStrip: RateStrip,
    MiniPanel: MiniPanel,
    MiniTable: MiniTable,
    HeadCell: HeadCell,
    BodyCell: BodyCell,
    BarsPane: BarsPane,
    Bar: Bar,
    BarLabel: BarLabel,
    BarsEmpty: BarsEmpty,
    LocksLine: LocksLine,
    payload: payload,
    declaredFields: declaredFields,
    field: field,
    tableAt: tableAt,
    rowsOf: rowsOf,
    cellTexts: cellTexts,
    cellFills: cellFills,
    timeframes: timeframes,
    titlesOf: titlesOf,
    barsAt: barsAt,
    barConfidences: barConfidences,
    colourOf: colourOf,
    cssAlpha: cssAlpha,
    alphaUnitOf: alphaUnitOf,
    rgba: rgba,
    opaque: opaque,
    frameInterval: frameInterval,
    advance: advance,
    length: length,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
