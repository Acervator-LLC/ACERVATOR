// Draws the Audio Suite tab from the audio_suite.state payload: the
// waveform strip, the music player and the ambient drone engine.
//
// Every colour, every word and every measurement is a field of the
// payload. The one value this module works out for itself is the alpha
// SHARE, because the payload carries Qt's 0-to-255 byte and a browser
// clamps anything above 1 to fully opaque.
(function (global) {
  "use strict";

  var METHOD = "audio_suite.state";

  var ACCESSIBLE_NAMES = "accessible_names";
  var ACTIONS = "actions";
  var ANIMATION_PHASE_GAIN = "animation_phase_gain";
  var ANIMATION_STEP_S = "animation_step_s";
  var BASE_FREQUENCIES = "base_frequencies";
  var BASE_FREQUENCY_INDEX = "base_frequency_index";
  var CONTROL_LABELS = "control_labels";
  var DETUNE_RANGE = "detune_range";
  var DETUNE_TOOLTIP = "detune_tooltip";
  var DRONE_BUTTON_LABELS = "drone_button_labels";
  var DRONE_TITLE = "drone_title";
  var KEY_NAMES = "key_names";
  var KEY_UP_TOOLTIP = "key_up_tooltip";
  var LAYER_LABEL_FORMAT = "layer_label_format";
  var LAYER_TOTAL = "layer_total";
  var LAYER_TRACE_ALPHA = "layer_trace_alpha";
  var LAYER_TRACE_COLOURS = "layer_trace_colours";
  var LAYER_TRACE_STEP_PX = "layer_trace_step_px";
  var LAYER_TRACE_WIDTH_PX = "layer_trace_width_px";
  var LFO_RANGE = "lfo_range";
  var LFO_TOOLTIP = "lfo_tooltip";
  var MEDIA_MISSING_TEXT = "media_missing_text";
  var MEDIA_STATES = "media_states";
  var MUSIC_BUTTON_LABELS = "music_button_labels";
  var MUSIC_LIST_MAX_HEIGHT_PX = "music_list_max_height_px";
  var MUSIC_TITLE = "music_title";
  var OFF_LABEL = "off_label";
  var OFF_VALUE = "off_value";
  var PLAY_LABEL = "play_label";
  var PRESET_NAMES = "preset_names";
  var RICHNESS_RANGE = "richness_range";
  var RICHNESS_TOOLTIP = "richness_tooltip";
  var RUN = "run";
  var SKIN = "skin";
  var SPLITTER_HANDLE_WIDTH_PX = "splitter_handle_width_px";
  var SPLITTER_SIZES_PX = "splitter_sizes_px";
  var TAB_MARGINS_PX = "tab_margins_px";
  var TAB_SPACING_PX = "tab_spacing_px";
  var TIMERS = "timers";
  var TRACE_AMPLITUDE_BASE_PX = "trace_amplitude_base_px";
  var TRACE_AMPLITUDE_STEP_PX = "trace_amplitude_step_px";
  var TRACE_CYCLES = "trace_cycles";
  var TRACE_PHASE_STEP = "trace_phase_step";
  var TRACE_RATE_BASE = "trace_rate_base";
  var TRACE_RATE_STEP = "trace_rate_step";
  var VOLUME_LABEL_WIDTH_PX = "volume_label_width_px";
  var VOLUME_RANGE_PCT = "volume_range_pct";
  var WAVEFORM_BACKGROUND_BOTTOM = "waveform_background_bottom";
  var WAVEFORM_BACKGROUND_TOP = "waveform_background_top";
  var WAVEFORM_IDLE_COLOUR = "waveform_idle_colour";
  var WAVEFORM_IDLE_FONT = "waveform_idle_font";
  var WAVEFORM_IDLE_TEXT = "waveform_idle_text";
  var WAVEFORM_KEY_BASELINE_PX = "waveform_key_baseline_px";
  var WAVEFORM_KEY_COLOUR = "waveform_key_colour";
  var WAVEFORM_KEY_FONT = "waveform_key_font";
  var WAVEFORM_KEY_FORMAT = "waveform_key_format";
  var WAVEFORM_KEY_INSET_PX = "waveform_key_inset_px";
  var WAVEFORM_MIN_HEIGHT_PX = "waveform_min_height_px";

  // Every top-level field the tab is drawn from. One that never arrives
  // is reported rather than drawn around.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAMES,
    ACTIONS,
    ANIMATION_PHASE_GAIN,
    ANIMATION_STEP_S,
    BASE_FREQUENCIES,
    BASE_FREQUENCY_INDEX,
    CONTROL_LABELS,
    DETUNE_RANGE,
    DETUNE_TOOLTIP,
    DRONE_BUTTON_LABELS,
    DRONE_TITLE,
    KEY_NAMES,
    KEY_UP_TOOLTIP,
    LAYER_LABEL_FORMAT,
    LAYER_TOTAL,
    LAYER_TRACE_ALPHA,
    LAYER_TRACE_COLOURS,
    LAYER_TRACE_STEP_PX,
    LAYER_TRACE_WIDTH_PX,
    LFO_RANGE,
    LFO_TOOLTIP,
    MEDIA_MISSING_TEXT,
    MEDIA_STATES,
    MUSIC_BUTTON_LABELS,
    MUSIC_LIST_MAX_HEIGHT_PX,
    MUSIC_TITLE,
    OFF_LABEL,
    OFF_VALUE,
    PLAY_LABEL,
    PRESET_NAMES,
    RICHNESS_RANGE,
    RICHNESS_TOOLTIP,
    RUN,
    SKIN,
    SPLITTER_HANDLE_WIDTH_PX,
    SPLITTER_SIZES_PX,
    TAB_MARGINS_PX,
    TAB_SPACING_PX,
    TIMERS,
    TRACE_AMPLITUDE_BASE_PX,
    TRACE_AMPLITUDE_STEP_PX,
    TRACE_CYCLES,
    TRACE_PHASE_STEP,
    TRACE_RATE_BASE,
    TRACE_RATE_STEP,
    VOLUME_LABEL_WIDTH_PX,
    VOLUME_RANGE_PCT,
    WAVEFORM_BACKGROUND_BOTTOM,
    WAVEFORM_BACKGROUND_TOP,
    WAVEFORM_IDLE_COLOUR,
    WAVEFORM_IDLE_FONT,
    WAVEFORM_IDLE_TEXT,
    WAVEFORM_KEY_BASELINE_PX,
    WAVEFORM_KEY_COLOUR,
    WAVEFORM_KEY_FONT,
    WAVEFORM_KEY_FORMAT,
    WAVEFORM_KEY_INSET_PX,
    WAVEFORM_MIN_HEIGHT_PX
  ];

  // The run report, and the live screen state inside it.
  var STATE = "state";
  var MEDIA = "media";
  var LAYER_PRESETS = "layer_presets";
  var LAYER_VOLUMES_PCT = "layer_volumes_pct";
  var LAYER_VOLUME_LABELS = "layer_volume_labels";
  var LAYER_PLAYING = "layer_playing";
  var KEY_INDEX = "key_index";
  var BASE_INDEX = "base_index";
  var DETUNE_PCT = "detune_pct";
  var LFO_PCT = "lfo_pct";
  var RICHNESS_PCT = "richness_pct";
  var DRONE_STATUS = "drone_status";
  var MUSIC_FILES = "music_files";
  var MUSIC_ROW = "music_row";
  var MUSIC_PLAYING = "music_playing";
  var MUSIC_VOLUME_PCT = "music_volume_pct";
  var MUSIC_BUTTON_LABEL = "music_button_label";
  var MUSIC_CAPTION = "music_caption";
  var WAVEFORM_LAYERS = "waveform_layers";
  var WAVEFORM_KEY = "waveform_key";
  var WAVEFORM_PHASE = "waveform_phase";

  var CONTROL_VOLUME = "volume";
  var CONTROL_KEY = "key";
  var CONTROL_BASE = "base";
  var CONTROL_DETUNE = "detune";
  var CONTROL_LFO = "lfo";
  var CONTROL_RICHNESS = "richness";

  var SKIN_LAYER_FRAME = "layer_frame";
  var SKIN_MUSIC_PLAY_BUTTON = "music_play_button";
  var SKIN_MUSIC_NOW_PLAYING = "music_now_playing";
  var SKIN_DRONE_PLAY_ALL_BUTTON = "drone_play_all_button";
  var SKIN_DRONE_STATUS = "drone_status";

  var NAME_TAB = "tab";
  var NAME_WAVEFORM = "waveform";
  var NAME_LAYER = "layer";
  var NAME_MUSIC_PANEL = "music_panel";
  var NAME_DRONE_PANEL = "drone_panel";

  // The library-missing state is the last the surface lists; in it the
  // music player shows one line of text instead of its controls.
  var LIBRARY_MISSING_AT = 2;

  // The play-all button is the second the drone panel shows, and the
  // key-up button the last. Only those two carry chrome of their own.
  var PLAY_ALL_AT = 1;

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt writes an alpha byte running to this; a browser wants the share
  // of full opacity, and paints anything above one solid.
  var ALPHA_SCALE = 255;
  var ALPHA_STEP = Math.pow(ALPHA_SCALE, -1);

  var HALF = 0.5;
  var TURN = Math.PI * 2;
  var HEX_MARK = "#";
  var HEX_RADIX = 16;
  var CHANNEL_DIGITS = 2;
  var CHANNELS = 3;
  var SHORT_HEX = 3;

  var RGBA_OPEN = "rgba(";
  var CLOSE = ")";
  var COMMA = ",";
  var PX = "px";
  var PT = "pt";
  var POINT_SPLIT = " ";
  var AXIS_SPLIT = ",";
  var EMPTY = "";
  var SLOT = "{}";

  var RULE_SPLIT = ";";
  var DECLARATION_SPLIT = ":";
  var WORD_SPLIT = "-";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";

  var GRADIENT_OPEN = "linear-gradient(to bottom,";
  var FLEX = "flex";
  var NONE = "none";
  var COLUMN = "column";
  var ROW = "row";
  var ABSOLUTE = "absolute";
  var RELATIVE = "relative";
  var SCROLL = "auto";
  var RANGE = "range";
  var BUTTON = "button";

  var PART_ATTR = "data-part";
  var INDEX_ATTR = "data-index";
  var LAYER_ATTR = "data-layer";
  var TRACE_ATTR = "data-trace-count";
  var ALPHA_ATTR = "data-alpha-share";
  var MEDIA_ATTR = "data-media";
  var PLAYING_ATTR = "data-playing";
  var CURRENT_ATTR = "data-current";
  var ARIA_LABEL = "aria-label";

  var PART_TAB = "tab";
  var PART_WAVEFORM = "waveform";
  var PART_IDLE = "waveform-idle";
  var PART_KEY = "waveform-key";
  var PART_TRACE = "waveform-trace";
  var PART_PANELS = "panels";
  var PART_MUSIC = "music-panel";
  var PART_DRONE = "drone-panel";
  var PART_TITLE = "panel-title";
  var PART_MEDIA_MISSING = "media-missing";
  var PART_MUSIC_LIST = "music-list";
  var PART_MUSIC_FILE = "music-file";
  var PART_MUSIC_BUTTON = "music-button";
  var PART_MUSIC_VOLUME = "music-volume";
  var PART_MUSIC_CAPTION = "music-caption";
  var PART_ROW = "control-row";
  var PART_CONTROL = "control";
  var PART_CONTROL_LABEL = "control-label";
  var PART_LAYER = "layer";
  var PART_LAYER_LABEL = "layer-label";
  var PART_LAYER_PRESET = "layer-preset";
  var PART_LAYER_VOLUME = "layer-volume";
  var PART_LAYER_VOLUME_LABEL = "layer-volume-label";
  var PART_DRONE_BUTTON = "drone-button";
  var PART_DRONE_STATUS = "drone-status";

  var held = null;
  var suiteFaults = [];
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
    return value === null ? NULL_FAULT : typeof value;
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

  // One "{}" slot filled, which is the only format the surface writes.
  function filled(format, value) {
    return typeof format === "string" ? format.replace(SLOT, String(value)) : EMPTY;
  }

  // -- colour ----------------------------------------------------------
  //
  // The payload carries Qt's own values: a "#rrggbb" and a 0-to-255 alpha
  // byte. CSS reads a share of full opacity and clamps anything above 1,
  // so a byte handed straight to a browser paints the trace solid.

  function alphaShare(byte) {
    return isNumber(byte) ? byte * ALPHA_STEP : undefined;
  }

  function channels(colour) {
    var digits = typeof colour === "string" ? colour.split(HEX_MARK).pop() : EMPTY;
    if (digits.length === SHORT_HEX) {
      digits = digits
        .split(EMPTY)
        .map(function (one) {
          return one + one;
        })
        .join(EMPTY);
    }
    var found = [];
    var at;
    for (at = 0; at < CHANNELS; at += 1) {
      found.push(
        parseInt(
          digits.slice(at * CHANNEL_DIGITS, (at + 1) * CHANNEL_DIGITS),
          HEX_RADIX
        )
      );
    }
    return found;
  }

  // One published colour and one Qt alpha byte as the rgba() a browser reads.
  function traceStroke(colour, byte) {
    var parts = channels(colour);
    if (parts.some(isNaN)) {
      return undefined;
    }
    return (
      RGBA_OPEN +
      parts[0] +
      COMMA +
      parts[1] +
      COMMA +
      parts[2] +
      COMMA +
      alphaShare(byte) +
      CLOSE
    );
  }

  function backgroundWash(top, bottom) {
    if (typeof top !== "string" || typeof bottom !== "string") {
      return undefined;
    }
    return GRADIENT_OPEN + top + COMMA + bottom + CLOSE;
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
  // block's contents are what a panel carries, the selector is Qt's own.
  function styleOf(model, name) {
    var sheet = objectField(model, SKIN)[name];
    if (typeof sheet !== "string") {
      return null;
    }
    var opened = sheet.indexOf(BLOCK_OPEN);
    var body =
      opened < 0
        ? sheet
        : sheet.slice(opened + 1, sheet.lastIndexOf(BLOCK_CLOSE));
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

  // A published (family, size) pair as the two CSS values that carry it.
  function fontOf(pair) {
    var named = Array.isArray(pair) ? pair : [];
    return {
      fontFamily: text(named[0]),
      fontSize: isNumber(named[1]) ? String(named[1]) + PT : undefined
    };
  }

  // -- the waveform ----------------------------------------------------

  function stateOf(model) {
    return objectField(objectField(model, RUN), STATE);
  }

  function drawnLayerTotal(model) {
    var wanted = stateOf(model)[WAVEFORM_LAYERS];
    var most = model[LAYER_TOTAL];
    if (!isNumber(wanted) || !isNumber(most)) {
      return 0;
    }
    return Math.max(0, Math.min(wanted, most));
  }

  function amplitudeFor(model, layer) {
    return model[TRACE_AMPLITUDE_BASE_PX] + layer * model[TRACE_AMPLITUDE_STEP_PX];
  }

  // The points of one trace, left to right, across a box `width` wide and
  // `height` tall. Every constant comes from the payload.
  function tracePoints(model, layer, width, height, phase) {
    var step = model[LAYER_TRACE_STEP_PX];
    if (!isNumber(width) || !isNumber(step) || step <= 0) {
      return [];
    }
    var middle = height * HALF;
    var reach = amplitudeFor(model, layer);
    var rate = model[TRACE_RATE_BASE] + layer * model[TRACE_RATE_STEP];
    var turn = layer * model[TRACE_PHASE_STEP];
    var span = Math.pow(width, -1) * model[TRACE_CYCLES];
    var found = [];
    var at;
    for (at = 0; at < width; at += step) {
      var moment = phase + at * span;
      found.push([at, middle + reach * Math.sin(TURN * rate * moment + turn)]);
    }
    return found;
  }

  function pointsText(points) {
    return points
      .map(function (one) {
        return String(one[0]) + AXIS_SPLIT + String(one[1]);
      })
      .join(POINT_SPLIT);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function Trace(props) {
    var model = props.model;
    var colours = listField(model, LAYER_TRACE_COLOURS);
    var traceProps = {
      key: props.layer,
      fill: NONE,
      stroke: traceStroke(colours[props.layer], model[LAYER_TRACE_ALPHA]),
      strokeWidth: model[LAYER_TRACE_WIDTH_PX],
      points: pointsText(
        tracePoints(model, props.layer, props.width, props.height, props.phase)
      )
    };
    traceProps[PART_ATTR] = PART_TRACE;
    traceProps[LAYER_ATTR] = String(props.layer);
    return element("polyline", traceProps);
  }

  function Waveform(props) {
    var model = props.model;
    var screen = stateOf(model);
    var height = model[WAVEFORM_MIN_HEIGHT_PX];
    var drawn = drawnLayerTotal(model);
    var stripProps = {
      style: {
        position: RELATIVE,
        height: pixels(height),
        background: backgroundWash(
          model[WAVEFORM_BACKGROUND_TOP],
          model[WAVEFORM_BACKGROUND_BOTTOM]
        )
      }
    };
    stripProps[PART_ATTR] = PART_WAVEFORM;
    stripProps[ARIA_LABEL] = text(objectField(model, ACCESSIBLE_NAMES)[NAME_WAVEFORM]);
    stripProps[TRACE_ATTR] = String(drawn);
    stripProps[ALPHA_ATTR] = text(alphaShare(model[LAYER_TRACE_ALPHA]));

    if (drawn === 0) {
      var idle = fontOf(model[WAVEFORM_IDLE_FONT]);
      var idleProps = {
        style: {
          color: text(model[WAVEFORM_IDLE_COLOUR]),
          fontFamily: idle.fontFamily,
          fontSize: idle.fontSize
        }
      };
      idleProps[PART_ATTR] = PART_IDLE;
      return element(
        "div",
        stripProps,
        element("div", idleProps, text(model[WAVEFORM_IDLE_TEXT]))
      );
    }

    var traces = [];
    var layer;
    for (layer = 0; layer < drawn; layer += 1) {
      traces.push(
        element(Trace, {
          key: layer,
          model: model,
          layer: layer,
          width: props.width,
          height: height,
          phase: screen[WAVEFORM_PHASE]
        })
      );
    }
    var caption = fontOf(model[WAVEFORM_KEY_FONT]);
    var keyProps = {
      style: {
        position: ABSOLUTE,
        right: pixels(model[WAVEFORM_KEY_INSET_PX]),
        bottom: pixels(model[WAVEFORM_KEY_BASELINE_PX]),
        color: text(model[WAVEFORM_KEY_COLOUR]),
        fontFamily: caption.fontFamily,
        fontSize: caption.fontSize
      }
    };
    keyProps[PART_ATTR] = PART_KEY;
    return element(
      "div",
      stripProps,
      element("svg", { width: props.width, height: height }, traces),
      element(
        "span",
        keyProps,
        filled(model[WAVEFORM_KEY_FORMAT], screen[WAVEFORM_KEY])
      )
    );
  }

  // -- the two panels --------------------------------------------------

  function ControlLabel(props) {
    var labelProps = { key: props.name };
    labelProps[PART_ATTR] = PART_CONTROL_LABEL;
    labelProps[INDEX_ATTR] = props.name;
    return element("span", labelProps, text(props.wording));
  }

  function Slider(props) {
    var range = Array.isArray(props.range) ? props.range : [];
    var sliderProps = {
      type: RANGE,
      min: range[0],
      max: range[1],
      value: props.value,
      title: text(props.tooltip),
      disabled: true,
      onChange: function () {}
    };
    sliderProps[PART_ATTR] = props.part;
    sliderProps[INDEX_ATTR] = props.name;
    return element("input", sliderProps);
  }

  function ControlRow(props) {
    var rowProps = { style: { display: FLEX, flexDirection: ROW } };
    rowProps[PART_ATTR] = PART_ROW;
    return element.apply(null, ["div", rowProps].concat(props.children));
  }

  function musicHasControls(model) {
    var states = listField(model, MEDIA_STATES);
    return stateOf(model)[MEDIA] !== states[LIBRARY_MISSING_AT];
  }

  function MusicPanel(props) {
    var model = props.model;
    var screen = stateOf(model);
    var wording = objectField(model, CONTROL_LABELS);
    var panelProps = {
      style: { flexGrow: listField(model, SPLITTER_SIZES_PX)[0] }
    };
    panelProps[PART_ATTR] = PART_MUSIC;
    panelProps[ARIA_LABEL] = text(
      objectField(model, ACCESSIBLE_NAMES)[NAME_MUSIC_PANEL]
    );
    panelProps[MEDIA_ATTR] = text(screen[MEDIA]);
    panelProps[PLAYING_ATTR] = text(screen[MUSIC_PLAYING]);
    var titleProps = {};
    titleProps[PART_ATTR] = PART_TITLE;
    var title = element("div", titleProps, text(model[MUSIC_TITLE]));

    if (!musicHasControls(model)) {
      var missingProps = {};
      missingProps[PART_ATTR] = PART_MEDIA_MISSING;
      return element(
        "div",
        panelProps,
        title,
        element("div", missingProps, text(model[MEDIA_MISSING_TEXT]))
      );
    }

    var listProps = {
      style: {
        maxHeight: pixels(model[MUSIC_LIST_MAX_HEIGHT_PX]),
        overflowY: SCROLL
      }
    };
    listProps[PART_ATTR] = PART_MUSIC_LIST;
    var files = listField(screen, MUSIC_FILES).map(function (one, at) {
      var fileProps = { key: at };
      fileProps[PART_ATTR] = PART_MUSIC_FILE;
      fileProps[INDEX_ATTR] = String(at);
      fileProps[CURRENT_ATTR] = text(at === screen[MUSIC_ROW]);
      return element("li", fileProps, text(one));
    });

    // The play button carries the label the screen state holds, which is
    // the play word or the pause word, never both.
    var buttons = listField(model, MUSIC_BUTTON_LABELS).map(function (one, at) {
      var plays = one === model[PLAY_LABEL];
      var buttonProps = {
        key: at,
        type: BUTTON,
        disabled: true,
        style: plays ? styleOf(model, SKIN_MUSIC_PLAY_BUTTON) : null
      };
      buttonProps[PART_ATTR] = PART_MUSIC_BUTTON;
      buttonProps[INDEX_ATTR] = String(at);
      return element(
        "button",
        buttonProps,
        text(plays ? screen[MUSIC_BUTTON_LABEL] : one)
      );
    });

    var captionProps = { style: styleOf(model, SKIN_MUSIC_NOW_PLAYING) };
    captionProps[PART_ATTR] = PART_MUSIC_CAPTION;

    return element(
      "div",
      panelProps,
      title,
      element("ul", listProps, files),
      element(ControlRow, { children: buttons }),
      element(ControlRow, {
        children: [
          element(ControlLabel, {
            key: CONTROL_VOLUME,
            name: CONTROL_VOLUME,
            wording: wording[CONTROL_VOLUME]
          }),
          element(Slider, {
            key: PART_MUSIC_VOLUME,
            part: PART_MUSIC_VOLUME,
            name: CONTROL_VOLUME,
            range: model[VOLUME_RANGE_PCT],
            value: screen[MUSIC_VOLUME_PCT],
            tooltip: null
          })
        ]
      }),
      element("div", captionProps, text(screen[MUSIC_CAPTION]))
    );
  }

  function Layer(props) {
    var model = props.model;
    var screen = stateOf(model);
    var wording = objectField(model, CONTROL_LABELS);
    var at = props.layer;
    var layerProps = { key: at, style: styleOf(model, SKIN_LAYER_FRAME) };
    layerProps[PART_ATTR] = PART_LAYER;
    layerProps[LAYER_ATTR] = String(at);
    layerProps[PLAYING_ATTR] = text(listField(screen, LAYER_PLAYING)[at]);
    layerProps[ARIA_LABEL] = text(objectField(model, ACCESSIBLE_NAMES)[NAME_LAYER]);

    var labelProps = {};
    labelProps[PART_ATTR] = PART_LAYER_LABEL;

    var chosen = listField(screen, LAYER_PRESETS)[at];
    var presetProps = {
      value: chosen === undefined ? model[OFF_VALUE] : chosen,
      disabled: true,
      onChange: function () {}
    };
    presetProps[PART_ATTR] = PART_LAYER_PRESET;
    presetProps[LAYER_ATTR] = String(at);
    var options = [
      element(
        "option",
        { key: model[OFF_LABEL], value: model[OFF_VALUE] },
        text(model[OFF_LABEL])
      )
    ].concat(
      listField(model, PRESET_NAMES).map(function (one) {
        return element("option", { key: one, value: one }, text(one));
      })
    );

    var volumeLabelProps = {
      style: { width: pixels(model[VOLUME_LABEL_WIDTH_PX]) }
    };
    volumeLabelProps[PART_ATTR] = PART_LAYER_VOLUME_LABEL;
    volumeLabelProps[LAYER_ATTR] = String(at);

    return element(
      "div",
      layerProps,
      element("div", labelProps, filled(model[LAYER_LABEL_FORMAT], at + 1)),
      element("select", presetProps, options),
      element(ControlLabel, {
        name: CONTROL_VOLUME,
        wording: wording[CONTROL_VOLUME]
      }),
      element(Slider, {
        part: PART_LAYER_VOLUME,
        name: String(at),
        range: model[VOLUME_RANGE_PCT],
        value: listField(screen, LAYER_VOLUMES_PCT)[at],
        tooltip: null
      }),
      element(
        "span",
        volumeLabelProps,
        text(listField(screen, LAYER_VOLUME_LABELS)[at])
      )
    );
  }

  function DronePanel(props) {
    var model = props.model;
    var screen = stateOf(model);
    var wording = objectField(model, CONTROL_LABELS);
    var panelProps = {
      style: { flexGrow: listField(model, SPLITTER_SIZES_PX)[1] }
    };
    panelProps[PART_ATTR] = PART_DRONE;
    panelProps[ARIA_LABEL] = text(
      objectField(model, ACCESSIBLE_NAMES)[NAME_DRONE_PANEL]
    );
    var titleProps = {};
    titleProps[PART_ATTR] = PART_TITLE;

    var keyProps = {
      value: listField(model, KEY_NAMES)[screen[KEY_INDEX]],
      disabled: true,
      onChange: function () {}
    };
    keyProps[PART_ATTR] = PART_CONTROL;
    keyProps[INDEX_ATTR] = CONTROL_KEY;
    var keys = listField(model, KEY_NAMES).map(function (one) {
      return element("option", { key: one, value: one }, text(one));
    });

    var bases = listField(model, BASE_FREQUENCIES);
    var atBase = bases[screen[BASE_INDEX]];
    var baseProps = {
      value: Array.isArray(atBase) ? atBase[0] : undefined,
      disabled: true,
      onChange: function () {}
    };
    baseProps[PART_ATTR] = PART_CONTROL;
    baseProps[INDEX_ATTR] = CONTROL_BASE;
    var baseOptions = bases.map(function (one) {
      return element("option", { key: one[0], value: one[0] }, text(one[0]));
    });

    var layers = [];
    var at;
    for (at = 0; at < model[LAYER_TOTAL]; at += 1) {
      layers.push(element(Layer, { key: at, model: model, layer: at }));
    }

    var labels = listField(model, DRONE_BUTTON_LABELS);
    var lastAt = labels.length - 1;
    var buttons = labels.map(function (one, position) {
      var buttonProps = {
        key: position,
        type: BUTTON,
        disabled: true,
        title: position === lastAt ? text(model[KEY_UP_TOOLTIP]) : undefined,
        style:
          position === PLAY_ALL_AT
            ? styleOf(model, SKIN_DRONE_PLAY_ALL_BUTTON)
            : null
      };
      buttonProps[PART_ATTR] = PART_DRONE_BUTTON;
      buttonProps[INDEX_ATTR] = String(position);
      return element("button", buttonProps, text(one));
    });

    var statusProps = { style: styleOf(model, SKIN_DRONE_STATUS) };
    statusProps[PART_ATTR] = PART_DRONE_STATUS;

    return element(
      "div",
      panelProps,
      element("div", titleProps, text(model[DRONE_TITLE])),
      element(ControlRow, {
        children: [
          element(ControlLabel, {
            key: CONTROL_KEY,
            name: CONTROL_KEY,
            wording: wording[CONTROL_KEY]
          }),
          element("select", keyProps, keys),
          element(ControlLabel, {
            key: CONTROL_BASE,
            name: CONTROL_BASE,
            wording: wording[CONTROL_BASE]
          }),
          element("select", baseProps, baseOptions)
        ]
      }),
      element(ControlRow, {
        children: [
          element(ControlLabel, {
            key: CONTROL_DETUNE,
            name: CONTROL_DETUNE,
            wording: wording[CONTROL_DETUNE]
          }),
          element(Slider, {
            key: CONTROL_DETUNE,
            part: PART_CONTROL,
            name: CONTROL_DETUNE,
            range: model[DETUNE_RANGE],
            value: screen[DETUNE_PCT],
            tooltip: model[DETUNE_TOOLTIP]
          }),
          element(ControlLabel, {
            key: CONTROL_LFO,
            name: CONTROL_LFO,
            wording: wording[CONTROL_LFO]
          }),
          element(Slider, {
            key: CONTROL_LFO,
            part: PART_CONTROL,
            name: CONTROL_LFO,
            range: model[LFO_RANGE],
            value: screen[LFO_PCT],
            tooltip: model[LFO_TOOLTIP]
          }),
          element(ControlLabel, {
            key: CONTROL_RICHNESS,
            name: CONTROL_RICHNESS,
            wording: wording[CONTROL_RICHNESS]
          }),
          element(Slider, {
            key: CONTROL_RICHNESS,
            part: PART_CONTROL,
            name: CONTROL_RICHNESS,
            range: model[RICHNESS_RANGE],
            value: screen[RICHNESS_PCT],
            tooltip: model[RICHNESS_TOOLTIP]
          })
        ]
      }),
      layers,
      element(ControlRow, { children: buttons }),
      element("div", statusProps, text(screen[DRONE_STATUS]))
    );
  }

  function AudioSuite(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var margins = listField(model, TAB_MARGINS_PX);
    var tabProps = {
      style: {
        display: FLEX,
        flexDirection: COLUMN,
        gap: pixels(model[TAB_SPACING_PX]),
        paddingLeft: pixels(margins[0]),
        paddingTop: pixels(margins[1]),
        paddingRight: pixels(margins[2]),
        paddingBottom: pixels(margins[3])
      }
    };
    tabProps[PART_ATTR] = PART_TAB;
    tabProps[ARIA_LABEL] = text(objectField(model, ACCESSIBLE_NAMES)[NAME_TAB]);
    var panelsProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        gap: pixels(model[SPLITTER_HANDLE_WIDTH_PX])
      }
    };
    panelsProps[PART_ATTR] = PART_PANELS;
    return element(
      "div",
      tabProps,
      element(Waveform, { model: model, width: props.width }),
      element(
        "div",
        panelsProps,
        element(MusicPanel, { model: model }),
        element(DronePanel, { model: model })
      )
    );
  }

  // -- holding the payload ---------------------------------------------

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        suiteFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null) {
        suiteFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  function heldFieldTotal() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function setAudioSuite(model) {
    if (!isPlainObject(model)) {
      held = null;
      suiteFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: suiteFaults.slice() };
    }
    held = { model: model };
    suiteFaults = [];
    checkFields(model);
    return {
      declared: { fields: DECLARED_FIELDS.length },
      held: { fields: heldFieldTotal(), layers: drawnLayerTotal(model) },
      faults: suiteFaults.slice()
    };
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadAudioSuite(params) {
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
        setAudioSuite(model);
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

  function screenState() {
    return held === null ? {} : copyOf(stateOf(held.model));
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function traceAlphaShare() {
    return held === null ? undefined : alphaShare(held.model[LAYER_TRACE_ALPHA]);
  }

  function traceStrokes() {
    if (held === null) {
      return [];
    }
    var model = held.model;
    return listField(model, LAYER_TRACE_COLOURS).map(function (one) {
      return traceStroke(one, model[LAYER_TRACE_ALPHA]);
    });
  }

  function layersDrawn() {
    return held === null ? 0 : drawnLayerTotal(held.model);
  }

  function traceOf(layer, width, height, phase) {
    return held === null ? [] : tracePoints(held.model, layer, width, height, phase);
  }

  // The points of every trace the strip actually draws, which is none
  // while no layer is sounding.
  function drawnTraces(width, height) {
    if (held === null) {
      return [];
    }
    var phase = stateOf(held.model)[WAVEFORM_PHASE];
    var found = [];
    var layer;
    for (layer = 0; layer < drawnLayerTotal(held.model); layer += 1) {
      found.push(tracePoints(held.model, layer, width, height, phase));
    }
    return found;
  }

  function amplitudeOf(layer) {
    return held === null ? undefined : amplitudeFor(held.model, layer);
  }

  function animationDelays() {
    return held === null ? {} : copyOf(objectField(held.model, TIMERS));
  }

  function controlWording() {
    return held === null ? {} : copyOf(objectField(held.model, CONTROL_LABELS));
  }

  function droneButtonLabels() {
    return held === null ? [] : listField(held.model, DRONE_BUTTON_LABELS).slice();
  }

  function musicControlsShown() {
    return held === null ? false : musicHasControls(held.model);
  }

  function skinOf(name) {
    return held === null ? null : styleOf(held.model, name);
  }

  function faults() {
    return suiteFaults.slice();
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

  function renderAudioSuite(target, model, width) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(AudioSuite, { model: payload, width: width }));
  }

  function forget() {
    held = null;
    suiteFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetAudioSuite = setAudioSuite;
  global.acervatorLoadAudioSuite = loadAudioSuite;
  global.acervatorAudioSuite = {
    method: METHOD,
    AudioSuite: AudioSuite,
    Waveform: Waveform,
    MusicPanel: MusicPanel,
    DronePanel: DronePanel,
    Layer: Layer,
    Trace: Trace,
    field: field,
    screenState: screenState,
    declaredFields: declaredFields,
    traceAlphaShare: traceAlphaShare,
    traceStrokes: traceStrokes,
    layersDrawn: layersDrawn,
    traceOf: traceOf,
    drawnTraces: drawnTraces,
    amplitudeOf: amplitudeOf,
    animationDelays: animationDelays,
    controlWording: controlWording,
    droneButtonLabels: droneButtonLabels,
    musicControlsShown: musicControlsShown,
    skinOf: skinOf,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderAudioSuite: renderAudioSuite,
    forget: forget
  };
})(window);
