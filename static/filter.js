// Filters the coverage table as you type. The table is fully rendered server-side,
// so it works without this file; this only hides rows.
(function () {
  "use strict";

  var input = document.getElementById("journal-filter");
  var table = document.getElementById("coverage-table");
  var count = document.getElementById("result-count");
  var empty = document.getElementById("no-results");
  if (!input || !table) return;

  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var total = rows.length;
  var timer = null;

  function apply() {
    var query = input.value.trim().toLowerCase();
    var shown = 0;

    rows.forEach(function (row) {
      var match = !query || (row.dataset.name || "").indexOf(query) !== -1;
      row.hidden = !match;
      if (match) shown++;
    });

    if (empty) empty.hidden = shown !== 0;
    // All three states go through the one live region: an empty result and a
    // cleared field were both silent before.
    if (count) {
      count.textContent = !query
        ? "Showing all " + total + " journals"
        : shown === 0
          ? "No journal by that name in the survey. Send it along and I'll add it."
          : "Showing " + shown + " of " + total;
    }
  }

  // Debounced so a long table doesn't relayout on every keystroke.
  input.addEventListener("input", function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(apply, 120);
  });

  input.addEventListener("search", apply);
})();
