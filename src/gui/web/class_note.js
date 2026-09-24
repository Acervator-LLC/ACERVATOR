// Draws the asset class note one filtered tab shows while the active class
// holds nothing, from the model `class_filter_surface.note_model` builds.
// Every colour and size arrives as an `--empty-tab-` property from
// `src/gui/main_tabs/empty_tabs.py`, which paints the Qt side from the same
// numbers.
(function (global) {
  "use strict";

  var METHOD = "class_note.model";

  var ROOT_CLASS = "acervator-empty-tab";
  var HEADING_CLASS = "acervator-empty-tab-heading";
  var STATE_CLASS = "acervator-empty-tab-state";
  var ISSUE_CLASS = "acervator-empty-tab-issue";

  var HEADING_PART = "class-note-heading";
  var STATE_PART = "class-note-state";
  var ISSUE_PART = "class-note-issue";
  var ROOT_PART = "class-note";
  var PART_ATTR = "data-part";

  var DIV_TAG = "div";
  var HEADING_TAG = "h1";
  var LINE_TAG = "p";

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

  // ClassNote draws the three lines the model carries, and nothing else.
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
    ClassNote: ClassNote,
    Line: Line,
    renderNote: renderNote,
    forget: forget
  };
})(window);
