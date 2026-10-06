// User page: library, queue and upload. DOM wiring only; the rules (texts,
// filtering, paging) live in userlogic.js. Every node is built with Common.el.
(function () {
  var el = Common.el;
  var POLL_MS = 3000;
  var UPLOAD_CATEGORY = "Subidas";

  var lastState = null;
  var stateSeq = 0; // responses older than the last applied one are dropped
  var appliedSeq = 0;

  var queueBox = document.getElementById("queue");
  var bannerBox = document.getElementById("queue-banner");
  var counterBox = document.getElementById("queue-counter");
  var summaryBox = document.getElementById("queue-info");
  var offlineNotice = document.getElementById("offline-notice");
  var audioNotice = document.getElementById("audio-notice");
  var uploadInput = document.getElementById("upload-input");
  var uploadBtn = document.getElementById("upload-btn");
  var uploadEnqueue = document.getElementById("upload-enqueue");

  var queueSig = null;
  var introPlayed = false;

  var player = NowPlaying.create();
  document.getElementById("now-playing").appendChild(player.node);

  // Library / add panel shared with the admin page (library.js).
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

  // -- queue --------------------------------------------------------------

  function removeItem(id) {
    Common.api("DELETE", "/api/queue/" + encodeURIComponent(id)).then(
      function () { return safeRefresh(); },
      function (err) {
        handleActionError(err);
        return safeRefresh();
      }
    );
  }

  // Owner tag and remove button. `onPlayer` uses the light style for the red card.
  function ownerControls(item, onPlayer) {
    if (!item.mine) return null;
    return [
      el("span", { class: "tag" }, "Tuya"),
      el("button", {
        class: onPlayer ? "btn btn-light" : "btn btn-text",
        type: "button",
        onclick: function (ev) {
          ev.currentTarget.disabled = true;
          removeItem(item.id);
        },
      }, el("span", { class: "ico ico-x", "aria-hidden": "true" }), "Quitar"),
    ];
  }

  function queueRow(item, etaText, index) {
    return el("div", { class: "q-row" + (item.mine ? " is-mine" : ""), style: "--i:" + index },
      el("span", { class: "q-pos", "aria-hidden": "true" }, String(index + 1)),
      el("div", { class: "q-main" },
        el("div", { class: "q-title" }, item.title),
        el("div", { class: "q-meta" }, "Suena en " + etaText)),
      el("div", { class: "q-actions" }, ownerControls(item, false)));
  }

  function emptyState(playing) {
    return el("div", { class: "empty" },
      el("span", { class: "ico ico-notes", "aria-hidden": "true" }),
      el("strong", null, playing ? "No hay más canciones en la cola" : "La cola está vacía"),
      el("span", null, "Elige una canción de la lista para añadirla."));
  }

  function renderQueue(state) {
    var np = state.now_playing || null;
    var queue = Array.isArray(state.queue) ? state.queue : [];

    var banner = UserLogic.computeBanner(state);
    setHidden(bannerBox, banner === null);
    bannerBox.textContent = banner === null ? "" : banner;
    counterBox.textContent = UserLogic.counterText(state);
    summaryBox.textContent = UserLogic.summaryLine(state);

    // The player card updates itself (and keeps its own bar ticking).
    player.update(np, function (playing) { return ownerControls(playing, true); });

    var etas = queue.map(function (item) { return Format.formatEta(item.eta_seconds); });
    var sig = JSON.stringify([
      !!np,
      queue.map(function (item, i) { return [item.id, item.title, item.mine, etas[i]]; }),
    ]);
    if (sig === queueSig) return;
    queueSig = sig;

    var rows = queue.map(function (item, i) { return queueRow(item, etas[i], i); });
    if (rows.length === 0) rows.push(emptyState(!!np));
    replaceChildren(queueBox, rows);
    if (!introPlayed) {
      introPlayed = true;
      queueBox.classList.add("is-intro"); // rows rise in once, on the first draw
      setTimeout(function () { queueBox.classList.remove("is-intro"); }, 1200);
    }
  }

  // -- state / polling -------------------------------------------------------

  function setOffline(offline) {
    setHidden(offlineNotice, !offline);
  }

  function renderAudioNotice(state) {
    var text = UserLogic.audioNotice(state);
    setHidden(audioNotice, text === null);
    audioNotice.textContent = text === null ? "" : text;
  }

  function refreshState() {
    var seq = ++stateSeq;
    return Common.api("GET", "/api/state").then(
      function (state) {
        setOffline(false);
        if (seq < appliedSeq || !state || typeof state !== "object") return;
        appliedSeq = seq;
        lastState = state;
        renderAudioNotice(state);
        renderQueue(state);
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

  function handleActionError(err) {
    panel.invalidate(); // rebuild the rows so disabled buttons come back
    queueSig = null;
    if (err && err.status === 409) {
      Common.toast(UserLogic.conflictMessage(err, lastState), "danger");
    } else {
      Common.toast((err && err.message) || "No se pudo completar la acción.", "danger");
    }
  }

  // -- upload ----------------------------------------------------------------

  function finishUpload() {
    uploadInput.value = "";
    panel.showCategory(UPLOAD_CATEGORY);
    return Promise.all([panel.load(), refreshState()]).catch(function () {});
  }

  uploadBtn.onclick = function () {
    if (uploadBtn.disabled) return;
    if (!uploadInput.files || !uploadInput.files.length) {
      Common.toast("Selecciona un archivo .mp3, .wav u .ogg", "warning");
      return;
    }
    var form = new FormData();
    form.append("song", uploadInput.files[0]);
    if (uploadEnqueue.checked) form.append("enqueue", "1");
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Subiendo…";
    Common.api("POST", "/api/upload", form).then(
      function () {
        Common.toast("Canción subida", "success");
        return finishUpload();
      },
      function (err) {
        handleActionError(err);
        // 409: the file was saved but not queued, so the library changed anyway.
        if (err && err.status === 409) return finishUpload();
      }
    ).then(function () {
      uploadBtn.disabled = false;
      uploadBtn.textContent = "Subir";
    });
  };

  panel.load().catch(function () {}); // polling retries it if this fails
  Common.startPolling(refreshState, POLL_MS);
})();
