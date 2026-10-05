// Time and summary formatting helpers (Spanish UI strings).
// Classic script: defines the global `Format` in the browser and exports it
// under node for the frontend tests.
var Format = (function () {
  function toSeconds(value) {
    var n = Number(value);
    return isFinite(n) && n > 0 ? n : 0;
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  // "menos de 1 min" | "~N min" | "~H h MM min"
  function formatEta(seconds) {
    var s = toSeconds(seconds);
    if (s < 60) return "menos de 1 min";
    var minutes = Math.round(s / 60);
    if (minutes < 60) return "~" + minutes + " min";
    var hours = Math.floor(minutes / 60);
    return "~" + hours + " h " + pad2(minutes % 60) + " min";
  }

  // "3 canciones en la cola | Quedan ~1 h 05 min"
  function formatSummary(count, totalSeconds) {
    var n = Number(count);
    if (!isFinite(n) || n < 0) n = 0;
    if (n === 0) return "0 canciones en la cola";
    var noun = n === 1 ? "canción" : "canciones";
    return n + " " + noun + " en la cola | Quedan " + formatEta(totalSeconds);
  }

  return { formatEta: formatEta, formatSummary: formatSummary };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Format;
}
