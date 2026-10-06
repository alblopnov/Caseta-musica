// Library / add panel shared by the user page and the admin page: category
// buttons, search, pagination and the song table with "Añadir". Browser only;
// the rules live in userlogic.js. Every node is built with Common.el.
//
//   var panel = LibraryPanel.create({
//     getState: function () { return lastState; },   // latest /api/state
//     refresh: function () { return promise; },      // reload the state after an add
//     onError: function (err) {},                    // a failed add (already refreshed after)
//   });
var LibraryPanel = (function () {
  var el = Common.el;
  var SONGS_PER_PAGE = 20;

  function replaceChildren(node, children) {
    while (node.firstChild) node.removeChild(node.firstChild);
    children.forEach(function (c) { node.appendChild(c); });
  }

  function create(opts) {
    var allSongs = [];
    var songsLoaded = false;
    var songsLoading = false;
    var selectedCategory = "Todas";
    var currentPage = 1;
    var songsSig = null; // last rendered song rows, to skip identical re-renders

    var searchInput = document.getElementById("search");
    var prevBtn = document.getElementById("prev-page");
    var nextBtn = document.getElementById("next-page");
    var pageInfo = document.getElementById("page-info");
    var categoriesBox = document.getElementById("categories");
    var songBody = document.querySelector("#song-list tbody");

    function renderCategories(names) {
      replaceChildren(
        categoriesBox,
        names.map(function (name) {
          var active = name === selectedCategory;
          return el("button", {
            class: "chip" + (active ? " is-active" : ""),
            type: "button",
            "aria-pressed": active ? "true" : "false",
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
        function () { return opts.refresh(); },
        function (err) {
          opts.onError(err);
          return opts.refresh();
        }
      );
    }

    function songRow(song) {
      var inQueue = UserLogic.isInQueue(song, opts.getState());
      var button = inQueue
        ? el("button", { class: "btn btn-done", type: "button", disabled: true }, "En la cola")
        : el("button", {
            class: "btn btn-primary",
            type: "button",
            onclick: function (ev) {
              ev.currentTarget.disabled = true;
              addSong(song);
            },
          }, el("span", { class: "ico ico-plus", "aria-hidden": "true" }), "Añadir");
      return el("tr", null,
        el("td", null, UserLogic.songTitle(song)),
        el("td", null, button));
    }

    function renderSongs(force) {
      var state = opts.getState();
      var names = UserLogic.categories(allSongs);
      if (names.indexOf(selectedCategory) === -1) selectedCategory = "Todas";
      var filtered = UserLogic.filterSongs(allSongs, selectedCategory, searchInput.value);
      var page = UserLogic.paginate(filtered, currentPage, SONGS_PER_PAGE);
      currentPage = page.page;

      // Polling re-renders every 3 s; skip when nothing visible changed so a
      // tap in progress is never swallowed by a rebuilt button.
      var sig = JSON.stringify([
        names, selectedCategory, page.page, page.totalPages,
        page.items.map(function (s) { return [s, UserLogic.songState(s, state)]; }),
      ]);
      if (!force && sig === songsSig) return;
      songsSig = sig;

      renderCategories(names);
      prevBtn.disabled = page.page <= 1;
      nextBtn.disabled = page.page >= page.totalPages;
      pageInfo.textContent = "Página " + page.page + " de " + page.totalPages;
      if (page.items.length === 0) {
        replaceChildren(songBody, [
          el("tr", null, el("td", { colspan: 2, class: "row-empty" },
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
          throw err; // polling retries while the list is not loaded
        }
      );
    }

    // Shows `category` from page 1 with an empty search (after an upload).
    function showCategory(category) {
      searchInput.value = "";
      selectedCategory = category;
      currentPage = 1;
    }

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

    return {
      render: renderSongs,
      load: loadSongs,
      isLoaded: function () { return songsLoaded; },
      showCategory: showCategory,
      invalidate: function () { songsSig = null; }, // next render rebuilds the rows
    };
  }

  return { create: create };
})();
