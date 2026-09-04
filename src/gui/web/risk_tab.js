// Draws the Risk and Capital Management tab from the risk_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "risk_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ALERT_COLUMNS = "alert_columns";
  var ALERT_ROWS = "alert_rows";
  var ASSET_BARS = "asset_bars";
  var BAR = "bar";
  var BAR_MARGINS = "bar_margins";
  var BOTS_STYLE = "bots_style";
  var BOTS_TEXT = "bots_text";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var EXCHANGE_BARS = "exchange_bars";
  var EXPOSURE_STYLE = "exposure_style";
  var EXPOSURE_TEXT = "exposure_text";
  var GAUGE = "gauge";
  var GAUGE_PAINT = "gauge_paint";
  var GROUP_TITLES = "group_titles";
  var PANE_MARGINS = "pane_margins";
  var PEAK_STYLE = "peak_style";
  var PEAK_TEXT = "peak_text";
  var RULE_COLUMNS = "rule_columns";
  var RULE_ROWS = "rule_rows";
  var SPLITTER_HANDLE_WIDTH = "splitter_handle_width";
  var SPLITTER_SIZES = "splitter_sizes";
  var STATUS_STYLE = "status_style";
  var STATUS_TEXT = "status_text";
  var STRETCHES = "stretches";
  var STYLES = "styles";

  // READ_FIELDS is every top-level field this file draws from. A field the
  // payload carries for the Qt side alone is not listed and not reported;
  // the surface parity tests hold the payload's whole shape.
  var READ_FIELDS = [
    ACCESSIBLE_NAME,
    ALERT_COLUMNS,
    ALERT_ROWS,
    ASSET_BARS,
    BAR,
    BAR_MARGINS,
    BOTS_STYLE,
    BOTS_TEXT,
    CONTENT_MARGINS,
    CONTENT_SPACING,
    EXCHANGE_BARS,
    EXPOSURE_STYLE,
    EXPOSURE_TEXT,
    GAUGE,
    GAUGE_PAINT,
    GROUP_TITLES,
    PANE_MARGINS,
    PEAK_STYLE,
    PEAK_TEXT,
    RULE_COLUMNS,
    RULE_ROWS,
    SPLITTER_HANDLE_WIDTH,
    SPLITTER_SIZES,
    STATUS_STYLE,
    STATUS_TEXT,
    STRETCHES,
    STYLES
  ];

  var ALERTS = "alerts";
  var ALIGNMENT = "alignment";
  var ANGLE_UNIT = "angle_unit";
  var ASKED_VALUE = "asked_value";
  var BAND = "band";
  var BAR_STYLE = "bar_style";
  var BOX = "box";
  var COLOR = "color";
  var FAMILY = "family";
  var FORMAT_TEXT = "format_text";
  var GROUP_BOX = "group_box";
  var KIND = "kind";
  var LABEL = "label";
  var LABEL_MIN_WIDTH = "label_min_width";
  var LABEL_STYLE = "label_style";
  var METRICS = "metrics";
  var MINIMUM_SIZE = "minimum_size";
  var PEN_WIDTH = "pen_width";
  var POINT_SIZE = "point_size";
  var RANGE = "range";
  var RECT_SIZE = "rect_size";
  var RULES = "rules";
  var SPAN_ANGLE = "span_angle";
  var START_ANGLE = "start_angle";
  var STEPS = "steps";
  var TEXT = "text";
  var VALUE_ALIGNMENT = "value_alignment";
  var VALUE_MIN_WIDTH = "value_min_width";
  var VALUE_STYLE = "value_style";
  var VALUE_TEXT = "value_text";
  var WEIGHT_VALUE = "weight_value";

  var BAR_FIELDS = [LABEL_MIN_WIDTH, RANGE, VALUE_MIN_WIDTH];
  var GAUGE_FIELDS = [ANGLE_UNIT, MINIMUM_SIZE, VALUE_ALIGNMENT];
  var GAUGE_PAINT_FIELDS = [BAND, RECT_SIZE, STEPS];
  var STRETCH_FIELDS = [ALERTS, BAR, METRICS, RULES];
  var STYLE_FIELDS = [GROUP_BOX];

  var BAG_FIELDS = {};
  BAG_FIELDS[BAR] = BAR_FIELDS;
  BAG_FIELDS[GAUGE] = GAUGE_FIELDS;
  BAG_FIELDS[GAUGE_PAINT] = GAUGE_PAINT_FIELDS;
  BAG_FIELDS[STRETCHES] = STRETCH_FIELDS;
  BAG_FIELDS[STYLES] = STYLE_FIELDS;

  // The step kind the surface gives an arc, as against a painted string.
  var RING_KIND = "arc";
  // The Qt sub-control that paints the filled part of a progress bar.
  var CHUNK_NAME = "chunk";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var NO_BRIDGE = "the preload bridge is not present";

  var PART_ATTR = "data-part";
  var BAND_ATTR = "data-band";
  var LABEL_ATTR = "aria-label";
  var ROLE_ATTR = "role";
  var VALUE_NOW_ATTR = "aria-valuenow";
  var VALUE_MIN_ATTR = "aria-valuemin";
  var VALUE_MAX_ATTR = "aria-valuemax";

  var TAB_PART = "risk-tab";
  var PANE_PART = "risk-pane";
  var SPLIT_PART = "risk-split";
  var HANDLE_PART = "risk-handle";
  var GAUGE_ROW_PART = "risk-gauge-row";
  var GAUGE_PART = "risk-gauge";
  var TRACK_PART = "risk-gauge-track";
  var SWEEP_PART = "risk-gauge-sweep";
  var GAUGE_TEXT_PART = "risk-gauge-text";
  var METRICS_PART = "risk-metrics";
  var METRIC_PART = "risk-metric";
  var GROUP_PART = "risk-group";
  var GROUP_TITLE_PART = "risk-group-title";
  var BAR_PART = "risk-bar";
  var BAR_LABEL_PART = "risk-bar-label";
  var BAR_TRACK_PART = "risk-bar-track";
  var BAR_CHUNK_PART = "risk-bar-chunk";
  var BAR_FORMAT_PART = "risk-bar-format";
  var BAR_VALUE_PART = "risk-bar-value";
  var ALERT_TABLE_PART = "risk-alert-table";
  var RULE_TABLE_PART = "risk-rule-table";
  var HEAD_CELL_PART = "risk-head-cell";
  var ROW_PART = "risk-row";
  var CELL_PART = "risk-cell";
  var SPACER_PART = "risk-spacer";

  var TAB_CLASS = "acervator-risk-tab";

  var DIV_TAG = "div";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var SVG_TAG = "svg";
  var CIRCLE_TAG = "circle";
  var SVG_NAMESPACE = "http://www.w3.org/2000/svg";

  var EMPTY = "";
  var FIELD_SPLIT = ",";
  var PX = "px";
  var PT = "pt";
  var FULL = "100%";
  var FLEX = "flex";
  var BLOCK = "block";
  var NONE = "none";
  var COLUMN = "column";
  var ROW = "row";
  var CENTER = "center";
  var FLEX_START = "flex-start";
  var FLEX_END = "flex-end";
  var RELATIVE = "relative";
  var ABSOLUTE = "absolute";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var COLLAPSE = "collapse";
  var FIXED = "fixed";
  var BORDER_BOX = "border-box";
  var PROGRESS_ROLE = "progressbar";
  var SEPARATOR_ROLE = "separator";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var CLOSE_PAREN = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";
  var ROTATE_OPEN = "rotate(";
  var SCALE_OPEN = "scaleX(";

  // The ring is given this many path units, so a dash length is read in
  // the degrees the surface publishes its angles in.
  var FULL_TURN_DEGREES = 360;
  // Qt's arc box is square, so half its width reaches the circle's centre.
  var CENTRE_SHARE = 0.5;
  var ZERO = 0;
  var NOT_FOUND = -1;

  var BOX_LEFT = 0;
  var BOX_TOP = 1;
  var BOX_WIDTH = 2;
  var BOX_HEIGHT = 3;

  var RANGE_LOW = 0;
  var RANGE_HIGH = 1;

  var MARGIN_LEFT = 0;
  var MARGIN_TOP = 1;
  var MARGIN_RIGHT = 2;
  var MARGIN_BOTTOM = 3;

  var WIDTH_AT = 0;
  var HEIGHT_AT = 1;

  var ASSET_TITLE_AT = 0;
  var EXCHANGE_TITLE_AT = 1;
  var ALERTS_TITLE_AT = 2;
  var RULES_TITLE_AT = 3;

  var LEFT_PANE_AT = 0;
  var RIGHT_PANE_AT = 1;

  var held = null;
  var tabFaults = [];
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

  // A Qt sub-control such as `QProgressBar::chunk` paints its own element
  // here, so its block is read apart from the widget's own.
  function subControlStyle(sheet, name) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (String(rule.selector).indexOf(name) === NOT_FOUND) {
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

  // Qt reads a painted font in points, which CSS also carries natively.
  function points(value) {
    return isNumber(value) ? String(value) + PT : undefined;
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

  // -- the drawdown gauge ------------------------------------------------

  function degreesOf(angle, unit) {
    if (!isNumber(angle) || !isNumber(unit) || unit === ZERO) {
      return undefined;
    }
    return angle / unit;
  }

  // An SVG dash starts at three o'clock and runs clockwise; Qt counts its
  // start angle the other way round, so the ring turns by its negation.
  function ringRotation(startDegrees) {
    return startDegrees === undefined ? undefined : -startDegrees;
  }

  // The ring carries FULL_TURN_DEGREES path units, so the drawn run and
  // the gap after it are both written in degrees.
  function ringDash(spanDegrees) {
    if (spanDegrees === undefined) {
      return undefined;
    }
    var drawn = Math.abs(spanDegrees);
    return String(drawn) + FIELD_SPLIT + String(FULL_TURN_DEGREES - drawn);
  }

  function Ring(props) {
    var step = props.step;
    var box = listField(step, BOX);
    var side = at(box, BOX_WIDTH);
    var radius = isNumber(side) ? side * CENTRE_SHARE : undefined;
    var centreX = isNumber(radius) ? at(box, BOX_LEFT) + radius : undefined;
    var centreY = isNumber(radius) ? at(box, BOX_TOP) + radius : undefined;
    var turn = ringRotation(degreesOf(step[START_ANGLE], props.unit));
    var ringProps = {
      cx: centreX,
      cy: centreY,
      r: radius,
      fill: NONE,
      stroke: colour(step[COLOR]),
      strokeWidth: step[PEN_WIDTH],
      pathLength: FULL_TURN_DEGREES,
      strokeDasharray: ringDash(degreesOf(step[SPAN_ANGLE], props.unit)),
      transform:
        ROTATE_OPEN +
        String(turn) +
        FIELD_SPLIT +
        String(centreX) +
        FIELD_SPLIT +
        String(centreY) +
        CLOSE_PAREN
    };
    ringProps[PART_ATTR] = props.part;
    return element(CIRCLE_TAG, ringProps);
  }

  // Qt aligns a painted string inside the box it was handed, so the box is
  // laid over the gauge and the string placed inside it the same way.
  function GaugeText(props) {
    var step = props.step;
    var box = listField(step, BOX);
    var centred = step[ALIGNMENT] === props.centredAlignment;
    var textProps = {
      style: {
        position: ABSOLUTE,
        left: length(at(box, BOX_LEFT)),
        top: length(at(box, BOX_TOP)),
        width: length(at(box, BOX_WIDTH)),
        height: length(at(box, BOX_HEIGHT)),
        display: FLEX,
        justifyContent: CENTER,
        alignItems: centred ? CENTER : FLEX_START,
        color: colour(step[COLOR]),
        fontFamily: text(step[FAMILY]),
        fontSize: points(step[POINT_SIZE]),
        fontWeight: text(step[WEIGHT_VALUE]),
        pointerEvents: NONE
      }
    };
    textProps[PART_ATTR] = props.part;
    return element(DIV_TAG, textProps, text(step[TEXT]));
  }

  function Gauge(props) {
    var model = props.model;
    var paint = objectField(model, GAUGE_PAINT);
    var gauge = objectField(model, GAUGE);
    var size = listField(gauge, MINIMUM_SIZE);
    var width = at(size, WIDTH_AT);
    var height = at(size, HEIGHT_AT);
    var rings = [];
    var strings = [];
    listField(paint, STEPS).forEach(function (step, index) {
      var key = String(index);
      if (step[KIND] === RING_KIND) {
        rings.push(
          element(Ring, {
            key: key,
            step: step,
            unit: gauge[ANGLE_UNIT],
            part: rings.length ? SWEEP_PART : TRACK_PART
          })
        );
        return;
      }
      strings.push(
        element(GaugeText, {
          key: key,
          step: step,
          part: GAUGE_TEXT_PART,
          centredAlignment: gauge[VALUE_ALIGNMENT]
        })
      );
    });
    var frameProps = {
      style: {
        position: RELATIVE,
        flex: NONE,
        overflow: HIDDEN,
        width: length(width),
        height: length(height)
      }
    };
    frameProps[PART_ATTR] = GAUGE_PART;
    frameProps[BAND_ATTR] = text(paint[BAND]);
    frameProps[LABEL_ATTR] = label(gauge[ACCESSIBLE_NAME]);
    var svgProps = {
      xmlns: SVG_NAMESPACE,
      width: FULL,
      height: FULL,
      style: { position: ABSOLUTE, display: BLOCK },
      viewBox:
        String(ZERO) +
        FIELD_SPLIT +
        String(ZERO) +
        FIELD_SPLIT +
        String(width) +
        FIELD_SPLIT +
        String(height)
    };
    return element(
      DIV_TAG,
      frameProps,
      element(SVG_TAG, svgProps, rings),
      strings
    );
  }

  // -- the metric column -------------------------------------------------

  function Metric(props) {
    var style = styleOf(props.sheet);
    style.flex = NONE;
    var lineProps = { style: style };
    lineProps[PART_ATTR] = METRIC_PART;
    return element(DIV_TAG, lineProps, text(props.words));
  }

  function Spacer() {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = SPACER_PART;
    return element(DIV_TAG, spacerProps);
  }

  function Metrics(props) {
    var model = props.model;
    var columnProps = {
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO }
    };
    columnProps[PART_ATTR] = METRICS_PART;
    return element(
      DIV_TAG,
      columnProps,
      element(Metric, {
        key: STATUS_TEXT,
        words: model[STATUS_TEXT],
        sheet: model[STATUS_STYLE]
      }),
      element(Metric, {
        key: PEAK_TEXT,
        words: model[PEAK_TEXT],
        sheet: model[PEAK_STYLE]
      }),
      element(Metric, {
        key: EXPOSURE_TEXT,
        words: model[EXPOSURE_TEXT],
        sheet: model[EXPOSURE_STYLE]
      }),
      element(Metric, {
        key: BOTS_TEXT,
        words: model[BOTS_TEXT],
        sheet: model[BOTS_STYLE]
      }),
      element(Spacer, { key: METRICS })
    );
  }

  // -- one exposure bar --------------------------------------------------

  // The share of its track the chunk covers, as the factor an x-scale takes.
  function chunkShare(value, low, high) {
    var span = isNumber(low) && isNumber(high) ? high - low : ZERO;
    if (!isNumber(value) || span === ZERO) {
      return undefined;
    }
    return (value - low) / span;
  }

  function Bar(props) {
    var bar = props.bar;
    var limits = props.limits;
    var span = listField(limits, RANGE);
    var sheet = bar[BAR_STYLE];
    var trackStyle = merged(styleOf(sheet), {
      position: RELATIVE,
      flex: AUTO,
      overflow: HIDDEN,
      display: FLEX,
      alignItems: CENTER,
      justifyContent: CENTER
    });
    var share = chunkShare(
      bar[ASKED_VALUE],
      at(span, RANGE_LOW),
      at(span, RANGE_HIGH)
    );
    var chunkStyle = merged(
      {
        position: ABSOLUTE,
        left: String(ZERO),
        top: String(ZERO),
        bottom: String(ZERO),
        width: FULL,
        transformOrigin: String(ZERO),
        transform:
          share === undefined
            ? undefined
            : SCALE_OPEN + String(share) + CLOSE_PAREN
      },
      subControlStyle(sheet, CHUNK_NAME)
    );
    var labelStyle = merged(styleOf(bar[LABEL_STYLE]), {
      minWidth: length(limits[LABEL_MIN_WIDTH]),
      flex: NONE
    });
    var valueStyle = merged(styleOf(bar[VALUE_STYLE]), {
      minWidth: length(limits[VALUE_MIN_WIDTH]),
      flex: NONE,
      display: FLEX,
      alignItems: CENTER,
      justifyContent: FLEX_END
    });
    var rowProps = {
      style: merged(
        { display: FLEX, flexDirection: ROW, alignItems: CENTER, flex: NONE },
        marginsOf(props.margins)
      )
    };
    rowProps[PART_ATTR] = BAR_PART;
    rowProps[LABEL_ATTR] = label(limits[ACCESSIBLE_NAME]);
    var labelProps = { style: labelStyle };
    labelProps[PART_ATTR] = BAR_LABEL_PART;
    var trackProps = { style: trackStyle };
    trackProps[PART_ATTR] = BAR_TRACK_PART;
    trackProps[ROLE_ATTR] = PROGRESS_ROLE;
    trackProps[VALUE_NOW_ATTR] = text(bar[ASKED_VALUE]);
    trackProps[VALUE_MIN_ATTR] = text(at(span, RANGE_LOW));
    trackProps[VALUE_MAX_ATTR] = text(at(span, RANGE_HIGH));
    var chunkProps = { style: chunkStyle };
    chunkProps[PART_ATTR] = BAR_CHUNK_PART;
    var formatProps = { style: { position: RELATIVE } };
    formatProps[PART_ATTR] = BAR_FORMAT_PART;
    var valueProps = { style: valueStyle };
    valueProps[PART_ATTR] = BAR_VALUE_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(DIV_TAG, labelProps, text(bar[LABEL])),
      element(
        DIV_TAG,
        trackProps,
        element(DIV_TAG, chunkProps),
        element(DIV_TAG, formatProps, text(bar[FORMAT_TEXT]))
      ),
      element(DIV_TAG, valueProps, text(bar[VALUE_TEXT]))
    );
  }

  function BarStack(props) {
    var limits = objectField(props.model, BAR);
    var margins = listField(props.model, BAR_MARGINS);
    return props.bars.map(function (bar, index) {
      return element(Bar, {
        key: String(index),
        bar: isPlainObject(bar) ? bar : {},
        limits: limits,
        margins: margins
      });
    });
  }

  // -- a group box -------------------------------------------------------

  function Group(props) {
    var style = merged(styleOf(props.sheet), {
      display: FLEX,
      flexDirection: COLUMN,
      flexGrow: props.stretch,
      minHeight: String(ZERO),
      boxSizing: BORDER_BOX
    });
    var groupProps = { style: style };
    groupProps[PART_ATTR] = GROUP_PART;
    var titleProps = { style: { flex: NONE } };
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    return element(
      DIV_TAG,
      groupProps,
      element(DIV_TAG, titleProps, text(props.title)),
      props.children
    );
  }

  // -- a table -----------------------------------------------------------

  function HeadCell(props) {
    var cellProps = { scope: COLUMN };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    return element(HEAD_CELL_TAG, cellProps, text(props.words));
  }

  function Cell(props) {
    var cell = isPlainObject(props.cell) ? props.cell : {};
    var painted = colour(cell[COLOR]);
    var cellProps = {
      style: {
        color: painted === EMPTY ? undefined : painted,
        textAlign: CENTER
      }
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

  // -- the two panes ------------------------------------------------------

  function LeftPane(props) {
    var model = props.model;
    var titles = listField(model, GROUP_TITLES);
    var sheet = objectField(model, STYLES)[GROUP_BOX];
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
    var rowProps = { style: { display: FLEX, flexDirection: ROW, flex: NONE } };
    rowProps[PART_ATTR] = GAUGE_ROW_PART;
    return element(
      DIV_TAG,
      paneProps,
      element(
        DIV_TAG,
        rowProps,
        element(Gauge, { model: model }),
        element(Metrics, { model: model })
      ),
      element(
        Group,
        { sheet: sheet, title: at(titles, ASSET_TITLE_AT) },
        element(BarStack, { model: model, bars: listField(model, ASSET_BARS) })
      ),
      element(
        Group,
        { sheet: sheet, title: at(titles, EXCHANGE_TITLE_AT) },
        element(BarStack, { model: model, bars: listField(model, EXCHANGE_BARS) })
      ),
      element(Spacer, null)
    );
  }

  function RightPane(props) {
    var model = props.model;
    var titles = listField(model, GROUP_TITLES);
    var stretches = objectField(model, STRETCHES);
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
    return element(
      DIV_TAG,
      paneProps,
      element(
        Group,
        {
          sheet: sheet,
          title: at(titles, ALERTS_TITLE_AT),
          stretch: stretches[ALERTS]
        },
        element(Table, {
          part: ALERT_TABLE_PART,
          columns: listField(model, ALERT_COLUMNS),
          rows: listField(model, ALERT_ROWS)
        })
      ),
      element(
        Group,
        {
          sheet: sheet,
          title: at(titles, RULES_TITLE_AT),
          stretch: stretches[RULES]
        },
        element(Table, {
          part: RULE_TABLE_PART,
          columns: listField(model, RULE_COLUMNS),
          rows: listField(model, RULE_ROWS)
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
          element(LeftPane, { model: model })
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
          element(RightPane, { model: model })
        )
      )
    );
  }

  // -- holding one payload ------------------------------------------------

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
        bars:
          listField(model, ASSET_BARS).length +
          listField(model, EXCHANGE_BARS).length,
        rows:
          listField(model, ALERT_ROWS).length + listField(model, RULE_ROWS).length,
        steps: listField(objectField(model, GAUGE_PAINT), STEPS).length
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

  function gaugeSteps() {
    return held === null ? [] : listField(objectField(held.model, GAUGE_PAINT), STEPS);
  }

  function gaugeBand() {
    return bag(GAUGE_PAINT)[BAND];
  }

  function assetBars() {
    return list(ASSET_BARS);
  }

  function exchangeBars() {
    return list(EXCHANGE_BARS);
  }

  function alertRows() {
    return list(ALERT_ROWS);
  }

  function ruleRows() {
    return list(RULE_ROWS);
  }

  function groupTitles() {
    return list(GROUP_TITLES);
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
  }

  global.acervatorSetRiskTab = setTab;
  global.acervatorLoadRiskTab = loadTab;
  global.acervatorRiskTab = {
    method: METHOD,
    Tab: Tab,
    LeftPane: LeftPane,
    RightPane: RightPane,
    Gauge: Gauge,
    Ring: Ring,
    GaugeText: GaugeText,
    Metrics: Metrics,
    Metric: Metric,
    Spacer: Spacer,
    Group: Group,
    Bar: Bar,
    BarStack: BarStack,
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
    gaugeSteps: gaugeSteps,
    gaugeBand: gaugeBand,
    assetBars: assetBars,
    exchangeBars: exchangeBars,
    alertRows: alertRows,
    ruleRows: ruleRows,
    groupTitles: groupTitles,
    degreesOf: degreesOf,
    ringDash: ringDash,
    ringRotation: ringRotation,
    chunkShare: chunkShare,
    subControlStyle: subControlStyle,
    styleOf: styleOf,
    declarations: declarations,
    stateRules: stateRules,
    variableFor: variableFor,
    colour: colour,
    length: length,
    points: points,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
