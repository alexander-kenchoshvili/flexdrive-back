(function () {
  "use strict";
  var SCALE = 10000000000n;

  function decimal(value, places) {
    var text = String(value).trim().replace(",", ".");
    if (!/^\d+(\.\d*)?$/.test(text)) return null;
    var parts = text.split(".");
    var fraction = parts[1] || "";
    if (fraction.length > places) return null;
    return BigInt(parts[0]) * (10n ** BigInt(places)) +
      BigInt(fraction.padEnd(places, "0") || "0");
  }

  function fixed(value, places) {
    var text = value.toString().padStart(places + 1, "0");
    return text.slice(0, -places) + "." + text.slice(-places);
  }

  function roundedDivide(value, divisor) {
    return (value + divisor / 2n) / divisor;
  }

  function readonly(name) {
    return document.querySelector(".field-" + name + " .readonly");
  }

  function bind() {
    var supplier = document.getElementById("id_supplier_price");
    var markup = document.getElementById("id_markup_percent_override");
    var price = document.getElementById("id_price");
    var mode = document.getElementById("id_pricing_input");
    var preview = readonly("calculated_customer_price_readonly");
    if (!supplier || !markup || !price || !mode) return;
    var exactMarkup = decimal(markup.getAttribute("data-exact-markup") || markup.value || "0", 10);

    function update() {
      price.setCustomValidity("");
      if (!mode.value) mode.value = "supplier";
      var cost = decimal(supplier.value, 2);
      if (cost === null) {
        if (preview) preview.textContent = price.value ? price.value + " GEL" : "—";
        return;
      }
      var amount;
      if (mode.value === "price") {
        amount = decimal(price.value, 2);
        if (amount === null) return;
        if (cost === 0n && amount !== 0n) {
          price.setCustomValidity("ფასნამატის გამოსათვლელად მომწოდებლის ფასი უნდა იყოს ნულზე მეტი.");
          return;
        }
        if (amount < cost || amount > cost * 11n) {
          price.setCustomValidity("გასაყიდი ფასი უნდა შეესაბამებოდეს 0–1000% ფასნამატს.");
          return;
        }
        if (cost > 0n) {
          var rate = roundedDivide((amount - cost) * 100n * SCALE, cost);
          exactMarkup = rate;
          markup.value = fixed(roundedDivide(rate, SCALE / 100n), 2);
        }
      } else {
        var percent = exactMarkup;
        if (percent === null) return;
        amount = roundedDivide(cost * (100n * SCALE + percent), 100n * SCALE);
        price.value = fixed(amount, 2);
      }
      if (preview) preview.textContent = fixed(amount, 2) + " GEL";
    }

    price.addEventListener("input", function () { mode.value = "price"; update(); });
    markup.addEventListener("input", function () {
      exactMarkup = decimal(markup.value.trim() || "0", 10);
      mode.value = "markup";
      update();
    });
    supplier.addEventListener("input", update);
    // Keep bound values intact when redisplaying server-side validation errors.
    // Only edits should select a source and change another input.
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bind);
  } else {
    bind();
  }
})();
