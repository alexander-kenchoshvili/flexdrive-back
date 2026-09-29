"use strict";
(() => {
    const mode = document.getElementById("id_period_mode");
    if (!mode) return;
    const update = () => {
        document.querySelectorAll(".accounting-field[data-field]").forEach(field => {
            const name = field.dataset.field;
            if (["start", "end", "start_month", "end_month"].includes(name)) {
                field.hidden = name.endsWith("_month") !== (mode.value === "months");
            }
        });
    };
    mode.addEventListener("change", update);
    update();
})();
