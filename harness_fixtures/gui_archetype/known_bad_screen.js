// Calibration body for the gui-js analyzer, built to FAIL it. One
// deliberate defect per rule: GUIJS001, GUIJS002, GUIJS003, GUIJS004.
(function (global) {
  "use strict";

  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var SECTION_TAG = "section";
  var SCREEN_CLASS = "acervator-known-bad";

  var TEXT = "text";
  var VALUE = "value";

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function text(value) {
    return typeof value === "string" ? value : "";
  }

  function objectField(model, key) {
    var found = model && model[key];
    return found && typeof found === "object" ? found : {};
  }

  // GUIJS001: no accessible name and no child content.
  function Amount(props) {
    var model = objectField(props.state, "amount");
    var fieldProps = {
      className: SCREEN_CLASS,
      value: text(model[VALUE])
    };
    fieldProps.onChange = function (event) {
      props.onAmount(event.target.value);
    };
    return element(INPUT_TAG, fieldProps);
  }

  // GUIJS002: named, drawn, and answers no click.
  function Action(props) {
    var model = objectField(props.state, "action");
    var buttonProps = {
      className: SCREEN_CLASS,
      type: BUTTON_TAG,
      title: "Fire the order"
    };
    buttonProps["data-action"] = "known_bad.fire";
    return element(BUTTON_TAG, buttonProps, text(model[TEXT]));
  }

  // GUIJS003 and GUIJS004: a colour the design tokens already serve, and
  // an element taken out of flow.
  function Screen(props) {
    var screenProps = {
      className: SCREEN_CLASS,
      style: { color: "#3366ff", position: "absolute", top: 12, left: 40 }
    };
    screenProps["aria-label"] = "Known bad screen";
    return element(
      SECTION_TAG,
      screenProps,
      element(Amount, { key: "amount", state: props.state, onAmount: props.onAmount }),
      element(Action, { key: "action", state: props.state })
    );
  }

  global.acervatorKnownBadScreen = Screen;
})(window);
