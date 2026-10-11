// Pure helpers for the admin page (reorder position, PIN error texts, which
// rows can be dragged, the volume slider's value and label). Classic script:
// defines the global `AdminLogic` in the browser and exports it under node for
// the frontend tests.
var AdminLogic = (function () {
  var SESSION_EXPIRED_MESSAGE = "La sesión de administrador caducó. Introduce el PIN otra vez.";

  function idsOf(queue) {
    return Array.isArray(queue)
      ? queue.map(function (item) { return item ? item.id : undefined; })
      : [];
  }

  // 1-based position among the queued songs (the playing one is not part of
  // `queue`) for dropping `draggedId` on the row `targetId`; null if no move.
  function movePosition(queue, draggedId, targetId) {
    if (draggedId === null || draggedId === undefined) return null;
    if (targetId === null || targetId === undefined) return null;
    if (draggedId === targetId) return null;
    var ids = idsOf(queue);
    if (ids.indexOf(draggedId) === -1) return null;
    var index = ids.indexOf(targetId);
    return index === -1 ? null : index + 1;
  }

  // Only queued rows can be reordered; the playing song is not in state.queue.
  function isDraggable(item, state) {
    if (!item || !state || !Array.isArray(state.queue)) return false;
    return idsOf(state.queue).indexOf(item.id) !== -1;
  }

  // Text under the PIN field for a failed POST /api/admin/login.
  function pinErrorMessage(err) {
    var status = err ? err.status : undefined;
    if (status === 401) return "PIN incorrecto";
    if (status === 429) return "Demasiados intentos. Espera un minuto.";
    if (status === 503) return "El administrador no está configurado en el servidor";
    if ((status === 0 || status >= 500) && err && typeof err.message === "string" && err.message) {
      return err.message;
    }
    return "No se pudo iniciar sesión.";
  }

  // An admin action answered 401 (cookie gone) or 403 (remove falls back to the
  // owner check without the cookie): the page re-checks the session.
  function isSessionError(err) {
    return !!err && (err.status === 401 || err.status === 403);
  }

  // Text beside the volume slider: 0 is silence, anything else the percentage.
  function volumeLabel(percent) {
    return percent === 0 ? "Silencio" : percent + "%";
  }

  // The volume in /api/state when it is a whole number from 0 to 100, else null
  // (an older server, or a bad payload, leaves the slider alone).
  function volumeOf(state) {
    var volume = state ? state.volume : undefined;
    return Number.isInteger(volume) && volume >= 0 && volume <= 100 ? volume : null;
  }

  return {
    SESSION_EXPIRED_MESSAGE: SESSION_EXPIRED_MESSAGE,
    movePosition: movePosition,
    isDraggable: isDraggable,
    pinErrorMessage: pinErrorMessage,
    isSessionError: isSessionError,
    volumeLabel: volumeLabel,
    volumeOf: volumeOf,
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AdminLogic;
}
