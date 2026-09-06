// Calibration body for the gui-js analyzer. Every control here is
// named and wired, so the archetype must exit 0 on this file.
(function (global) {
  "use strict";

  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var SECTION_TAG = "section";
  var SCREEN_CLASS = "acervator-known-good";

  var ACCESSIBLE_NAME = "accessible_name";
  var LABEL = "label";
  var OPTIONS = "options";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
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

  function listField(model, key) {
    var found = model && model[key];
    return Array.isArray(found) ? found : [];
  }

  function Action(props) {
    var model = objectField(props.state, "action");
    var buttonProps = {
      className: SCREEN_CLASS,
      type: BUTTON_TAG,
      title: text(model[TOOLTIP])
    };
    buttonProps.onClick = function () {
      props.onAct("action");
    };
    return element(BUTTON_TAG, buttonProps, text(model[TEXT]));
  }

  function Amount(props) {
    var model = objectField(props.state, "amount");
    var fieldProps = {
      className: SCREEN_CLASS,
      value: text(model[VALUE])
    };
    fieldProps["aria-label"] = text(model[LABEL]);
    fieldProps.onChange = function (event) {
      props.onAmount(event.target.value);
    };
    return element(INPUT_TAG, fieldProps);
  }

  function Venue(props) {
    var model = objectField(props.state, "venue");
    var venueProps = {
      className: SCREEN_CLASS,
      title: text(model[TOOLTIP]),
      value: text(model[VALUE])
    };
    venueProps.onChange = function (event) {
      props.onVenue(event.target.value);
    };
    return element(
      SELECT_TAG,
      venueProps,
      listField(model, OPTIONS).map(function (option) {
        return element(OPTION_TAG, { key: text(option) }, text(option));
      })
    );
  }

  function Screen(props) {
    var screenProps = { className: SCREEN_CLASS };
    screenProps["aria-label"] = text(props.state[ACCESSIBLE_NAME]);
    return element(
      SECTION_TAG,
      screenProps,
      element(Amount, { key: "amount", state: props.state, onAmount: props.onAmount }),
      element(Venue, { key: "venue", state: props.state, onVenue: props.onVenue }),
      element(Action, { key: "action", state: props.state, onAct: props.onAct })
    );
  }

  global.acervatorKnownGoodScreen = Screen;
})(window);
