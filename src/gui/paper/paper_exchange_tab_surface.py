"""One Paper venue page's view model, forked from ``exchange_tab_surface``.

``build_view_model`` is Live's ``exchange_tab_surface.build_view_model`` under
``METHOD``, with Privacy Mode kept where Live draws it, the news-ticker fields
not carried, and the data-pool text and timer not carried, ``DATA_POOL_ROW_TEXT``
holding the row at Live's height. ``screen`` builds the venue's
``ExchangeTabModel`` with no news factory and no pool reader, and ``drive``
answers the request fields a Paper venue takes.
"""

from __future__ import annotations

from typing import Any

from ..main_tabs import exchange_tab_surface as live

METHOD = "paper_exchange_tab.state"

#: The data-pool row keeps Live's style and holds nothing.
DATA_POOL_ROW_TEXT = ""

ACTIONS = {
    "privacy_mode_clicked": "on_global_privacy_clicked",
    "add_bot_clicked": "on_new_bot_clicked",
    "bot_wizard_closed": "close_bot_wizard",
    "scrum_selection_changed": "on_scrum_selection_changed",
    "extractor_selection_changed": "on_extractor_selection_changed",
    "command_clicked": "cmd",
}


def screen(
    exchange_id: str,
    exchange_name: str,
    status_log: Any = None,
    on_bot_clicked: Any = None,
    on_bot_fire: Any = None,
    on_new_bot: Any = None,
    on_bot_cmd: Any = None,
    on_fleet_cmd: Any = None,
) -> live.ExchangeTabModel:
    """One venue's ``ExchangeTabModel`` with no news strip and no pool reader,
    its Detail, Fire, ``+ New Bot`` and command bar reaching ``on_bot_clicked``,
    ``on_bot_fire``, ``on_new_bot`` and ``on_bot_cmd``, and its all-bots form
    reaching ``on_fleet_cmd``."""
    return live.ExchangeTabModel(
        exchange_id,
        exchange_name,
        on_new_bot=on_new_bot,
        on_bot_clicked=on_bot_clicked,
        on_bot_cmd=on_bot_cmd,
        on_fleet_cmd=on_fleet_cmd,
        on_bot_fire=on_bot_fire,
        status_log=status_log,
    )


def build_view_model(model: live.ExchangeTabModel) -> dict:
    """Return the whole venue page state as one serialisable dict."""
    return {
        "method": METHOD,
        "accessible_name": live.ACCESSIBLE_NAME,
        "exchange_id": model.exchange_id,
        "exchange_name": model.exchange_name,
        "privacy_label": model.privacy_label_text,
        "privacy_label_on": live.PRIVACY_LABEL_ON,
        "privacy_label_off": live.PRIVACY_LABEL_OFF,
        "privacy_tooltip": live.PRIVACY_TOOLTIP,
        "privacy_style": model.privacy_style_sheet,
        "privacy_style_on": live.PRIVACY_STYLE_ON,
        "privacy_style_off": live.PRIVACY_STYLE_OFF,
        "privacy_focus_policy": live.PRIVACY_FOCUS_POLICY,
        "privacy_focusable": live.PRIVACY_FOCUSABLE,
        "header_stretch": model.header_stretch,
        "add_bot_label": live.ADD_BOT_LABEL,
        "add_bot_accent": live.ADD_BOT_ACCENT,
        "new_bot_asks": list(model.new_bot_asks),
        "bot_wizard_module": live.BOT_WIZARD_MODULE,
        "bot_wizard_open": model.bot_wizard is not None,
        "bot_wizard_stretch": live.BOT_WIZARD_STRETCH,
        "pull_rate_text": DATA_POOL_ROW_TEXT,
        "pull_rate_style": live.PULL_RATE_STYLE,
        "scrum_table_stretch": live.SCRUM_TABLE_STRETCH,
        "extractor_table_stretch": live.EXTRACTOR_TABLE_STRETCH,
        "scrum_section_label": live.SCRUM_SECTION_LABEL,
        "scrum_section_style": live.SCRUM_SECTION_STYLE,
        "scrum_section_visible": model.scrum_section_visible,
        "extractor_section_label": live.EXTRACTOR_SECTION_LABEL,
        "extractor_section_style": live.EXTRACTOR_SECTION_STYLE,
        "extractor_section_visible": model.extractor_section_visible,
        "command_buttons": [list(pair) for pair in live.COMMAND_BUTTONS],
        "danger_command_label": live.DANGER_COMMAND_LABEL,
        "fleet_commands": {
            key: list(pair) for key, pair in live.FLEET_COMMANDS.items()
        },
        "commands_sent": [list(sent) for sent in model.commands_sent],
        "fleet_commands_sent": list(model.fleet_commands_sent),
        "scrum_table": live.table_view(model.scrum_table),
        "extractor_table": live.table_view(model.extractor_table),
        "last_clicked_table": model.last_clicked_table,
        "default_table": live.DEFAULT_TABLE,
        "table_scrumming": live.TABLE_SCRUMMING,
        "table_extractor": live.TABLE_EXTRACTOR,
        "table_neither": live.TABLE_NEITHER,
        "mode_scrumming": live.MODE_SCRUMMING,
        "mode_extractor": live.MODE_EXTRACTOR,
        "no_mode": live.NO_MODE,
        "default_exchange_id": live.DEFAULT_EXCHANGE_ID,
        "default_exchange_name": live.DEFAULT_EXCHANGE_NAME,
        "no_selection_row": live.NO_SELECTION_ROW,
        "no_selection_bot_id": live.NO_SELECTION_BOT_ID,
        "no_bot_id": live.NO_BOT_ID,
        "no_number": live.NO_NUMBER,
        "select_first_message": live.SELECT_FIRST_MESSAGE,
        "select_first_level": live.SELECT_FIRST_LEVEL,
        "logged": [list(line) for line in model.logged],
        "bot_opens": list(model.bot_opens),
        "pins": [dict(pin) for pin in model.pins],
        "pin_command_routed": live.PIN_COMMAND_ROUTED,
        "pin_every_bot_drawn": live.PIN_EVERY_BOT_DRAWN,
        "pin_selection_survives": live.PIN_SELECTION_SURVIVES,
        "pin_privacy_applied": live.PIN_PRIVACY_APPLIED,
        "pin_privacy_button": live.PIN_PRIVACY_BUTTON,
        "refresh_every_s": live.REFRESH_EVERY_S,
        "no_every": live.NO_EVERY,
        "no_selection_moved": live.NO_SELECTION_MOVED,
        "row_checks": {
            kind: [list(pair) for pair in checks]
            for kind, checks in live.ROW_CHECKS.items()
        },
        "checks_before_first_cell": list(live.CHECKS_BEFORE_FIRST_CELL),
        "number_fields": list(live.NUMBER_FIELDS),
        "check_stats": live.CHECK_STATS,
        "check_numbers": live.CHECK_NUMBERS,
        "check_symbol": live.CHECK_SYMBOL,
        "check_state": live.CHECK_STATE,
        "refusal_types": sorted(live.REFUSAL_TYPES),
        "skin": dict(live.SKIN),
        "style_sheet": live.STYLE_SHEET,
        "timers": {},
        "timer_delays_ms": [],
        "bus_topics": list(live.BUS_TOPICS),
        "actions": dict(ACTIONS),
        "reset_param": live.RESET_PARAM,
        "scrum_table_exchange_param": live.SCRUM_TABLE_EXCHANGE_PARAM,
        "extractor_table_exchange_param": live.EXTRACTOR_TABLE_EXCHANGE_PARAM,
        "exchange_id_param": live.EXCHANGE_ID_PARAM,
        "exchange_name_param": live.EXCHANGE_NAME_PARAM,
        "statuses_param": live.STATUSES_PARAM,
        "select_scrum_param": live.SELECT_SCRUM_PARAM,
        "select_extractor_param": live.SELECT_EXTRACTOR_PARAM,
        "command_param": live.COMMAND_PARAM,
        "shift_param": live.SHIFT_PARAM,
        "new_bot_param": live.NEW_BOT_PARAM,
        "close_bot_wizard_param": live.CLOSE_BOT_WIZARD_PARAM,
        "privacy_param": live.PRIVACY_PARAM,
        "logger_name": live.LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


def drive(model: live.ExchangeTabModel, params: dict) -> dict:
    """Apply one request to ``model``, reading each ``*_PARAM`` field Live reads
    apart from the pull-rate ones."""
    statuses = params.get(live.STATUSES_PARAM)
    if statuses is not None:
        model.update_bots(statuses)
    if params.get(live.SELECT_SCRUM_PARAM) is not None:
        model.select_scrum_row(params[live.SELECT_SCRUM_PARAM])
    if params.get(live.SELECT_EXTRACTOR_PARAM) is not None:
        model.select_extractor_row(params[live.SELECT_EXTRACTOR_PARAM])
    if params.get(live.COMMAND_PARAM) is not None:
        model.cmd(params[live.COMMAND_PARAM], bool(params.get(live.SHIFT_PARAM, False)))
    if params.get(live.NEW_BOT_PARAM, False):
        model.on_new_bot_clicked()
    if params.get(live.CLOSE_BOT_WIZARD_PARAM, False):
        model.close_bot_wizard()
    if params.get(live.PRIVACY_PARAM, False):
        model.on_global_privacy_clicked()
    return build_view_model(model)
