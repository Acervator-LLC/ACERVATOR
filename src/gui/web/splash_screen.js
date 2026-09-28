// The `splash_screen.state` payload, replayed onto a canvas one call per entry.
(function (global) {
  "use strict";

  var METHOD = "splash_screen.state";

  var PAINT_OPS = "paint_ops";
  var GEOMETRY = "geometry";
  var MARK = "mark";
  var ELEMENTS = "elements";
  var AURA_POINTS = "aura_points";

  var NO_BRIDGE = "the preload bridge is not present";
  var NO_CANVAS = "the canvas has no two-dimensional context";

  var HOST_CLASS = "acervator-splash-screen";
  var CENTRE = "center";
  var MIDDLE = "middle";
  var BOLD = "bold";
  var ROUND = "round";
  var TRANSPARENT = "rgba(0,0,0,0)";
  var DEGREES_PER_RADIAN = 180;
  var SEAM_WIDTH = 0.6;

  var faults = [];
  var issued = 0;
  var loadError = null;
  var payload = null;

  function rgba(colour) {
    return (
      "rgba(" +
      colour[0] +
      "," +
      colour[1] +
      "," +
      colour[2] +
      "," +
      colour[3] / 255 +
      ")"
    );
  }

  function fontOf(op) {
    var weight = op.length > 3 && op[3] === BOLD ? BOLD + " " : "";
    return weight + op[2] + "px " + op[1];
  }

  function gradientOf(context, spec) {
    var start = spec[1];
    var end = spec[2];
    var ramp = context.createLinearGradient(start[0], start[1], end[0], end[1]);
    var stops = spec[3];
    var index;
    for (index = 0; index < stops.length; index += 1) {
      ramp.addColorStop(stops[index][0], rgba(stops[index][1]));
    }
    return ramp;
  }

  function path(context, points, close) {
    var index;
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    for (index = 1; index < points.length; index += 1) {
      context.lineTo(points[index][0], points[index][1]);
    }
    if (close) {
      context.closePath();
    }
  }

  function ellipse(context, box) {
    var rx = box[2] / 2;
    var ry = box[3] / 2;
    context.beginPath();
    context.ellipse(box[0] + rx, box[1] + ry, rx, ry, 0, 0, Math.PI * 2);
  }

  function mesh(context, faces) {
    var index;
    var face;
    var tone;
    for (index = 0; index < faces.length; index += 1) {
      face = faces[index];
      tone = rgba(face[3]);
      context.fillStyle = tone;
      context.strokeStyle = tone;
      context.lineWidth = SEAM_WIDTH;
      path(context, [face[0], face[1], face[2]], true);
      context.fill();
      context.stroke();
    }
  }

  function replay(context, ops) {
    var index;
    var op;
    var name;
    var count = 0;
    context.lineJoin = ROUND;
    context.lineCap = ROUND;
    context.textAlign = CENTRE;
    context.textBaseline = MIDDLE;
    for (index = 0; index < ops.length; index += 1) {
      op = ops[index];
      name = op[0];
      if (name === "render_hint") {
        context.imageSmoothingEnabled = true;
      } else if (name === "pen") {
        context.strokeStyle = rgba(op[1]);
        context.lineWidth = op[2];
      } else if (name === "pen_colour") {
        context.strokeStyle = rgba(op[1]);
        context.fillStyle = rgba(op[1]);
      } else if (name === "pen_style") {
        context.strokeStyle = TRANSPARENT;
      } else if (name === "brush_colour") {
        context.fillStyle = rgba(op[1]);
      } else if (name === "brush_style") {
        context.fillStyle = TRANSPARENT;
      } else if (name === "mesh") {
        mesh(context, op[1]);
      } else if (name === "polygon") {
        path(context, op[1], true);
        context.fill();
      } else if (name === "polyline") {
        path(context, op[1], false);
        context.stroke();
      } else if (name === "ellipse") {
        ellipse(context, op[1]);
        context.fill();
        context.stroke();
      } else if (name === "line") {
        path(
          context,
          [
            [op[1], op[2]],
            [op[3], op[4]]
          ],
          false
        );
        context.stroke();
      } else if (name === "fill_rect") {
        context.fillStyle = gradientOf(context, op[5]);
        context.fillRect(op[1], op[2], op[3], op[4]);
      } else if (name === "font") {
        context.font = fontOf(op);
      } else if (name === "text") {
        context.fillText(op[3], op[1][0] + op[1][2] / 2, op[1][1] + op[1][3] / 2);
      } else if (name === "save") {
        context.save();
      } else if (name === "restore") {
        context.restore();
      } else if (name === "translate") {
        context.translate(op[1], op[2]);
      } else if (name === "rotate") {
        context.rotate((op[1] * Math.PI) / DEGREES_PER_RADIAN);
      } else if (name === "end") {
        continue;
      } else {
        faults.push(name);
        continue;
      }
      count += 1;
    }
    issued = count;
    return count;
  }

  function render(canvas, state) {
    var context = canvas.getContext("2d");
    if (!context) {
      loadError = NO_CANVAS;
      return 0;
    }
    payload = state;
    canvas.className = HOST_CLASS;
    canvas.width = state[GEOMETRY][2];
    canvas.height = state[GEOMETRY][3];
    context.clearRect(0, 0, canvas.width, canvas.height);
    return replay(context, state[PAINT_OPS]);
  }

  function load(params) {
    var bridge = global.acervator;
    if (!bridge || typeof bridge.call !== "function") {
      loadError = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return bridge.call(METHOD, params || {}).then(function (state) {
      payload = state;
      return state;
    });
  }

  function markElements() {
    return payload && payload[MARK] ? payload[MARK][ELEMENTS] : [];
  }

  function auraPoints() {
    return payload && payload[MARK] ? payload[MARK][AURA_POINTS] : 0;
  }

  global.acervatorSplashScreen = {
    METHOD: METHOD,
    replay: replay,
    render: render,
    load: load,
    issued: function () {
      return issued;
    },
    faults: function () {
      return faults.slice();
    },
    loadError: function () {
      return loadError;
    },
    markElements: markElements,
    auraPoints: auraPoints
  };
})(window);
