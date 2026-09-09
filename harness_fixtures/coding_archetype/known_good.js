// Calibration body for eslint. Every name here is declared and read, so
// the archetype must report passed=True on this file.
(function (global) {
  "use strict";

  var PANEL_ID = "acervator-known-good";
  var EMPTY_TEXT = "no value";

  function formatUsd(amount) {
    return typeof amount === "number" ? amount.toFixed(2) : EMPTY_TEXT;
  }

  function panelElement() {
    return document.getElementById(PANEL_ID);
  }

  function render(amount) {
    var host = panelElement();
    if (host === null) {
      return false;
    }
    host.textContent = formatUsd(amount);
    return true;
  }

  global.acervatorKnownGoodScript = { render: render, formatUsd: formatUsd };
})(window);
