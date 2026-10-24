// The FAQ uses native <details>, so everything below is an enhancement:
// with JavaScript off the questions still open and close on their own.
(function () {
  "use strict";

  var list = document.getElementById("faq-list");
  var toggle = document.getElementById("faq-toggle");
  if (!list) return;

  var items = Array.prototype.slice.call(list.querySelectorAll("details.qa"));

  // This page gets forwarded and printed for editorial-board meetings, so a
  // collapsed answer must never be missing from the printout. Open everything
  // before printing, then restore whatever the reader had open.
  var restore = [];
  function openAllForPrint() {
    restore = items.map(function (item) { return item.open; });
    items.forEach(function (item) { item.open = true; });
  }
  function restoreAfterPrint() {
    items.forEach(function (item, i) { item.open = restore[i]; });
  }
  window.addEventListener("beforeprint", openAllForPrint);
  window.addEventListener("afterprint", restoreAfterPrint);
  if (!toggle) return;

  function sync() {
    var allOpen = items.every(function (item) { return item.open; });
    toggle.textContent = allOpen ? "Close all" : "Open all " + numberWord(items.length);
  }

  function numberWord(n) {
    var words = ["", "one", "two", "three", "four", "five",
                 "six", "seven", "eight", "nine", "ten"];
    return words[n] || String(n);
  }

  toggle.addEventListener("click", function () {
    var opening = !items.every(function (item) { return item.open; });
    items.forEach(function (item) { item.open = opening; });
    sync();
  });

  // Keep the button honest when someone opens questions one at a time.
  items.forEach(function (item) { item.addEventListener("toggle", sync); });

  sync();
})();

// Open and scroll to a question when the URL carries its fragment, so a link
// to a specific answer lands on an open one.
(function () {
  "use strict";
  function openFromHash() {
    if (!location.hash) return;
    var target = document.getElementById(location.hash.slice(1));
    if (!target) return;
    var details = target.closest ? target.closest("details.qa") : null;
    if (details) details.open = true;
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();
})();
