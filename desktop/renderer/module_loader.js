// Loads every module_manifest.js entry the page has not already asked for, in manifest order.

"use strict";

(function (global, doc) {
  var DIRECTORY = "../../src/gui/web/";
  var FAULT_ATTRIBUTE = "data-module-error";
  var absent = [];

  function fileName(url) {
    var path = String(url).split("?")[0].split("#")[0];
    var parts = path.split("/");
    return parts[parts.length - 1];
  }

  function asked() {
    var seen = {};
    var tags = doc.querySelectorAll("script[src]");
    for (var index = 0; index < tags.length; index++) {
      seen[fileName(tags[index].getAttribute("src"))] = true;
    }
    return seen;
  }

  function wanted() {
    var list = global.ACERVATOR_MODULES;
    return Object.prototype.toString.call(list) === "[object Array]" ? list : null;
  }

  // Written into the parser at this point, so the modules run here rather than after boot.js.
  function inject() {
    var list = wanted();
    if (!list) {
      return;
    }
    var seen = asked();
    var markup = "";
    for (var index = 0; index < list.length; index++) {
      if (!seen[list[index]]) {
        seen[list[index]] = true;
        markup += '<script src="' + DIRECTORY + list[index] + '"><\/script>';
      }
    }
    if (markup) {
      doc.write(markup);
    }
  }

  function report() {
    var list = wanted();
    if (!list) {
      absent = ["module_manifest.js"];
    } else {
      var seen = asked();
      var failed = global.acervatorModuleErrors
        ? global.acervatorModuleErrors.names()
        : [];
      absent = [];
      for (var index = 0; index < list.length; index++) {
        if (!seen[list[index]] || failed.indexOf(list[index]) >= 0) {
          absent.push(list[index]);
        }
      }
    }
    if (absent.length) {
      doc.documentElement.setAttribute(FAULT_ATTRIBUTE, absent.join(","));
      global.console.error("Acervator module not loaded: " + absent.join(", "));
    } else {
      doc.documentElement.removeAttribute(FAULT_ATTRIBUTE);
    }
    return absent;
  }

  global.acervatorModules = {
    check: report,
    missing: function () {
      return absent.slice();
    },
    names: function () {
      return (wanted() || []).slice();
    }
  };

  global.addEventListener("load", report);
  inject();
})(window, document);
