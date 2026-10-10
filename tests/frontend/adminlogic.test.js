const test = require("node:test");
const assert = require("node:assert/strict");
const AdminLogic = require("../../static/adminlogic.js");

const q = (id) => ({ id, song: id + ".mp3", title: id });
const queue = [q("a"), q("b"), q("c"), q("d")];

test("movePosition: dropping on the row at index i gives position i + 1", () => {
  assert.equal(AdminLogic.movePosition(queue, "d", "a"), 1);
  assert.equal(AdminLogic.movePosition(queue, "a", "c"), 3);
  assert.equal(AdminLogic.movePosition(queue, "a", "d"), 4);
  assert.equal(AdminLogic.movePosition(queue, "c", "b"), 2);
});

test("movePosition: dropping a row on itself is not a move", () => {
  assert.equal(AdminLogic.movePosition(queue, "b", "b"), null);
});

test("movePosition: unknown ids or a bad queue are not a move", () => {
  assert.equal(AdminLogic.movePosition(queue, "zzz", "a"), null);
  assert.equal(AdminLogic.movePosition(queue, "a", "zzz"), null);
  assert.equal(AdminLogic.movePosition(queue, null, "a"), null);
  assert.equal(AdminLogic.movePosition(queue, "a", undefined), null);
  assert.equal(AdminLogic.movePosition(null, "a", "b"), null);
  assert.equal(AdminLogic.movePosition(undefined, "a", "b"), null);
});

test("movePosition: the playing song is never part of the queue positions", () => {
  // The playing id is not in state.queue, so it can neither be moved nor be a target.
  assert.equal(AdminLogic.movePosition(queue, "playing", "a"), null);
  assert.equal(AdminLogic.movePosition(queue, "a", "playing"), null);
});

test("isDraggable: only queued rows, never the playing one", () => {
  const state = { now_playing: q("p"), queue };
  assert.equal(AdminLogic.isDraggable(q("b"), state), true);
  assert.equal(AdminLogic.isDraggable(state.now_playing, state), false);
  assert.equal(AdminLogic.isDraggable(q("gone"), state), false);
  assert.equal(AdminLogic.isDraggable(null, state), false);
  assert.equal(AdminLogic.isDraggable(q("b"), null), false);
  assert.equal(AdminLogic.isDraggable(q("b"), {}), false);
});

test("pinErrorMessage: wrong PIN, lockout and missing admin PIN", () => {
  assert.equal(AdminLogic.pinErrorMessage({ status: 401 }), "PIN incorrecto");
  assert.equal(AdminLogic.pinErrorMessage({ status: 429 }), "Demasiados intentos. Espera un minuto.");
  assert.equal(
    AdminLogic.pinErrorMessage({ status: 503 }),
    "El administrador no está configurado en el servidor"
  );
});

test("pinErrorMessage: network and unknown failures", () => {
  assert.equal(
    AdminLogic.pinErrorMessage({ status: 0, message: "No se pudo conectar con el servidor" }),
    "No se pudo conectar con el servidor"
  );
  assert.equal(AdminLogic.pinErrorMessage({ status: 500, message: "Error 500" }), "Error 500");
  assert.equal(AdminLogic.pinErrorMessage(null), "No se pudo iniciar sesión.");
  assert.equal(AdminLogic.pinErrorMessage({ status: 418 }), "No se pudo iniciar sesión.");
});

test("isSessionError: 401 and 403 mean the admin cookie may be gone", () => {
  assert.equal(AdminLogic.isSessionError({ status: 401 }), true);
  assert.equal(AdminLogic.isSessionError({ status: 403 }), true);
  assert.equal(AdminLogic.isSessionError({ status: 404 }), false);
  assert.equal(AdminLogic.isSessionError({ status: 0 }), false);
  assert.equal(AdminLogic.isSessionError(null), false);
});
