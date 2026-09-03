// Draws the opacity pulse driver's whole published state from one payload.
(function (global) {
  "use strict";

  var METHOD = "pulse_manager.state";

  var CSS = "css";
  var STYLE_SHEET_APPLIED = "style_sheet_applied";
  var TIMER = "timer";
  var PHASE_START = "phase_start";
  var PHASE = "phase";
  var PHASE_STEP = "phase_step";
  var OPACITY_MID = "opacity_mid";
  var OPACITY_SWING = "opacity_swing";
  var OPACITY_FLOOR = "opacity_floor";
  var OPACITY_CEILING = "opacity_ceiling";
  var SETTER = "setter";
  var SWALLOWS = "swallows";
  var RUN_CAP = "run_cap";
  var REGISTERED = "registered";
  var APPLIED = "applied";
  var SKIPPED = "skipped";
  var FAILED = "failed";
  var SEEN = "seen";
  var PAINTS = "paints";
  var WIDGETS = "widgets";
  var SIGNALS = "signals";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var METHOD_FIELD = "method";

  // Every top-level name the pulse_manager.state payload carries.
  var DECLARED_FIELDS = [
    ACTIONS,
    APPLIED,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CSS,
    FAILED,
    METHOD_FIELD,
    OPACITY_CEILING,
    OPACITY_FLOOR,
    OPACITY_MID,
    OPACITY_SWING,
    PAINTS,
    PHASE,
    PHASE_START,
    PHASE_STEP,
    REGISTERED,
    RUN_CAP,
    SEEN,
    SETTER,
    SIGNALS,
    SKIPPED,
    STYLE_SHEET_APPLIED,
    SWALLOWS,
    TIMER,
    TIMER_DELAYS_MS,
    TIMERS,
    WIDGETS
  ];

  var DECLARED_BAGS = [ACTIONS, TIMER, TIMERS];

  var DECLARED_LISTS = [
    APPLIED,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    FAILED,
    SEEN,
    SIGNALS,
    SKIPPED,
    TIMER_DELAYS_MS,
    WIDGETS
  ];

  var DECLARED_NUMBERS = [
    OPACITY_CEILING,
    OPACITY_FLOOR,
    OPACITY_MID,
    OPACITY_SWING,
    PHASE,
    PHASE_START,
    PHASE_STEP,
    REGISTERED,
    RUN_CAP
  ];

  var DECLARED_WORDS = [CSS, METHOD_FIELD, SETTER, SWALLOWS];

  var DECLARED_FLAGS = [PAINTS, STYLE_SHEET_APPLIED];

  var NAME = "name";
  var INTERVAL_MS = "interval_ms";
  var ACTIVE = "active";
  var STARTS = "starts";
  var STOPS = "stops";

  // The timer bag's own names, as a list, because a bag would lose their order.
  var TIMER_KEYS = [NAME, INTERVAL_MS, ACTIVE, STARTS, STOPS];

  var TARGET = "target";
  var OPACITIES = "opacities";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_A_NUMBER_FAULT = "not-a-number";
  var NOT_A_WORD_FAULT = "not-a-word";
  var NOT_A_FLAG_FAULT = "not-a-flag";
  var NOT_A_CADENCE_FAULT = "not-a-cadence";
  var DISAGREES_FAULT = "disagrees";
  var OUT_OF_BAND_FAULT = "out-of-band";
  var UNKNOWN_STEP_FAULT = "unknown-step";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var REORDERED_KEY_FAULT = "reordered-key";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var MARKUP_FAULT = "markup";

  var PATH_SPLIT = ".";
  var EMPTY = "";
  var NO_BRIDGE = "the preload bridge is not present";

  var PANEL_CLASS = "acervator-pulse-manager";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var PANEL_PART = "pulse-panel";
  var PAGE_PART = "pulse-page";
  var TIMER_ROW_PART = "timer-row";
  var TIMER_NAME_PART = "timer-name";
  var TIMER_DELAY_PART = "timer-delay";
  var TIMER_ACTIVE_PART = "timer-active";
  var TIMER_STARTS_PART = "timer-starts";
  var TIMER_STOPS_PART = "timer-stops";
  var WAVE_ROW_PART = "wave-row";
  var PHASE_START_PART = "phase-start";
  var PHASE_NOW_PART = "phase-now";
  var PHASE_STEP_PART = "phase-step";
  var FLOOR_PART = "opacity-floor";
  var MID_PART = "opacity-mid";
  var SWING_PART = "opacity-swing";
  var CEILING_PART = "opacity-ceiling";
  var DRIVER_ROW_PART = "driver-row";
  var SETTER_PART = "driver-setter";
  var SWALLOWS_PART = "driver-swallows";
  var PAINTS_PART = "driver-paints";
  var RUN_CAP_PART = "driver-run-cap";
  var REGISTERED_PART = "driver-registered";
  var SHEET_PART = "sheet";
  var TARGET_LIST_PART = "target-list";
  var TARGET_ROW_PART = "target-row";
  var TARGET_NAME_PART = "target-name";
  var TARGET_OPACITY_PART = "target-opacity";
  var APPLIED_LIST_PART = "applied-list";
  var APPLIED_VALUE_PART = "applied-value";
  var SKIPPED_LIST_PART = "skipped-list";
  var SKIPPED_INDEX_PART = "skipped-index";
  var FAILED_LIST_PART = "failed-list";
  var FAILED_INDEX_PART = "failed-index";
  var WIRING_ROW_PART = "wiring-row";
  var ACTION_PART = "action";
  var TIMER_ENTRY_PART = "timer-entry";
  var DELAY_PART = "timer-delay-ms";
  var TOPIC_PART = "bus-topic";
  var SIGNAL_PART = "signal";
  var WIDGET_PART = "widget";
  var CALL_LIST_PART = "call-list";
  var CALL_NAME_PART = "call-name";
  var STEP_LIST_PART = "step-list";
  var STEP_PART = "step";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var APPLIED_ATTR = "data-applied";
  var PAINTS_ATTR = "data-paints";
  var METHOD_ATTR = "data-method";
  var ACTIVE_ATTR = "data-active";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  var DIGITS = "0123456789";
  // MARKUP_OPEN starts a tag a Qt rich-text label would read as formatting.
  var MARKUP_OPEN = "<";

  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

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

  function isNumber(value) {
    return typeof value === NUMBER_KIND && isFinite(value);
  }

  function objectField(model, name) {
    return isPlainObject(model) && isPlainObject(model[name]) ? model[name] : {};
  }

  function listField(model, name) {
    return isPlainObject(model) && Array.isArray(model[name]) ? model[name] : [];
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  function note(where, name, kind, detail) {
    panelFaults.push(fault(where, name, kind, detail));
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function carries(value, mark) {
    return String(value).indexOf(mark) >= ZERO;
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === STRING_KIND &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  // True for a key a browser lists before every worded key of the same bag.
  function isReorderedKey(key) {
    var printed = String(key);
    if (!printed.length) {
      return false;
    }
    var digitsOnly = true;
    printed.split(EMPTY).forEach(function (letter) {
      if (DIGITS.indexOf(letter) < ZERO) {
        digitsOnly = false;
      }
    });
    return digitsOnly;
  }

  function model() {
    return held === null ? null : held.model;
  }

  function timerBag() {
    return objectField(model(), TIMER);
  }

  function seenRows() {
    return listField(model(), SEEN);
  }

  function opacitiesOf(row) {
    return isPlainObject(row) && Array.isArray(row[OPACITIES]) ? row[OPACITIES] : [];
  }

  function lastOpacity(row) {
    var values = opacitiesOf(row);
    return values.length ? values[values.length - STEP] : undefined;
  }

  // The cadence the payload publishes, in milliseconds, or nothing readable.
  function cadence() {
    var value = timerBag()[INTERVAL_MS];
    return isNumber(value) && value > ZERO ? value : undefined;
  }

  function seenNames() {
    return seenRows().map(function (row) {
      return isPlainObject(row) ? row[TARGET] : row;
    });
  }

  // One row found by its own name, never by where it sits.
  function rowNamed(wanted) {
    var found;
    seenRows().forEach(function (row) {
      if (found === undefined && isPlainObject(row) && row[TARGET] === wanted) {
        found = row;
      }
    });
    return found;
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        note(null, name, MISSING_FAULT, undefined);
        return;
      }
      if (found[name] === null) {
        note(null, name, NULL_FAULT, undefined);
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        note(null, name, NOT_A_BAG_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_NUMBERS.forEach(function (name) {
      if (owns(found, name) && !isNumber(found[name])) {
        note(null, name, NOT_A_NUMBER_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_WORDS.forEach(function (name) {
      if (owns(found, name) && typeof found[name] !== STRING_KIND) {
        note(null, name, NOT_A_WORD_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_FLAGS.forEach(function (name) {
      if (owns(found, name) && typeof found[name] !== BOOLEAN_KIND) {
        note(null, name, NOT_A_FLAG_FAULT, kindOf(found[name]));
      }
    });
  }

  // The delay is read three ways, and a disagreement between them is a fault.
  function checkCadence(found) {
    var bag = objectField(found, TIMER);
    TIMER_KEYS.forEach(function (key) {
      if (!owns(bag, key)) {
        note(TIMER, key, MISSING_FAULT, undefined);
      }
    });
    var delay = bag[INTERVAL_MS];
    if (!isNumber(delay) || delay <= ZERO) {
      note(TIMER, INTERVAL_MS, NOT_A_CADENCE_FAULT, kindOf(delay));
      return;
    }
    var named = objectField(found, TIMERS)[bag[NAME]];
    if (named !== delay) {
      note(TIMERS, bag[NAME], DISAGREES_FAULT, [named, delay]);
    }
    var listed = listField(found, TIMER_DELAYS_MS);
    if (listed.length !== Object.keys(objectField(found, TIMERS)).length) {
      note(TIMER_DELAYS_MS, TIMERS, DISAGREES_FAULT, [
        listed.length,
        Object.keys(objectField(found, TIMERS)).length
      ]);
    }
    if (listed[ZERO] !== delay) {
      note(TIMER_DELAYS_MS, INTERVAL_MS, DISAGREES_FAULT, [listed[ZERO], delay]);
    }
  }

  // Both lengths are counted before either list is paired with the other.
  function checkCounts(found) {
    var rows = listField(found, SEEN);
    var declared = found[REGISTERED];
    if (isNumber(declared) && declared !== rows.length) {
      note(REGISTERED, SEEN, DISAGREES_FAULT, [declared, rows.length]);
    }
    var handed = ZERO;
    rows.forEach(function (row) {
      handed += opacitiesOf(row).length;
    });
    var values = listField(found, APPLIED);
    if (values.length !== handed) {
      note(APPLIED, SEEN, DISAGREES_FAULT, [values.length, handed]);
    }
  }

  function checkBand(found) {
    var floor = found[OPACITY_FLOOR];
    var ceiling = found[OPACITY_CEILING];
    if (!isNumber(floor) || !isNumber(ceiling)) {
      return;
    }
    function judge(where, at, value) {
      if (!isNumber(value) || value < floor || value > ceiling) {
        note(where, at, OUT_OF_BAND_FAULT, value);
      }
    }
    listField(found, APPLIED).forEach(function (value, at) {
      judge(APPLIED, at, value);
    });
    listField(found, SEEN).forEach(function (row, at) {
      opacitiesOf(row).forEach(function (value) {
        judge(SEEN, at, value);
      });
    });
  }

  function checkSteps(found) {
    var declared = listField(found, CALL_NAMES);
    listField(found, CALLS).forEach(function (one, at) {
      if (declared.indexOf(one) < ZERO) {
        note(CALLS, at, UNKNOWN_STEP_FAULT, one);
      }
    });
  }

  function checkNames(found) {
    var seenAlready = [];
    listField(found, SEEN).forEach(function (row, at) {
      var name = isPlainObject(row) ? row[TARGET] : row;
      if (seenAlready.indexOf(name) >= ZERO) {
        note(SEEN, at, DUPLICATE_NAME_FAULT, name);
      }
      seenAlready.push(name);
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          note(name, key, REORDERED_KEY_FAULT, undefined);
        }
      });
    });
  }

  function checkStrings(found) {
    walkOf(found, function (path, value) {
      if (isSwappedAlpha(value)) {
        note(path, null, SWAPPED_ALPHA_FAULT, value);
      }
      if (typeof value === STRING_KIND && carries(value, MARKUP_OPEN)) {
        note(path, null, MARKUP_FAULT, value);
      }
    });
  }

  function walkOf(node, visit) {
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          visit(inner, one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, bag) {
      Object.keys(bag).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        visit(path, bag[name]);
        descend(path, bag[name]);
      });
    }
    if (isPlainObject(node)) {
      walk(EMPTY, node);
    }
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // Cell draws one published value as characters under its own part name.
  function Cell(props) {
    var cellProps = { className: PANEL_CLASS, key: props.part };
    cellProps[PART_ATTR] = props.part;
    if (props.name !== undefined) {
      cellProps[NAME_ATTR] = text(props.name);
    }
    if (props.at !== undefined) {
      cellProps[INDEX_ATTR] = text(props.at);
      cellProps.key = props.part + PATH_SPLIT + String(props.at);
    }
    if (props.count !== undefined) {
      cellProps[COUNT_ATTR] = text(props.count);
    }
    if (props.opacity !== undefined) {
      cellProps.style = { opacity: text(props.opacity) };
    }
    return element(SPAN_TAG, cellProps, text(props.value));
  }

  function group(part, drawn, extra) {
    var groupProps = { className: PANEL_CLASS, key: part };
    groupProps[PART_ATTR] = part;
    Object.keys(extra || {}).forEach(function (name) {
      groupProps[name] = extra[name];
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function TimerRow(props) {
    var bag = objectField(props.model, TIMER);
    return group(TIMER_ROW_PART, [
      element(Cell, { key: TIMER_NAME_PART, part: TIMER_NAME_PART, value: bag[NAME] }),
      element(Cell, { key: TIMER_DELAY_PART, part: TIMER_DELAY_PART, value: bag[INTERVAL_MS] }),
      element(Cell, { key: TIMER_ACTIVE_PART, part: TIMER_ACTIVE_PART, value: bag[ACTIVE] }),
      element(Cell, { key: TIMER_STARTS_PART, part: TIMER_STARTS_PART, value: bag[STARTS] }),
      element(Cell, { key: TIMER_STOPS_PART, part: TIMER_STOPS_PART, value: bag[STOPS] })
    ]);
  }

  function WaveRow(props) {
    var found = props.model;
    return group(WAVE_ROW_PART, [
      element(Cell, { key: PHASE_START_PART, part: PHASE_START_PART, value: found[PHASE_START] }),
      element(Cell, { key: PHASE_NOW_PART, part: PHASE_NOW_PART, value: found[PHASE] }),
      element(Cell, { key: PHASE_STEP_PART, part: PHASE_STEP_PART, value: found[PHASE_STEP] }),
      element(Cell, { key: FLOOR_PART, part: FLOOR_PART, value: found[OPACITY_FLOOR] }),
      element(Cell, { key: MID_PART, part: MID_PART, value: found[OPACITY_MID] }),
      element(Cell, { key: SWING_PART, part: SWING_PART, value: found[OPACITY_SWING] }),
      element(Cell, { key: CEILING_PART, part: CEILING_PART, value: found[OPACITY_CEILING] })
    ]);
  }

  function DriverRow(props) {
    var found = props.model;
    return group(DRIVER_ROW_PART, [
      element(Cell, { key: SETTER_PART, part: SETTER_PART, value: found[SETTER] }),
      element(Cell, { key: SWALLOWS_PART, part: SWALLOWS_PART, value: found[SWALLOWS] }),
      element(Cell, { key: PAINTS_PART, part: PAINTS_PART, value: found[PAINTS] }),
      element(Cell, { key: RUN_CAP_PART, part: RUN_CAP_PART, value: found[RUN_CAP] }),
      element(Cell, { key: REGISTERED_PART, part: REGISTERED_PART, value: found[REGISTERED] })
    ]);
  }

  // The sheet is drawn beside the flag saying nothing applied it.
  function Sheet(props) {
    var found = props.model;
    var sheetProps = { className: PANEL_CLASS, key: SHEET_PART };
    sheetProps[PART_ATTR] = SHEET_PART;
    sheetProps[APPLIED_ATTR] = text(found[STYLE_SHEET_APPLIED]);
    return element(SPAN_TAG, sheetProps, text(found[CSS]));
  }

  function TargetRow(props) {
    var row = props.row;
    var values = opacitiesOf(row);
    var drawn = [
      element(Cell, {
        part: TARGET_NAME_PART,
        value: isPlainObject(row) ? row[TARGET] : row
      })
    ];
    values.forEach(function (one, at) {
      drawn.push(
        element(Cell, { key: TARGET_OPACITY_PART, part: TARGET_OPACITY_PART, at: at, value: one, opacity: one })
      );
    });
    var extra = {};
    extra[NAME_ATTR] = text(isPlainObject(row) ? row[TARGET] : row);
    extra[INDEX_ATTR] = text(props.at);
    extra[COUNT_ATTR] = text(values.length);
    extra.key = TARGET_ROW_PART + PATH_SPLIT + String(props.at);
    extra.style = { opacity: text(lastOpacity(row)) };
    return group(TARGET_ROW_PART, drawn, extra);
  }

  function TargetList(props) {
    var found = props.model;
    var rows = listField(found, SEEN);
    var extra = {};
    extra[COUNT_ATTR] = text(found[REGISTERED]);
    return group(
      TARGET_LIST_PART,
      rows.map(function (row, at) {
        return element(TargetRow, {
          key: TARGET_ROW_PART + PATH_SPLIT + String(at),
          row: row,
          at: at
        });
      }),
      extra
    );
  }

  function ValueList(props) {
    var values = listField(props.model, props.field);
    var extra = {};
    extra[COUNT_ATTR] = text(values.length);
    return group(
      props.part,
      values.map(function (one, at) {
        return element(Cell, {
          key: props.cell + PATH_SPLIT + String(at),
          part: props.cell,
          at: at,
          value: one,
          opacity: props.paint ? one : undefined
        });
      }),
      extra
    );
  }

  function BagList(props) {
    var bag = objectField(props.model, props.field);
    var keys = Object.keys(bag);
    var extra = {};
    extra[COUNT_ATTR] = text(keys.length);
    return group(
      props.part,
      keys.map(function (key, at) {
        return element(Cell, {
          key: props.cell + PATH_SPLIT + String(at),
          part: props.cell,
          at: at,
          name: key,
          value: bag[key]
        });
      }),
      extra
    );
  }

  function WiringRow(props) {
    var found = props.model;
    return group(WIRING_ROW_PART, [
      element(BagList, {
        key: ACTIONS,
        model: found,
        field: ACTIONS,
        part: ACTIONS,
        cell: ACTION_PART
      }),
      element(BagList, {
        key: TIMERS,
        model: found,
        field: TIMERS,
        part: TIMERS,
        cell: TIMER_ENTRY_PART
      }),
      element(ValueList, {
        key: TIMER_DELAYS_MS,
        model: found,
        field: TIMER_DELAYS_MS,
        part: TIMER_DELAYS_MS,
        cell: DELAY_PART
      }),
      element(ValueList, {
        key: BUS_TOPICS,
        model: found,
        field: BUS_TOPICS,
        part: BUS_TOPICS,
        cell: TOPIC_PART
      }),
      element(ValueList, {
        key: SIGNALS,
        model: found,
        field: SIGNALS,
        part: SIGNALS,
        cell: SIGNAL_PART
      }),
      element(ValueList, {
        key: WIDGETS,
        model: found,
        field: WIDGETS,
        part: WIDGETS,
        cell: WIDGET_PART
      })
    ]);
  }

  function Panel(props) {
    var found = props.model;
    if (!isPlainObject(found)) {
      return null;
    }
    var extra = {};
    extra.id = props.id;
    extra[METHOD_ATTR] = text(found[METHOD_FIELD]);
    extra[PAINTS_ATTR] = text(found[PAINTS]);
    extra[ACTIVE_ATTR] = text(objectField(found, TIMER)[ACTIVE]);
    return group(
      PANEL_PART,
      [
        element(TimerRow, { key: TIMER_ROW_PART, model: found }),
        element(WaveRow, { key: WAVE_ROW_PART, model: found }),
        element(DriverRow, { key: DRIVER_ROW_PART, model: found }),
        element(Sheet, { key: SHEET_PART, model: found }),
        element(TargetList, { key: TARGET_LIST_PART, model: found }),
        element(ValueList, {
          key: APPLIED_LIST_PART,
          model: found,
          field: APPLIED,
          part: APPLIED_LIST_PART,
          cell: APPLIED_VALUE_PART,
          paint: true
        }),
        element(ValueList, {
          key: SKIPPED_LIST_PART,
          model: found,
          field: SKIPPED,
          part: SKIPPED_LIST_PART,
          cell: SKIPPED_INDEX_PART
        }),
        element(ValueList, {
          key: FAILED_LIST_PART,
          model: found,
          field: FAILED,
          part: FAILED_LIST_PART,
          cell: FAILED_INDEX_PART
        }),
        element(WiringRow, { key: WIRING_ROW_PART, model: found }),
        element(ValueList, {
          key: CALL_LIST_PART,
          model: found,
          field: CALL_NAMES,
          part: CALL_LIST_PART,
          cell: CALL_NAME_PART
        }),
        element(ValueList, {
          key: STEP_LIST_PART,
          model: found,
          field: CALLS,
          part: STEP_LIST_PART,
          cell: STEP_PART
        })
      ],
      extra
    );
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts the fields, targets and steps declared against those held.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        bags: DECLARED_BAGS.length,
        lists: DECLARED_LISTS.length,
        steps: listField(found, CALL_NAMES).length,
        targets: isNumber(found[REGISTERED]) ? found[REGISTERED] : null,
        cadence_ms: cadence() === undefined ? null : cadence()
      },
      held: {
        fields: heldFieldCount(found),
        steps: listField(found, CALLS).length,
        targets: listField(found, SEEN).length,
        applied: listField(found, APPLIED).length,
        skipped: listField(found, SKIPPED).length,
        failed: listField(found, FAILED).length
      },
      faults: panelFaults.slice()
    };
  }

  function setPulse(found) {
    if (!isPlainObject(found)) {
      held = null;
      panelFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: panelFaults.slice() };
    }
    held = { model: found };
    panelFaults = [];
    checkFields(found);
    checkCadence(found);
    checkCounts(found);
    checkBand(found);
    checkSteps(found);
    checkNames(found);
    checkBagOrder(found);
    checkStrings(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadPulse(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (found) {
        loadFault = null;
        setPulse(found);
        return found;
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

  function declaredNames() {
    return DECLARED_FIELDS.slice();
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

  function bagKeys(name) {
    return Object.keys(bag(name));
  }

  function timerKeys() {
    return Object.keys(timerBag());
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function steps() {
    return list(CALLS);
  }

  function appliedValues() {
    return list(APPLIED);
  }

  function opacitiesFor(wanted) {
    var row = rowNamed(wanted);
    return row === undefined ? [] : opacitiesOf(row).slice();
  }

  function kinds() {
    var found = {};
    walkOf(model(), function (path, value) {
      found[path] = kindOf(value);
    });
    return found;
  }

  // Every path whose value is not a word, number, flag, list, bag or null.
  function notPlainData() {
    var found = [];
    walkOf(model(), function (path, value) {
      var kind = kindOf(value);
      var plain =
        kind === NULL_FAULT ||
        kind === STRING_KIND ||
        kind === NUMBER_KIND ||
        kind === BOOLEAN_KIND ||
        isPlainObject(value) ||
        Array.isArray(value);
      if (!plain) {
        found.push({ path: path, kind: kind });
      }
    });
    return found;
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

  // A payload given here is set first, so every drawn piece reads one model.
  function renderPulse(target, found) {
    if (isPlainObject(found)) {
      setPulse(found);
    }
    return draw(target, element(Panel, { model: model() }));
  }

  // The named empty space the window left for this panel, or root itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== FUNCTION_KIND) {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === PAGE_PART) {
      return root;
    }
    if (typeof root.querySelector !== FUNCTION_KIND) {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE
    );
  }

  function fill(root, found) {
    var space = spaceIn(root);
    return space === null ? null : renderPulse(space, found);
  }

  function forget() {
    held = null;
    panelFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetPulse = setPulse;
  global.acervatorLoadPulse = loadPulse;
  global.acervatorPulseManager = {
    method: METHOD,
    spacePart: PAGE_PART,
    Panel: Panel,
    TimerRow: TimerRow,
    WaveRow: WaveRow,
    DriverRow: DriverRow,
    Sheet: Sheet,
    TargetList: TargetList,
    WiringRow: WiringRow,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    timerKeys: timerKeys,
    cadence: cadence,
    seenNames: seenNames,
    opacitiesFor: opacitiesFor,
    callNames: callNames,
    steps: steps,
    appliedValues: appliedValues,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPulse: renderPulse,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
