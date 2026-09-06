// The Bot Swarm tab shell: composes the fleet list and the selected bot's swarm panel.
(function (global) {
  "use strict";

  var FUNCTION_KIND = "function";

  var LIST_API = "acervatorSwarmList";
  var TAB_API = "acervatorBotSwarmSettingsTab";
  var LIST_LOADER = "acervatorLoadBotSwarmList";
  var TAB_LOADER = "acervatorLoadBotSwarmSettingsTab";

  var SHELL_CLASS = "acervator-bot-swarm-shell";
  var PART_ATTR = "data-part";
  var SHELL_PART = "bot-swarm-shell";
  var LIST_REGION_PART = "bot-swarm-list-region";
  var DETAIL_REGION_PART = "bot-swarm-detail-region";
  var LIST_LOADED_ATTR = "data-list-loaded";
  var TAB_LOADED_ATTR = "data-tab-loaded";
  var SELECTED_ATTR = "data-selected-bot-id";
  var BOT_ID_ATTR = "data-bot-id";

  var DIV_TAG = "div";
  var COLUMN_DIRECTION = "column";
  var FLEX = "flex";

  var held = { list: null, tab: null, selectedBotId: null };
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The list module's exports, or null while it has not loaded.
  function listApi() {
    var found = global[LIST_API];
    return found && typeof found.SwarmList === FUNCTION_KIND ? found : null;
  }

  // The settings-tab module's exports, or null while it has not loaded.
  function tabApi() {
    var found = global[TAB_API];
    return found && typeof found.Tab === FUNCTION_KIND ? found : null;
  }

  // The bot the clicked node names, read off the nearest ancestor that carries one.
  function botIdAt(node) {
    var at = node;
    while (at) {
      if (typeof at.getAttribute === FUNCTION_KIND) {
        var found = at.getAttribute(BOT_ID_ATTR);
        if (found !== null) {
          return found;
        }
      }
      at = at.parentElement;
    }
    return null;
  }

  // ListRegion draws nothing of its own; a row click reports the bot it names.
  function ListRegion(props) {
    var api = listApi();
    var regionProps = {
      className: SHELL_CLASS,
      onClick: function (event) {
        var found = event && event.target ? botIdAt(event.target) : null;
        if (found !== null && typeof props.onSelectBot === FUNCTION_KIND) {
          props.onSelectBot(found);
        }
      }
    };
    regionProps[PART_ATTR] = LIST_REGION_PART;
    return element(
      DIV_TAG,
      regionProps,
      api ? element(api.SwarmList, { model: props.model }) : null
    );
  }

  // DetailRegion draws the settings panel for whichever bot is held selected.
  function DetailRegion(props) {
    var api = tabApi();
    var regionProps = { className: SHELL_CLASS };
    regionProps[PART_ATTR] = DETAIL_REGION_PART;
    return element(
      DIV_TAG,
      regionProps,
      api ? element(api.Tab, { model: props.model }) : null
    );
  }

  // SwarmTab composes the two already-built panels; it owns no payload of its own.
  function SwarmTab(props) {
    var shellProps = {
      id: props.id,
      className: SHELL_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    shellProps[PART_ATTR] = SHELL_PART;
    shellProps[LIST_LOADED_ATTR] = String(listApi() !== null);
    shellProps[TAB_LOADED_ATTR] = String(tabApi() !== null);
    shellProps[SELECTED_ATTR] = text(props.selectedBotId);
    return element(
      DIV_TAG,
      shellProps,
      element(ListRegion, {
        key: LIST_REGION_PART,
        model: props.listModel,
        onSelectBot: props.onSelectBot
      }),
      element(DetailRegion, { key: DETAIL_REGION_PART, model: props.tabModel })
    );
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

  function propsFor(target) {
    return {
      listModel: held.list,
      tabModel: held.tab,
      selectedBotId: held.selectedBotId,
      onSelectBot: function (botId) {
        selectBot(target, botId);
      }
    };
  }

  // A model given here replaces the held one; the other stays as it was.
  function renderShell(target, listModel, tabModel) {
    if (listModel !== undefined) {
      held.list = listModel;
    }
    if (tabModel !== undefined) {
      held.tab = tabModel;
    }
    return draw(target, element(SwarmTab, propsFor(target)));
  }

  // Marks the bot chosen, redraws with it, then asks the settings panel for it.
  function selectBot(target, botId) {
    held.selectedBotId = botId;
    draw(target, element(SwarmTab, propsFor(target)));
    return askSelectedBot(target, botId);
  }

  // A reply for a bot that is no longer the one held selected is dropped.
  function askSelectedBot(target, botId) {
    var loader = global[TAB_LOADER];
    if (typeof loader !== FUNCTION_KIND) {
      return Promise.resolve(null);
    }
    return loader({ bot: { bot_id: botId } }).then(function (model) {
      if (held.selectedBotId === botId) {
        held.tab = model;
        draw(target, element(SwarmTab, propsFor(target)));
      }
      return model;
    });
  }

  // Asks the list module for the fleet, then draws whatever it now holds.
  function loadShell(target, params) {
    var loader = global[LIST_LOADER];
    var opts = isPlainObject(params) ? params : {};
    if (typeof loader !== FUNCTION_KIND) {
      return Promise.resolve(draw(target, element(SwarmTab, propsFor(target))));
    }
    return loader(opts.list).then(function (model) {
      held.list = model;
      return draw(target, element(SwarmTab, propsFor(target)));
    });
  }

  function setShell(state) {
    var given = isPlainObject(state) ? state : {};
    if ("list" in given) {
      held.list = given.list;
    }
    if ("tab" in given) {
      held.tab = given.tab;
    }
    if ("selected_bot_id" in given) {
      held.selectedBotId = given.selected_bot_id;
    }
    return report();
  }

  function report() {
    return {
      hasList: listApi() !== null,
      hasTab: tabApi() !== null,
      selectedBotId: held.selectedBotId
    };
  }

  function selectedBotId() {
    return held.selectedBotId;
  }

  function listModel() {
    return held.list;
  }

  function tabModel() {
    return held.tab;
  }

  function forget() {
    held = { list: null, tab: null, selectedBotId: null };
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere. The list
  // module owns the fleet request, so its loader and its fault are used here.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: function (target, model) {
        return renderShell(target, model, undefined);
      },
      load: function (params) {
        var loader = global[LIST_LOADER];
        if (typeof loader !== FUNCTION_KIND) {
          return Promise.resolve(null);
        }
        return loader(isPlainObject(params) ? params.list : undefined);
      },
      loadError: function () {
        var found = global[LIST_API];
        return found && typeof found.loadError === FUNCTION_KIND
          ? found.loadError()
          : null;
      }
    });
  }

  global.acervatorSetBotSwarmTab = setShell;
  global.acervatorBotSwarmTab = {
    SwarmTab: SwarmTab,
    ListRegion: ListRegion,
    DetailRegion: DetailRegion,
    botIdAt: botIdAt,
    hasListApi: function () {
      return listApi() !== null;
    },
    hasTabApi: function () {
      return tabApi() !== null;
    },
    selectedBotId: selectedBotId,
    listModel: listModel,
    tabModel: tabModel,
    selectBot: selectBot,
    askSelectedBot: askSelectedBot,
    renderShell: renderShell,
    loadShell: loadShell,
    report: report,
    forget: forget
  };
})(window);
