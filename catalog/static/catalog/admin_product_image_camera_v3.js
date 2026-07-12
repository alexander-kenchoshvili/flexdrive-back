(function () {
  "use strict";

  var ORIGINAL_SELECTOR = '#images-group input[type="file"][name$="-image_original"]';
  var previewUrls = [];

  function endpointUrl() {
    var marker = "/catalog/product/";
    var index = window.location.pathname.indexOf(marker);
    return index === -1
      ? null
      : window.location.pathname.slice(0, index + marker.length) +
          "images/ai-background-preview/";
  }

  function csrfToken() {
    var input = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return input ? input.value : "";
  }

  function rowFor(input) {
    return input.closest("tr") || input.closest(".inline-related");
  }

  function field(row, suffix) {
    return row.querySelector('[name$="-' + suffix + '"]');
  }

  function setFiles(input, files) {
    var transfer = new DataTransfer();
    Array.prototype.forEach.call(files, function (file) {
      transfer.items.add(file);
    });
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function objectUrl(blob) {
    var url = URL.createObjectURL(blob);
    previewUrls.push(url);
    return url;
  }

  function buildCameraControl(uploadInput) {
    var control = document.createElement("span");
    control.className = "product-image-camera-control";

    var cameraInput = document.createElement("input");
    cameraInput.type = "file";
    cameraInput.accept = "image/*";
    cameraInput.setAttribute("capture", "environment");
    cameraInput.className = "product-image-camera-input";
    cameraInput.tabIndex = -1;

    var button = document.createElement("button");
    button.type = "button";
    button.className = "button product-image-camera-button";
    button.textContent = "📷 გადაღება";
    button.addEventListener("click", function () {
      cameraInput.value = "";
      cameraInput.click();
    });
    cameraInput.addEventListener("change", function () {
      if (cameraInput.files.length) setFiles(uploadInput, cameraInput.files);
    });

    control.appendChild(cameraInput);
    control.appendChild(button);
    return control;
  }

  function buildAiControl(row, originalInput, checkbox, processedInput) {
    var panel = document.createElement("div");
    panel.className = "product-image-ai-control";

    var previewButton = document.createElement("button");
    previewButton.type = "button";
    previewButton.className = "button product-image-ai-preview-button";
    previewButton.textContent = "თეთრი ფონის Preview";

    var status = document.createElement("span");
    status.className = "product-image-ai-status";

    var comparison = document.createElement("div");
    comparison.className = "product-image-ai-comparison";
    comparison.hidden = true;
    comparison.innerHTML =
      '<div><strong>Original</strong><img data-ai-original alt="Original photo preview"></div>' +
      '<div><strong>თეთრი ფონი</strong><img data-ai-result alt="Processed photo preview"></div>';

    var actions = document.createElement("div");
    actions.className = "product-image-ai-actions";
    actions.hidden = true;

    var applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "button default";
    applyButton.textContent = "გამოყენება";

    var cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "button";
    cancelButton.textContent = "გაუქმება";

    var resultBlob = null;

    function syncState() {
      previewButton.disabled = !checkbox.checked;
      if (!checkbox.checked) {
        comparison.hidden = true;
        actions.hidden = true;
        status.textContent = "";
        resultBlob = null;
      }
    }

    checkbox.addEventListener("change", syncState);
    originalInput.addEventListener("change", function () {
      processedInput.value = "";
      checkbox.checked = false;
      syncState();
      status.textContent = "ახალი ფოტო არჩეულია — მონიშნე AI checkbox Preview-სთვის.";
    });
    previewButton.addEventListener("click", async function () {
      var file = originalInput.files && originalInput.files[0];
      if (!file) {
        status.textContent = "ჯერ გადაიღე ან აირჩიე ფოტო.";
        return;
      }

      var url = endpointUrl();
      if (!url) {
        status.textContent = "Preview endpoint ვერ მოიძებნა.";
        return;
      }

      previewButton.disabled = true;
      status.textContent = "მუშავდება…";
      comparison.hidden = true;
      actions.hidden = true;

      var body = new FormData();
      body.append("image", file, file.name);

      try {
        var response = await fetch(url, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken() },
          body: body,
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error(await response.text());

        resultBlob = await response.blob();
        comparison.querySelector("[data-ai-original]").src = objectUrl(file);
        comparison.querySelector("[data-ai-result]").src = objectUrl(resultBlob);
        comparison.hidden = false;
        actions.hidden = false;
        status.textContent = "შეამოწმე შედეგი და აირჩიე გამოყენება ან გაუქმება.";
      } catch (error) {
        status.textContent = error.message || "დამუშავება ვერ შესრულდა.";
      } finally {
        previewButton.disabled = !checkbox.checked;
      }
    });

    applyButton.addEventListener("click", function () {
      if (!resultBlob) return;
      var stem = (originalInput.files[0].name || "product-photo").replace(/\.[^.]+$/, "");
      var processedFile = new File([resultBlob], stem + "-white-bg.jpg", {
        type: "image/jpeg",
      });
      setFiles(processedInput, [processedFile]);
      status.textContent = "თეთრი ფონის შედეგი გამოყენებულია. ახლა დააჭირე Save-ს.";
      comparison.hidden = true;
      actions.hidden = true;
    });

    cancelButton.addEventListener("click", function () {
      resultBlob = null;
      comparison.hidden = true;
      actions.hidden = true;
      status.textContent = "Preview გაუქმდა; original ფოტო უცვლელია.";
    });

    actions.appendChild(applyButton);
    actions.appendChild(cancelButton);
    panel.appendChild(previewButton);
    panel.appendChild(status);
    panel.appendChild(comparison);
    panel.appendChild(actions);
    syncState();
    return panel;
  }

  function enhance(originalInput) {
    if (originalInput.dataset.cameraAiReady === "1") return;
    var row = rowFor(originalInput);
    var checkbox = row && field(row, "use_ai_background");
    var processedInput = row && field(row, "image_ai_background");
    if (!row || !checkbox || !processedInput) return;

    originalInput.dataset.cameraAiReady = "1";
    originalInput.insertAdjacentElement("afterend", buildCameraControl(originalInput));
    originalInput.parentElement.appendChild(
      buildAiControl(row, originalInput, checkbox, processedInput)
    );
  }

  function enhanceAll() {
    document.querySelectorAll(ORIGINAL_SELECTOR).forEach(enhance);
  }

  function init() {
    enhanceAll();
    document.addEventListener("formset:added", enhanceAll);
  }

  window.addEventListener("beforeunload", function () {
    previewUrls.forEach(URL.revokeObjectURL);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
