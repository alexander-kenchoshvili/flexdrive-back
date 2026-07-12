(function () {
  "use strict";

  var CONTROL_CLASS = "product-image-camera-control";
  var INPUT_SELECTOR = '#images-group input[type="file"][name$="-image_original"]';

  function transferPhoto(cameraInput, uploadInput) {
    if (!cameraInput.files || !cameraInput.files.length) return;

    var transfer = new DataTransfer();
    Array.prototype.forEach.call(cameraInput.files, function (file) {
      transfer.items.add(file);
    });
    uploadInput.files = transfer.files;
    uploadInput.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function addCameraControl(uploadInput) {
    var next = uploadInput.nextElementSibling;
    if (next && next.classList.contains(CONTROL_CLASS)) return;

    var control = document.createElement("span");
    control.className = CONTROL_CLASS;

    var cameraInput = document.createElement("input");
    cameraInput.type = "file";
    cameraInput.accept = "image/*";
    cameraInput.setAttribute("capture", "environment");
    cameraInput.className = "product-image-camera-input";
    cameraInput.tabIndex = -1;
    cameraInput.setAttribute("aria-hidden", "true");

    var button = document.createElement("button");
    button.type = "button";
    button.className = "button product-image-camera-button";
    button.textContent = "📷 გადაღება";

    button.addEventListener("click", function () {
      cameraInput.value = "";
      cameraInput.click();
    });
    cameraInput.addEventListener("change", function () {
      transferPhoto(cameraInput, uploadInput);
    });

    control.appendChild(cameraInput);
    control.appendChild(button);
    uploadInput.insertAdjacentElement("afterend", control);
  }

  function addCameraControls(root) {
    var scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(INPUT_SELECTOR).forEach(addCameraControl);
  }

  function init() {
    addCameraControls(document);
    document.addEventListener("formset:added", function () {
      addCameraControls(document);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
