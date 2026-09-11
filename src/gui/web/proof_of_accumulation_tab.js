// The Proof of Accumulation tab shell, as the Python surface serves it.
//
// The top row is bisected: VesselPanel draws the current Vessel and its details
// left of the divider, RightRegion draws MapRegion right of it until
// encounter.running is set and EncounterRegion after that, with the square enemy
// screen inside it. The party window takes the lower half. The Quintessence balance sits
// in the party header and the wallet opens as a panel over the party window.
// Four subtabs sit above the zones and selectSubtab draws one of them; the map
// entry and the player window's map button both read the payload's reachable
// flag. A row of control buttons sits under the state line and fireControl sends
// the params the payload gave that control, then redraws from the answer, so the
// verdict and the figures on screen are the mechanism's own. MeterPair draws the
// block fill and the turn completion side by side in the player window, and
// ResetPanel names the two chain files and both reasons a reset carries.
// Glyph draws one stand-in mark a kind; GlyphLegend lists them all and
// GlyphAbsence names what nothing supplies.
// Every word on screen comes from the payload.
(function (global) {
  "use strict";

  var METHOD = "proof_of_accumulation_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BUILT = "built";
  var CHAIN = "chain";
  var CHAIN_RESET = "chain_reset";
  var CHARACTER_STATS = "character_stats";
  var CLASSES = "classes";
  var CONSERVATION = "conservation";
  var CONTROLS = "controls";
  var ENCOUNTER = "encounter";
  var EVENT = "event";
  var GEAR = "gear";
  var HEADING = "heading";
  var ISSUE = "issue";
  var ISSUE_TEXT = "issue_text";
  var MAP = "map";
  var MAP_MARKS = "map_marks";
  var METERS = "meters";
  var METRIC_SOURCES = "metric_sources";
  var METHOD_FIELD = "method";
  var MODES = "modes";
  var PARTICIPANTS = "participants";
  var PARTY = "party";
  var PICK_NOTE = "pick_note";
  var REDISTRIBUTION = "redistribution";
  var SEASON = "season";
  var SKILL_TREE = "skill_tree";
  var SKILLS = "skills";
  var STATE_TEXT = "state_text";
  var SUBTAB = "subtab";
  var SUBTABS = "subtabs";
  var VESSEL = "vessel";
  var WALLET = "wallet";
  var ZONES = "zones";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BUILT,
    CHAIN,
    CHAIN_RESET,
    CHARACTER_STATS,
    CLASSES,
    CONSERVATION,
    CONTROLS,
    ENCOUNTER,
    EVENT,
    GEAR,
    HEADING,
    ISSUE,
    ISSUE_TEXT,
    MAP,
    MAP_MARKS,
    METERS,
    METRIC_SOURCES,
    METHOD_FIELD,
    MODES,
    PARTICIPANTS,
    PARTY,
    PICK_NOTE,
    REDISTRIBUTION,
    SEASON,
    SKILL_TREE,
    SKILLS,
    STATE_TEXT,
    SUBTAB,
    SUBTABS,
    VESSEL,
    WALLET,
    ZONES
  ];

  var PLAYER_WINDOW = "player_window";
  var ENEMY_SCREEN = "enemy_screen";
  var PARTY_WINDOW = "party_window";
  var ZONE_ORDER = [PLAYER_WINDOW, ENEMY_SCREEN, PARTY_WINDOW];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var ZONE_COUNT_FAULT = "zone-count";
  var ZONE_ORDER_FAULT = "zone-order";

  var NO_BRIDGE = "the preload bridge is not present";

  var TAB_CLASS = "acervator-poa-tab";

  var PART_ATTR = "data-part";
  var ZONE_ATTR = "data-zone";
  var CHAIN_ATTR = "data-chain";
  var ISSUE_ATTR = "data-issue";
  var OPEN_ATTR = "data-wallet-open";

  var HEADING_PART = "heading";
  var STATE_PART = "state";
  var UPPER_PART = "upper-band";
  var SUBTAB_BAR_PART = "subtab-bar";
  var SUBTAB_BUTTON_PART = "subtab-button";
  var SUBTAB_PANEL_PART = "subtab-panel";
  var SUBTAB_TITLE_PART = "subtab-title";

  // A button the running event does not open carries data-reachable="false".
  var REACHABLE_ATTR = "data-reachable";
  var SELECTED_ATTR = "data-selected";
  var SUBTAB_ATTR = "data-subtab";

  var STATS_PANEL_PART = "stats-panel";
  var STAT_LIST_PART = "stat-list";
  var STAT_ROW_PART = "stat-row";
  var STAT_METRIC_PART = "stat-metric";
  var STAT_SOURCE_PART = "stat-source";
  var STAT_VALUE_PART = "stat-value";
  var STAT_COUNT_PART = "stat-count";
  var STAT_NOTE_PART = "stat-note";
  var STAT_SEAM_PART = "stat-seam";

  var GEAR_PANEL_PART = "gear-panel";
  var GEAR_LIST_PART = "gear-list";
  var GEAR_ROW_PART = "gear-row";
  var GEAR_LABEL_PART = "gear-label";
  var GEAR_VALUE_PART = "gear-value";
  var GEAR_NOTE_PART = "gear-note";
  var GEAR_ABSENT_PART = "gear-absent";

  var TREE_PANEL_PART = "tree-panel";
  var TREE_LIST_PART = "tree-list";
  var TREE_ROW_PART = "tree-row";
  var TREE_LEVEL_PART = "tree-level";
  var TREE_COST_PART = "tree-cost";
  var TREE_EFFECT_PART = "tree-effect";
  var TREE_BLEED_PART = "tree-bleed";
  var TREE_STANDING_PART = "tree-standing";
  var TREE_LIST_NOTE_PART = "tree-list-note";
  var TREE_NOTE_PART = "tree-note";

  // One glyph span a kind. data-kind names the kind and data-codepoint the glyph,
  // so a reader can tell which mark drew without reading the character itself.
  var GLYPH_PART = "glyph";
  var GLYPH_LEGEND_PART = "glyph-legend";
  var GLYPH_ABSENCE_PART = "glyph-absence";
  var GLYPH_TITLE_PART = "glyph-title";
  var GLYPH_FAMILY_PART = "glyph-family";
  var GLYPH_FAMILY_NAME_PART = "glyph-family-name";
  var GLYPH_LIST_PART = "glyph-list";
  var GLYPH_ROW_PART = "glyph-row";
  var GLYPH_LABEL_PART = "glyph-label";
  var GLYPH_CODEPOINT_PART = "glyph-codepoint";
  var GLYPH_COUNT_PART = "glyph-count";
  var GLYPH_COLOUR_PART = "glyph-colour";
  var GLYPH_ART_PART = "glyph-art";
  var GLYPH_ABSENT_TITLE_PART = "glyph-absent-title";
  var GLYPH_ABSENT_LIST_PART = "glyph-absent-list";
  var GLYPH_ABSENT_ROW_PART = "glyph-absent-row";
  var GLYPH_ABSENT_NAME_PART = "glyph-absent-name";
  var GLYPH_ABSENT_NOTE_PART = "glyph-absent-note";

  var KIND_ATTR = "data-kind";
  var CODEPOINT_ATTR = "data-codepoint";
  var FAMILY_ATTR = "data-family";

  var CSS_VAR_OPEN = "var(--";
  var CSS_VAR_CLOSE = ")";

  var MAP_PANEL_PART = "map-panel";
  var MAP_NOTE_PART = "map-note";
  var MAP_CONTROL_PART = "map-control";
  var MAP_REFUSAL_PART = "map-refusal";
  var MAP_OPEN_PART = "map-open";
  var MAP_REGION_PART = "map-region";
  var MAP_REGION_TITLE_PART = "map-region-title";

  // The top row's divider and the right half it separates the Vessel from.
  var TOP_DIVIDER_PART = "top-divider";
  var RIGHT_REGION_PART = "right-region";
  var ENCOUNTER_REGION_PART = "encounter-region";
  var ENCOUNTER_TEXT_PART = "encounter-text";
  var ENCOUNTER_TITLE_PART = "encounter-title";
  var ENEMY_SLOT_PART = "enemy-slot";
  var ENCOUNTER_NOTE_PART = "encounter-note";
  var TACTICAL_NOTE_PART = "tactical-note";

  // The right half carries data-encounter, which says which of its two states drew.
  var ENCOUNTER_ATTR = "data-encounter";

  var VESSEL_PANEL_PART = "vessel-panel";
  var VESSEL_LIST_PART = "vessel-list";
  var VESSEL_ROW_PART = "vessel-row";
  var VESSEL_ROW_LABEL_PART = "vessel-row-label";
  var VESSEL_ROW_VALUE_PART = "vessel-row-value";
  var VESSEL_DETAILS_TITLE_PART = "vessel-details-title";
  var VESSEL_DETAILS_LIST_PART = "vessel-details-list";
  var VESSEL_NOTE_PART = "vessel-note";
  var VESSEL_BOUND_PART = "vessel-bound";
  var VESSEL_ABSENT_TITLE_PART = "vessel-absent-title";
  var VESSEL_ABSENT_LIST_PART = "vessel-absent-list";
  var VESSEL_ABSENT_ROW_PART = "vessel-absent-row";
  var VESSEL_ABSENT_NAME_PART = "vessel-absent-name";
  var VESSEL_ABSENT_NOTE_PART = "vessel-absent-note";
  var VESSEL_CLICK_NOTE_PART = "vessel-click-note";
  var ZONE_TITLE_PART = "zone-title";
  var ZONE_PLACEHOLDER_PART = "zone-placeholder";
  var PARTY_HEADER_PART = "party-header";
  var PARTY_PAGE_PART = "party-page";
  var PARTY_PAGES_PART = "party-pages";
  var PARTY_GROUP_PART = "party-group";
  var PARTY_SLOT_PART = "party-slot";
  var SLOT_NAME_PART = "slot-name";
  var SLOT_SYMBOL_PART = "slot-symbol";
  var SLOT_CLASS_PART = "slot-class";
  var SLOT_LEVEL_PART = "slot-level";
  var SLOT_IMPETUS_PART = "slot-impetus";
  var SLOT_HEALTH_PART = "slot-health";
  var SLOT_MARK_PART = "slot-mark";
  var MARK_SEAM_NOTE_PART = "mark-seam-note";

  // A slot with no mark carries no data-mark, so the CSS paints nothing there.
  var MARK_ATTR = "data-mark";
  var EVENT_BAND_PART = "event-band";
  var EVENT_LABEL_PART = "event-label";
  var EVENT_VARIANT_PART = "event-variant";
  var EVENT_TURN_PART = "event-turn";
  var EVENT_IMPETUS_PART = "event-impetus";
  var MODE_LIST_PART = "mode-list";
  var MODE_ROW_PART = "mode-row";
  var MODE_NAME_PART = "mode-name";
  var MODE_VARIANT_PART = "mode-variant";
  var MODE_TURN_PART = "mode-turn";
  var MODE_RANKS_PART = "mode-ranks";
  var PICK_NOTE_PART = "pick-note";
  var CLASS_LIST_PART = "class-list";
  var CLASS_ROW_PART = "class-row";
  var CLASS_NAME_PART = "class-name";
  var CLASS_ROLE_PART = "class-role";
  var SKILL_PANEL_PART = "skill-panel";
  var SKILL_TITLE_PART = "skill-title";
  var SKILL_STANDING_PART = "skill-standing";
  var SKILL_GATE_PART = "skill-gate";
  var SKILL_TOP_OUT_PART = "skill-top-out";
  var SKILL_DURATION_PART = "skill-duration";
  var SKILL_LIST_PART = "skill-list";
  var SKILL_ROW_PART = "skill-row";
  var SKILL_LEVEL_PART = "skill-level";
  var SKILL_COST_PART = "skill-cost";
  var SKILL_REACH_PART = "skill-reach";
  var SKILL_EFFECT_PART = "skill-effect";
  var SKILL_BLEED_PART = "skill-bleed";
  var SKILL_NOTE_PART = "skill-note";

  var CHAIN_LABEL_PART = "chain-label";
  var CHAIN_BUTTON_PART = "chain-button";
  var EVENT_PICK_LABEL_PART = "event-pick-label";
  var EVENT_BUTTON_PART = "event-button";

  // The event type a picker button selects, which its own params carry.
  var EVENT_ATTR = "data-event";

  var CONTROL_BAR_PART = "control-bar";
  var CONTROL_BUTTON_PART = "control-button";
  var CONTROL_RESULT_PART = "control-result";
  var CONTROL_MESSAGE_PART = "control-message";
  var CONTROL_ROW_PART = "control-row";
  var CONTROL_ROW_LABEL_PART = "control-row-label";
  var CONTROL_ROW_VALUE_PART = "control-row-value";
  var CONTROL_NOTE_PART = "control-note";

  // The verdict the surface answered for the control that was fired last.
  var ACTION_ATTR = "data-action";
  var ACTED_ATTR = "data-acted";

  var KEEP_PANEL_PART = "keep-panel";
  var KEEP_TITLE_PART = "keep-title";
  var KEEP_ROW_PART = "keep-row";
  var KEEP_ROW_LABEL_PART = "keep-row-label";
  var KEEP_ROW_VALUE_PART = "keep-row-value";
  var KEEP_NOTE_PART = "keep-note";

  var METER_PAIR_PART = "meter-pair";
  var METER_PAIR_TITLE_PART = "meter-pair-title";
  var METER_PART = "meter";
  var METER_LABEL_PART = "meter-label";
  var METER_BAR_PART = "meter-bar";
  var METER_FILL_PART = "meter-fill";
  var METER_PERCENT_PART = "meter-percent";
  var METER_VALUE_PART = "meter-value";
  var METER_NOTE_PART = "meter-note";

  // The meter a card draws, which is what the style sheet colours its bar by.
  var METER_ATTR = "data-meter";

  // The share the bar draws. A chain past its capacity still draws a full bar.
  var FULL_BAR = 100;

  var RESET_PANEL_PART = "reset-panel";
  var RESET_TITLE_PART = "reset-title";
  var RESET_ROW_PART = "reset-row";
  var RESET_ROW_LABEL_PART = "reset-row-label";
  var RESET_ROW_VALUE_PART = "reset-row-value";
  var RESET_NOTE_PART = "reset-note";

  var SEASON_PANEL_PART = "season-panel";
  var SEASON_TITLE_PART = "season-title";
  var SEASON_ROW_PART = "season-row";
  var SEASON_ROW_LABEL_PART = "season-row-label";
  var SEASON_ROW_VALUE_PART = "season-row-value";
  var SEASON_ADVANCE_PART = "season-advance";
  var SEASON_BOUNDARY_PART = "season-boundary";

  var POT_PANEL_PART = "pot-panel";
  var POT_TITLE_PART = "pot-title";
  var POT_ROW_PART = "pot-row";
  var POT_ROW_LABEL_PART = "pot-row-label";
  var POT_ROW_VALUE_PART = "pot-row-value";
  var POT_SHARE_PART = "pot-share";
  var POT_UNSCORED_PART = "pot-unscored";
  var POT_NOTE_PART = "pot-note";
  var SETTLED_ATTR = "data-settled";

  var QUINT_LABEL_PART = "quint-label";
  var QUINT_BALANCE_PART = "quint-balance";
  var WALLET_OPEN_PART = "wallet-open";
  var WALLET_PANEL_PART = "wallet-panel";
  var WALLET_TITLE_PART = "wallet-title";
  var WALLET_CLOSE_PART = "wallet-close";
  var WALLET_SECTIONS_PART = "wallet-sections";
  var WALLET_SECTION_PART = "wallet-section";
  var WALLET_SECTION_NAME_PART = "wallet-section-name";
  var WALLET_NOTE_PART = "wallet-note";
  var WALLET_ROW_PART = "wallet-row";
  var WALLET_ROW_LABEL_PART = "wallet-row-label";
  var WALLET_ROW_VALUE_PART = "wallet-row-value";
  var WALLET_ADDRESS_PART = "wallet-address";
  var WALLET_CHAIN_PART = "wallet-chain";

  var ZONE_PART = {};
  ZONE_PART[PLAYER_WINDOW] = "player-window";
  ZONE_PART[ENEMY_SCREEN] = "enemy-screen";
  ZONE_PART[PARTY_WINDOW] = "party-window";

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var walletOpen = false;
  var roots = [];

  // null until a subtab is chosen, when the payload's own subtab is drawn.
  var subtabName = null;

  var NO_SUCH_SUBTAB = "no subtab carries that name";
  var NO_SUCH_CONTROL = "no control carries that name";
  var NO_SUCH_CHAIN = "no chain carries that name";
  var NO_SUCH_EVENT = "no event type carries that name";

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function fault(field, kind, detail) {
    return { field: field, fault: kind, detail: detail };
  }

  // Returns undefined for an absent value so no attribute is written.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function part(className, name) {
    var props = { className: className };
    props[PART_ATTR] = name;
    return props;
  }

  // aria-label so a reader can pick one row out of the panel by its label.
  function named(className, name, label) {
    var props = part(className, name);
    props["aria-label"] = label;
    return props;
  }

  function zoneList(model) {
    return Array.isArray(model[ZONES]) ? model[ZONES] : [];
  }

  function zoneNamed(model, name) {
    var found = null;
    zoneList(model).forEach(function (zone) {
      if (isPlainObject(zone) && zone.name === name) {
        found = zone;
      }
    });
    return found;
  }

  // The glyph draws in the colour colour_token names, read off the page root.
  function Glyph(props) {
    var mark = props.mark;
    var label = text(props.label === undefined ? mark.label : props.label);
    var glyphProps = named(TAB_CLASS + "-glyph", GLYPH_PART, label);
    glyphProps[KIND_ATTR] = text(mark.kind);
    glyphProps[CODEPOINT_ATTR] = text(mark.codepoint);
    glyphProps.style = {
      color: CSS_VAR_OPEN + String(mark.colour_token) + CSS_VAR_CLOSE
    };
    return element("span", glyphProps, text(mark.glyph));
  }

  function GlyphRow(props) {
    var mark = props.mark;
    var label = text(mark.label);
    return element(
      "li",
      named(TAB_CLASS + "-glyph-row", GLYPH_ROW_PART, label),
      element(Glyph, { mark: mark }),
      element(
        "span",
        named(TAB_CLASS + "-glyph-label", GLYPH_LABEL_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-glyph-codepoint", GLYPH_CODEPOINT_PART, label),
        text(mark.codepoint)
      )
    );
  }

  function GlyphFamily(props) {
    var entry = props.entry;
    var marks = Array.isArray(entry.marks) ? entry.marks : [];
    var familyProps = part(TAB_CLASS + "-glyph-family", GLYPH_FAMILY_PART);
    familyProps[FAMILY_ATTR] = text(entry.family);
    return element(
      "div",
      familyProps,
      element(
        "h5",
        part(TAB_CLASS + "-glyph-family-name", GLYPH_FAMILY_NAME_PART),
        text(entry.family)
      ),
      element(
        "ul",
        part(TAB_CLASS + "-glyph-list", GLYPH_LIST_PART),
        marks.filter(isPlainObject).map(function (mark) {
          return element(GlyphRow, { key: mark.kind, mark: mark });
        })
      )
    );
  }

  function GlyphAbsentRow(props) {
    var row = props.row;
    var label = text(row.family);
    return element(
      "li",
      named(TAB_CLASS + "-glyph-absent-row", GLYPH_ABSENT_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-glyph-absent-name", GLYPH_ABSENT_NAME_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-glyph-absent-note", GLYPH_ABSENT_NOTE_PART, label),
        text(row.note)
      )
    );
  }

  function GlyphLegend(props) {
    var marks = props.marks;
    var families = Array.isArray(marks.families) ? marks.families : [];
    return element(
      "div",
      part(TAB_CLASS + "-glyph-legend", GLYPH_LEGEND_PART),
      element(
        "h4",
        part(TAB_CLASS + "-glyph-title", GLYPH_TITLE_PART),
        text(marks.title)
      ),
      element(
        "p",
        part(TAB_CLASS + "-glyph-count", GLYPH_COUNT_PART),
        text(marks.count_text)
      ),
      families.filter(isPlainObject).map(function (entry) {
        return element(GlyphFamily, { key: entry.family, entry: entry });
      }),
      element(
        "p",
        part(TAB_CLASS + "-glyph-colour", GLYPH_COLOUR_PART),
        text(marks.colour_text)
      ),
      element(
        "p",
        part(TAB_CLASS + "-glyph-art", GLYPH_ART_PART),
        text(marks.art_text)
      )
    );
  }

  // Drawn in the enemy screen, the zone a monster would draw in.
  function GlyphAbsence(props) {
    var marks = props.marks;
    var absent = Array.isArray(marks.absent) ? marks.absent : [];
    return element(
      "div",
      part(TAB_CLASS + "-glyph-absence", GLYPH_ABSENCE_PART),
      element(
        "h5",
        part(TAB_CLASS + "-glyph-absent-title", GLYPH_ABSENT_TITLE_PART),
        text(marks.absent_title)
      ),
      element(
        "ul",
        part(TAB_CLASS + "-glyph-absent-list", GLYPH_ABSENT_LIST_PART),
        absent.filter(isPlainObject).map(function (row) {
          return element(GlyphAbsentRow, { key: row.family, row: row });
        })
      )
    );
  }

  // One mark slot a row. An absent mark leaves the slot empty and unpainted.
  function MarkSlot(props) {
    var mark = text(props.mark);
    var markProps = named(
      TAB_CLASS + "-slot-mark",
      SLOT_MARK_PART,
      mark ? props.participant + " " + mark : props.participant
    );
    if (mark) {
      markProps[MARK_ATTR] = mark;
      markProps.title = mark;
    }
    return element("span", markProps);
  }

  // An empty slot carries only its label; a held one carries the fields the
  // participant row shows, its market symbol and its one mark slot.
  function Slot(props) {
    var row = props.row;
    var slotProps = part(TAB_CLASS + "-slot", PARTY_SLOT_PART);
    slotProps.key = props.index;
    slotProps["aria-label"] = isPlainObject(row)
      ? text(row.participant)
      : props.label;
    if (!isPlainObject(row)) {
      return element("li", slotProps);
    }
    return element(
      "li",
      slotProps,
      element(
        "span",
        named(TAB_CLASS + "-slot-name", SLOT_NAME_PART, text(row.participant)),
        text(row.participant)
      ),
      element(
        "span",
        named(
          TAB_CLASS + "-slot-symbol",
          SLOT_SYMBOL_PART,
          text(row.participant)
        ),
        text(row.symbol)
      ),
      element(
        "span",
        named(TAB_CLASS + "-slot-class", SLOT_CLASS_PART, text(row.participant)),
        text(row.class_name)
      ),
      element(
        "span",
        named(TAB_CLASS + "-slot-level", SLOT_LEVEL_PART, text(row.participant)),
        text(row.level_text)
      ),
      element(
        "span",
        named(
          TAB_CLASS + "-slot-impetus",
          SLOT_IMPETUS_PART,
          text(row.participant)
        ),
        text(row.impetus_text)
      ),
      element(
        "span",
        named(
          TAB_CLASS + "-slot-health",
          SLOT_HEALTH_PART,
          text(row.participant)
        ),
        text(row.health_text)
      ),
      element(MarkSlot, {
        key: "mark",
        mark: row.mark,
        participant: text(row.participant)
      })
    );
  }

  function Group(props) {
    var children = [];
    var first = props.index * props.size;
    for (var at = 0; at < props.size; at++) {
      children.push(
        element(Slot, {
          key: first + at,
          index: first + at,
          row: props.rows[first + at],
          label: props.slotLabel
        })
      );
    }
    var groupProps = part(TAB_CLASS + "-group", PARTY_GROUP_PART);
    groupProps.key = props.index;
    return element("ul", groupProps, children);
  }

  function PartyPages(props) {
    var groups = [];
    for (var at = 0; at < props.groups; at++) {
      groups.push(
        element(Group, {
          key: at,
          index: at,
          size: props.size,
          rows: props.rows,
          slotLabel: props.slotLabel
        })
      );
    }
    return element(
      "div",
      part(TAB_CLASS + "-pages", PARTY_PAGES_PART),
      groups
    );
  }

  // The turn readout and the Impetus remaining, which the fixed candle requires
  // the player window to make legible.
  function EventBand(props) {
    var event = props.event;
    return element(
      "div",
      named(TAB_CLASS + "-event-band", EVENT_BAND_PART, text(event.code)),
      element(
        "span",
        named(TAB_CLASS + "-event-label", EVENT_LABEL_PART, text(event.code)),
        text(event.label)
      ),
      element(
        "span",
        named(TAB_CLASS + "-event-variant", EVENT_VARIANT_PART, text(event.code)),
        text(event.variant_label)
      ),
      element(
        "span",
        named(TAB_CLASS + "-event-turn", EVENT_TURN_PART, text(event.code)),
        text(event.turn_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-event-impetus", EVENT_IMPETUS_PART, text(event.code)),
        text(event.impetus_text)
      )
    );
  }

  // One meter: its label, a bar at its own share, the percentage and the figures
  // behind it. The bar stops at FULL_BAR so a chain past its capacity still draws.
  // A meter carrying no note draws none, so the pair keeps one baseline.
  function Meter(props) {
    var row = props.row;
    var label = text(row.label);
    var share = Number(row.percent);
    var barProps = named(TAB_CLASS + "-meter-bar", METER_BAR_PART, label);
    barProps["aria-valuenow"] = text(row.percent);
    var fillProps = named(TAB_CLASS + "-meter-fill", METER_FILL_PART, label);
    fillProps.style = {
      width: String(share > FULL_BAR ? FULL_BAR : share) + "%"
    };
    var meterProps = named(TAB_CLASS + "-meter", METER_PART, label);
    meterProps[METER_ATTR] = text(row.name);
    var children = [
      element(
        "span",
        Object.assign(
          named(TAB_CLASS + "-meter-label", METER_LABEL_PART, label),
          { key: METER_LABEL_PART }
        ),
        label
      ),
      element(
        "div",
        Object.assign(barProps, { key: METER_BAR_PART }),
        element("div", fillProps)
      ),
      element(
        "span",
        Object.assign(
          named(TAB_CLASS + "-meter-percent", METER_PERCENT_PART, label),
          { key: METER_PERCENT_PART }
        ),
        text(row.percent_text)
      ),
      element(
        "span",
        Object.assign(
          named(TAB_CLASS + "-meter-value", METER_VALUE_PART, label),
          { key: METER_VALUE_PART }
        ),
        text(row.value_text)
      )
    ];
    if (text(row.note)) {
      children.push(
        element(
          "p",
          Object.assign(
            named(TAB_CLASS + "-meter-note", METER_NOTE_PART, label),
            { key: METER_NOTE_PART }
          ),
          text(row.note)
        )
      );
    }
    return element("div", meterProps, children);
  }

  // The two meters read as one unit: one heading over two equal columns, in the
  // order the payload lists them.
  function MeterPair(props) {
    var meters = props.meters;
    var rows = Array.isArray(meters.rows) ? meters.rows : [];
    var titleProps = part(TAB_CLASS + "-meter-pair-title", METER_PAIR_TITLE_PART);
    titleProps.key = METER_PAIR_TITLE_PART;
    var children = [element("h4", titleProps, text(meters.title))];
    rows.filter(isPlainObject).forEach(function (row) {
      children.push(element(Meter, { key: text(row.name), row: row }));
    });
    return element(
      "div",
      named(TAB_CLASS + "-meter-pair", METER_PAIR_PART, text(meters.title)),
      children
    );
  }

  function ranksText(row) {
    return (
      "difficulty " +
      String(row.difficulty_rank) +
      " - entry fee " +
      String(row.entry_fee_rank) +
      " - loot " +
      String(row.loot_rarity_rank) +
      "/" +
      String(row.loot_drop_rank)
    );
  }

  function ModeRow(props) {
    var row = props.row;
    return element(
      "li",
      named(TAB_CLASS + "-mode-row", MODE_ROW_PART, text(row.code)),
      element(Glyph, { mark: row, label: text(row.code) }),
      element(
        "span",
        named(TAB_CLASS + "-mode-name", MODE_NAME_PART, text(row.code)),
        text(row.label)
      ),
      element(
        "span",
        named(TAB_CLASS + "-mode-variant", MODE_VARIANT_PART, text(row.code)),
        text(row.variant_label)
      ),
      element(
        "span",
        named(TAB_CLASS + "-mode-turn", MODE_TURN_PART, text(row.code)),
        text(row.turn_timeframe)
      ),
      element(
        "span",
        named(TAB_CLASS + "-mode-ranks", MODE_RANKS_PART, text(row.code)),
        ranksText(row)
      )
    );
  }

  function ModeList(props) {
    return element(
      "ul",
      part(TAB_CLASS + "-mode-list", MODE_LIST_PART),
      props.rows.filter(isPlainObject).map(function (row) {
        return element(ModeRow, { key: row.code, row: row });
      })
    );
  }

  function ClassRow(props) {
    var entry = props.entry;
    return element(
      "li",
      named(TAB_CLASS + "-class-row", CLASS_ROW_PART, text(entry.name)),
      element(Glyph, { mark: entry, label: text(entry.name) }),
      element(
        "span",
        named(TAB_CLASS + "-class-name", CLASS_NAME_PART, text(entry.name)),
        text(entry.name)
      ),
      element(
        "span",
        named(TAB_CLASS + "-class-role", CLASS_ROLE_PART, text(entry.name)),
        text(entry.assignment)
      )
    );
  }

  function ClassList(props) {
    return element(
      "ul",
      part(TAB_CLASS + "-class-list", CLASS_LIST_PART),
      props.entries.filter(isPlainObject).map(function (entry) {
        return element(ClassRow, { key: entry.name, entry: entry });
      })
    );
  }

  function SkillRow(props) {
    var row = props.row;
    var label = text(row.level_text);
    return element(
      "li",
      named(TAB_CLASS + "-skill-row", SKILL_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-skill-level", SKILL_LEVEL_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-skill-cost", SKILL_COST_PART, label),
        text(row.cost_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-skill-reach", SKILL_REACH_PART, label),
        text(row.reach_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-skill-effect", SKILL_EFFECT_PART, label),
        text(row.effect_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-skill-bleed", SKILL_BLEED_PART, label),
        text(row.bleed_text)
      )
    );
  }

  function skillLine(name, value, label) {
    var lineProps = named(TAB_CLASS + "-" + name, name, label);
    lineProps.key = name;
    return element("p", lineProps, value);
  }

  // The gate line is drawn only while the skill gate refuses a transfer.
  function SkillPanel(props) {
    var skills = props.skills;
    var transfer = isPlainObject(skills.transfer) ? skills.transfer : {};
    var rows = Array.isArray(skills.levels) ? skills.levels : [];
    var notes = Array.isArray(skills.notes) ? skills.notes : [];
    var titleProps = part(TAB_CLASS + "-skill-title", SKILL_TITLE_PART);
    titleProps.key = SKILL_TITLE_PART;
    var label = text(transfer.name);
    var children = [
      element("h4", titleProps, text(skills.title)),
      skillLine(SKILL_STANDING_PART, text(transfer.standing_text), label)
    ];
    if (text(transfer.gate_text)) {
      children.push(
        skillLine(SKILL_GATE_PART, text(transfer.gate_text), label)
      );
    }
    children.push(
      element(
        "ul",
        Object.assign(part(TAB_CLASS + "-skill-list", SKILL_LIST_PART), {
          key: SKILL_LIST_PART
        }),
        rows.filter(isPlainObject).map(function (row) {
          return element(SkillRow, { key: row.level, row: row });
        })
      ),
      skillLine(SKILL_TOP_OUT_PART, text(skills.top_out_text), label),
      skillLine(SKILL_DURATION_PART, text(skills.duration_text), label)
    );
    notes.forEach(function (note, at) {
      var noteProps = named(
        TAB_CLASS + "-skill-note",
        SKILL_NOTE_PART,
        text(note)
      );
      noteProps.key = SKILL_NOTE_PART + "-" + String(at);
      children.push(element("p", noteProps, text(note)));
    });
    var panelProps = part(TAB_CLASS + "-skill-panel", SKILL_PANEL_PART);
    panelProps["aria-label"] = text(skills.title);
    return element("div", panelProps, children);
  }

  function PotRow(props) {
    var row = props.row;
    var label = text(row.label);
    return element(
      "div",
      named(TAB_CLASS + "-pot-row", POT_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-pot-row-label", POT_ROW_LABEL_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-pot-row-value", POT_ROW_VALUE_PART, label),
        text(row.value)
      )
    );
  }

  // A share line names the score and the amount; no line names what was spent.
  // One labelled figure a mechanism answered, in the panel the props name.
  function FigureRow(props) {
    var rowProps = named(TAB_CLASS + "-" + props.rowPart, props.rowPart, props.label);
    return element(
      "div",
      rowProps,
      element(
        "span",
        named(TAB_CLASS + "-" + props.labelPart, props.labelPart, props.label),
        text(props.label)
      ),
      element(
        "span",
        named(TAB_CLASS + "-" + props.valuePart, props.valuePart, props.label),
        text(props.value)
      )
    );
  }

  function figureRows(rows, rowPart, labelPart, valuePart) {
    return (Array.isArray(rows) ? rows : [])
      .filter(isPlainObject)
      .map(function (row, at) {
        return element(FigureRow, {
          key: rowPart + "-" + String(at),
          label: text(row.label),
          value: text(row.value),
          rowPart: rowPart,
          labelPart: labelPart,
          valuePart: valuePart
        });
      });
  }

  // One button a control. Clicking it sends that control's own params.
  function ControlButton(props) {
    var row = props.row;
    var buttonProps = named(
      TAB_CLASS + "-control-button",
      CONTROL_BUTTON_PART,
      text(row.title)
    );
    buttonProps[ACTION_ATTR] = text(row.name);
    buttonProps.type = "button";
    buttonProps.title = text(row.note);
    buttonProps.onClick = function () {
      fireControl(row.name);
    };
    return element("button", buttonProps, text(row.label));
  }

  // The note of the control that was fired, so the page says what it refuses.
  function noteFor(rows, action) {
    var found = "";
    rows.filter(isPlainObject).forEach(function (row) {
      if (row.name === action) {
        found = text(row.note) || "";
      }
    });
    return found;
  }

  // One button a chain. Clicking it redraws the whole tab against that chain.
  function ChainButton(props) {
    var entry = props.entry;
    var buttonProps = named(
      TAB_CLASS + "-chain-button",
      CHAIN_BUTTON_PART,
      text(entry.label)
    );
    buttonProps[CHAIN_ATTR] = text(entry.name);
    buttonProps[SELECTED_ATTR] = String(entry.selected === true);
    buttonProps.type = "button";
    buttonProps.onClick = function () {
      selectChain(entry.name);
    };
    return element("button", buttonProps, text(entry.label));
  }

  // One button an event type. Clicking it redraws the tab against that event.
  function EventButton(props) {
    var entry = props.entry;
    var buttonProps = named(
      TAB_CLASS + "-event-button",
      EVENT_BUTTON_PART,
      text(entry.label)
    );
    buttonProps[EVENT_ATTR] = text(entry.name);
    buttonProps[SELECTED_ATTR] = String(entry.selected === true);
    buttonProps.type = "button";
    buttonProps.onClick = function () {
      selectEvent(entry.name);
    };
    return element("button", buttonProps, text(entry.label));
  }

  function pickerRow(entries, labelPart, labelText, Button, keyPart) {
    var children = [];
    if (!entries.length) {
      return children;
    }
    var labelProps = part(TAB_CLASS + "-" + labelPart, labelPart);
    labelProps.key = labelPart;
    children.push(element("span", labelProps, text(labelText)));
    entries.filter(isPlainObject).forEach(function (entry) {
      children.push(
        element(Button, { key: keyPart + text(entry.name), entry: entry })
      );
    });
    return children;
  }

  function ControlBar(props) {
    var bar = props.controls;
    var rows = Array.isArray(bar.rows) ? bar.rows : [];
    var chains = Array.isArray(bar.chains) ? bar.chains : [];
    var events = Array.isArray(bar.events) ? bar.events : [];
    var fired = isPlainObject(bar.result) ? bar.result : {};
    var children = pickerRow(
      chains,
      CHAIN_LABEL_PART,
      bar.chain_label,
      ChainButton,
      CHAIN_BUTTON_PART
    ).concat(
      pickerRow(
        events,
        EVENT_PICK_LABEL_PART,
        bar.event_label,
        EventButton,
        EVENT_BUTTON_PART
      )
    );
    rows.filter(isPlainObject).forEach(function (row) {
      children.push(element(ControlButton, { key: text(row.name), row: row }));
    });
    var resultProps = named(
      TAB_CLASS + "-control-result",
      CONTROL_RESULT_PART,
      text(bar.title)
    );
    resultProps.key = CONTROL_RESULT_PART;
    resultProps[ACTED_ATTR] = String(fired.acted === true);
    resultProps[ACTION_ATTR] = text(fired.action);
    var lines = [
      element(
        "span",
        Object.assign(
          named(
            TAB_CLASS + "-control-message",
            CONTROL_MESSAGE_PART,
            text(bar.verdict)
          ),
          { key: CONTROL_MESSAGE_PART }
        ),
        text(fired.message)
      )
    ];
    lines = lines.concat(
      figureRows(
        fired.rows,
        CONTROL_ROW_PART,
        CONTROL_ROW_LABEL_PART,
        CONTROL_ROW_VALUE_PART
      )
    );
    var note = noteFor(rows, fired.action);
    if (note) {
      var noteProps = named(TAB_CLASS + "-control-note", CONTROL_NOTE_PART, note);
      noteProps.key = CONTROL_NOTE_PART;
      lines.push(element("p", noteProps, note));
    }
    children.push(element("div", resultProps, lines));
    if (isPlainObject(props.reset)) {
      children.push(
        element(ResetPanel, { key: RESET_PANEL_PART, reset: props.reset })
      );
    }
    var barProps = named(TAB_CLASS + "-control-bar", CONTROL_BAR_PART, text(bar.title));
    return element("div", barProps, children);
  }

  function KeepPanel(props) {
    var keep = props.conservation;
    var titleProps = part(TAB_CLASS + "-keep-title", KEEP_TITLE_PART);
    titleProps.key = KEEP_TITLE_PART;
    var children = [element("h4", titleProps, text(keep.title))];
    children = children.concat(
      figureRows(keep.rows, KEEP_ROW_PART, KEEP_ROW_LABEL_PART, KEEP_ROW_VALUE_PART)
    );
    if (text(keep.note)) {
      var noteProps = named(
        TAB_CLASS + "-keep-note",
        KEEP_NOTE_PART,
        text(keep.note)
      );
      noteProps.key = KEEP_NOTE_PART;
      children.push(element("p", noteProps, text(keep.note)));
    }
    var panelProps = named(
      TAB_CLASS + "-keep-panel",
      KEEP_PANEL_PART,
      text(keep.title)
    );
    return element("div", panelProps, children);
  }

  // The two chain files the reset control deletes, and both reasons one signal
  // carries, so a deliberate reset and a schema wipe read differently here. It
  // sits in the control bar, under the two buttons it reports on.
  function ResetPanel(props) {
    var panel = props.reset;
    var titleProps = part(TAB_CLASS + "-reset-title", RESET_TITLE_PART);
    titleProps.key = RESET_TITLE_PART;
    var children = [element("h4", titleProps, text(panel.title))];
    children = children.concat(
      figureRows(
        panel.rows,
        RESET_ROW_PART,
        RESET_ROW_LABEL_PART,
        RESET_ROW_VALUE_PART
      )
    );
    if (text(panel.note)) {
      var noteProps = named(
        TAB_CLASS + "-reset-note",
        RESET_NOTE_PART,
        text(panel.note)
      );
      noteProps.key = RESET_NOTE_PART;
      children.push(element("p", noteProps, text(panel.note)));
    }
    var panelProps = named(
      TAB_CLASS + "-reset-panel",
      RESET_PANEL_PART,
      text(panel.title)
    );
    panelProps[CHAIN_ATTR] = text(panel.chain);
    return element("div", panelProps, children);
  }

  function SeasonPanel(props) {
    var run = props.season;
    var titleProps = part(TAB_CLASS + "-season-title", SEASON_TITLE_PART);
    titleProps.key = SEASON_TITLE_PART;
    var children = [element("h4", titleProps, text(run.title))];
    children = children.concat(
      figureRows(
        run.rows,
        SEASON_ROW_PART,
        SEASON_ROW_LABEL_PART,
        SEASON_ROW_VALUE_PART
      )
    );
    [
      [SEASON_BOUNDARY_PART, run.boundary_text],
      [SEASON_ADVANCE_PART, run.advance_text]
    ].forEach(function (pair) {
      if (!text(pair[1])) {
        return;
      }
      var lineProps = named(TAB_CLASS + "-" + pair[0], pair[0], text(pair[1]));
      lineProps.key = pair[0];
      children.push(element("p", lineProps, text(pair[1])));
    });
    var panelProps = named(
      TAB_CLASS + "-season-panel",
      SEASON_PANEL_PART,
      text(run.title)
    );
    return element("div", panelProps, children);
  }

  function PotPanel(props) {
    var pot = props.redistribution;
    var rows = Array.isArray(pot.rows) ? pot.rows : [];
    var shares = Array.isArray(pot.shares) ? pot.shares : [];
    var unscored = Array.isArray(pot.unscored) ? pot.unscored : [];
    var notes = Array.isArray(pot.notes) ? pot.notes : [];
    var titleProps = part(TAB_CLASS + "-pot-title", POT_TITLE_PART);
    titleProps.key = POT_TITLE_PART;
    var children = [element("h4", titleProps, text(pot.title))];
    rows.filter(isPlainObject).forEach(function (row) {
      children.push(element(PotRow, { key: text(row.label), row: row }));
    });
    shares.forEach(function (line, at) {
      var shareProps = named(
        TAB_CLASS + "-pot-share",
        POT_SHARE_PART,
        text(line)
      );
      shareProps.key = POT_SHARE_PART + "-" + String(at);
      children.push(element("p", shareProps, text(line)));
    });
    unscored.forEach(function (line, at) {
      var missProps = named(
        TAB_CLASS + "-pot-unscored",
        POT_UNSCORED_PART,
        text(line)
      );
      missProps.key = POT_UNSCORED_PART + "-" + String(at);
      children.push(element("p", missProps, text(line)));
    });
    notes.concat([text(pot.note)]).forEach(function (note, at) {
      if (!text(note)) {
        return;
      }
      var noteProps = named(TAB_CLASS + "-pot-note", POT_NOTE_PART, text(note));
      noteProps.key = POT_NOTE_PART + "-" + String(at);
      children.push(element("p", noteProps, text(note)));
    });
    var panelProps = part(TAB_CLASS + "-pot-panel", POT_PANEL_PART);
    panelProps["aria-label"] = text(pot.title);
    panelProps[SETTLED_ATTR] = String(pot.is_settled === true);
    return element("div", panelProps, children);
  }

  function WalletRow(props) {
    var rowProps = named(TAB_CLASS + "-wallet-row", props.name, props.label);
    return element(
      "div",
      rowProps,
      element(
        "span",
        named(
          TAB_CLASS + "-wallet-row-label",
          WALLET_ROW_LABEL_PART,
          props.label
        ),
        text(props.label)
      ),
      element(
        "span",
        named(
          TAB_CLASS + "-wallet-row-value",
          WALLET_ROW_VALUE_PART,
          props.label
        ),
        text(props.value)
      )
    );
  }

  function WalletSection(props) {
    var section = props.section;
    var rows = Array.isArray(section.rows) ? section.rows : [];
    return element(
      "div",
      named(TAB_CLASS + "-wallet-section", WALLET_SECTION_PART, section.name),
      element(
        "h4",
        part(TAB_CLASS + "-wallet-section-name", WALLET_SECTION_NAME_PART),
        text(section.name)
      ),
      rows.filter(isPlainObject).map(function (row) {
        return element(WalletRow, {
          key: row.label,
          name: WALLET_ROW_PART,
          label: row.label,
          value: row.value
        });
      }),
      element(
        "p",
        named(TAB_CLASS + "-wallet-note", WALLET_NOTE_PART, section.name),
        text(section.note)
      )
    );
  }

  function WalletPanel(props) {
    var wallet = props.wallet;
    var sections = Array.isArray(wallet.sections) ? wallet.sections : [];
    var panelProps = part(TAB_CLASS + "-wallet", WALLET_PANEL_PART);
    panelProps["aria-label"] = text(wallet.title);
    return element(
      "div",
      panelProps,
      element(
        "h3",
        part(TAB_CLASS + "-wallet-title", WALLET_TITLE_PART),
        text(wallet.title)
      ),
      element(
        "button",
        buttonProps(WALLET_CLOSE_PART, text(wallet.close_text), closeWallet),
        text(wallet.close_text)
      ),
      element(WalletRow, {
        key: WALLET_ADDRESS_PART,
        name: WALLET_ADDRESS_PART,
        label: wallet.address_label,
        value: wallet.address_text
      }),
      element(WalletRow, {
        key: WALLET_CHAIN_PART,
        name: WALLET_CHAIN_PART,
        label: wallet.chain_label,
        value: wallet.chain
      }),
      element(
        "div",
        part(TAB_CLASS + "-wallet-sections", WALLET_SECTIONS_PART),
        sections.filter(isPlainObject).map(function (section) {
          return element(WalletSection, { key: section.name, section: section });
        })
      )
    );
  }

  function buttonProps(name, label, onClick) {
    var props = part(TAB_CLASS + "-button", name);
    props.type = "button";
    props["aria-label"] = label;
    props.onClick = onClick;
    return props;
  }

  function subtabList(model) {
    return Array.isArray(model[SUBTABS]) ? model[SUBTABS] : [];
  }

  function subtabNamed(model, name) {
    var found = null;
    subtabList(model).forEach(function (entry) {
      if (isPlainObject(entry) && entry.name === name) {
        found = entry;
      }
    });
    return found;
  }

  // An entry the running event does not open is never the drawn one, so a
  // chosen map falls back to the payload's subtab when the mode changes.
  function selectedSubtab(model) {
    var chosen = subtabNamed(model, subtabName);
    if (chosen !== null && chosen.reachable !== false) {
      return subtabName;
    }
    return text(model[SUBTAB]);
  }

  function SubtabButton(props) {
    var entry = props.entry;
    var label = text(entry.title);
    var buttonArgs = buttonProps(SUBTAB_BUTTON_PART, label, function () {
      selectSubtab(entry.name);
    });
    buttonArgs.key = entry.name;
    buttonArgs[SUBTAB_ATTR] = text(entry.name);
    buttonArgs[SELECTED_ATTR] = String(entry.name === props.selected);
    buttonArgs[REACHABLE_ATTR] = String(entry.reachable !== false);
    if (entry.reachable === false) {
      buttonArgs.disabled = true;
      buttonArgs.title = text(entry.refusal);
    }
    return element("button", buttonArgs, label);
  }

  function SubtabBar(props) {
    return element(
      "nav",
      named(TAB_CLASS + "-subtab-bar", SUBTAB_BAR_PART, props.selected),
      props.entries.filter(isPlainObject).map(function (entry) {
        return element(SubtabButton, {
          key: entry.name,
          entry: entry,
          selected: props.selected
        });
      })
    );
  }

  function StatRow(props) {
    var row = props.row;
    var label = text(row.metric);
    return element(
      "li",
      named(TAB_CLASS + "-stat-row", STAT_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-stat-metric", STAT_METRIC_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-stat-source", STAT_SOURCE_PART, label),
        text(row.source)
      ),
      element(
        "span",
        named(TAB_CLASS + "-stat-value", STAT_VALUE_PART, label),
        text(row.value_text)
      )
    );
  }

  function note(className, name, value) {
    if (!text(value)) {
      return null;
    }
    var noteProps = named(TAB_CLASS + "-" + className, name, text(value));
    noteProps.key = name;
    return element("p", noteProps, text(value));
  }

  function StatsPanel(props) {
    var stats = props.stats;
    var rows = Array.isArray(stats.rows) ? stats.rows : [];
    return element(
      "div",
      part(TAB_CLASS + "-stats", STATS_PANEL_PART),
      element(
        "ul",
        part(TAB_CLASS + "-stat-list", STAT_LIST_PART),
        rows.filter(isPlainObject).map(function (row) {
          return element(StatRow, { key: row.metric, row: row });
        })
      ),
      note("stat-count", STAT_COUNT_PART, stats.count_text),
      note("stat-note", STAT_NOTE_PART, stats.note),
      note("stat-seam", STAT_SEAM_PART, stats.seam_text)
    );
  }

  function GearRow(props) {
    var row = props.row;
    var label = text(row.label);
    return element(
      "li",
      named(TAB_CLASS + "-gear-row", GEAR_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-gear-label", GEAR_LABEL_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-gear-value", GEAR_VALUE_PART, label),
        text(row.value)
      )
    );
  }

  function GearPanel(props) {
    var gear = props.gear;
    var rows = Array.isArray(gear.rows) ? gear.rows : [];
    return element(
      "div",
      part(TAB_CLASS + "-gear", GEAR_PANEL_PART),
      element(
        "ul",
        part(TAB_CLASS + "-gear-list", GEAR_LIST_PART),
        rows.filter(isPlainObject).map(function (row) {
          return element(GearRow, { key: row.label, row: row });
        })
      ),
      note("gear-note", GEAR_NOTE_PART, gear.note),
      note("gear-absent", GEAR_ABSENT_PART, gear.absent_text)
    );
  }

  function TreeRow(props) {
    var row = props.row;
    var label = text(row.level_text);
    return element(
      "li",
      named(TAB_CLASS + "-tree-row", TREE_ROW_PART, label),
      element(
        "span",
        named(TAB_CLASS + "-tree-level", TREE_LEVEL_PART, label),
        label
      ),
      element(
        "span",
        named(TAB_CLASS + "-tree-cost", TREE_COST_PART, label),
        text(row.reach_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-tree-effect", TREE_EFFECT_PART, label),
        text(row.effect_text)
      ),
      element(
        "span",
        named(TAB_CLASS + "-tree-bleed", TREE_BLEED_PART, label),
        text(row.bleed_text)
      )
    );
  }

  function TreePanel(props) {
    var tree = props.tree;
    var rows = Array.isArray(tree.levels) ? tree.levels : [];
    var transfer = isPlainObject(tree.transfer) ? tree.transfer : {};
    var notes = Array.isArray(tree.notes) ? tree.notes : [];
    var children = [
      note("tree-list-note", TREE_LIST_NOTE_PART, tree.list_text),
      note("tree-standing", TREE_STANDING_PART, transfer.standing_text),
      element(
        "ul",
        Object.assign(part(TAB_CLASS + "-tree-list", TREE_LIST_PART), {
          key: TREE_LIST_PART
        }),
        rows.filter(isPlainObject).map(function (row) {
          return element(TreeRow, { key: row.level, row: row });
        })
      )
    ];
    notes.forEach(function (line, at) {
      var lineProps = named(TAB_CLASS + "-tree-note", TREE_NOTE_PART, text(line));
      lineProps.key = TREE_NOTE_PART + "-" + String(at);
      children.push(element("p", lineProps, text(line)));
    });
    return element("div", part(TAB_CLASS + "-tree", TREE_PANEL_PART), children);
  }

  function MapPanel(props) {
    return element(
      "div",
      part(TAB_CLASS + "-map", MAP_PANEL_PART),
      note("map-note", MAP_NOTE_PART, props.map.absent_text)
    );
  }

  var SUBTAB_BODY = {};
  SUBTAB_BODY[CHARACTER_STATS] = function (model) {
    return isPlainObject(model[CHARACTER_STATS])
      ? element(StatsPanel, { stats: model[CHARACTER_STATS] })
      : null;
  };
  SUBTAB_BODY[GEAR] = function (model) {
    return isPlainObject(model[GEAR])
      ? element(GearPanel, { gear: model[GEAR] })
      : null;
  };
  SUBTAB_BODY[SKILL_TREE] = function (model) {
    return isPlainObject(model[SKILL_TREE])
      ? element(TreePanel, { tree: model[SKILL_TREE] })
      : null;
  };
  SUBTAB_BODY[MAP] = function (model) {
    return isPlainObject(model[MAP])
      ? element(MapPanel, { map: model[MAP] })
      : null;
  };

  function SubtabArea(props) {
    var model = props.model;
    var name = props.selected;
    var entry = subtabNamed(model, name);
    var body = owns(SUBTAB_BODY, name) ? SUBTAB_BODY[name](model) : null;
    var areaProps = named(
      TAB_CLASS + "-subtab-panel",
      SUBTAB_PANEL_PART,
      entry === null ? name : text(entry.title)
    );
    areaProps[SUBTAB_ATTR] = text(name);
    return element(
      "section",
      areaProps,
      element(
        "h3",
        part(TAB_CLASS + "-subtab-title", SUBTAB_TITLE_PART),
        entry === null ? text(name) : text(entry.title)
      ),
      body
    );
  }

  // The player window's own map control. It opens the map subtab through the
  // same selectSubtab the bar uses, so one mode property decides both.
  function MapControl(props) {
    var map = props.map;
    var label = text(map.open_text);
    var openProps = buttonProps(MAP_OPEN_PART, label, function () {
      selectSubtab(MAP);
    });
    openProps.key = MAP_OPEN_PART;
    openProps[REACHABLE_ATTR] = String(map.reachable !== false);
    if (map.reachable === false) {
      openProps.disabled = true;
    }
    return element(
      "div",
      named(TAB_CLASS + "-map-control", MAP_CONTROL_PART, label),
      element("button", openProps, label),
      note("map-refusal", MAP_REFUSAL_PART, map.refusal)
    );
  }

  function PartyHeader(props) {
    var wallet = props.wallet;
    return element(
      "div",
      part(TAB_CLASS + "-party-header", PARTY_HEADER_PART),
      element(
        "h2",
        part(TAB_CLASS + "-zone-title", ZONE_TITLE_PART),
        text(props.title)
      ),
      element(
        "span",
        part(TAB_CLASS + "-quint-label", QUINT_LABEL_PART),
        text(wallet.balance_label)
      ),
      element(
        "span",
        part(TAB_CLASS + "-quint-balance", QUINT_BALANCE_PART),
        text(wallet.balance_text)
      ),
      element(
        "button",
        buttonProps(WALLET_OPEN_PART, text(wallet.open_text), openWallet),
        text(wallet.open_text)
      ),
      element(
        "span",
        part(TAB_CLASS + "-party-page", PARTY_PAGE_PART),
        text(props.pageText)
      ),
      element(
        "span",
        part(TAB_CLASS + "-mark-seam-note", MARK_SEAM_NOTE_PART),
        text(props.markSeamNote)
      )
    );
  }

  function zoneProps(zone, className) {
    var props = part(className, ZONE_PART[zone.name]);
    props[ZONE_ATTR] = zone.name;
    props["aria-label"] = text(zone.title);
    return props;
  }

  // One absent mechanism and what it waits on, from the vessels module's own list.
  function VesselAbsentRow(props) {
    var entry = props.entry;
    var rowProps = part(TAB_CLASS + "-vessel-absent-row", VESSEL_ABSENT_ROW_PART);
    rowProps.key = VESSEL_ABSENT_ROW_PART + "-" + text(entry.name);
    return element(
      "li",
      rowProps,
      element(
        "span",
        part(TAB_CLASS + "-vessel-absent-name", VESSEL_ABSENT_NAME_PART),
        text(entry.name)
      ),
      element(
        "span",
        part(TAB_CLASS + "-vessel-absent-note", VESSEL_ABSENT_NOTE_PART),
        text(entry.note)
      )
    );
  }

  // The left half: the Vessel the class pick names, its details against the wallet
  // balance, and the mechanisms no module builds for it.
  function VesselPanel(props) {
    var vessel = props.vessel;
    var absent = Array.isArray(vessel.absent) ? vessel.absent : [];
    var children = [
      element(
        "div",
        part(TAB_CLASS + "-vessel-list", VESSEL_LIST_PART),
        figureRows(
          vessel.rows,
          VESSEL_ROW_PART,
          VESSEL_ROW_LABEL_PART,
          VESSEL_ROW_VALUE_PART
        )
      ),
      element(
        "h3",
        part(TAB_CLASS + "-vessel-details-title", VESSEL_DETAILS_TITLE_PART),
        text(vessel.details_title)
      ),
      element(
        "div",
        part(TAB_CLASS + "-vessel-details-list", VESSEL_DETAILS_LIST_PART),
        figureRows(
          vessel.details,
          VESSEL_ROW_PART,
          VESSEL_ROW_LABEL_PART,
          VESSEL_ROW_VALUE_PART
        )
      ),
      note("vessel-note", VESSEL_NOTE_PART, vessel.note),
      note("vessel-note", VESSEL_BOUND_PART, vessel.bound),
      note("vessel-note", VESSEL_CLICK_NOTE_PART, vessel.click_note),
      element(
        "h3",
        part(TAB_CLASS + "-vessel-absent-title", VESSEL_ABSENT_TITLE_PART),
        text(vessel.absent_title)
      ),
      element(
        "ul",
        part(TAB_CLASS + "-vessel-absent-list", VESSEL_ABSENT_LIST_PART),
        absent.filter(isPlainObject).map(function (entry) {
          return element(VesselAbsentRow, {
            key: VESSEL_ABSENT_ROW_PART + "-" + text(entry.name),
            entry: entry
          });
        })
      )
    ];
    return element(
      "div",
      part(TAB_CLASS + "-vessel-panel", VESSEL_PANEL_PART),
      children
    );
  }

  // The right half while an encounter runs. The enemy screen draws inside it as its
  // own zone, squared off the row height, with the title and the absence beside it.
  function EncounterRegion(props) {
    var encounter = props.encounter;
    return element(
      "section",
      named(
        TAB_CLASS + "-encounter-region",
        ENCOUNTER_REGION_PART,
        text(encounter.title)
      ),
      element(
        "div",
        part(TAB_CLASS + "-encounter-text", ENCOUNTER_TEXT_PART),
        element(
          "h2",
          part(TAB_CLASS + "-encounter-title", ENCOUNTER_TITLE_PART),
          text(encounter.title)
        ),
        note("encounter-note", ENCOUNTER_NOTE_PART, encounter.running_text),
        note("tactical-note", TACTICAL_NOTE_PART, encounter.tactical_absent)
      ),
      element(
        "div",
        part(TAB_CLASS + "-enemy-slot", ENEMY_SLOT_PART),
        props.zone === null
          ? null
          : element(UpperZone, { zone: props.zone, absent: props.marks })
      )
    );
  }

  // The right-hand half while no encounter runs. The whole region is the button,
  // so clicking the map opens the map subtab through selectSubtab.
  function MapRegion(props) {
    var map = props.map;
    var label = text(map.title);
    var regionProps = buttonProps(MAP_REGION_PART, label, function () {
      selectSubtab(MAP);
    });
    return element(
      "button",
      regionProps,
      element(
        "span",
        part(TAB_CLASS + "-map-region-title", MAP_REGION_TITLE_PART),
        label
      ),
      element(
        "span",
        part(TAB_CLASS + "-map-note", MAP_NOTE_PART),
        text(map.region_absent_text)
      ),
      element(
        "span",
        part(TAB_CLASS + "-encounter-note", ENCOUNTER_NOTE_PART),
        text(props.encounter.resting_text)
      ),
      element(
        "span",
        part(TAB_CLASS + "-map-open", MAP_OPEN_PART),
        text(map.open_text)
      )
    );
  }

  // The right half of the top row: the Encounter while one runs, the Map otherwise.
  function RightRegion(props) {
    var encounter = props.encounter;
    var running = isPlainObject(encounter) && encounter.running === true;
    var regionProps = part(TAB_CLASS + "-right-region", RIGHT_REGION_PART);
    regionProps[ENCOUNTER_ATTR] = String(running);
    var body = null;
    if (running) {
      body = element(EncounterRegion, {
        encounter: encounter,
        zone: props.zone,
        marks: props.marks
      });
    } else if (isPlainObject(props.map) && isPlainObject(encounter)) {
      body = element(MapRegion, { map: props.map, encounter: encounter });
    }
    return element("div", regionProps, body);
  }

  function UpperZone(props) {
    var zone = props.zone;
    var titleProps = part(TAB_CLASS + "-zone-title", ZONE_TITLE_PART);
    titleProps.key = ZONE_TITLE_PART;
    var children = [element("h2", titleProps, text(zone.title))];
    if (isPlainObject(props.vessel)) {
      children.push(
        element(VesselPanel, { key: VESSEL_PANEL_PART, vessel: props.vessel })
      );
    }
    if (isPlainObject(props.event)) {
      children.push(
        element(EventBand, { key: EVENT_BAND_PART, event: props.event })
      );
    }
    if (isPlainObject(props.meters)) {
      children.push(
        element(MeterPair, { key: METER_PAIR_PART, meters: props.meters })
      );
    }
    if (isPlainObject(props.map)) {
      children.push(element(MapControl, { key: MAP_CONTROL_PART, map: props.map }));
    }
    if (Array.isArray(props.modes)) {
      children.push(element(ModeList, { key: MODE_LIST_PART, rows: props.modes }));
    }
    if (isPlainObject(props.marks)) {
      children.push(
        element(GlyphLegend, { key: GLYPH_LEGEND_PART, marks: props.marks })
      );
    }
    if (isPlainObject(props.absent)) {
      children.push(
        element(GlyphAbsence, { key: GLYPH_ABSENCE_PART, marks: props.absent })
      );
    }
    var placeholderProps = part(
      TAB_CLASS + "-zone-placeholder",
      ZONE_PLACEHOLDER_PART
    );
    placeholderProps.key = ZONE_PLACEHOLDER_PART;
    children.push(element("p", placeholderProps, text(zone.placeholder)));
    return element(
      "section",
      zoneProps(zone, TAB_CLASS + "-" + ZONE_PART[zone.name]),
      children
    );
  }

  function PartyZone(props) {
    var zone = props.zone;
    var party = props.party;
    var rows = props.rows;
    var children = [
      element(PartyHeader, {
        key: PARTY_HEADER_PART,
        title: zone.title,
        wallet: props.wallet,
        pageText: party.page_text,
        markSeamNote: party.mark_seam_note
      }),
      element(PartyPages, {
        key: PARTY_PAGES_PART,
        groups: Number(party.groups),
        size: Number(party.group_size),
        rows: rows,
        slotLabel: text(zone.title)
      }),
      element(ClassList, { key: CLASS_LIST_PART, entries: props.classes })
    ];
    if (isPlainObject(props.skills)) {
      children.push(
        element(SkillPanel, { key: SKILL_PANEL_PART, skills: props.skills })
      );
    }
    if (isPlainObject(props.redistribution)) {
      children.push(
        element(PotPanel, {
          key: POT_PANEL_PART,
          redistribution: props.redistribution
        })
      );
    }
    if (isPlainObject(props.conservation)) {
      children.push(
        element(KeepPanel, {
          key: KEEP_PANEL_PART,
          conservation: props.conservation
        })
      );
    }
    if (isPlainObject(props.season)) {
      children.push(
        element(SeasonPanel, { key: SEASON_PANEL_PART, season: props.season })
      );
    }
    if (props.pickNote !== undefined) {
      children.push(
        element(
          "p",
          Object.assign(part(TAB_CLASS + "-pick-note", PICK_NOTE_PART), {
            key: PICK_NOTE_PART
          }),
          props.pickNote
        )
      );
    }
    if (rows.length === 0) {
      children.push(
        element(
          "p",
          part(TAB_CLASS + "-zone-placeholder", ZONE_PLACEHOLDER_PART),
          text(zone.placeholder)
        )
      );
    }
    if (walletOpen) {
      children.push(
        element(WalletPanel, { key: WALLET_PANEL_PART, wallet: props.wallet })
      );
    }
    return element(
      "section",
      zoneProps(zone, TAB_CLASS + "-party-window"),
      children
    );
  }

  function PoaTab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var player = zoneNamed(model, PLAYER_WINDOW);
    var enemy = zoneNamed(model, ENEMY_SCREEN);
    var party = zoneNamed(model, PARTY_WINDOW);
    var paging = isPlainObject(model[PARTY]) ? model[PARTY] : {};
    var wallet = isPlainObject(model[WALLET]) ? model[WALLET] : {};
    var rows = Array.isArray(model[PARTICIPANTS]) ? model[PARTICIPANTS] : [];
    var entries = Array.isArray(model[CLASSES]) ? model[CLASSES] : [];
    var event = isPlainObject(model[EVENT]) ? model[EVENT] : null;
    var modeRows = Array.isArray(model[MODES]) ? model[MODES] : null;
    var map = isPlainObject(model[MAP]) ? model[MAP] : null;
    var encounter = isPlainObject(model[ENCOUNTER]) ? model[ENCOUNTER] : null;
    var vessel = isPlainObject(model[VESSEL]) ? model[VESSEL] : null;
    var marks = isPlainObject(model[MAP_MARKS]) ? model[MAP_MARKS] : null;
    var meters = isPlainObject(model[METERS]) ? model[METERS] : null;
    var chosen = selectedSubtab(model);
    var tabProps = {
      className: TAB_CLASS,
      "aria-label": text(model[ACCESSIBLE_NAME])
    };
    tabProps[CHAIN_ATTR] = text(model[CHAIN]);
    tabProps[ISSUE_ATTR] = text(model[ISSUE]);
    tabProps[OPEN_ATTR] = String(walletOpen);
    tabProps[SUBTAB_ATTR] = chosen;
    return element(
      "section",
      tabProps,
      element("h1", part(TAB_CLASS + "-heading", HEADING_PART), text(model[HEADING])),
      element("p", part(TAB_CLASS + "-state", STATE_PART), text(model[STATE_TEXT])),
      isPlainObject(model[CONTROLS])
        ? element(ControlBar, {
            controls: model[CONTROLS],
            reset: isPlainObject(model[CHAIN_RESET]) ? model[CHAIN_RESET] : null
          })
        : null,
      element(SubtabBar, { entries: subtabList(model), selected: chosen }),
      element(SubtabArea, { model: model, selected: chosen }),
      element(
        "div",
        part(TAB_CLASS + "-upper", UPPER_PART),
        player === null
          ? null
          : element(UpperZone, {
              zone: player,
              vessel: vessel,
              event: event,
              meters: meters,
              modes: modeRows,
              map: map,
              marks: marks
            }),
        element("div", part(TAB_CLASS + "-top-divider", TOP_DIVIDER_PART)),
        element(RightRegion, {
          zone: enemy,
          map: map,
          marks: marks,
          encounter: encounter
        })
      ),
      party === null
        ? null
        : element(PartyZone, {
            zone: party,
            party: paging,
            wallet: wallet,
            rows: rows,
            classes: entries,
            skills: isPlainObject(model[SKILLS]) ? model[SKILLS] : null,
            redistribution: isPlainObject(model[REDISTRIBUTION])
              ? model[REDISTRIBUTION]
              : null,
            conservation: isPlainObject(model[CONSERVATION])
              ? model[CONSERVATION]
              : null,
            season: isPlainObject(model[SEASON]) ? model[SEASON] : null,
            pickNote: text(model[PICK_NOTE])
          })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tabFaults.push(fault(field, NULL_FAULT, null));
      }
    });
  }

  function checkZones(model) {
    var list = zoneList(model);
    if (list.length !== ZONE_ORDER.length) {
      tabFaults.push(fault(ZONES, ZONE_COUNT_FAULT, String(list.length)));
      return;
    }
    for (var at = 0; at < ZONE_ORDER.length; at++) {
      if (!isPlainObject(list[at]) || list[at].name !== ZONE_ORDER[at]) {
        tabFaults.push(fault(ZONES, ZONE_ORDER_FAULT, String(at)));
      }
    }
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report() {
    return {
      declared: { fields: DECLARED_FIELDS.length, zones: ZONE_ORDER.length },
      held: { fields: heldFieldCount(held), zones: zoneList(held).length },
      faults: tabFaults.slice()
    };
  }

  function setProofOfAccumulationTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      tabFaults = [fault(null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = model;
    tabFaults = [];
    checkFields(model);
    checkZones(model);
    return report();
  }

  // Asks once, and forgets a refused ask so the next mount asks again.
  function loadProofOfAccumulationTab(params) {
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
        setProofOfAccumulationTab(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
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

  function drawAgain() {
    roots.forEach(function (pair) {
      renderTab(pair.node, held);
    });
  }

  // Answers which subtab is drawn afterwards and, when the ask was refused,
  // the payload's own sentence saying why the running event does not open it.
  function selectSubtab(name) {
    var entry = held === null ? null : subtabNamed(held, name);
    if (entry === null) {
      return {
        name: held === null ? null : selectedSubtab(held),
        opened: false,
        refusal: NO_SUCH_SUBTAB
      };
    }
    if (entry.reachable === false) {
      return {
        name: selectedSubtab(held),
        opened: false,
        refusal: text(entry.refusal)
      };
    }
    subtabName = name;
    drawAgain();
    return { name: selectedSubtab(held), opened: true, refusal: "" };
  }

  function controlRows(model) {
    var bar = isPlainObject(model) && isPlainObject(model[CONTROLS])
      ? model[CONTROLS]
      : null;
    return bar === null || !Array.isArray(bar.rows) ? [] : bar.rows;
  }

  function controlNamed(model, name) {
    var found = null;
    controlRows(model).forEach(function (row) {
      if (isPlainObject(row) && row.name === name) {
        found = row;
      }
    });
    return found;
  }

  // Asks the surface again with the params a button carries, then redraws from
  // the answer, so every figure on screen is the one the surface just computed.
  function askWith(name, params) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve({ name: name, acted: false, message: NO_BRIDGE });
    }
    return global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setProofOfAccumulationTab(model);
        drawAgain();
        return controlResult();
      })
      .catch(function (err) {
        loadFault = err.message;
        return { name: name, acted: false, message: err.message };
      });
  }

  function fireControl(name) {
    var row = held === null ? null : controlNamed(held, name);
    if (row === null) {
      return Promise.resolve({
        name: name,
        acted: false,
        message: NO_SUCH_CONTROL
      });
    }
    return askWith(name, row.params);
  }

  function pickerNamed(model, field, name) {
    var bar = isPlainObject(model) && isPlainObject(model[CONTROLS])
      ? model[CONTROLS]
      : null;
    var entries = bar === null || !Array.isArray(bar[field]) ? [] : bar[field];
    var found = null;
    entries.forEach(function (entry) {
      if (isPlainObject(entry) && entry.name === name) {
        found = entry;
      }
    });
    return found;
  }

  function selectChain(name) {
    var entry = held === null ? null : pickerNamed(held, "chains", name);
    if (entry === null) {
      return Promise.resolve({
        name: name,
        acted: false,
        message: NO_SUCH_CHAIN
      });
    }
    return askWith(name, entry.params);
  }

  function selectEvent(name) {
    var entry = held === null ? null : pickerNamed(held, "events", name);
    if (entry === null) {
      return Promise.resolve({
        name: name,
        acted: false,
        message: NO_SUCH_EVENT
      });
    }
    return askWith(name, entry.params);
  }

  function controlResult() {
    var bar = held === null ? null : held[CONTROLS];
    if (!isPlainObject(bar) || !isPlainObject(bar.result)) {
      return null;
    }
    return {
      name: bar.result.action,
      acted: bar.result.acted === true,
      message: bar.result.message,
      rows: Array.isArray(bar.result.rows) ? bar.result.rows.slice() : []
    };
  }

  function openWallet() {
    walletOpen = true;
    drawAgain();
  }

  function closeWallet() {
    walletOpen = false;
    drawAgain();
  }

  // flushSync so the document is current when renderTab returns.
  function renderTab(target, model) {
    var payload = isPlainObject(model) ? model : held;
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(element(PoaTab, { model: payload }));
    });
    return target;
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
    walletOpen = false;
    subtabName = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadProofOfAccumulationTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorSetProofOfAccumulationTab = setProofOfAccumulationTab;
  global.acervatorLoadProofOfAccumulationTab = loadProofOfAccumulationTab;
  global.acervatorProofOfAccumulationTab = {
    method: METHOD,
    PoaTab: PoaTab,
    zoneOrder: function () {
      return ZONE_ORDER.slice();
    },
    zonePart: function (name) {
      return ZONE_PART[name];
    },
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    state: function () {
      return held;
    },
    faults: function () {
      return tabFaults.slice();
    },
    loadError: function () {
      return loadFault;
    },
    isLoaded: function () {
      return held !== null && tabFaults.length === 0;
    },
    walletOpen: function () {
      return walletOpen;
    },
    openWallet: openWallet,
    closeWallet: closeWallet,
    subtabNames: function () {
      return held === null
        ? []
        : subtabList(held).map(function (entry) {
            return entry.name;
          });
    },
    subtab: function () {
      return held === null ? null : selectedSubtab(held);
    },
    selectSubtab: selectSubtab,
    controlNames: function () {
      return controlRows(held).map(function (row) {
        return row.name;
      });
    },
    controlResult: controlResult,
    fireControl: fireControl,
    selectChain: selectChain,
    selectEvent: selectEvent,
    renderTab: renderTab,
    forget: forget
  };
})(window);
