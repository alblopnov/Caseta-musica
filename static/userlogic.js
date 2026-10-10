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

  // Text of the "no audio output" notice, or null when it should stay hidden.
  // Only an explicit `audio_ok: false` shows it (older servers omit the key).
  function audioNotice(state) {
    return state && state.audio_ok === false ? "Sin salida de audio: las canciones esperan" : null;
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
    if (code === "shuffle_locked") {
      return "Otro teléfono tiene activado el aleatorio. Solo esa persona o el administrador puede cambiarlo.";
    }
    if (err && typeof err.message === "string" && err.message) return err.message;
    return "No se pudo completar la acción.";
  }

  function counterText(state) {
    if (!state || !state.me) return "";
    var pending = Number(state.me.pending) || 0;
    if (state.me.max === null) {  // the admin has no limit
      return "Tienes " + pending + (pending === 1 ? " canción" : " canciones") + " en la cola (sin límite)";
    }
    return "Tienes " + pending + " de " + maxOf(state) + " canciones en la cola";
  }

  // "Todas" reads better as "toda la biblioteca" inside a sentence.
  function sectionLabel(category) {
    return !category || category === "Todas" ? "toda la biblioteca" : category;
  }

  // The "Aleatorio" toggle for the selected section: what it says and what a press does.
  // action: "start" | "stop" | "change" | "none" (someone else's shuffle: not ours to touch).
  // `shuffle` is state.shuffle: null, or {category, can_stop}.
  function shuffleControl(category, shuffle) {
    var wanted = category || "Todas";
    if (!shuffle) {
      return {
        label: "Aleatorio",
        pressed: false,
        action: "start",
        hint: "Reproduce canciones al azar de " + sectionLabel(wanted) + " hasta que lo detengas",
      };
    }
    if (shuffle.category === wanted) {
      return shuffle.can_stop
        ? { label: "Aleatorio activo", pressed: true, action: "stop", hint: "Pulsa otra vez para detenerlo" }
        : {
            label: "Aleatorio activo",
            pressed: true,
            action: "none",
            hint: "Lo activó otro teléfono. Solo esa persona o el administrador puede detenerlo.",
          };
    }
    if (shuffle.can_stop) {
      return {
        label: "Cambiar a " + wanted,
        pressed: false,
        action: "change",
        hint: "Ahora suenan canciones al azar de " + sectionLabel(shuffle.category),
      };
    }
    return {
      label: "Aleatorio",
      pressed: false,
      action: "none",
      hint: "Aleatorio activo en " + sectionLabel(shuffle.category) + " (lo activó otro teléfono)",
    };
  }

  // The bar above the player while shuffle runs: {text, canStop}, or null when it is off.
  function shuffleStatus(shuffle) {
    if (!shuffle) return null;
    return { text: "Aleatorio activo: " + sectionLabel(shuffle.category), canStop: !!shuffle.can_stop };
  }

  function shuffleStartedMessage(category) {
    return "Aleatorio activado: " + sectionLabel(category);
  }

  function shuffleStoppedMessage() {
    return "Aleatorio detenido";
  }

  // Title and hint of the empty-queue panel.
  function emptyQueueText(state) {
    if (state && state.shuffle) {
      return {
        title: "Después sonará una canción al azar",
        hint: "Aleatorio activo: " + sectionLabel(state.shuffle.category) + ". Lo que añadas sonará antes.",
      };
    }
    return {
      title: nowPlaying(state) ? "No hay más canciones en la cola" : "La cola está vacía",
      hint: "Elige una canción de la lista para añadirla.",
    };
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
    audioNotice: audioNotice,
    isInQueue: isInQueue,
    songState: songState,
    conflictMessage: conflictMessage,
    counterText: counterText,
    shuffleControl: shuffleControl,
    shuffleStatus: shuffleStatus,
    shuffleStartedMessage: shuffleStartedMessage,
    shuffleStoppedMessage: shuffleStoppedMessage,
    emptyQueueText: emptyQueueText,
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
