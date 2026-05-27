(function () {
  "use strict";

  function parseDecimal(value) {
    if (value === null || value === undefined) return null;
    var normalized = String(value).trim().replace(",", ".");
    if (!normalized) return null;

    var parsed = Number(normalized.replace(/[^\d.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function formatMoney(value) {
    return value.toFixed(2) + " GEL";
  }

  function findReadonlyValue(fieldName) {
    var row = document.querySelector(".field-" + fieldName);
    if (!row) return null;
    return row.querySelector(".readonly");
  }

  function findInput(id) {
    return document.getElementById(id);
  }

  function updatePricingPreview() {
    var supplierInput = findInput("id_supplier_price");
    var overrideInput = findInput("id_markup_percent_override");
    var categoryMarkupNode = findReadonlyValue("category_markup_readonly");
    var calculatedNode = findReadonlyValue("calculated_customer_price_readonly");
    var priceNode = findReadonlyValue("price");
    var priceInput = findInput("id_price");

    if (!supplierInput || !calculatedNode) return;

    var supplierPrice = parseDecimal(supplierInput.value);
    if (supplierPrice === null) return;

    var overrideMarkup = overrideInput ? parseDecimal(overrideInput.value) : null;
    var categoryMarkup = categoryMarkupNode
      ? parseDecimal(categoryMarkupNode.textContent)
      : 0;
    var markup = overrideMarkup !== null ? overrideMarkup : categoryMarkup || 0;
    var finalPrice = supplierPrice * (1 + markup / 100);
    var formatted = formatMoney(finalPrice);

    calculatedNode.textContent = formatted;
    calculatedNode.title = "Live preview. Save the product to apply this price.";

    if (priceNode) {
      priceNode.textContent = finalPrice.toFixed(2);
      priceNode.title = "Live preview. Save the product to apply this price.";
    }

    if (priceInput && priceInput.readOnly) {
      priceInput.value = finalPrice.toFixed(2);
    }
  }

  function bindPricingPreview() {
    var supplierInput = findInput("id_supplier_price");
    var overrideInput = findInput("id_markup_percent_override");

    if (supplierInput) {
      supplierInput.addEventListener("input", updatePricingPreview);
      supplierInput.addEventListener("change", updatePricingPreview);
    }

    if (overrideInput) {
      overrideInput.addEventListener("input", updatePricingPreview);
      overrideInput.addEventListener("change", updatePricingPreview);
    }

    updatePricingPreview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindPricingPreview);
  } else {
    bindPricingPreview();
  }
})();
