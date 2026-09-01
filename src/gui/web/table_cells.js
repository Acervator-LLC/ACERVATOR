// Draws one bot-table cell from the table_cells.state payload, holding
// no colour, format or number of its own.
(function (global) {
  "use strict";

  var METHOD = "table_cells.state";

  var CELLS = "cells";
  var CELL_COLUMNS = "cell_columns";
  var CELL_QUOTES = "cell_quotes";
  var CELL_MASK_KEYS = "cell_mask_keys";
  var CELL_TOOLTIPS = "cell_tooltips";
  var CELL_ICONS = "cell_icons";
  var ALIGNMENT = "alignment";
  var ALIGNMENT_VALUE = "alignment_value";
  var COLUMN_COUNT = "column_count";
  var SORTING_ENABLED = "sorting_enabled";
  var SORT_KEYS = "sort_keys";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var SKIN = "skin";
  var STYLE_SHEET = "style_sheet";
  var AMMO = "ammo";
  var AMMO_PATH = "ammo_path";
  var AMMO_PATHS = "ammo_paths";
  var AMMO_FIELDS = "ammo_fields";
  var AMMO_EARLY_FIELDS = "ammo_early_fields";
  var DENOM = "denom";
  var DENOM_PATH = "denom_path";
  var DENOM_PATHS = "denom_paths";
  var DENOM_PATH_TEXTS = "denom_path_texts";
  var TERRITORIES = "territories";
  var TERRITORY_COLORS = "territory_colors";
  var TERRITORY_TIPS = "territory_tips";
  var PRICE = "price";
  var PRICE_AGE_S = "price_age_s";
  var PRICE_STALE_AFTER_S = "price_stale_after_s";
  var MANUAL_FIRE_DUST_PCT = "manual_fire_dust_pct";
  var STALE_MARKER = "stale_marker";
  var POOL_FOUND = "pool_found";
  var CALLS = "calls";

  // Every top-level field of the table_cells.state payload.
  var CARRIED_FIELDS = [
    CELLS,
    CELL_COLUMNS,
    CELL_QUOTES,
    CELL_MASK_KEYS,
    CELL_TOOLTIPS,
    CELL_ICONS,
    ALIGNMENT,
    ALIGNMENT_VALUE,
    COLUMN_COUNT,
    SORTING_ENABLED,
    SORT_KEYS,
    ACTIONS,
    TIMERS,
    TIMER_DELAYS_MS,
    SKIN,
    STYLE_SHEET,
    AMMO,
    AMMO_PATH,
    AMMO_PATHS,
    AMMO_FIELDS,
    AMMO_EARLY_FIELDS,
    DENOM,
    DENOM_PATH,
    DENOM_PATHS,
    DENOM_PATH_TEXTS,
    TERRITORIES,
    TERRITORY_COLORS,
    TERRITORY_TIPS,
    PRICE,
    PRICE_AGE_S,
    PRICE_STALE_AFTER_S,
    MANUAL_FIRE_DUST_PCT,
    STALE_MARKER,
    POOL_FOUND,
    CALLS
  ];

  // The payload tables keyed by every name in CELLS; CELL_QUOTES omits AMMO_CELL.
  var PER_CELL_TABLES = [CELL_COLUMNS, CELL_MASK_KEYS, CELL_TOOLTIPS, CELL_ICONS];

  var TEXT = "text";
  var COLOR = "color";
  var TIP = "tip";
  var STALE = "stale";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_TABLE_FAULT = "not-a-table";
  var UNKNOWN_PATH_FAULT = "unknown-path";
  var UNKNOWN_FIELD_SET_FAULT = "unknown-field-set";
  var UNEXPECTED_FAULT = "unexpected";
  var TEXT_MISMATCH_FAULT = "text-mismatch";

  var NO_BRIDGE = "the preload bridge is not present";

  var CELL_CLASS = "acervator-table-cell";
  var CELL_TAG = "td";
  var ARIA_LABEL = "aria-label";

  var CELL_ATTR = "data-cell";
  var COLUMN_ATTR = "data-column";
  var QUOTE_ATTR = "data-quote";
  var MASK_KEY_ATTR = "data-mask-key";
  var ALIGNMENT_ATTR = "data-alignment";
  var ALIGNMENT_VALUE_ATTR = "data-alignment-value";
  var ICON_ATTR = "data-icon";
  var PATH_ATTR = "data-path";
  var STALE_ATTR = "data-stale";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";

  var held = null;
  var cellFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function contains(list, value) {
    var found = false;
    list.forEach(function (item) {
      if (item === value) {
        found = true;
      }
    });
    return found;
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

  function isFilledText(value) {
    return typeof value === "string" && value.length ? true : false;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // Returns String(value), or undefined for null and undefined.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // Returns value when it is a non-empty string, else undefined.
  function label(value) {
    return isFilledText(value) ? value : undefined;
  }

  // Returns the single entry of candidates, or undefined.
  function onlyName(candidates) {
    var only;
    var many = false;
    candidates.forEach(function (name) {
      if (only === undefined) {
        only = name;
        return;
      }
      many = true;
    });
    return many ? undefined : only;
  }

  // Names every acervatorTokens token equal to printed, skipping aliasTarget names.
  function tokenCandidates(printed) {
    var api = global.acervatorTokens;
    var usable =
      api && typeof api.names === "function" && typeof api.token === "function";
    if (!usable) {
      return [];
    }
    return api.names().filter(function (name) {
      var aliased =
        typeof api.aliasTarget === "function" && api.aliasTarget(name) !== undefined;
      if (aliased) {
        return false;
      }
      var carried = api.token(name);
      return carried !== null && carried !== undefined && String(carried) === printed;
    });
  }

  // Names every acervatorThemes.painted field equal to printed.
  function themeCandidates(printed) {
    var api = global.acervatorThemes;
    if (!api || typeof api.painted !== "function") {
      return [];
    }
    var values = api.painted();
    return Object.keys(values).filter(function (field) {
      var carried = values[field];
      return carried !== null && carried !== undefined && String(carried) === printed;
    });
  }

  // Returns the one token or theme name equal to value, else undefined.
  function variableFor(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var printed = String(value);
    var candidates = tokenCandidates(printed);
    if (candidates.length) {
      return onlyName(candidates);
    }
    return onlyName(themeCandidates(printed));
  }

  // Returns var(--NAME, value) when variableFor answers, else text(value).
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // True when CELL_QUOTES names this cell.
  function isDenomCell(model, name) {
    return owns(objectField(model, CELL_QUOTES), name);
  }

  function cellBody(model, name) {
    return objectField(model, isDenomCell(model, name) ? DENOM : AMMO);
  }

  function cellPath(model, name) {
    return model[isDenomCell(model, name) ? DENOM_PATH : AMMO_PATH];
  }

  function cellStyle(body) {
    return { color: colour(body[COLOR]) };
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Cell(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var name = props.cell;
    var body = cellBody(model, name);
    var wantsTip = objectField(model, CELL_TOOLTIPS)[name] === true;

    var cellProps = { id: props.id, className: CELL_CLASS, style: cellStyle(body) };
    cellProps.title = wantsTip ? label(body[TIP]) : undefined;
    cellProps[ARIA_LABEL] = label(name);
    cellProps[CELL_ATTR] = text(name);
    cellProps[COLUMN_ATTR] = text(objectField(model, CELL_COLUMNS)[name]);
    cellProps[QUOTE_ATTR] = text(objectField(model, CELL_QUOTES)[name]);
    cellProps[MASK_KEY_ATTR] = text(objectField(model, CELL_MASK_KEYS)[name]);
    cellProps[ICON_ATTR] = text(objectField(model, CELL_ICONS)[name]);
    cellProps[ALIGNMENT_ATTR] = text(model[ALIGNMENT]);
    cellProps[ALIGNMENT_VALUE_ATTR] = text(model[ALIGNMENT_VALUE]);
    cellProps[PATH_ATTR] = text(cellPath(model, name));
    cellProps[STALE_ATTR] = text(body[STALE]);

    return element(CELL_TAG, cellProps, text(body[TEXT]));
  }

  function checkCells() {
    listField(held.model, CELLS).forEach(function (name) {
      PER_CELL_TABLES.forEach(function (field) {
        if (!owns(objectField(held.model, field), name)) {
          cellFaults.push(fault(name, field, MISSING_FAULT, null));
        }
      });
    });
  }

  // Returns held.model[where], or null after pushing its MISSING, NULL or NOT_A_TABLE fault.
  function cellBodyOrFault(where) {
    var body = owns(held.model, where) ? held.model[where] : undefined;
    if (body === undefined) {
      cellFaults.push(fault(where, null, MISSING_FAULT, null));
      return null;
    }
    if (body === null) {
      cellFaults.push(fault(where, null, NULL_FAULT, null));
      return null;
    }
    if (!isPlainObject(body)) {
      cellFaults.push(fault(where, null, NOT_A_TABLE_FAULT, kindOf(body)));
      return null;
    }
    return body;
  }

  function checkPath(where, path, field, names) {
    if (!contains(names, path)) {
      cellFaults.push(fault(where, field, UNKNOWN_PATH_FAULT, path));
    }
  }

  function coversAll(names, bag) {
    var all = true;
    names.forEach(function (name) {
      if (!owns(bag, name)) {
        all = false;
      }
    });
    return all;
  }

  function onlyFrom(bag, names) {
    var all = true;
    Object.keys(bag).forEach(function (name) {
      if (!contains(names, name)) {
        all = false;
      }
    });
    return all;
  }

  function sameNames(bag, names) {
    return coversAll(names, bag) && onlyFrom(bag, names);
  }

  // Returns AMMO_EARLY_FIELDS or AMMO_FIELDS, whichever names exactly the keys of body.
  function ammoDeclaredFields(body) {
    var full = listField(held.model, AMMO_FIELDS);
    var early = listField(held.model, AMMO_EARLY_FIELDS);
    if (sameNames(body, early)) {
      return early;
    }
    if (sameNames(body, full)) {
      return full;
    }
    cellFaults.push(
      fault(AMMO, null, UNKNOWN_FIELD_SET_FAULT, Object.keys(body).slice())
    );
    return full;
  }

  function checkAmmo() {
    var body = cellBodyOrFault(AMMO);
    var path = held.model[AMMO_PATH];
    if (body === null || !isFilledText(path)) {
      return;
    }
    checkPath(AMMO, path, AMMO_PATH, listField(held.model, AMMO_PATHS));
    var full = listField(held.model, AMMO_FIELDS);
    var early = listField(held.model, AMMO_EARLY_FIELDS);
    ammoDeclaredFields(body).forEach(function (name) {
      if (!owns(body, name)) {
        cellFaults.push(fault(AMMO, name, MISSING_FAULT, null));
      }
    });
    Object.keys(body).forEach(function (name) {
      if (!contains(full, name) && !contains(early, name)) {
        cellFaults.push(fault(AMMO, name, UNEXPECTED_FAULT, kindOf(body[name])));
      }
    });
  }

  function checkDenom() {
    var body = cellBodyOrFault(DENOM);
    var path = held.model[DENOM_PATH];
    if (body === null || !isFilledText(path)) {
      return;
    }
    checkPath(DENOM, path, DENOM_PATH, listField(held.model, DENOM_PATHS));
    var fixed = objectField(held.model, DENOM_PATH_TEXTS);
    if (owns(fixed, path) && body[TEXT] !== fixed[path]) {
      cellFaults.push(
        fault(DENOM, TEXT, TEXT_MISMATCH_FAULT, {
          declared: fixed[path],
          held: body[TEXT]
        })
      );
    }
  }

  // Counts CARRIED_FIELDS, CELLS and AMMO_FIELDS declared against those held.
  function report() {
    var columns = objectField(held.model, CELL_COLUMNS);
    return {
      declared: {
        fields: CARRIED_FIELDS.length,
        cells: listField(held.model, CELLS).length,
        ammoFields: listField(held.model, AMMO_FIELDS).length
      },
      held: {
        fields: CARRIED_FIELDS.filter(function (name) {
          return owns(held.model, name);
        }).length,
        cells: listField(held.model, CELLS).filter(function (name) {
          return owns(columns, name);
        }).length,
        ammoFields: Object.keys(objectField(held.model, AMMO)).length
      },
      faults: cellFaults.slice()
    };
  }

  function setCells(model) {
    if (!isPlainObject(model)) {
      held = null;
      cellFaults = [fault(CELLS, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: cellFaults.slice() };
    }
    held = { model: model };
    cellFaults = [];
    checkCells();
    checkAmmo();
    checkDenom();
    return report();
  }

  // Calls METHOD once per page, clearing asked on failure so a later call retries.
  function loadCells(params) {
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
        setCells(model);
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

  function carriedNames() {
    return CARRIED_FIELDS.slice();
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function cellNames() {
    return held === null ? [] : listField(held.model, CELLS).slice();
  }

  function ammo() {
    return held === null ? {} : copyOf(objectField(held.model, AMMO));
  }

  function denom() {
    return held === null ? {} : copyOf(objectField(held.model, DENOM));
  }

  function ammoPath() {
    return field(AMMO_PATH);
  }

  function denomPath() {
    return field(DENOM_PATH);
  }

  function territoryColour(name) {
    var colours = held === null ? {} : objectField(held.model, TERRITORY_COLORS);
    return owns(colours, name) ? colours[name] : undefined;
  }

  function territoryTip(name) {
    var tips = held === null ? {} : objectField(held.model, TERRITORY_TIPS);
    return owns(tips, name) ? tips[name] : undefined;
  }

  function column(name) {
    var columns = held === null ? {} : objectField(held.model, CELL_COLUMNS);
    return owns(columns, name) ? columns[name] : undefined;
  }

  function quote(name) {
    var quotes = held === null ? {} : objectField(held.model, CELL_QUOTES);
    return owns(quotes, name) ? quotes[name] : undefined;
  }

  function maskKey(name) {
    var keys = held === null ? {} : objectField(held.model, CELL_MASK_KEYS);
    return owns(keys, name) ? keys[name] : undefined;
  }

  function wantsTooltip(name) {
    var flags = held === null ? {} : objectField(held.model, CELL_TOOLTIPS);
    return owns(flags, name) ? flags[name] : undefined;
  }

  function wantsIcon(name) {
    var flags = held === null ? {} : objectField(held.model, CELL_ICONS);
    return owns(flags, name) ? flags[name] : undefined;
  }

  function calls() {
    return held === null ? [] : listField(held.model, CALLS).slice();
  }

  // Returns typeof each field of ammo or denom, with null named apart.
  function types(where) {
    var body = where === DENOM ? denom() : ammo();
    var found = {};
    Object.keys(body).forEach(function (name) {
      found[name] = kindOf(body[name]);
    });
    return found;
  }

  function faults() {
    return cellFaults.slice();
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

  // Renders node into target inside ReactDOM.flushSync.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function payloadOr(model) {
    if (isPlainObject(model)) {
      return model;
    }
    return held === null ? {} : held.model;
  }

  function renderCell(target, name, model) {
    return draw(target, element(Cell, { cell: name, model: payloadOr(model) }));
  }

  function forget() {
    held = null;
    cellFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetCells = setCells;
  global.acervatorLoadCells = loadCells;
  global.acervatorCells = {
    method: METHOD,
    Cell: Cell,
    payload: payload,
    carriedNames: carriedNames,
    field: field,
    cellNames: cellNames,
    ammo: ammo,
    denom: denom,
    ammoPath: ammoPath,
    denomPath: denomPath,
    territoryColour: territoryColour,
    territoryTip: territoryTip,
    column: column,
    quote: quote,
    maskKey: maskKey,
    wantsTooltip: wantsTooltip,
    wantsIcon: wantsIcon,
    calls: calls,
    isDenomCell: isDenomCell,
    cellStyle: cellStyle,
    variableFor: variableFor,
    colour: colour,
    types: types,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderCell: renderCell,
    forget: forget
  };
})(window);
