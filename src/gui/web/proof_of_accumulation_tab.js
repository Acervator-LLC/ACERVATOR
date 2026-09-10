// The Proof of Accumulation tab shell, as the Python surface serves it.
//
// Three zones: the player window and the square enemy screen across the upper
// band, the party window across the lower half. The Quintessence balance sits
// in the party header and the wallet opens as a panel over the party window.
// Every word on screen comes from the payload.
(function (global) {
  "use strict";

  var METHOD = "proof_of_accumulation_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BUILT = "built";
  var CHAIN = "chain";
  var CLASSES = "classes";
  var EVENT = "event";
  var HEADING = "heading";
  var ISSUE = "issue";
  var ISSUE_TEXT = "issue_text";
  var METRIC_SOURCES = "metric_sources";
  var METHOD_FIELD = "method";
  var MODES = "modes";
  var PARTICIPANTS = "participants";
  var PARTY = "party";
  var PICK_NOTE = "pick_note";
  var SKILLS = "skills";
  var STATE_TEXT = "state_text";
  var WALLET = "wallet";
  var ZONES = "zones";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BUILT,
    CHAIN,
    CLASSES,
    EVENT,
    HEADING,
    ISSUE,
    ISSUE_TEXT,
    METRIC_SOURCES,
    METHOD_FIELD,
    MODES,
    PARTICIPANTS,
    PARTY,
    PICK_NOTE,
    SKILLS,
    STATE_TEXT,
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
  var ZONE_TITLE_PART = "zone-title";
  var ZONE_PLACEHOLDER_PART = "zone-placeholder";
  var PARTY_HEADER_PART = "party-header";
  var PARTY_PAGE_PART = "party-page";
  var PARTY_PAGES_PART = "party-pages";
  var PARTY_GROUP_PART = "party-group";
  var PARTY_SLOT_PART = "party-slot";
  var SLOT_NAME_PART = "slot-name";
  var SLOT_CLASS_PART = "slot-class";
  var SLOT_LEVEL_PART = "slot-level";
  var SLOT_IMPETUS_PART = "slot-impetus";
  var SLOT_HEALTH_PART = "slot-health";
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

  // An empty slot carries only its label; a held one carries the three fields
  // the participant row shows.
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
      )
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
      )
    );
  }

  function zoneProps(zone, className) {
    var props = part(className, ZONE_PART[zone.name]);
    props[ZONE_ATTR] = zone.name;
    props["aria-label"] = text(zone.title);
    return props;
  }

  function UpperZone(props) {
    var zone = props.zone;
    var titleProps = part(TAB_CLASS + "-zone-title", ZONE_TITLE_PART);
    titleProps.key = ZONE_TITLE_PART;
    var children = [element("h2", titleProps, text(zone.title))];
    if (isPlainObject(props.event)) {
      children.push(
        element(EventBand, { key: EVENT_BAND_PART, event: props.event })
      );
    }
    if (Array.isArray(props.modes)) {
      children.push(element(ModeList, { key: MODE_LIST_PART, rows: props.modes }));
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
        pageText: party.page_text
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
    var tabProps = {
      className: TAB_CLASS,
      "aria-label": text(model[ACCESSIBLE_NAME])
    };
    tabProps[CHAIN_ATTR] = text(model[CHAIN]);
    tabProps[ISSUE_ATTR] = text(model[ISSUE]);
    tabProps[OPEN_ATTR] = String(walletOpen);
    return element(
      "section",
      tabProps,
      element("h1", part(TAB_CLASS + "-heading", HEADING_PART), text(model[HEADING])),
      element("p", part(TAB_CLASS + "-state", STATE_PART), text(model[STATE_TEXT])),
      element(
        "div",
        part(TAB_CLASS + "-upper", UPPER_PART),
        player === null
          ? null
          : element(UpperZone, {
              zone: player,
              event: event,
              modes: modeRows
            }),
        enemy === null ? null : element(UpperZone, { zone: enemy })
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
    renderTab: renderTab,
    forget: forget
  };
})(window);
