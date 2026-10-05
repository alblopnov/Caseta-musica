// User page: library, queue and upload. DOM wiring only; the rules (texts,
// filtering, paging) live in userlogic.js. Every node is built with Common.el.
(function () {
  var el = Common.el;
  var SONGS_PER_PAGE = 20;
  var POLL_MS = 3000;
  var UPLOAD_CATEGORY = "Subidas";

  var allSongs = [];
  var songsLoaded = false;
  var songsLoading = false;
  var selectedCategory = "Todas";
  var currentPage = 1;
  var lastState = null;
  var stateSeq = 0; // responses older than the last applied one are dropped
  var appliedSeq = 0;

  var searchInput = document.getElementById("search");
  var prevBtn = document.getElementById("prev-page");
  var nextBtn = document.getElementById("next-page");
  var pageInfo = document.getElementById("page-info");
  var categoriesBox = document.getElementById("categories");
  var songBody = document.querySelector("#song-list tbody");
  var queueBox = document.getElementById("queue");
  var bannerBox = document.getElementById("queue-banner");
  var counterBox = document.getElementById("queue-counter");
  var summaryBox = document.getElementById("queue-info");
  var offlineNotice = document.getElementById("offline-notice");
  var uploadInput = document.getElementById("upload-input");
  var uploadBtn = document.getElementById("upload-btn");
  var uploadEnqueue = document.getElementById("upload-enqueue");

  var songsSig = null; // last rendered song rows, to skip identical re-renders
  var queueSig = null;

  function replaceChildren(node, children) {
    while (node.firstChild) node.removeChild(node.firstChild);
    children.forEach(function (c) { node.appendChild(c); });
  }

  function setHidden(node, hidden) {
    node.classList.toggle("is-hidden", hidden);
  }

  // -- library ------------------------------------------------------------

  function renderCategories(names) {
    replaceChildren(
      categoriesBox,
      names.map(function (name) {
        var kind = name === selectedCategory ? "is-primary" : name === "Todas" ? "is-white" : "is-light";
        return el("button", {
          class: "button " + kind,
          type: "button",
          onclick: function () {
            selectedCategory = name;
            currentPage = 1;
            renderSongs(true);
          },
        }, name);
      })
    );
  }

  function addSong(song) {
    Common.api("POST", "/api/queue", { song: song }).then(
      function () { return safeRefresh(); },
      function (err) {
        handleActionError(err);
        return safeRefresh();
      }
    );
  }

  function songRow(song) {
    var inQueue = UserLogic.isInQueue(song, lastState);
    var button = inQueue
      ? el("button", { class: "button", type: "button", disabled: true }, "En la cola")
      : el("button", {
          class: "button is-primary",
          type: "button",
          onclick: function (ev) {
            ev.currentTarget.disabled = true;
            addSong(song);
          },
        }, "Añadir");
    return el("tr", null,
      el("td", { class: "is-vcentered" }, UserLogic.songTitle(song)),
      el("td", { class: "has-text-right" }, button));
  }

  function renderSongs(force) {
    var names = UserLogic.categories(allSongs);
    if (names.indexOf(selectedCategory) === -1) selectedCategory = "Todas";
    var filtered = UserLogic.filterSongs(allSongs, selectedCategory, searchInput.value);
    var page = UserLogic.paginate(filtered, currentPage, SONGS_PER_PAGE);
    currentPage = page.page;

    // Polling re-renders every 3 s; skip when nothing visible changed so a
    // tap in progress is never swallowed by a rebuilt button.
    var sig = JSON.stringify([
      names, selectedCategory, page.page, page.totalPages,
      page.items.map(function (s) { return [s, UserLogic.songState(s, lastState)]; }),
    ]);
    if (!force && sig === songsSig) return;
    songsSig = sig;

    renderCategories(names);
    prevBtn.disabled = page.page <= 1;
    nextBtn.disabled = page.page >= page.totalPages;
    pageInfo.textContent = "Página " + page.page + " de " + page.totalPages;
    if (page.items.length === 0) {
      replaceChildren(songBody, [
        el("tr", null, el("td", { colspan: 2, class: "has-text-grey" },
          allSongs.length === 0 ? "No hay canciones todavía." : "No hay canciones que coincidan.")),
      ]);
    } else {
      replaceChildren(songBody, page.items.map(songRow));
    }
  }

  function loadSongs() {
    if (songsLoading) return Promise.resolve();
    songsLoading = true;
    return Common.api("GET", "/api/songs").then(
      function (data) {
        songsLoading = false;
        allSongs = Array.isArray(data) ? data : [];
        songsLoaded = true;
        renderSongs(true);
      },
      function (err) {
        songsLoading = false;
        throw err; // polling retries while songsLoaded is false
      }
    );
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

  function ownerControls(item) {
    if (!item.mine) return null;
    return [
      el("span", { class: "tag is-warning ml-2" }, "Tuya"),
      el("button", {
        class: "button is-danger is-light ml-2",
        type: "button",
        onclick: function (ev) {
          ev.currentTarget.disabled = true;
          removeItem(item.id);
        },
      }, "Quitar"),
    ];
  }

  function queueRow(item, etaText) {
    return el("div", { class: "is-flex is-align-items-center is-justify-content-space-between py-2" },
      el("div", { class: "mr-2", style: "min-width:0;overflow-wrap:anywhere" },
        el("div", null, item.title),
        el("small", { class: "has-text-grey" }, etaText)),
      el("div", { class: "is-flex is-align-items-center is-flex-shrink-0" }, ownerControls(item)));
  }

  function playingRow(np) {
    return el("div", { class: "py-2" },
      el("div", { class: "is-flex is-align-items-center is-justify-content-space-between" },
        el("div", { class: "mr-2", style: "min-width:0;overflow-wrap:anywhere" },
          el("span", { class: "tag is-success mr-2" }, "Sonando"),
          el("strong", null, np.title)),
        el("div", { class: "is-flex is-align-items-center is-flex-shrink-0" }, ownerControls(np))),
      el("progress", { class: "progress is-success is-small mt-2 mb-0", value: Math.round(UserLogic.clampElapsed(np)), max: Math.round(Number(np.duration) || 0) || 1 }));
  }

  function renderQueue(state) {
    var np = state.now_playing || null;
    var queue = Array.isArray(state.queue) ? state.queue : [];

    var banner = UserLogic.computeBanner(state);
    setHidden(bannerBox, banner === null);
    bannerBox.textContent = banner === null ? "" : banner;
    counterBox.textContent = UserLogic.counterText(state);
    summaryBox.textContent = UserLogic.summaryLine(state);

    var etas = queue.map(function (item) { return Format.formatEta(item.eta_seconds); });
    var sig = JSON.stringify([
      np && [np.id, np.title, np.mine],
      queue.map(function (item, i) { return [item.id, item.title, item.mine, etas[i]]; }),
    ]);
    if (sig === queueSig) {
      var bar = queueBox.querySelector("progress");
      if (bar && np) bar.value = Math.round(UserLogic.clampElapsed(np));
      return;
    }
    queueSig = sig;

    var rows = [];
    if (np) rows.push(playingRow(np));
    queue.forEach(function (item, i) { rows.push(queueRow(item, etas[i])); });
    if (rows.length === 0) rows.push(el("p", { class: "has-text-grey has-text-centered" }, "La cola está vacía."));
    replaceChildren(queueBox, rows);
  }

  // -- state / polling -------------------------------------------------------

  function setOffline(offline) {
    setHidden(offlineNotice, !offline);
  }

  function refreshState() {
    var seq = ++stateSeq;
    return Common.api("GET", "/api/state").then(
      function (state) {
        setOffline(false);
        if (seq < appliedSeq || !state || typeof state !== "object") return;
        appliedSeq = seq;
        lastState = state;
        renderQueue(state);
        renderSongs(false);
        if (!songsLoaded) loadSongs().catch(function () {});
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
    songsSig = null; // rebuild the rows so disabled buttons come back
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
    searchInput.value = "";
    selectedCategory = UPLOAD_CATEGORY;
    currentPage = 1;
    return Promise.all([loadSongs(), refreshState()]).catch(function () {});
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

  // -- events ----------------------------------------------------------------

  searchInput.addEventListener("input", function () {
    currentPage = 1;
    renderSongs(true);
  });
  prevBtn.addEventListener("click", function () {
    currentPage--;
    renderSongs(true);
  });
  nextBtn.addEventListener("click", function () {
    currentPage++;
    renderSongs(true);
  });

  loadSongs().catch(function () {}); // polling retries it if this fails
  Common.startPolling(refreshState, POLL_MS);
})();
