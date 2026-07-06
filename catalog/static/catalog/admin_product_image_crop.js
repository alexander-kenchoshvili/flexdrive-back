(function () {
  "use strict";

  var MIN_SIZE = 0.05;

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function toFixed(value) {
    return clamp(value, 0, 1).toFixed(5);
  }

  function readNumber(root, key, fallback) {
    var value = Number(root.getAttribute("data-crop-" + key));
    return Number.isFinite(value) ? value : fallback;
  }

  function initCrop(root) {
    var stage = root.querySelector("[data-crop-stage]");
    var box = root.querySelector("[data-crop-box]");
    var image = root.querySelector("[data-crop-image]");
    var form = root.querySelector("[data-crop-form]");
    if (!stage || !box || !image || !form) return;

    var state = {
      x: readNumber(root, "x", 0),
      y: readNumber(root, "y", 0),
      width: readNumber(root, "width", 1),
      height: readNumber(root, "height", 1),
    };
    var drag = null;

    function normalizeState() {
      state.width = clamp(state.width, MIN_SIZE, 1);
      state.height = clamp(state.height, MIN_SIZE, 1);
      state.x = clamp(state.x, 0, 1 - state.width);
      state.y = clamp(state.y, 0, 1 - state.height);
    }

    function updateInputs() {
      var inputs = {
        x: form.querySelector('[data-crop-input="x"]'),
        y: form.querySelector('[data-crop-input="y"]'),
        width: form.querySelector('[data-crop-input="width"]'),
        height: form.querySelector('[data-crop-input="height"]'),
      };
      Object.keys(inputs).forEach(function (key) {
        if (inputs[key]) inputs[key].value = toFixed(state[key]);
      });

      var readouts = {
        x: root.querySelector('[data-crop-readout="x"]'),
        y: root.querySelector('[data-crop-readout="y"]'),
        width: root.querySelector('[data-crop-readout="width"]'),
        height: root.querySelector('[data-crop-readout="height"]'),
      };
      Object.keys(readouts).forEach(function (key) {
        if (readouts[key]) {
          readouts[key].textContent = Math.round(state[key] * 1000) / 10 + "%";
        }
      });
    }

    function render() {
      normalizeState();
      box.style.left = state.x * 100 + "%";
      box.style.top = state.y * 100 + "%";
      box.style.width = state.width * 100 + "%";
      box.style.height = state.height * 100 + "%";
      updateInputs();
    }

    function pointerPosition(event) {
      var rect = stage.getBoundingClientRect();
      return {
        x: clamp((event.clientX - rect.left) / rect.width, 0, 1),
        y: clamp((event.clientY - rect.top) / rect.height, 0, 1),
      };
    }

    function startDrag(event, mode) {
      if (event.button !== undefined && event.button !== 0) return;
      event.preventDefault();
      box.setPointerCapture?.(event.pointerId);
      drag = {
        mode: mode,
        start: pointerPosition(event),
        initial: {
          x: state.x,
          y: state.y,
          width: state.width,
          height: state.height,
        },
      };
    }

    function moveDrag(event) {
      if (!drag) return;
      event.preventDefault();

      var point = pointerPosition(event);
      var dx = point.x - drag.start.x;
      var dy = point.y - drag.start.y;
      var initial = drag.initial;

      if (drag.mode === "move") {
        state.x = initial.x + dx;
        state.y = initial.y + dy;
        render();
        return;
      }

      var left = initial.x;
      var top = initial.y;
      var right = initial.x + initial.width;
      var bottom = initial.y + initial.height;

      if (drag.mode.indexOf("w") !== -1) left = initial.x + dx;
      if (drag.mode.indexOf("e") !== -1) right = initial.x + initial.width + dx;
      if (drag.mode.indexOf("n") !== -1) top = initial.y + dy;
      if (drag.mode.indexOf("s") !== -1) bottom = initial.y + initial.height + dy;

      left = clamp(left, 0, right - MIN_SIZE);
      top = clamp(top, 0, bottom - MIN_SIZE);
      right = clamp(right, left + MIN_SIZE, 1);
      bottom = clamp(bottom, top + MIN_SIZE, 1);

      state.x = left;
      state.y = top;
      state.width = right - left;
      state.height = bottom - top;
      render();
    }

    function endDrag(event) {
      if (!drag) return;
      box.releasePointerCapture?.(event.pointerId);
      drag = null;
    }

    box.addEventListener("pointerdown", function (event) {
      var handle = event.target.closest("[data-crop-handle]");
      startDrag(event, handle ? handle.getAttribute("data-crop-handle") : "move");
    });
    box.addEventListener("pointermove", moveDrag);
    box.addEventListener("pointerup", endDrag);
    box.addEventListener("pointercancel", endDrag);

    if (image.complete) {
      render();
    } else {
      image.addEventListener("load", render, { once: true });
    }
    window.addEventListener("resize", render);
    form.addEventListener("submit", updateInputs);
  }

  function init() {
    document.querySelectorAll(".product-image-crop").forEach(initCrop);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
