// One news strip, drawn from the crypto_news_ticker state method.
(function (global) {
  "use strict";
  var METHOD = "crypto_news_ticker.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var CALLS = "calls";
  var CYCLE_INTERVAL_MS = "cycle_interval_ms";
  var CYCLE_RUNNING = "cycle_running";
  var FETCHES_STARTED = "fetches_started";
  var HEADLINES = "headlines";
  var HEADLINE_TOOLTIP_FORMAT = "headline_tooltip_format";
  var INDEX = "index";
  var INITIAL_TEXT = "initial_text";
  var LABEL_CURSOR = "label_cursor";
  var LABEL_STRETCH = "label_stretch";
  var LABEL_STYLE = "label_style";
  var LABEL_TEXT = "label_text";
  var LABEL_TEXT_FLAGS = "label_text_flags";
  var LABEL_TOOLTIP = "label_tooltip";
  var LAST_REFRESH_TS = "last_refresh_ts";
  var LAYOUT_MARGINS = "layout_margins";
  var LAYOUT_SPACING = "layout_spacing";
  var LIVE_WORKERS = "live_workers";
  var MAX_FETCH_WORKERS = "max_fetch_workers";
  var NO_FEEDS_TEXT = "no_feeds_text";
  var OPENED = "opened";
  var PAUSED = "paused";
  var REFRESH_INTERVAL_MS = "refresh_interval_ms";
  var REFRESH_RUNNING = "refresh_running";
  var SOURCES = "sources";
  var SOURCE_JOIN = "source_join";
  var STYLE_SHEET = "style_sheet";
  var THREAD_COUNT = "thread_count";
  var TIMERS = "timers";
  var TIMER_COUNT = "timer_count";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TITLE_MAX_CHARS = "title_max_chars";
  var UNAVAILABLE_TEXT = "unavailable_text";
  var WORKER_LIFECYCLE = "worker_lifecycle";
  var WORKER_RUNNING = "worker_running";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    "abandoned_log",
    "accept_header",
    ACTIONS,
    "aggregate_log",
    "allowlist_log",
    "at_exit_log",
    "browser_new_tab",
    "budget_spent_log",
    "bus_topics",
    CALLS,
    CYCLE_INTERVAL_MS,
    CYCLE_RUNNING,
    "date_tags",
    "default_timeout_s",
    "event_enter",
    "event_leave",
    "event_mouse_release",
    "fetch_accept",
    "fetch_budget_s",
    "fetch_failed_log",
    "fetch_poll_s",
    "fetch_stopped_log",
    "fetch_user_agent",
    FETCHES_STARTED,
    HEADLINE_TOOLTIP_FORMAT,
    HEADLINES,
    INDEX,
    INITIAL_TEXT,
    "item_tags",
    LABEL_CURSOR,
    LABEL_STRETCH,
    LABEL_STYLE,
    LABEL_TEXT,
    LABEL_TEXT_FLAGS,
    LABEL_TOOLTIP,
    LAST_REFRESH_TS,
    LAYOUT_MARGINS,
    LAYOUT_SPACING,
    "link_href",
    "link_tags",
    LIVE_WORKERS,
    "logger_name",
    "malformed_feed_log",
    "max_feed_bytes",
    MAX_FETCH_WORKERS,
    "method",
    "namespace_mark",
    NO_FEEDS_TEXT,
    "no_sources_refusal",
    "no_text",
    "no_timestamp",
    OPENED,
    "oversized_feed_log",
    "open_failed_log",
    "parse_limit",
    PAUSED,
    "per_source_limit",
    "position_format",
    "read_budget_log",
    "read_chunk_bytes",
    "read_stopped_log",
    "refused_feed_log",
    REFRESH_INTERVAL_MS,
    REFRESH_RUNNING,
    "retire_wait_ms",
    "skin",
    SOURCE_JOIN,
    SOURCES,
    "still_running_log",
    "stop_wait_ms",
    STYLE_SHEET,
    THREAD_COUNT,
    TIMER_COUNT,
    TIMER_DELAYS_MS,
    TIMERS,
    TITLE_MAX_CHARS,
    "title_tags",
    UNAVAILABLE_TEXT,
    "user_agent_header",
    "widget_fetch_failed_log",
    WORKER_LIFECYCLE,
    "worker_name",
    WORKER_RUNNING
  ];

  var TITLE = "title";
  var URL = "url";
  var SOURCE = "source";
  var PUBLISHED_TS = "published_ts";
  var DISPLAY_TEXT = "display_text";
  var SLUG = "slug";
  var NAME = "name";

  var HEADLINE_TEXT_FIELDS = [TITLE, URL, DISPLAY_TEXT];
  var WORD_FIELDS = [
    ACCESSIBLE_NAME,
    INITIAL_TEXT,
    LABEL_TEXT,
    LABEL_TOOLTIP,
    NO_FEEDS_TEXT,
    UNAVAILABLE_TEXT
  ];
  var RESTING_TEXTS = [INITIAL_TEXT, NO_FEEDS_TEXT, UNAVAILABLE_TEXT];
  var SHEET_FIELDS = [LABEL_STYLE, STYLE_SHEET];
  var SOURCE_TEXT_FIELDS = [SLUG, NAME, URL];

  var CYCLE_TIMEOUT = "cycle_timeout";
  var REFRESH_TIMEOUT = "refresh_timeout";

  var EVENT_ENTER = "event_enter";
  var EVENT_LEAVE = "event_leave";
  var EVENT_MOUSE_RELEASE = "event_mouse_release";

  var ADVANCE_PARAM = "advance";
  var CLICK_PARAM = "click";
  var HOVER_PARAM = "hover";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_PLAIN_FAULT = "not-plain";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var DISAGREES_FAULT = "disagrees";
  var OUT_OF_RANGE_FAULT = "out-of-range";
  var TOO_LONG_FAULT = "too-long";

  var NO_BRIDGE = "the preload bridge is not present";

  var HEADLINE_AT = "headline:";
  var SOURCE_AT = "source:";
  var CALL_AT = "call:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var HASH = "#";
  var GAP = " ";
  var DOT = ".";
  var COMMA = ",";
  var COLON = ":";
  var SEMICOLON = ";";
  var PERCENT = "%";
  var CLOSE = ")";
  var RGBA_OPEN = "rgba(";
  var MARKUP_OPEN = "<";
  var HEX_ARGB = "AARRGGBB";

  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";
  var PX = "px";

  var FONT_SIZE = "font-size";
  var FONT_PROPERTIES = [FONT_SIZE];
  var FONT_GROUPS = ["type_scale"];
  var SPACING_GROUPS = ["spacing"];

  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  var CURSOR_BY_NAME = { PointingHandCursor: "pointer" };
  var SELECT_BY_FLAG = { TextSelectableByMouse: "text" };

  var ROW = "row";
  var FLEX = "flex";
  var CENTER = "center";
  var HIDDEN = "hidden";
  var NOWRAP = "nowrap";

  var DIV_TAG = "div";

  var TICKER_CLASS = "acervator-news-ticker";
  var LINE_CLASS = "acervator-news-ticker-line";

  var TICKER_PART = "ticker";
  var HEADLINE_PART = "headline";
  var TICKER_SLOT = "news-ticker";

  var PART_ATTR = "data-part";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var TOTAL_ATTR = "data-total";
  var PAUSED_ATTR = "data-paused";
  var CYCLE_ATTR = "data-cycle-running";
  var REFRESH_ATTR = "data-refresh-running";
  var CYCLE_MS_ATTR = "data-cycle-interval-ms";
  var REFRESH_MS_ATTR = "data-refresh-interval-ms";
  var WORKER_ATTR = "data-worker-running";
  var LIVE_WORKERS_ATTR = "data-live-workers";
  var FETCHES_ATTR = "data-fetches-started";
  var THREADS_ATTR = "data-thread-count";
  var TIMERS_ATTR = "data-timer-count";
  var REFRESHED_ATTR = "data-last-refresh-ts";
  var URL_ATTR = "data-url";
  var SOURCE_ATTR = "data-source";
  var PUBLISHED_ATTR = "data-published-ts";
  var ARIA_LABEL = "aria-label";
  var SLOT_ATTR = "data-slot";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var NOT_LISTED = ZERO - STEP;

  var held = null;
  var tickerFaults = [];
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
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    tickerFaults.push(fault(where, field, kind, detail));
  }

  // Undefined leaves an attribute off, so `text` writes nothing for a null value.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // `shared_widgets.js` owns the one-carrier rule naming the variable for one value.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // A margin painted through a radius token would move with the radius, so groups matter.
  function inGroups(name, groups) {
    var api = global.acervatorTokens;
    if (!api || typeof api.group !== "function") {
      return false;
    }
    var matched = groups.filter(function (one) {
      return owns(api.group(one), name);
    });
    return Boolean(matched.length);
  }

  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function scaled(value, groups) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, groups);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  function length(value) {
    return scaled(value, SPACING_GROUPS);
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  function headerStyleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // Whether one value counts its alpha in bytes, as Qt does and CSS does not.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return false;
    }
    var fields = String(parts.shift()).split(CLOSE).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined) {
      return false;
    }
    return !carries(alpha, DOT) && !carries(alpha, PERCENT);
  }

  // The reason CSS would read one value as a different colour.
  function qtColour(value) {
    if (hexWord(value).length === HEX_ARGB.length) {
      return HEX_ARGB;
    }
    if (byteAlpha(value)) {
      return RGBA_OPEN;
    }
    return undefined;
  }

  // One length without its unit, so a token holding a bare number matches.
  function unitless(value) {
    var parts = String(value).split(PX);
    var tail = String(parts.pop());
    if (tail !== EMPTY || !parts.length) {
      return undefined;
    }
    return parts.join(PX);
  }

  function groupsFor(property) {
    return FONT_PROPERTIES.indexOf(property) === NOT_LISTED
      ? SPACING_GROUPS
      : FONT_GROUPS;
  }

  function tokenised(property, value) {
    var head = unitless(value);
    if (head === undefined) {
      return value;
    }
    var name = variableInGroups(head, groupsFor(property));
    if (name === undefined) {
      return value;
    }
    return CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + head + VAR_CLOSE + PX_FACTOR;
  }

  // The sheet without the declarations CSS would read as another colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) === undefined) {
        kept.push(one.property + COLON + tokenised(one.property, one.value));
      }
    });
    return kept.join(SEMICOLON);
  }

  function styleOf(sheet) {
    return headerStyleOf(keptSheet(sheet));
  }

  function cursorOf(model) {
    var named = model[LABEL_CURSOR];
    return owns(CURSOR_BY_NAME, named) ? CURSOR_BY_NAME[named] : undefined;
  }

  function selectionOf(model) {
    var named = model[LABEL_TEXT_FLAGS];
    return owns(SELECT_BY_FLAG, named) ? SELECT_BY_FLAG[named] : undefined;
  }

  // Qt puts the layout's four margins on the strip, in this order.
  function marginStyle(model) {
    var style = {};
    var margins = listField(model, LAYOUT_MARGINS);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
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

  function dispatch(event, params) {
    dispatched.push({ event: event, params: params });
    if (!hasBridge()) {
      return null;
    }
    // An answer that is not a payload is named and the strip keeps its story.
    return global.acervator.call(METHOD, copyOf(params)).then(function (answer) {
      if (!isPlainObject(answer)) {
        tickerFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(answer))];
        return answer;
      }
      setTicker(answer);
      redraw();
      return answer;
    });
  }

  function request(field, value) {
    var params = {};
    params[field] = value;
    return params;
  }

  // One cycle timeout, which asks the bridge to advance one step.
  function advance() {
    var model = heldModel();
    return dispatch(actionNamed(model, CYCLE_TIMEOUT), request(ADVANCE_PARAM, STEP));
  }

  // No parameter reaches force_refresh, so the refresh timeout asks for the state again.
  function refresh() {
    var model = heldModel();
    return dispatch(actionNamed(model, REFRESH_TIMEOUT), {});
  }

  function hover() {
    return dispatch(heldModel()[EVENT_ENTER], request(HOVER_PARAM, true));
  }

  function release() {
    return dispatch(heldModel()[EVENT_LEAVE], request(HOVER_PARAM, false));
  }

  function openStory() {
    var model = heldModel();
    return dispatch(model[EVENT_MOUSE_RELEASE], request(CLICK_PARAM, true));
  }

  function currentHeadline(model) {
    var stories = listField(model, HEADLINES);
    var at = model[INDEX];
    if (typeof at !== "number" || at < ZERO || at >= stories.length) {
      return {};
    }
    return isPlainObject(stories[at]) ? stories[at] : {};
  }

  // React writes every word as text, so markup in a feed title stays words.
  function Headline(props) {
    var model = props.model;
    var story = currentHeadline(model);
    var lineProps = {
      className: LINE_CLASS,
      style: styleOf(model[LABEL_STYLE]),
      title: text(model[LABEL_TOOLTIP]),
      onClick: openStory,
      onMouseEnter: hover,
      onMouseLeave: release
    };
    lineProps.style.flexGrow = text(model[LABEL_STRETCH]);
    lineProps.style.whiteSpace = NOWRAP;
    lineProps.style.overflow = HIDDEN;
    lineProps.style.cursor = cursorOf(model);
    lineProps.style.userSelect = selectionOf(model);
    lineProps[PART_ATTR] = HEADLINE_PART;
    lineProps[ACTION_ATTR] = text(actionNamed(model, CYCLE_TIMEOUT));
    lineProps[URL_ATTR] = text(story[URL]);
    lineProps[SOURCE_ATTR] = text(objectField(story, SOURCE)[SLUG]);
    lineProps[PUBLISHED_ATTR] = text(story[PUBLISHED_TS]);
    return element(DIV_TAG, lineProps, text(model[LABEL_TEXT]));
  }

  // The strip follows Qt's two waits only where a bridge can answer them.
  function useTickerWaits(model) {
    var cycle = model[CYCLE_RUNNING] === true ? model[CYCLE_INTERVAL_MS] : undefined;
    var hourly =
      model[REFRESH_RUNNING] === true ? model[REFRESH_INTERVAL_MS] : undefined;
    hooks().useEffect(
      function () {
        if (!hasBridge() || typeof cycle !== "number") {
          return undefined;
        }
        var handle = global.setInterval(advance, cycle);
        return function () {
          global.clearInterval(handle);
        };
      },
      [cycle]
    );
    hooks().useEffect(
      function () {
        if (!hasBridge() || typeof hourly !== "number") {
          return undefined;
        }
        var handle = global.setInterval(refresh, hourly);
        return function () {
          global.clearInterval(handle);
        };
      },
      [hourly]
    );
  }

  // `Ticker` draws nothing for a payload that is not an object.
  function Ticker(props) {
    useTickerWaits(isPlainObject(props.model) ? props.model : {});
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var tickerProps = { id: props.id, className: TICKER_CLASS, style: marginStyle(model) };
    tickerProps.style.display = FLEX;
    tickerProps.style.flexDirection = ROW;
    tickerProps.style.alignItems = CENTER;
    tickerProps.style.overflow = HIDDEN;
    tickerProps.style.gap = length(model[LAYOUT_SPACING]);
    tickerProps[PART_ATTR] = TICKER_PART;
    tickerProps[ARIA_LABEL] = text(model[ACCESSIBLE_NAME]);
    tickerProps[INDEX_ATTR] = text(model[INDEX]);
    tickerProps[TOTAL_ATTR] = String(listField(model, HEADLINES).length);
    tickerProps[PAUSED_ATTR] = text(model[PAUSED]);
    tickerProps[CYCLE_ATTR] = text(model[CYCLE_RUNNING]);
    tickerProps[REFRESH_ATTR] = text(model[REFRESH_RUNNING]);
    tickerProps[CYCLE_MS_ATTR] = text(model[CYCLE_INTERVAL_MS]);
    tickerProps[REFRESH_MS_ATTR] = text(model[REFRESH_INTERVAL_MS]);
    tickerProps[WORKER_ATTR] = text(model[WORKER_RUNNING]);
    tickerProps[LIVE_WORKERS_ATTR] = text(model[LIVE_WORKERS]);
    tickerProps[FETCHES_ATTR] = text(model[FETCHES_STARTED]);
    tickerProps[THREADS_ATTR] = text(model[THREAD_COUNT]);
    tickerProps[TIMERS_ATTR] = text(model[TIMER_COUNT]);
    tickerProps[REFRESHED_ATTR] = text(model[LAST_REFRESH_TS]);
    return element(
      DIV_TAG,
      tickerProps,
      element(Headline, { key: HEADLINE_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        note(null, field, MISSING_FAULT, null);
        return;
      }
      if (model[field] === null) {
        note(null, field, NULL_FAULT, null);
      }
    });
  }

  // A JSON line carries only these, so any other value is data from this process.
  function isData(value) {
    if (value === null || Array.isArray(value)) {
      return true;
    }
    var named = typeof value;
    if (named === "boolean" || named === "number" || named === "string") {
      return true;
    }
    if (named !== "object") {
      return false;
    }
    var under = Object.getPrototypeOf(value);
    return under === Object.prototype || under === null;
  }

  function plainness() {
    var found = [];
    function descend(path, value) {
      if (!isData(value)) {
        found.push(path);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          descend(path + PATH_SPLIT + String(at), one);
        });
        return;
      }
      if (isPlainObject(value)) {
        Object.keys(value).forEach(function (name) {
          descend(path + PATH_SPLIT + name, value[name]);
        });
      }
    }
    if (held !== null) {
      Object.keys(held.model).forEach(function (name) {
        descend(name, held.model[name]);
      });
    }
    return found;
  }

  function checkPlainData() {
    plainness().forEach(function (path) {
      note(null, path, NOT_PLAIN_FAULT, null);
    });
  }

  function nameMarkup(where, field, value) {
    if (typeof value === "string" && carries(value, MARKUP_OPEN)) {
      note(where, field, MARKUP_FAULT, MARKUP_OPEN);
    }
  }

  // Every word this strip draws, refused as markup before React draws it.
  function checkMarkup(model) {
    WORD_FIELDS.forEach(function (field) {
      nameMarkup(null, field, model[field]);
    });
    listField(model, HEADLINES).forEach(function (story, at) {
      if (!isPlainObject(story)) {
        return;
      }
      var where = HEADLINE_AT + String(at);
      nameMarkup(where, TITLE, story[TITLE]);
      nameMarkup(where, DISPLAY_TEXT, story[DISPLAY_TEXT]);
      nameMarkup(where, NAME, objectField(story, SOURCE)[NAME]);
    });
  }

  function checkTextFields(where, row, fields) {
    fields.forEach(function (field) {
      if (!owns(row, field)) {
        note(where, field, MISSING_FAULT, null);
        return;
      }
      if (typeof row[field] !== "string") {
        note(where, field, WRONG_TYPE_FAULT, kindOf(row[field]));
      }
    });
  }

  function checkStamp(where, story) {
    var stamp = story[PUBLISHED_TS];
    if (typeof stamp !== "number") {
      note(where, PUBLISHED_TS, WRONG_TYPE_FAULT, kindOf(stamp));
      return;
    }
    if (!global.isFinite(stamp)) {
      note(where, PUBLISHED_TS, WRONG_TYPE_FAULT, String(stamp));
    }
  }

  // The printed line is the feed name, the join and the title, in that order.
  function checkDisplayText(where, model, story) {
    var named = objectField(story, SOURCE)[NAME];
    if (typeof named !== "string" || typeof story[TITLE] !== "string") {
      return;
    }
    var wanted = named + String(model[SOURCE_JOIN]) + story[TITLE];
    if (story[DISPLAY_TEXT] !== wanted) {
      note(where, DISPLAY_TEXT, DISAGREES_FAULT, wanted);
    }
  }

  function checkTitleLength(where, model, story) {
    var cap = model[TITLE_MAX_CHARS];
    if (typeof story[TITLE] !== "string" || typeof cap !== "number") {
      return;
    }
    if (story[TITLE].length > cap) {
      note(where, TITLE, TOO_LONG_FAULT, String(story[TITLE].length));
    }
  }

  function checkHeadlines(model) {
    if (owns(model, HEADLINES) && !Array.isArray(model[HEADLINES])) {
      note(null, HEADLINES, NOT_A_LIST_FAULT, kindOf(model[HEADLINES]));
      return;
    }
    listField(model, HEADLINES).forEach(function (story, at) {
      var where = HEADLINE_AT + String(at);
      if (!isPlainObject(story)) {
        note(where, null, NOT_AN_OBJECT_FAULT, kindOf(story));
        return;
      }
      checkTextFields(where, story, HEADLINE_TEXT_FIELDS);
      checkStamp(where, story);
      if (!isPlainObject(story[SOURCE])) {
        note(where, SOURCE, NOT_AN_OBJECT_FAULT, kindOf(story[SOURCE]));
      } else {
        checkTextFields(where, story[SOURCE], SOURCE_TEXT_FIELDS);
      }
      checkDisplayText(where, model, story);
      checkTitleLength(where, model, story);
    });
  }

  function checkSources(model) {
    if (owns(model, SOURCES) && !Array.isArray(model[SOURCES])) {
      note(null, SOURCES, NOT_A_LIST_FAULT, kindOf(model[SOURCES]));
      return;
    }
    var feeds = listField(model, SOURCES);
    feeds.forEach(function (feed, at) {
      var where = SOURCE_AT + String(at);
      if (!isPlainObject(feed)) {
        note(where, null, NOT_AN_OBJECT_FAULT, kindOf(feed));
        return;
      }
      checkTextFields(where, feed, SOURCE_TEXT_FIELDS);
    });
    var most = model[MAX_FETCH_WORKERS];
    if (typeof most === "number" && feeds.length > most) {
      note(null, SOURCES, DISAGREES_FAULT, String(feeds.length));
    }
  }

  // The index must name a story the headlines list really holds.
  function checkIndex(model) {
    var at = model[INDEX];
    var total = listField(model, HEADLINES).length;
    if (typeof at !== "number") {
      note(null, INDEX, WRONG_TYPE_FAULT, kindOf(at));
      return;
    }
    if (at < ZERO || (total ? at >= total : at !== ZERO)) {
      note(null, INDEX, OUT_OF_RANGE_FAULT, String(total));
    }
  }

  // With no story the strip rests on one of the three words it publishes.
  function checkLabelText(model) {
    var words = model[LABEL_TEXT];
    var story = currentHeadline(model);
    if (typeof words !== "string") {
      note(null, LABEL_TEXT, WRONG_TYPE_FAULT, kindOf(words));
      return;
    }
    if (typeof story[DISPLAY_TEXT] === "string") {
      if (!carries(words, story[DISPLAY_TEXT])) {
        note(null, LABEL_TEXT, DISAGREES_FAULT, story[DISPLAY_TEXT]);
      }
      return;
    }
    var resting = RESTING_TEXTS.filter(function (field) {
      return model[field] === words;
    });
    if (!resting.length) {
      note(null, LABEL_TEXT, DISAGREES_FAULT, null);
    }
  }

  // The tooltip names the feed and its address once a story is on the strip.
  function checkLabelTooltip(model) {
    var words = model[LABEL_TOOLTIP];
    var story = currentHeadline(model);
    if (typeof words !== "string") {
      note(null, LABEL_TOOLTIP, WRONG_TYPE_FAULT, kindOf(words));
      return;
    }
    if (typeof story[URL] !== "string") {
      return;
    }
    if (!carries(words, story[URL])) {
      note(null, LABEL_TOOLTIP, DISAGREES_FAULT, story[URL]);
    }
  }

  function timerOrder(model) {
    return Object.keys(objectField(model, TIMERS));
  }

  // The bag and the list must name the same two waits, in the same order.
  function checkTimers(model) {
    var timers = objectField(model, TIMERS);
    var delays = listField(model, TIMER_DELAYS_MS);
    var named = timerOrder(model).map(function (one) {
      return timers[one];
    });
    if (String(named) !== String(delays)) {
      note(null, TIMER_DELAYS_MS, DISAGREES_FAULT, String(named));
    }
    if (named.length !== model[TIMER_COUNT]) {
      note(null, TIMER_COUNT, DISAGREES_FAULT, String(named.length));
    }
    var waits = [model[CYCLE_INTERVAL_MS], model[REFRESH_INTERVAL_MS]];
    if (String(waits) !== String(delays)) {
      note(null, TIMERS, DISAGREES_FAULT, String(waits));
    }
  }

  function checkWorker(model) {
    var lifecycle = objectField(model, WORKER_LIFECYCLE);
    if (Object.keys(lifecycle).length !== model[THREAD_COUNT]) {
      note(null, THREAD_COUNT, DISAGREES_FAULT, String(Object.keys(lifecycle).length));
    }
    if (model[WORKER_RUNNING] === true && model[LIVE_WORKERS] === ZERO) {
      note(null, LIVE_WORKERS, DISAGREES_FAULT, text(model[WORKER_RUNNING]));
    }
  }

  function checkColours(model) {
    SHEET_FIELDS.forEach(function (field) {
      declarations(model[field]).forEach(function (one) {
        var named = qtColour(one.value);
        if (named !== undefined) {
          note(one.property, field, QT_COLOUR_FAULT, named);
        }
      });
    });
  }

  function checkCalls(model) {
    listField(model, CALLS).forEach(function (one, at) {
      if (!Array.isArray(one)) {
        note(CALL_AT + String(at), CALLS, NOT_A_LIST_FAULT, kindOf(one));
      }
    });
    if (owns(model, OPENED) && !Array.isArray(model[OPENED])) {
      note(null, OPENED, NOT_A_LIST_FAULT, kindOf(model[OPENED]));
    }
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        headlines: listField(model, HEADLINES).length,
        sources: listField(model, SOURCES).length,
        timers: model[TIMER_COUNT]
      },
      held: {
        fields: heldFieldCount(model),
        headlines: listField(model, HEADLINES).filter(isPlainObject).length,
        sources: listField(model, SOURCES).filter(isPlainObject).length,
        timers: timerOrder(model).length
      },
      faults: tickerFaults.slice()
    };
  }

  function setTicker(model) {
    if (!isPlainObject(model)) {
      held = null;
      tickerFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tickerFaults.slice() };
    }
    held = { model: model };
    tickerFaults = [];
    checkFields(model);
    checkPlainData();
    checkMarkup(model);
    checkHeadlines(model);
    checkSources(model);
    checkIndex(model);
    checkLabelText(model);
    checkLabelTooltip(model);
    checkTimers(model);
    checkWorker(model);
    checkColours(model);
    checkCalls(model);
    return report();
  }

  // One round trip per page, and a failed ask leaves the ticker unloaded.
  function loadTicker(params) {
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
        setTicker(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function headlines() {
    return listField(heldModel(), HEADLINES).slice();
  }

  function headlineAt(at) {
    return headlines()[at];
  }

  // The sequence by address, so a check reads order without reading a place.
  function headlineOrder() {
    return headlines().map(function (story) {
      return isPlainObject(story) ? story[URL] : undefined;
    });
  }

  function sources() {
    return listField(heldModel(), SOURCES).slice();
  }

  function sourceOrder() {
    return sources().map(function (feed) {
      return isPlainObject(feed) ? feed[SLUG] : undefined;
    });
  }

  function calls() {
    return listField(heldModel(), CALLS).slice();
  }

  function callOrder() {
    return calls().map(function (one) {
      return Array.isArray(one) ? one.slice().shift() : undefined;
    });
  }

  function actionOrder() {
    return Object.keys(bag(ACTIONS));
  }

  function timerNames() {
    return timerOrder(heldModel());
  }

  function workerNames() {
    return Object.keys(bag(WORKER_LIFECYCLE));
  }

  function current() {
    return currentHeadline(heldModel());
  }

  function faults() {
    return tickerFaults.slice();
  }

  function sent() {
    return dispatched.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  // The JavaScript type of every payload value, by dotted path.
  function kinds() {
    var found = {};
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
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
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
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

  function renderTicker(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Ticker, { model: payload }));
  }

  // Every host this module has drawn into, re-drawn from the held payload.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Ticker, { model: heldModel() }));
    });
    return roots.length;
  }

  // The exchange screen leaves one named slot, which mount finds and fills.
  function mount(root) {
    var target = root === undefined || root === null ? global.document : root;
    var found = target.querySelector(
      SELECT_OPEN + SLOT_ATTR + SELECT_IS + TICKER_SLOT + SELECT_CLOSE
    );
    return found === null ? null : renderTicker(found);
  }

  function forget() {
    held = null;
    tickerFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetTicker = setTicker;
  global.acervatorLoadTicker = loadTicker;
  global.acervatorTicker = {
    method: METHOD,
    slot: TICKER_SLOT,
    Ticker: Ticker,
    Headline: Headline,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    headlines: headlines,
    headlineAt: headlineAt,
    headlineOrder: headlineOrder,
    current: current,
    sources: sources,
    sourceOrder: sourceOrder,
    calls: calls,
    callOrder: callOrder,
    actionOrder: actionOrder,
    timerNames: timerNames,
    workerNames: workerNames,
    styleOf: styleOf,
    keptSheet: keptSheet,
    qtColour: qtColour,
    cursorOf: cursorOf,
    selectionOf: selectionOf,
    marginStyle: marginStyle,
    length: length,
    variableFor: variableFor,
    plainness: plainness,
    kinds: kinds,
    faults: faults,
    sent: sent,
    advance: advance,
    refresh: refresh,
    hover: hover,
    release: release,
    openStory: openStory,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTicker: renderTicker,
    mount: mount,
    redraw: redraw,
    forget: forget
  };
})(window);
