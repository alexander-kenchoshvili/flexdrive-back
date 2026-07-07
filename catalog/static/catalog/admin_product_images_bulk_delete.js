(function () {
  "use strict";

  function getCsrfToken() {
    var tokenInput = document.querySelector("input[name=csrfmiddlewaretoken]");
    return tokenInput ? tokenInput.value : "";
  }

  function getDeleteUrl() {
    var path = window.location.pathname;
    if (!path.endsWith("/change/")) return null;
    return path.slice(0, -"/change/".length) + "/images/delete-selected/";
  }

  function getExistingImageRows(group) {
    return Array.prototype.slice
      .call(group.querySelectorAll(".dynamic-images"))
      .filter(function (row) {
        var idInput = row.querySelector('input[type="hidden"][name$="-id"]');
        return idInput && idInput.value;
      });
  }

  function getSelectedRows(group) {
    return getExistingImageRows(group).filter(function (row) {
      var deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
      return deleteCheckbox && deleteCheckbox.checked;
    });
  }

  function setAllDeleteCheckboxes(group, checked) {
    getExistingImageRows(group).forEach(function (row) {
      var deleteCheckbox = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
      if (deleteCheckbox && !deleteCheckbox.disabled) {
        deleteCheckbox.checked = checked;
      }
    });
  }

  function selectedImageIds(group) {
    return getSelectedRows(group)
      .map(function (row) {
        var idInput = row.querySelector('input[type="hidden"][name$="-id"]');
        return idInput ? idInput.value : "";
      })
      .filter(Boolean);
  }

  function buildToolbar(group) {
    var toolbar = document.createElement("div");
    toolbar.className = "product-images-bulk-delete-toolbar";
    toolbar.style.display = "flex";
    toolbar.style.alignItems = "center";
    toolbar.style.gap = "8px";
    toolbar.style.margin = "10px 0";

    var selectAll = document.createElement("button");
    selectAll.type = "button";
    selectAll.className = "button";
    selectAll.textContent = "Select all images";
    selectAll.addEventListener("click", function () {
      setAllDeleteCheckboxes(group, true);
    });

    var clearSelection = document.createElement("button");
    clearSelection.type = "button";
    clearSelection.className = "button";
    clearSelection.textContent = "Clear selection";
    clearSelection.addEventListener("click", function () {
      setAllDeleteCheckboxes(group, false);
    });

    var deleteSelected = document.createElement("button");
    deleteSelected.type = "button";
    deleteSelected.className = "button deletelink";
    deleteSelected.textContent = "Delete selected images";
    deleteSelected.addEventListener("click", function () {
      submitSelectedDelete(group);
    });

    var hint = document.createElement("span");
    hint.textContent = "Deletes saved image rows immediately and keeps you on this product.";
    hint.style.opacity = "0.8";

    toolbar.appendChild(selectAll);
    toolbar.appendChild(clearSelection);
    toolbar.appendChild(deleteSelected);
    toolbar.appendChild(hint);
    return toolbar;
  }

  function submitSelectedDelete(group) {
    var ids = selectedImageIds(group);
    if (!ids.length) {
      window.alert("Select at least one saved product image to delete.");
      return;
    }

    var confirmed = window.confirm(
      "Delete " +
        ids.length +
        " selected product image" +
        (ids.length === 1 ? "" : "s") +
        "? Unsaved product edits on this page will not be saved."
    );
    if (!confirmed) return;

    var url = getDeleteUrl();
    if (!url) {
      window.alert("Could not determine the product image delete URL.");
      return;
    }

    var form = document.createElement("form");
    form.method = "post";
    form.action = url;

    var csrf = document.createElement("input");
    csrf.type = "hidden";
    csrf.name = "csrfmiddlewaretoken";
    csrf.value = getCsrfToken();
    form.appendChild(csrf);

    ids.forEach(function (id) {
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = "image_ids";
      input.value = id;
      form.appendChild(input);
    });

    document.body.appendChild(form);
    form.submit();
  }

  function bindBulkDelete() {
    var group = document.getElementById("images-group");
    if (!group || group.querySelector(".product-images-bulk-delete-toolbar")) return;

    var header = group.querySelector("h2");
    if (!header) return;

    header.insertAdjacentElement("afterend", buildToolbar(group));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindBulkDelete);
  } else {
    bindBulkDelete();
  }
})();
