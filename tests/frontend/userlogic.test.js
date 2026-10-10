const test = require("node:test");
const assert = require("node:assert/strict");
const UserLogic = require("../../static/userlogic.js");

function state(over) {
  return Object.assign(
    { now_playing: null, queue: [], total_seconds: 0, me: { pending: 0, max: 5 } },
    over || {}
  );
}
const q = (id, song, mine, eta) => ({ id, song, title: song, mine, eta_seconds: eta });

test("computeBanner: pending song shows ETA of first own entry", () => {
  const s = state({
    now_playing: { id: "p", song: "x.mp3", mine: false, elapsed: 0, duration: 100 },
    queue: [q("1", "a.mp3", false, 30), q("2", "b.mp3", true, 200), q("3", "c.mp3", true, 500)],
    me: { pending: 2, max: 5 },
  });
  assert.equal(UserLogic.computeBanner(s), "Tu próxima canción suena en ~3 min");
});

test("computeBanner: short ETA reads naturally", () => {
  const s = state({ queue: [q("1", "a.mp3", true, 10)], me: { pending: 1, max: 5 } });
  assert.equal(UserLogic.computeBanner(s), "Tu próxima canción suena en menos de 1 min");
});

test("computeBanner: pending takes precedence over own playing song", () => {
  const s = state({
    now_playing: { id: "p", song: "x.mp3", mine: true, elapsed: 0, duration: 100 },
    queue: [q("1", "a.mp3", true, 100)],
  });
  assert.equal(UserLogic.computeBanner(s), "Tu próxima canción suena en ~2 min");
});

test("computeBanner: only own song playing", () => {
  const s = state({
    now_playing: { id: "p", song: "x.mp3", mine: true, elapsed: 5, duration: 100 },
    queue: [q("1", "a.mp3", false, 95)],
  });
  assert.equal(UserLogic.computeBanner(s), "Tu canción está sonando");
});

test("computeBanner: hidden otherwise (including missing now_playing)", () => {
  assert.equal(UserLogic.computeBanner(state()), null);
  assert.equal(UserLogic.computeBanner(state({ queue: [q("1", "a", false, 1)] })), null);
  const s = state({ now_playing: { id: "p", song: "x", mine: false, elapsed: 0, duration: 1 } });
  assert.equal(UserLogic.computeBanner(s), null);
  const noKey = { queue: [], me: { pending: 0, max: 5 } };
  assert.equal(UserLogic.computeBanner(noKey), null);
  assert.equal(UserLogic.computeBanner(null), null);
});

test("songState", () => {
  const s = state({
    now_playing: { id: "p", song: "Rock/now.mp3", mine: false, elapsed: 0, duration: 1 },
    queue: [q("1", "Rock/q.mp3", false, 1)],
  });
  assert.equal(UserLogic.songState("Rock/now.mp3", s), "playing");
  assert.equal(UserLogic.songState("Rock/q.mp3", s), "queued");
  assert.equal(UserLogic.songState("Rock/other.mp3", s), "available");
  assert.equal(UserLogic.songState("x", null), "available");
  assert.equal(UserLogic.songState("x", { queue: [] }), "available");
});

test("isInQueue: playing and queued songs both disable the button", () => {
  const s = state({
    now_playing: { id: "p", song: "n.mp3", mine: false, elapsed: 0, duration: 1 },
    queue: [q("1", "q.mp3", false, 1)],
  });
  assert.equal(UserLogic.isInQueue("n.mp3", s), true);
  assert.equal(UserLogic.isInQueue("q.mp3", s), true);
  assert.equal(UserLogic.isInQueue("z.mp3", s), false);
});

test("conflictMessage", () => {
  const s = state({ me: { pending: 5, max: 5 } });
  assert.equal(
    UserLogic.conflictMessage({ code: "full" }, s),
    "Ya tienes 5 canciones en la cola. Espera a que suene alguna."
  );
  assert.equal(
    UserLogic.conflictMessage({ code: "full" }, state({ me: { pending: 3, max: 3 } })),
    "Ya tienes 3 canciones en la cola. Espera a que suene alguna."
  );
  assert.equal(UserLogic.conflictMessage({ code: "duplicate" }, s), "Esa canción ya está en la cola.");
  // unknown code falls back to the server message, then to a generic one
  assert.equal(UserLogic.conflictMessage({ code: "x", message: "Hola" }, s), "Hola");
  assert.equal(UserLogic.conflictMessage({ code: "x" }, s), "No se pudo completar la acción.");
  // state not loaded yet: do not print "undefined"
  assert.equal(
    UserLogic.conflictMessage({ code: "full" }, null),
    "Ya tienes 5 canciones en la cola. Espera a que suene alguna."
  );
});

test("counterText", () => {
  assert.equal(UserLogic.counterText(state({ me: { pending: 2, max: 5 } })), "Tienes 2 de 5 canciones en la cola");
  assert.equal(UserLogic.counterText(state({ me: { pending: 0, max: 5 } })), "Tienes 0 de 5 canciones en la cola");
  assert.equal(UserLogic.counterText(null), "");
});

test("summaryLine counts the playing song and uses total_seconds", () => {
  const s = state({
    now_playing: { id: "p", song: "n", mine: false, elapsed: 0, duration: 100 },
    queue: [q("1", "a", false, 100), q("2", "b", false, 200)],
    total_seconds: 3900,
  });
  assert.equal(UserLogic.summaryLine(s), "3 canciones en la cola | Quedan ~1 h 05 min");
  assert.equal(UserLogic.summaryLine(state()), "0 canciones en la cola");
  assert.equal(
    UserLogic.summaryLine(state({ queue: [q("1", "a", false, 0)], total_seconds: 200 })),
    "1 canción en la cola | Quedan ~3 min"
  );
});

test("clampElapsed and progressFraction", () => {
  assert.equal(UserLogic.clampElapsed({ elapsed: 50, duration: 100 }), 50);
  assert.equal(UserLogic.clampElapsed({ elapsed: 130, duration: 100 }), 100);
  assert.equal(UserLogic.clampElapsed({ elapsed: -5, duration: 100 }), 0);
  assert.equal(UserLogic.clampElapsed(null), 0);
  assert.equal(UserLogic.progressFraction({ elapsed: 25, duration: 100 }), 0.25);
  assert.equal(UserLogic.progressFraction({ elapsed: 500, duration: 100 }), 1);
  assert.equal(UserLogic.progressFraction({ elapsed: 5, duration: 0 }), 0);
  assert.equal(UserLogic.progressFraction(null), 0);
});

test("categories: top-level folders, root songs only in Todas", () => {
  const songs = ["root.mp3", "Rock/a.mp3", "Rock/sub/b.mp3", "Pop/c.mp3", "Subidas/d.mp3"];
  assert.deepEqual(UserLogic.categories(songs), ["Todas", "Pop", "Rock", "Subidas"]);
  assert.deepEqual(UserLogic.categories(["root.mp3"]), ["Todas"]);
  assert.deepEqual(UserLogic.categories([]), ["Todas"]);
});

test("filterSongs by category and title search", () => {
  const songs = ["root.mp3", "Rock/Queen - Bohemian.mp3", "Rock/sub/b.mp3", "Pop/Queen2.mp3", "Rock2/x.mp3"];
  assert.deepEqual(UserLogic.filterSongs(songs, "Todas", ""), songs);
  assert.deepEqual(UserLogic.filterSongs(songs, "Rock", ""), ["Rock/Queen - Bohemian.mp3", "Rock/sub/b.mp3"]);
  assert.deepEqual(UserLogic.filterSongs(songs, "Todas", "queen"), ["Rock/Queen - Bohemian.mp3", "Pop/Queen2.mp3"]);
  assert.deepEqual(UserLogic.filterSongs(songs, "Pop", "  QUEEN "), ["Pop/Queen2.mp3"]);
  // search matches the title, not the folder name
  assert.deepEqual(UserLogic.filterSongs(songs, "Todas", "pop"), []);
  assert.deepEqual(UserLogic.filterSongs(songs, "Todas", "mp3"), []);
});

test("songTitle strips folders and extension", () => {
  assert.equal(UserLogic.songTitle("Rock/Queen - Bohemian.mp3"), "Queen - Bohemian");
  assert.equal(UserLogic.songTitle("a.b.wav"), "a.b");
  assert.equal(UserLogic.songTitle("plain"), "plain");
});

test("paginate", () => {
  const items = Array.from({ length: 45 }, (_, i) => i);
  let p = UserLogic.paginate(items, 1, 20);
  assert.equal(p.items.length, 20);
  assert.equal(p.totalPages, 3);
  assert.equal(p.page, 1);
  p = UserLogic.paginate(items, 3, 20);
  assert.deepEqual(p.items, [40, 41, 42, 43, 44]);
  // out-of-range pages clamp
  assert.equal(UserLogic.paginate(items, 9, 20).page, 3);
  assert.equal(UserLogic.paginate(items, 0, 20).page, 1);
  p = UserLogic.paginate([], 1, 20);
  assert.equal(p.totalPages, 1);
  assert.deepEqual(p.items, []);
});

test("audioNotice: shown only when the server says audio is down", () => {
  assert.equal(UserLogic.audioNotice(state({ audio_ok: false })), "Sin salida de audio: las canciones esperan");
  assert.equal(UserLogic.audioNotice(state({ audio_ok: true })), null);
  assert.equal(UserLogic.audioNotice(state()), null); // older server without the key
  assert.equal(UserLogic.audioNotice(null), null);
  assert.equal(UserLogic.audioNotice(state({ audio_ok: "false" })), null);
});

test("counterText has no cap for the admin (max is null)", () => {
  assert.equal(
    UserLogic.counterText({ me: { pending: 7, max: null } }),
    "Tienes 7 canciones en la cola (sin límite)"
  );
  assert.equal(
    UserLogic.counterText({ me: { pending: 1, max: null } }),
    "Tienes 1 canción en la cola (sin límite)"
  );
});

// -- shuffle mode ----------------------------------------------------------

const mode = (category, canStop) => ({ category, can_stop: canStop });

test("shuffleControl: off, the button starts shuffle for the selected section", () => {
  const all = UserLogic.shuffleControl("Todas", null);
  assert.deepEqual(
    { label: all.label, pressed: all.pressed, action: all.action },
    { label: "Aleatorio", pressed: false, action: "start" }
  );
  assert.equal(all.hint, "Reproduce canciones al azar de toda la biblioteca hasta que lo detengas");
  const rock = UserLogic.shuffleControl("Flamenquito", null);
  assert.equal(rock.action, "start");
  assert.equal(rock.hint, "Reproduce canciones al azar de Flamenquito hasta que lo detengas");
  assert.equal(UserLogic.shuffleControl(undefined, null).action, "start");
});

test("shuffleControl: on for this section, the button is a pressed toggle that stops it", () => {
  const c = UserLogic.shuffleControl("Flamenquito", mode("Flamenquito", true));
  assert.deepEqual(
    { label: c.label, pressed: c.pressed, action: c.action },
    { label: "Aleatorio activo", pressed: true, action: "stop" }
  );
  assert.equal(c.hint, "Pulsa otra vez para detenerlo");
});

test("shuffleControl: on for another section, the starter can switch it", () => {
  const c = UserLogic.shuffleControl("Reggaeton", mode("Flamenquito", true));
  assert.deepEqual(
    { label: c.label, pressed: c.pressed, action: c.action },
    { label: "Cambiar a Reggaeton", pressed: false, action: "change" }
  );
  assert.equal(c.hint, "Ahora suenan canciones al azar de Flamenquito");
  assert.equal(UserLogic.shuffleControl("Todas", mode("Flamenquito", true)).label, "Cambiar a Todas");
});

test("shuffleControl: someone else's shuffle cannot be touched from this phone", () => {
  const same = UserLogic.shuffleControl("Todas", mode("Todas", false));
  assert.equal(same.action, "none");
  assert.equal(same.pressed, true);
  assert.equal(same.hint, "Lo activó otro teléfono. Solo esa persona o el administrador puede detenerlo.");
  const other = UserLogic.shuffleControl("Reggaeton", mode("Flamenquito", false));
  assert.equal(other.action, "none");
  assert.equal(other.pressed, false);
});

test("shuffleStatus describes the running mode for the bar above the player", () => {
  assert.equal(UserLogic.shuffleStatus(null), null);
  assert.equal(UserLogic.shuffleStatus(undefined), null);
  assert.deepEqual(UserLogic.shuffleStatus(mode("Flamenquito", true)), {
    text: "Aleatorio activo: Flamenquito",
    canStop: true,
  });
  assert.deepEqual(UserLogic.shuffleStatus(mode("Todas", false)), {
    text: "Aleatorio activo: toda la biblioteca",
    canStop: false,
  });
});

test("shuffle toasts", () => {
  assert.equal(UserLogic.shuffleStartedMessage("Todas"), "Aleatorio activado: toda la biblioteca");
  assert.equal(UserLogic.shuffleStartedMessage("Reggaeton"), "Aleatorio activado: Reggaeton");
  assert.equal(UserLogic.shuffleStoppedMessage(), "Aleatorio detenido");
});

test("conflictMessage when another phone owns the shuffle", () => {
  assert.equal(
    UserLogic.conflictMessage({ code: "shuffle_locked" }, null),
    "Otro teléfono tiene activado el aleatorio. Solo esa persona o el administrador puede cambiarlo."
  );
});

test("emptyQueueText says what happens next", () => {
  assert.deepEqual(UserLogic.emptyQueueText(state()), {
    title: "La cola está vacía",
    hint: "Elige una canción de la lista para añadirla.",
  });
  assert.equal(
    UserLogic.emptyQueueText(state({ now_playing: { id: "p", song: "x", mine: false, elapsed: 0, duration: 9 } })).title,
    "No hay más canciones en la cola"
  );
  assert.deepEqual(UserLogic.emptyQueueText(state({ shuffle: mode("Reggaeton", false) })), {
    title: "Después sonará una canción al azar",
    hint: "Aleatorio activo: Reggaeton. Lo que añadas sonará antes.",
  });
});
