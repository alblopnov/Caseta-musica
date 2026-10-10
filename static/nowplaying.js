// Now-playing card shared by the user page and the admin page. Browser only.
//
//   var player = NowPlaying.create({ controls: [skipButton] });  // controls are permanent nodes
//   mount.appendChild(player.node);
//   player.update(state.now_playing, function (np) { return [nodes for this song]; });
//
// The server reports `elapsed` once per poll (3 s). Between polls the bar is
// advanced locally every TICK_MS from the last report, so it glides instead of
// jumping. Every poll re-syncs it. Nodes are built with Common.el (no innerHTML).
var NowPlaying = (function () {
  var el = Common.el;
  var TICK_MS = 250;

  function now() {
    return window.performance && performance.now ? performance.now() : Date.now();
  }

  function create(opts) {
    var controls = (opts && opts.controls) || [];

    var stateText = el("span", null, "En espera");
    var title = el("h3", { class: "player-title" }, "Nada suena ahora mismo");
    var actions = el("div", { class: "player-actions" });
    controls.forEach(function (c) { actions.appendChild(c); });
    var dynamic = []; // nodes belonging to the current song (owner tag, remove button)

    var fill = el("div", { class: "player-fill" });
    var knob = el("div", { class: "player-knob", "aria-hidden": "true" });
    var bar = el("div", {
      class: "player-bar",
      role: "progressbar",
      "aria-label": "Progreso de la canción",
      "aria-valuemin": "0",
      "aria-valuemax": "0",
      "aria-valuenow": "0",
    }, fill, knob);
    var elapsedText = el("span", null, "0:00");
    var totalText = el("span", null, "0:00");

    var node = el("section", { class: "player is-idle is-hidden", "aria-label": "Ahora suena" },
      el("div", { class: "player-top" },
        el("div", { class: "player-info" },
          el("div", { class: "player-state" },
            el("span", { class: "eq", "aria-hidden": "true" }, el("span"), el("span"), el("span")),
            stateText),
          title),
        actions),
      bar,
      el("div", { class: "player-times" }, elapsedText, totalText));

    var current = null; // { id, base, at, duration } from the last poll
    var timer = null;

    function paint(elapsed) {
      var duration = current.duration;
      var p = duration > 0 ? Math.min(1, elapsed / duration) : 0;
      bar.style.setProperty("--p", String(p));
      knob.style.transform = "translateX(" + p * bar.offsetWidth + "px)";
      elapsedText.textContent = Format.formatClock(elapsed);
      bar.setAttribute("aria-valuenow", String(Math.floor(elapsed)));
    }

    function tick() {
      if (!current) return;
      var elapsed = current.base + (now() - current.at) / 1000;
      paint(Math.min(current.duration, elapsed));
    }

    function setDynamic(nodes) {
      dynamic.forEach(function (n) { if (n.parentNode === actions) actions.removeChild(n); });
      dynamic = (nodes || []).filter(Boolean);
      var anchor = controls.length ? controls[0] : null;
      dynamic.forEach(function (n) { actions.insertBefore(n, anchor); });
    }

    function stop() {
      if (timer !== null) { clearInterval(timer); timer = null; }
    }

    function update(np, buildActions) {
      node.classList.remove("is-hidden"); // hidden until the first state arrives, so it never claims silence while loading
      if (!np) {
        current = null;
        stop();
        node.classList.add("is-idle");
        stateText.textContent = "En espera";
        title.textContent = "Nada suena ahora mismo";
        setDynamic([]);
        return;
      }
      var duration = Number(np.duration);
      if (!isFinite(duration) || duration < 0) duration = 0;
      node.classList.remove("is-idle");
      stateText.textContent = "Sonando";
      if (!current || current.id !== np.id) {
        title.textContent = np.title;
        totalText.textContent = Format.formatClock(duration);
        bar.setAttribute("aria-valuemax", String(Math.floor(duration)));
        setDynamic(buildActions ? buildActions(np) : []);
      }
      current = { id: np.id, base: UserLogic.clampElapsed(np), at: now(), duration: duration };
      if (timer === null) timer = setInterval(tick, TICK_MS);
      tick();
    }

    return { node: node, update: update };
  }

  return { create: create };
})();
