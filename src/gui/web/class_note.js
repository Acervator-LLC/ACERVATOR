// Draws the asset class note one filtered tab shows while the active class
// holds nothing, from the model `class_filter_surface.note_model` builds.
// Every colour and size arrives as an `--empty-tab-` property from
// `src/gui/main_tabs/empty_tabs.py`, which paints the Qt side from the same
// numbers. A model carrying `build_text` also draws the button that opens the
// Bot Creation Wizard, and a press sends `build_bot` back with the sector.
(function (global) {
  "use strict";

  var METHOD = "class_note.model";

  var ROOT_CLASS = "acervator-empty-tab";
  var HEADING_CLASS = "acervator-empty-tab-heading";
  var STATE_CLASS = "acervator-empty-tab-state";
  var ISSUE_CLASS = "acervator-empty-tab-issue";

  var BUILD_CLASS = "acervator-empty-tab-build";

  var HEADING_PART = "class-note-heading";
  var STATE_PART = "class-note-state";
  var ISSUE_PART = "class-note-issue";
  var BUILD_PART = "class-note-build";
  var ROOT_PART = "class-note";
  var PART_ATTR = "data-part";
  var CLASS_ATTR = "data-class";

  var DIV_TAG = "div";
  var HEADING_TAG = "h1";
  var LINE_TAG = "p";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";

  // The request field `class_filter_tab` reads off a press on the button.
  var BUILD_PARAM = "build_bot";

  var FIELDS = [
    { field: "heading", tag: HEADING_TAG, css: HEADING_CLASS, part: HEADING_PART },
    { field: "state_text", tag: LINE_TAG, css: STATE_CLASS, part: STATE_PART },
    { field: "issue_text", tag: LINE_TAG, css: ISSUE_CLASS, part: ISSUE_PART }
  ];

  var roots = [];

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function text(model, field) {
    var held = model && model[field];
    return typeof held === "string" ? held : "";
  }

  function Line(props) {
    var made = { className: props.css };
    made[PART_ATTR] = props.part;
    return element(props.tag, made, props.text);
  }

  function press(sector) {
    var params = {};
    params[BUILD_PARAM] = sector;
    global.acervator.call(METHOD, params);
  }

  // Build draws the button `build_text` names and sends its press back.
  function Build(props) {
    var made = {
      className: BUILD_CLASS,
      type: BUTTON_TYPE,
      onClick: function () {
        press(props.sector);
      }
    };
    made[PART_ATTR] = BUILD_PART;
    made[CLASS_ATTR] = props.sector;
    return element(BUTTON_TAG, made, props.text);
  }

  // ClassNote draws the three lines the model carries, and the button it
  // offers while `build_text` names one.
  function ClassNote(props) {
    var model = props.model || {};
    var made = [];
    for (var index = 0; index < FIELDS.length; index++) {
      var one = FIELDS[index];
      made.push(
        element(Line, {
          key: one.field,
          tag: one.tag,
          css: one.css,
          part: one.part,
          text: text(model, one.field)
        })
      );
    }
    var offered = text(model, "build_text");
    if (offered !== "") {
      made.push(
        element(Build, {
          key: BUILD_PART,
          text: offered,
          sector: text(model, "build_class")
        })
      );
    }
    var rootProps = {
      className: ROOT_CLASS,
      "aria-label": text(model, "accessible_name")
    };
    rootProps[PART_ATTR] = ROOT_PART;
    return element(DIV_TAG, rootProps, made);
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

  // flushSync so the three lines are on the page when this returns.
  function renderNote(target, model) {
    if (!target) {
      return null;
    }
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(element(ClassNote, { model: model }));
    });
    return target;
  }

  function forget() {
    roots.forEach(function (pair) {
      pair.root.unmount();
    });
    roots = [];
  }

  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderNote,
      load: function (params) {
        return global.acervator.call(METHOD, params);
      }
    });
  }

  global.acervatorClassNote = {
    method: METHOD,
    buildParam: BUILD_PARAM,
    ClassNote: ClassNote,
    Line: Line,
    Build: Build,
    renderNote: renderNote,
    forget: forget
  };
})(window);
