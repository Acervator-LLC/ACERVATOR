// Calibration body for eslint. Three defects: a misspelled global, a
// repeated object key that drops the first value, and an unread name.
(function (global) {
  "use strict";

  var PANEL_ID = "acervator-known-bad";
  var EMPTY_TEXT = "no value";
  var STALE_TEXT = "stale";

  function panelProps(amount) {
    return {
      className: PANEL_ID,
      title: EMPTY_TEXT,
      className: "acervator-known-bad--wide",
      textContent: String(amount)
    };
  }

  function render(amount) {
    var host = documnet.getElementById(PANEL_ID);
    if (host === null) {
      return false;
    }
    var props = panelProps(amount);
    host.className = props.className;
    return true;
  }

  global.acervatorKnownBadScript = { render: render };
})(window);
