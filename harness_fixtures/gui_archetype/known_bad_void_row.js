// A drawn row whose three slots fill only part of its width, so the rest of the
// row is empty background. GUI008 refuses this file on the tail void.
(function (global) {
  "use strict";

  var ROW_PART = "top-row";
  var SLOT_NAMES = ["spendable", "scrummed", "mode_button"];
  var SLOT_HEIGHT = "36px";
  var SLOT_WIDTH = "120px";
  var HOLDER_DISPLAY = "block";

  function slot(name) {
    var node = document.createElement("div");
    node.setAttribute("data-slot", name);
    node.style.width = SLOT_WIDTH;
    node.style.height = SLOT_HEIGHT;
    node.style.flexGrow = "0";
    node.style.flexShrink = "0";
    node.textContent = name;
    return node;
  }

  function draw(target) {
    var holder = document.createElement("div");
    holder.id = "fixture-holder";
    holder.style.display = HOLDER_DISPLAY;
    var row = document.createElement("div");
    row.setAttribute("data-part", ROW_PART);
    row.style.display = "flex";
    row.style.width = "100%";
    row.style.height = SLOT_HEIGHT;
    SLOT_NAMES.forEach(function (name) {
      row.appendChild(slot(name));
    });
    holder.appendChild(row);
    target.appendChild(holder);
    return row;
  }

  global.acervatorFixtureRow = {
    draw: draw,
    holderDisplay: HOLDER_DISPLAY,
    slotNames: SLOT_NAMES
  };
})(window);
