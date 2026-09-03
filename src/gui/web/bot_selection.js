// Draws the bot-table selection decision from the bot_selection.plan payload.
(function (global) {
  "use strict";

  var METHOD = "bot_selection.plan";

  var SELECTION = "selection";
  var BOT_IDS = "bot_ids";
  var FILLED_ROWS = "filled_rows";
  var PLAN = "plan";

  // Every top-level name the bot_selection.plan payload carries.
  var DECLARED_FIELDS = [BOT_IDS, FILLED_ROWS, PLAN, SELECTION];
  var DECLARED_BAGS = [PLAN, SELECTION];
  var DECLARED_LISTS = [BOT_IDS, FILLED_ROWS];

  var ANCHOR_COLUMN = "anchor_column";
  var CLEARED_ROW = "cleared_row";
  var CLEARED_COLUMN = "cleared_column";
  var REANCHOR_SILENT = "reanchor_blocks_signals";
  var SELECT_SILENT = "select_for_bot_blocks_signals";

  // Every name the selection bag carries, in the order the surface wrote it.
  var SELECTION_NAMES = [
    ANCHOR_COLUMN,
    CLEARED_ROW,
    CLEARED_COLUMN,
    REANCHOR_SILENT,
    SELECT_SILENT
  ];

  var ACTION = "action";
  var TARGET_ROW = "target_row";
  var BLOCK_SIGNALS = "block_signals";
  var READS = "reads";
  var CALLS = "calls";

  // Every name the plan bag carries, in the order the surface wrote it.
  var PLAN_NAMES = [ACTION, TARGET_ROW, BLOCK_SIGNALS, READS, CALLS];
  var PLAN_LISTS = [READS, CALLS];

  // Token names this module reads; each names a value, never spells one.
  var PANEL_FILL = "SURFACE_1";
  var ROW_FILL = "SURFACE_2";
  var CHOSEN_FILL = "MENU_ITEM_SELECTED";
  var CHOSEN_EDGE = "PRIMARY";
  var NAME_INK = "TEXT_HIGH";
  var ARGUMENT_INK = "TEXT_MED";
  var UNREADABLE_FILL = "MAIN_HIGHLIGHT_AMBER";
  var UNREADABLE_INK = "MAIN_HIGHLIGHT_AMBER_TEXT";
  var NAME_WEIGHT = "WEIGHT_BOLD";
  var ARGUMENT_WEIGHT = "WEIGHT_REGULAR";
  var ROW_HEIGHT = "TARGET_COMFORTABLE";
  var ROW_PAD = "SPACE_XS";
  var EDGE_WIDTH = "FOCUS_RING_WIDTH";

  var COLOUR_TOKENS = [
    PANEL_FILL,
    ROW_FILL,
    CHOSEN_FILL,
    CHOSEN_EDGE,
    NAME_INK,
    ARGUMENT_INK,
    UNREADABLE_FILL,
    UNREADABLE_INK
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_A_ROW_FAULT = "not-a-row";
  var NOT_A_CALL_FAULT = "not-a-call";
  var BEYOND_THE_FLEET_FAULT = "beyond-the-fleet";
  var REPEATED_ROW_FAULT = "repeated-row";
  var CHOSEN_ABSENT_FAULT = "chosen-row-absent";
  var CHOSEN_UNFILLED_FAULT = "chosen-row-unfilled";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var EQUAL_CHANNELS_FAULT = "three-equal-channels";
  var REORDERED_KEY_FAULT = "reordered-key";

  var TOKEN_AT = "token:";
  var ROW_AT = "row:";
  var CALL_AT = "call:";
  var READ_AT = "read:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  var PANEL_CLASS = "acervator-bot-selection";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var PANEL_PART = "bot-selection";
  var RULE_PART = "selection-rule";
  var ROW_PART = "selection-row";
  var ORPHAN_PART = "selection-orphan";
  var READ_PART = "selection-read";
  var CALL_PART = "selection-call";
  var NAME_PART = "step-name";
  var ARGUMENT_PART = "step-argument";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var VALUE_ATTR = "data-value";
  var KIND_ATTR = "data-kind";
  var BOT_ATTR = "data-bot";
  var ROW_ATTR = "data-row";
  var FILLED_ATTR = "data-filled";
  var CHOSEN_ATTR = "data-chosen";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var ACTION_ATTR = "data-action";
  var TARGET_ATTR = "data-target-row";
  var SILENT_ATTR = "data-block-signals";
  var BOT_COUNT_ATTR = "data-bot-count";
  var FILLED_COUNT_ATTR = "data-filled-count";
  var READ_COUNT_ATTR = "data-read-count";
  var CALL_COUNT_ATTR = "data-call-count";
  var FAULT_COUNT_ATTR = "data-fault-count";
  var ARIA_LABEL = "aria-label";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var PX = "px";
  var SOLID = "solid";
  var BLOCK = "block";
  var TRUE_WORD = String(true);
  var FALSE_WORD = String(false);

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;
  var CHANNEL_WIDTH = "aa".length;
  var SHORT_LENGTH = HEX_MARK.length + "abc".length;

  // A key made only of digits is the key a browser moves to the front.
  var DIGITS = "0123456789";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var CHANNELS = STEP + STEP + STEP;

  var held = null;
  var planFaults = [];
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

  function objectField(model, name) {
    return isPlainObject(model) && isPlainObject(model[name]) ? model[name] : {};
  }

  function listField(model, name) {
    return isPlainObject(model) && Array.isArray(model[name]) ? model[name] : [];
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  // Returns String(value), or undefined for null and undefined.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // The printed form of a string or a number, undefined for anything else.
  function readable(value) {
    var kind = kindOf(value);
    return kind === "string" || kind === "number" ? String(value) : undefined;
  }

  function labelOf(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function flag(value) {
    return value ? TRUE_WORD : FALSE_WORD;
  }

  // A whole finite number is the only value that names a table row.
  function isRowNumber(value) {
    return (
      typeof value === "number" &&
      isFinite(value) &&
      Math.floor(value) === value
    );
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === "string" &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  // True for a colour whose channels are equal, where a swap would not show.
  function isEqualChannels(value) {
    if (typeof value !== "string" || value.charAt(ZERO) !== HEX_MARK) {
      return false;
    }
    var body = value.slice(HEX_MARK.length).toLowerCase();
    var channels = [];
    if (value.length === SHORT_LENGTH) {
      body.split(EMPTY).forEach(function (one) {
        channels.push(one + one);
      });
    } else {
      while (body.length >= CHANNEL_WIDTH && channels.length < CHANNELS) {
        channels.push(body.slice(ZERO, CHANNEL_WIDTH));
        body = body.slice(CHANNEL_WIDTH);
      }
    }
    if (channels.length !== CHANNELS) {
      return false;
    }
    return channels[ZERO] === channels[STEP] && channels[STEP] === channels[CHANNELS - STEP];
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

  // acervatorTokens owns every skin value this panel paints with.
  function tokenValue(name) {
    var api = global.acervatorTokens;
    if (!api || typeof api.token !== "function") {
      return undefined;
    }
    return api.token(name);
  }

  // Returns var(--NAME, value), so the page resolves the token by its own name.
  function colour(name) {
    var value = tokenValue(name);
    if (value === null || value === undefined) {
      return undefined;
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  function length(name) {
    var value = tokenValue(name);
    if (typeof value !== "number") {
      return undefined;
    }
    return String(value) + PX;
  }

  function weight(name) {
    var value = tokenValue(name);
    return value === null || value === undefined ? undefined : String(value);
  }

  // Every colour token this panel paints with, by name and by value.
  function colourTokens() {
    return COLOUR_TOKENS.map(function (name) {
      return { name: name, value: tokenValue(name) };
    });
  }

  function model() {
    return held === null ? null : held.model;
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

  function selectionNames() {
    return SELECTION_NAMES.slice();
  }

  function planNames() {
    return PLAN_NAMES.slice();
  }

  // One selection rule by its own name, never by its place in the bag.
  function selectionRule(name) {
    var found = bag(SELECTION);
    return owns(found, name) ? found[name] : undefined;
  }

  // One plan value by its own name, never by its place in the bag.
  function planField(name) {
    var found = bag(PLAN);
    return owns(found, name) ? found[name] : undefined;
  }

  function botNames() {
    return list(BOT_IDS);
  }

  function filledRows() {
    return list(FILLED_ROWS);
  }

  function planList(name) {
    return held === null ? [] : listField(objectField(held.model, PLAN), name).slice();
  }

  function reads() {
    return planList(READS);
  }

  function calls() {
    return planList(CALLS);
  }

  function chosenRow() {
    return planField(TARGET_ROW);
  }

  // Whether one row carries an anchor item, read from filled_rows by value.
  function rowFilled(row) {
    var found = false;
    filledRows().forEach(function (one) {
      if (one === row) {
        found = true;
      }
    });
    return found;
  }

  // Each row paired with its own bot name, so nothing pairs by position.
  function rows() {
    return botNames().map(function (name, at) {
      return {
        row: at,
        bot: name,
        kind: kindOf(name),
        filled: rowFilled(at),
        chosen: chosenRow() === at
      };
    });
  }

  // Every filled row naming no bot, counted apart from the fleet rows.
  function orphanRows() {
    var fleet = botNames().length;
    return filledRows().filter(function (one) {
      return !isRowNumber(one) || one < ZERO || one >= fleet;
    });
  }

  // The name of one call, taken from its first place and nowhere else.
  function stepName(step) {
    return Array.isArray(step) && step.length ? step[ZERO] : undefined;
  }

  // Every argument of one call, after its name, in the order it was written.
  function stepArguments(step) {
    return Array.isArray(step) ? step.slice(STEP) : [];
  }

  // Each named call with the arguments it carries, so no check reads a place.
  function stepsOf(named) {
    return named.map(function (step, at) {
      return {
        index: at,
        name: stepName(step),
        kind: kindOf(step),
        args: stepArguments(step)
      };
    });
  }

  function readSteps() {
    return stepsOf(reads());
  }

  function callSteps() {
    return stepsOf(calls());
  }

  function walkPayload(visit) {
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
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        visit(path, node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
  }

  // The JavaScript type of every value in the payload, by dotted path.
  function kinds() {
    var found = {};
    walkPayload(function (path, value) {
      found[path] = kindOf(value);
    });
    return found;
  }

  // Every path whose value is not a string, number, flag, list, bag or null.
  function notPlainData() {
    var found = [];
    walkPayload(function (path, value) {
      var kind = kindOf(value);
      var plain =
        kind === NULL_FAULT ||
        kind === "string" ||
        kind === "number" ||
        kind === "boolean" ||
        isPlainObject(value) ||
        Array.isArray(value);
      if (!plain) {
        found.push({ path: path, kind: kind });
      }
    });
    return found;
  }

  function checkFields(given) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(given, name)) {
        planFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (given[name] === null) {
        planFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(given, name) && !isPlainObject(given[name])) {
        planFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(given[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(given, name) && !Array.isArray(given[name])) {
        planFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(given[name])));
      }
    });
  }

  function checkNamedBag(given, name, names) {
    var found = objectField(given, name);
    names.forEach(function (one) {
      if (!owns(found, one)) {
        planFaults.push(fault(name, one, MISSING_FAULT, null));
      }
    });
    Object.keys(found).forEach(function (key) {
      if (isReorderedKey(key)) {
        planFaults.push(fault(name, name, REORDERED_KEY_FAULT, key));
      }
    });
  }

  function checkPlanLists(given) {
    var found = objectField(given, PLAN);
    PLAN_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        planFaults.push(fault(PLAN, name, NOT_A_LIST_FAULT, kindOf(found[name])));
      }
    });
    listField(found, READS).forEach(function (step, at) {
      if (!Array.isArray(step)) {
        planFaults.push(
          fault(READ_AT + String(at), READS, NOT_A_CALL_FAULT, kindOf(step))
        );
      }
    });
    listField(found, CALLS).forEach(function (step, at) {
      if (!Array.isArray(step)) {
        planFaults.push(
          fault(CALL_AT + String(at), CALLS, NOT_A_CALL_FAULT, kindOf(step))
        );
      }
    });
  }

  // The fleet and the filled rows are two lists, so each is counted alone.
  function checkRows(given) {
    var fleet = listField(given, BOT_IDS).length;
    var seen = {};
    listField(given, FILLED_ROWS).forEach(function (one, at) {
      if (!isRowNumber(one)) {
        planFaults.push(
          fault(ROW_AT + String(at), FILLED_ROWS, NOT_A_ROW_FAULT, kindOf(one))
        );
        return;
      }
      if (owns(seen, String(one))) {
        planFaults.push(
          fault(ROW_AT + String(at), FILLED_ROWS, REPEATED_ROW_FAULT, one)
        );
      }
      seen[String(one)] = true;
      if (one < ZERO || one >= fleet) {
        planFaults.push(
          fault(ROW_AT + String(at), FILLED_ROWS, BEYOND_THE_FLEET_FAULT, one)
        );
      }
    });
  }

  // The chosen row must name a bot the fleet lists and a row that is filled.
  function checkChosenRow(given) {
    var found = objectField(given, PLAN);
    var chosen = owns(found, TARGET_ROW) ? found[TARGET_ROW] : null;
    if (chosen === null || chosen === undefined) {
      return;
    }
    var fleet = listField(given, BOT_IDS).length;
    if (!isRowNumber(chosen) || chosen < ZERO || chosen >= fleet) {
      planFaults.push(fault(PLAN, TARGET_ROW, CHOSEN_ABSENT_FAULT, chosen));
      return;
    }
    var filled = false;
    listField(given, FILLED_ROWS).forEach(function (one) {
      if (one === chosen) {
        filled = true;
      }
    });
    if (!filled) {
      planFaults.push(fault(PLAN, TARGET_ROW, CHOSEN_UNFILLED_FAULT, chosen));
    }
  }

  function checkColours() {
    colourTokens().forEach(function (one) {
      if (isSwappedAlpha(one.value)) {
        planFaults.push(
          fault(TOKEN_AT + one.name, SELECTION, SWAPPED_ALPHA_FAULT, one.value)
        );
      }
      if (isEqualChannels(one.value)) {
        planFaults.push(
          fault(TOKEN_AT + one.name, SELECTION, EQUAL_CHANNELS_FAULT, one.value)
        );
      }
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The panel paints an unreadable row amber so it cannot read as a choice.
  function rowStyle(one) {
    var unreadable = !one.filled || readable(one.bot) === undefined;
    return {
      display: BLOCK,
      background: colour(unreadable ? UNREADABLE_FILL : one.chosen ? CHOSEN_FILL : ROW_FILL),
      color: colour(unreadable ? UNREADABLE_INK : NAME_INK),
      borderStyle: SOLID,
      borderWidth: length(EDGE_WIDTH),
      borderColor: colour(one.chosen ? CHOSEN_EDGE : ROW_FILL),
      minHeight: length(ROW_HEIGHT),
      padding: length(ROW_PAD)
    };
  }

  function SelectionRow(props) {
    var one = props.row;
    var rowProps = { className: PANEL_CLASS, style: rowStyle(one) };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[BOT_ATTR] = readable(one.bot);
    rowProps[ROW_ATTR] = text(one.row);
    rowProps[KIND_ATTR] = one.kind;
    rowProps[FILLED_ATTR] = flag(one.filled);
    rowProps[CHOSEN_ATTR] = flag(one.chosen);
    rowProps[ARIA_LABEL] = labelOf(readable(one.bot));
    return element(DIV_TAG, rowProps, readable(one.bot));
  }

  function OrphanRow(props) {
    var orphanProps = { className: PANEL_CLASS, style: rowStyle(props) };
    orphanProps[PART_ATTR] = ORPHAN_PART;
    orphanProps[ROW_ATTR] = readable(props.value);
    orphanProps[KIND_ATTR] = kindOf(props.value);
    orphanProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, orphanProps, readable(props.value));
  }

  function SelectionRule(props) {
    var value = selectionRule(props.name);
    var ruleProps = { className: PANEL_CLASS, style: { color: colour(ARGUMENT_INK) } };
    ruleProps[PART_ATTR] = RULE_PART;
    ruleProps[NAME_ATTR] = props.name;
    ruleProps[VALUE_ATTR] = text(value);
    ruleProps[KIND_ATTR] = kindOf(value);
    return element(SPAN_TAG, ruleProps, text(value));
  }

  // The step name is drawn as its own element, and each argument as its own.
  function StepArgument(props) {
    var argumentProps = {
      className: PANEL_CLASS,
      style: { color: colour(ARGUMENT_INK), fontWeight: weight(ARGUMENT_WEIGHT) }
    };
    argumentProps[PART_ATTR] = ARGUMENT_PART;
    argumentProps[INDEX_ATTR] = text(props.at);
    argumentProps[VALUE_ATTR] = readable(props.value);
    argumentProps[KIND_ATTR] = kindOf(props.value);
    return element(SPAN_TAG, argumentProps, readable(props.value));
  }

  function StepRow(props) {
    var step = props.step;
    var stepProps = { className: PANEL_CLASS, style: { display: BLOCK } };
    stepProps[PART_ATTR] = props.part;
    stepProps[NAME_ATTR] = readable(step.name);
    stepProps[INDEX_ATTR] = text(step.index);
    stepProps[KIND_ATTR] = step.kind;
    stepProps[COUNT_ATTR] = text(step.args.length);
    var nameProps = {
      className: PANEL_CLASS,
      style: { color: colour(NAME_INK), fontWeight: weight(NAME_WEIGHT) }
    };
    nameProps[PART_ATTR] = NAME_PART;
    nameProps[VALUE_ATTR] = readable(step.name);
    nameProps[KIND_ATTR] = kindOf(step.name);
    var drawn = [element(SPAN_TAG, nameProps, readable(step.name))];
    step.args.forEach(function (one, at) {
      drawn.push(
        element(StepArgument, {
          key: ARGUMENT_PART + String(at),
          at: at,
          value: one
        })
      );
    });
    return element(DIV_TAG, stepProps, drawn);
  }

  // Panel draws nothing for a payload that is not an object.
  function Panel(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var panelProps = {
      id: props.id,
      className: PANEL_CLASS,
      style: { background: colour(PANEL_FILL), color: colour(NAME_INK) }
    };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[ACTION_ATTR] = readable(planField(ACTION));
    panelProps[TARGET_ATTR] = text(planField(TARGET_ROW));
    panelProps[SILENT_ATTR] = text(planField(BLOCK_SIGNALS));
    panelProps[BOT_COUNT_ATTR] = text(botNames().length);
    panelProps[FILLED_COUNT_ATTR] = text(filledRows().length);
    panelProps[READ_COUNT_ATTR] = text(reads().length);
    panelProps[CALL_COUNT_ATTR] = text(calls().length);
    panelProps[FAULT_COUNT_ATTR] = text(planFaults.length);
    var drawn = [];
    SELECTION_NAMES.forEach(function (name) {
      drawn.push(element(SelectionRule, { key: RULE_PART + name, name: name }));
    });
    rows().forEach(function (one) {
      drawn.push(
        element(SelectionRow, { key: ROW_PART + String(one.row), row: one })
      );
    });
    orphanRows().forEach(function (one, at) {
      drawn.push(
        element(OrphanRow, { key: ORPHAN_PART + String(at), value: one, at: at })
      );
    });
    readSteps().forEach(function (step) {
      drawn.push(
        element(StepRow, {
          key: READ_PART + String(step.index),
          part: READ_PART,
          step: step
        })
      );
    });
    callSteps().forEach(function (step) {
      drawn.push(
        element(StepRow, {
          key: CALL_PART + String(step.index),
          part: CALL_PART,
          step: step
        })
      );
    });
    return element(DIV_TAG, panelProps, drawn);
  }

  function heldFieldCount(given) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(given, name);
    }).length;
  }

  // Counts the fields, rows and calls declared against those held.
  function report() {
    var given = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        selection: SELECTION_NAMES.length,
        plan: PLAN_NAMES.length,
        colours: COLOUR_TOKENS.length
      },
      held: {
        fields: heldFieldCount(given),
        selection: Object.keys(objectField(given, SELECTION)).length,
        plan: Object.keys(objectField(given, PLAN)).length,
        bots: listField(given, BOT_IDS).length,
        filled: listField(given, FILLED_ROWS).length,
        reads: reads().length,
        calls: calls().length
      },
      faults: planFaults.slice()
    };
  }

  function faults() {
    return planFaults.slice();
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
  function renderPanel(target, given) {
    if (isPlainObject(given)) {
      setBotSelection(given);
    }
    return draw(target, element(Panel, { model: model() }));
  }

  function setBotSelection(given) {
    if (!isPlainObject(given)) {
      held = null;
      planFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(given))];
      return { declared: null, held: null, faults: planFaults.slice() };
    }
    held = { model: given };
    planFaults = [];
    checkFields(given);
    checkNamedBag(given, SELECTION, SELECTION_NAMES);
    checkNamedBag(given, PLAN, PLAN_NAMES);
    checkPlanLists(given);
    checkRows(given);
    checkChosenRow(given);
    checkColours();
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadBotSelection(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (given) {
        loadFault = null;
        setBotSelection(given);
        return given;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function forget() {
    held = null;
    planFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetBotSelection = setBotSelection;
  global.acervatorLoadBotSelection = loadBotSelection;
  global.acervatorBotSelection = {
    method: METHOD,
    Panel: Panel,
    SelectionRow: SelectionRow,
    StepRow: StepRow,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    selectionNames: selectionNames,
    planNames: planNames,
    selectionRule: selectionRule,
    planField: planField,
    botNames: botNames,
    filledRows: filledRows,
    rowFilled: rowFilled,
    rows: rows,
    orphanRows: orphanRows,
    chosenRow: chosenRow,
    reads: reads,
    calls: calls,
    readSteps: readSteps,
    callSteps: callSteps,
    stepName: stepName,
    stepArguments: stepArguments,
    colourTokens: colourTokens,
    tokenValue: tokenValue,
    colour: colour,
    isSwappedAlpha: isSwappedAlpha,
    isEqualChannels: isEqualChannels,
    isReorderedKey: isReorderedKey,
    isRowNumber: isRowNumber,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
