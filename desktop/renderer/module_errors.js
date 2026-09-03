// Records by file name every script tag the page asked for and did not get.

"use strict";

(function (global) {
  var failed = [];

  function fileName(url) {
    var path = String(url).split("?")[0].split("#")[0];
    var parts = path.split("/");
    return parts[parts.length - 1];
  }

  // A failed resource load does not bubble, so the capture phase is the only one that sees it.
  function record(event) {
    var target = event ? event.target : null;
    if (!target || target.tagName !== "SCRIPT" || !target.src) {
      return;
    }
    var name = fileName(target.src);
    if (failed.indexOf(name) < 0) {
      failed.push(name);
    }
  }

  global.addEventListener("error", record, true);

  global.acervatorModuleErrors = {
    fileName: fileName,
    names: function () {
      return failed.slice();
    }
  };
})(window);
