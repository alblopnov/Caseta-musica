// Admin page: PIN login, queue with remove / skip / drag-and-drop reorder, and
// the library panel shared with the user page. DOM wiring only; the rules live
// in adminlogic.js and userlogic.js. Every node is built with Common.el.
(function () {
  var el = Common.el;
  var POLL_MS = 3000;

  var isAdmin = false;
  var pollingStarted = false;
  var lastState = null;
  var stateSeq = 0; // responses older than the last applied one are dropped
  var appliedSeq = 0;
  var queueSig = null; // last rendered queue, to skip identical re-renders
  var renderedQueue = []; // queue items as drawn: drop positions are computed on these
  var dragging = null; // id of the queued row being dragged; freezes the queue DOM

  var offlineNotice = document.getElementById("offline-notice");
  var loginSection = document.getElementById("login-section");
  var adminSection = document.getElementById("admin-section");
  var pinForm = document.getElementById("pin-form");
  var pinInput = document.getElementById("pin-input");
  var pinError = document.getElementById("pin-error");
  var pinBtn = document.getElementById("pin-btn");
  var skipBtn = document.getElementById("skip-btn");
  var queueBox = document.getElementById("queue");
  var summaryBox = document.getElementById("queue-info");

  // Library / add panel shared with the user page (library.js).
  var panel = LibraryPanel.create({
    getState: function () { return lastState; },
    refresh: function () { return safeRefresh(); },
    onError: function (err) { handleActionError(err); },
  });

  function replaceChildren(node, children) {
    while (node.firstChild) node.removeChild(node.firstChild);
    children.forEach(function (c) { node.appendChild(c); });
  }

  function setHidden(node, hidden) {
    node.classList.toggle("is-hidden", hidden);
  }

  // -- login ---------------------------------------------------------------

  function showLogin(message) {
    isAdmin = false;
    dragging = null;
    setHidden(adminSection, true);
    setHidden(loginSection, false);
    pinError.textContent = message || "";
    pinInput.value = "";
    pinInput.focus();
  }

  function showPanel() {
    isAdmin = true;
    setHidden(loginSection, true);
    setHidden(adminSection, false);
    pinError.textContent = "";
    queueSig = null;
    panel.invalidate();
    panel.load().catch(function () {}); // polling retries it if this fails
    if (pollingStarted) {
      safeRefresh();
    } else {
      pollingStarted = true;
      Common.startPolling(poll, POLL_MS);
    }
  }

  function checkSession() {
    Common.api("GET", "/api/admin/session").then(
      function (data) {
        setOffline(false);
        if (data && data.admin === true) showPanel();
        else showLogin("");
      },
      function () {
        setOffline(true);
        setTimeout(checkSession, POLL_MS);
      }
    );
  }

  pinForm.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (pinBtn.disabled) return;
    pinBtn.disabled = true;
    pinError.textContent = "";
    Common.api("POST", "/api/admin/login", { pin: pinInput.value }).then(
      function () {
        pinBtn.disabled = false;
        showPanel();
      },
      function (err) {
        pinBtn.disabled = false;
        pinInput.value = "";
        pinError.textContent = AdminLogic.pinErrorMessage(err);
        pinInput.focus();
      }
    );
  });

  // -- queue ----------------------------------------------------------------

  function removeItem(id) {
    Common.api("DELETE", "/api/queue/" + encodeURIComponent(id)).then(
      function () { return safeRefresh(); },
      function (err) {
        handleActionError(err);
        return safeRefresh();
      }
    );
  }

  function removeButton(item) {
    return el("button", {
      class: "button is-danger is-light ml-2",
      type: "button",
      onclick: function (ev) {
        ev.currentTarget.disabled = true;
        removeItem(item.id);
      },
    }, "Eliminar");
  }

  function playingRow(np) {
    return el("div", { class: "py-2" },
      el("div", { class: "is-flex is-align-items-center is-justify-content-space-between" },
        el("div", { class: "mr-2", style: "min-width:0;overflow-wrap:anywhere" },
          el("span", { class: "tag is-success mr-2" }, "Sonando"),
          el("strong", null, np.title)),
        el("div", { class: "is-flex is-align-items-center is-flex-shrink-0" }, removeButton(np))),
      el("progress", { class: "progress is-success is-small mt-2 mb-0", value: Math.round(UserLogic.clampElapsed(np)), max: Math.round(Number(np.duration) || 0) || 1 }));
  }

  function queueRow(item, etaText, state) {
    var props = {
      class: "queue-row is-flex is-align-items-center is-justify-content-space-between py-2",
      dataset: { queueId: item.id },
    };
    var handle = null;
    if (AdminLogic.isDraggable(item, state)) {
      handle = el("span", { class: "drag-handle mr-2", title: "Arrastra para reordenar", "aria-label": "Arrastrar para reordenar" }, "⠿");
      props.draggable = "true";
      // Mouse: HTML5 drag and drop on the whole row.
      props.ondragstart = function (ev) {
        if (ev.target.closest && ev.target.closest("button")) {
          ev.preventDefault();
          return;
        }
        startDrag(item.id, ev.currentTarget);
        if (ev.dataTransfer) {
          ev.dataTransfer.effectAllowed = "move";
          try { ev.dataTransfer.setData("text/plain", item.id); } catch (e) { /* IE-style failure: ignore */ }
        }
      };
      props.ondragover = function (ev) {
        if (dragging === null) return;
        ev.preventDefault(); // allows the drop
        if (ev.dataTransfer) ev.dataTransfer.dropEffect = "move";
        markTarget(ev.currentTarget);
      };
      props.ondrop = function (ev) {
        if (dragging === null) return;
        ev.preventDefault();
        finishDrag(item.id);
      };
      props.ondragend = function () { finishDrag(null); };
    }
    var row = el("div", props,
      el("div", { class: "is-flex is-align-items-center mr-2", style: "min-width:0" },
        handle,
        el("div", { style: "min-width:0;overflow-wrap:anywhere" },
          el("div", null, item.title),
          el("small", { class: "has-text-grey" }, etaText))),
      el("div", { class: "is-flex is-align-items-center is-flex-shrink-0" }, removeButton(item)));
    if (handle) addTouchDrag(row, item.id);
    return row;
  }

  // Touch: a drag starts only on the grip so the page still scrolls everywhere
  // else. addEventListener (not on* properties): touch handlers must be
  // non-passive to cancel scrolling, and they are real listeners on any device.
  function addTouchDrag(row, id) {
    row.addEventListener("touchstart", function (ev) {
      if (ev.target.closest && ev.target.closest("button")) return;
      if (!ev.target.closest || !ev.target.closest(".drag-handle")) return;
      if (!ev.touches || ev.touches.length !== 1) return;
      startDrag(id, row);
    }, { passive: true });
    row.addEventListener("touchmove", function (ev) {
      if (dragging === null) return;
      ev.preventDefault(); // no page scroll while a drag is active
      var t = ev.touches[0];
      markTarget(rowAt(t.clientX, t.clientY));
    }, { passive: false });
    row.addEventListener("touchend", function (ev) {
      if (dragging === null) return;
      ev.preventDefault();
      var t = ev.changedTouches[0];
      var target = rowAt(t.clientX, t.clientY);
      finishDrag(target ? target.dataset.queueId : null);
    }, { passive: false });
    row.addEventListener("touchcancel", function () { finishDrag(null); });
  }

  function renderQueue(state) {
    var np = state.now_playing || null;
    var queue = Array.isArray(state.queue) ? state.queue : [];

    summaryBox.textContent = UserLogic.summaryLine(state);

    var etas = queue.map(function (item) { return Format.formatEta(item.eta_seconds); });
    var sig = JSON.stringify([
      np && [np.id, np.title],
      queue.map(function (item, i) { return [item.id, item.title, etas[i]]; }),
    ]);
    if (sig === queueSig) {
      var bar = queueBox.querySelector("progress");
      if (bar && np) bar.value = Math.round(UserLogic.clampElapsed(np));
      return;
    }
    queueSig = sig;
    renderedQueue = queue;

    var rows = [];
    if (np) rows.push(playingRow(np));
    queue.forEach(function (item, i) { rows.push(queueRow(item, etas[i], state)); });
    if (rows.length === 0) rows.push(el("p", { class: "has-text-grey has-text-centered" }, "La cola está vacía."));
    replaceChildren(queueBox, rows);
  }

  // -- drag and drop ------------------------------------------------------------

  function clearDragMarks() {
    var marked = queueBox.querySelectorAll(".is-dragging, .is-drop-target");
    Array.prototype.forEach.call(marked, function (node) {
      node.classList.remove("is-dragging", "is-drop-target");
    });
  }

  function startDrag(id, row) {
    dragging = id;
    row.classList.add("is-dragging");
  }

  function markTarget(row) {
    var old = queueBox.querySelectorAll(".is-drop-target");
    Array.prototype.forEach.call(old, function (node) {
      if (node !== row) node.classList.remove("is-drop-target");
    });
    if (row && row.dataset.queueId !== dragging) row.classList.add("is-drop-target");
  }

  // The queued row under a screen point (touch), or null.
  function rowAt(x, y) {
    var node = document.elementFromPoint(x, y);
    var row = node && node.closest ? node.closest("[data-queue-id]") : null;
    return row && queueBox.contains(row) ? row : null;
  }

  // Ends the drag (targetId null = dropped nowhere) and refreshes once.
  function finishDrag(targetId) {
    var id = dragging;
    if (id === null) return Promise.resolve();
    dragging = null;
    clearDragMarks();
    queueSig = null; // the next refresh redraws the rows
    var position = AdminLogic.movePosition(renderedQueue, id, targetId);
    if (position === null) return safeRefresh();
    return Common.api("POST", "/api/queue/" + encodeURIComponent(id) + "/move", { position: position }).then(
      function () { return safeRefresh(); },
      function (err) {
        handleActionError(err);
        return safeRefresh();
      }
    );
  }

  // -- skip ---------------------------------------------------------------------

  skipBtn.addEventListener("click", function () {
    if (skipBtn.disabled) return;
    skipBtn.disabled = true;
    Common.api("POST", "/api/skip").then(
      function () { return safeRefresh(); },
      function (err) {
        handleActionError(err);
        return safeRefresh();
      }
    ).then(function () {
      skipBtn.disabled = false;
    });
  });

  // -- state / polling -------------------------------------------------------------

  function setOffline(offline) {
    setHidden(offlineNotice, !offline);
  }

  function refreshState() {
    var seq = ++stateSeq;
    return Common.api("GET", "/api/state").then(
      function (state) {
        setOffline(false);
        if (!isAdmin || seq < appliedSeq || !state || typeof state !== "object") return;
        appliedSeq = seq;
        lastState = state;
        if (dragging === null) renderQueue(state); // never rebuild rows under a drag
        panel.render(false);
        if (!panel.isLoaded()) panel.load().catch(function () {});
      },
      function (err) {
        setOffline(true);
        throw err;
      }
    );
  }

  function safeRefresh() {
    return refreshState().catch(function () {});
  }

  function poll() {
    return isAdmin ? refreshState() : Promise.resolve();
  }

  function handleActionError(err) {
    panel.invalidate(); // rebuild the rows so disabled buttons come back
    queueSig = null;
    if (AdminLogic.isSessionError(err)) {
      // Cookie gone (expired session / restarted server): back to the PIN form.
      Common.api("GET", "/api/admin/session").then(
        function (data) {
          if (data && data.admin === true) {
            Common.toast((err && err.message) || "No se pudo completar la acción.", "danger");
          } else {
            showLogin(AdminLogic.SESSION_EXPIRED_MESSAGE);
          }
        },
        function () { Common.toast((err && err.message) || "No se pudo completar la acción.", "danger"); }
      );
      return;
    }
    if (err && err.status === 409) {
      Common.toast(UserLogic.conflictMessage(err, lastState), "danger");
    } else {
      Common.toast((err && err.message) || "No se pudo completar la acción.", "danger");
    }
  }

  checkSession();
})();
