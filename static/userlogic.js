// Pure helpers for the user page (texts, states, filtering, paging).
// Classic script: defines the global `UserLogic` in the browser (after
// format.js) and exports it under node for the frontend tests.
var UserLogic = (function () {
  var FormatLib = typeof Format !== "undefined" ? Format : require("./format.js");

  var DEFAULT_MAX = 5;

  function nowPlaying(state) {
    return state && state.now_playing ? state.now_playing : null;
  }

  function queueOf(state) {
    return state && Array.isArray(state.queue) ? state.queue : [];
  }

  function maxOf(state) {
    var max = state && state.me ? Number(state.me.max) : NaN;
    return isFinite(max) && max > 0 ? max : DEFAULT_MAX;
  }

  // Text of the banner above the queue, or null when it should stay hidden.
  function computeBanner(state) {
    var mine = queueOf(state).filter(function (item) { return item && item.mine; })[0];
    if (mine) return "Tu próxima canción suena en " + FormatLib.formatEta(mine.eta_seconds);
    var np = nowPlaying(state);
    if (np && np.mine) return "Tu canción está sonando";
    return null;
  }

  function isInQueue(song, state) {
    var np = nowPlaying(state);
    if (np && np.song === song) return true;
    return queueOf(state).some(function (item) { return item && item.song === song; });
  }

  // "playing" | "queued" | "available"
  function songState(song, state) {
    var np = nowPlaying(state);
    if (np && np.song === song) return "playing";
    var queued = queueOf(state).some(function (item) { return item && item.song === song; });
    return queued ? "queued" : "available";
  }

  // Toast text for a 409 from POST /api/queue or /api/upload.
  function conflictMessage(err, state) {
    var code = err && err.code;
    if (code === "full") {
      return "Ya tienes " + maxOf(state) + " canciones en la cola. Espera a que suene alguna.";
    }
    if (code === "duplicate") return "Esa canción ya está en la cola.";
    if (err && typeof err.message === "string" && err.message) return err.message;
    return "No se pudo completar la acción.";
  }

  function counterText(state) {
    if (!state || !state.me) return "";
    return "Tienes " + (Number(state.me.pending) || 0) + " de " + maxOf(state) + " canciones en la cola";
  }

  // The playing song counts as one more song in the footer.
  function summaryLine(state) {
    var count = queueOf(state).length + (nowPlaying(state) ? 1 : 0);
    return FormatLib.formatSummary(count, state ? state.total_seconds : 0);
  }

  // `elapsed` can exceed `duration` (the engine does not cap it).
  function clampElapsed(np) {
    if (!np) return 0;
    var elapsed = Number(np.elapsed);
    var duration = Number(np.duration);
    if (!isFinite(elapsed) || elapsed < 0) elapsed = 0;
    if (!isFinite(duration) || duration < 0) duration = 0;
    return Math.min(elapsed, duration);
  }

  function progressFraction(np) {
    if (!np) return 0;
    var duration = Number(np.duration);
    if (!isFinite(duration) || duration <= 0) return 0;
    return clampElapsed(np) / duration;
  }

  // "Todas" plus the top-level folders; songs at the root only show in "Todas".
  function categories(songs) {
    var folders = [];
    (songs || []).forEach(function (path) {
      var parts = String(path).split("/");
      if (parts.length > 1 && folders.indexOf(parts[0]) === -1) folders.push(parts[0]);
    });
    folders.sort();
    return ["Todas"].concat(folders);
  }

  function songTitle(path) {
    var name = String(path).split("/").pop();
    return name.replace(/\.[^/.]+$/, "");
  }

  // Category plus a case-insensitive search on the title (not the folder).
  function filterSongs(songs, category, term) {
    var needle = String(term || "").trim().toLowerCase();
    return (songs || []).filter(function (path) {
      if (category && category !== "Todas" && path.indexOf(category + "/") !== 0) return false;
      return !needle || songTitle(path).toLowerCase().indexOf(needle) !== -1;
    });
  }

  // {items, page, totalPages}: `page` is clamped to the valid range.
  function paginate(items, page, perPage) {
    var list = items || [];
    var totalPages = Math.max(1, Math.ceil(list.length / perPage));
    var current = Math.min(Math.max(1, Math.floor(Number(page)) || 1), totalPages);
    var start = (current - 1) * perPage;
    return { items: list.slice(start, start + perPage), page: current, totalPages: totalPages };
  }

  return {
    computeBanner: computeBanner,
    isInQueue: isInQueue,
    songState: songState,
    conflictMessage: conflictMessage,
    counterText: counterText,
    summaryLine: summaryLine,
    clampElapsed: clampElapsed,
    progressFraction: progressFraction,
    categories: categories,
    songTitle: songTitle,
    filterSongs: filterSongs,
    paginate: paginate,
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = UserLogic;
}
