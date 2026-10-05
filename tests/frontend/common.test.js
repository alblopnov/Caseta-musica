const test = require("node:test");
const assert = require("node:assert/strict");

// Minimal fake DOM, enough for Common.el / toast.
class FakeNode {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
  }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.children.push(c)); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  remove() { this.removed = true; }
}
global.document = {
  hidden: false,
  body: new FakeNode("body"),
  createElement: (t) => new FakeNode(t),
  createTextNode: (t) => ({ nodeType: 3, textContent: String(t) }),
};

const Common = require("../../static/common.js");

test("el builds nodes with text children, never innerHTML", () => {
  let clicked = 0;
  const n = Common.el("div", { class: "a b", onclick: () => clicked++, dataset: { id: "7" }, title: "t" },
    "<b>x</b>", null, false, Common.el("span"));
  assert.equal(n.className, "a b");
  assert.equal(n.dataset.id, "7");
  assert.equal(n.attrs.title, "t");
  assert.equal(n.children.length, 2);
  assert.equal(n.children[0].textContent, "<b>x</b>");
  assert.equal(n.children[1].tagName, "span");
  n.onclick();
  assert.equal(clicked, 1);
  assert.equal("innerHTML" in n, false);
});

function resp(status, body) {
  return { ok: status >= 200 && status < 300, status, text: async () => (typeof body === "string" ? body : JSON.stringify(body)) };
}

test("api sends JSON body and parses JSON", async () => {
  let seen;
  global.fetch = async (url, opts) => { seen = { url, opts }; return resp(200, { ok: 1 }); };
  const out = await Common.api("POST", "/api/x", { a: 1 });
  assert.deepEqual(out, { ok: 1 });
  assert.equal(seen.opts.method, "POST");
  assert.equal(seen.opts.credentials, "same-origin");
  assert.equal(seen.opts.headers["Content-Type"], "application/json");
  assert.equal(seen.opts.body, '{"a":1}');
});

test("api passes FormData untouched", async () => {
  let seen;
  global.fetch = async (url, opts) => { seen = opts; return resp(200, {}); };
  const fd = new FormData();
  fd.append("f", "v");
  await Common.api("POST", "/api/up", fd);
  assert.equal(seen.body, fd);
  assert.equal(seen.headers && seen.headers["Content-Type"], undefined);
});

test("api rejects with ApiError on non-2xx", async () => {
  global.fetch = async () => resp(409, { code: "duplicate", error: "Ya está en la cola" });
  await assert.rejects(Common.api("POST", "/api/queue", { song: "a" }), (e) => {
    assert.ok(e instanceof Common.ApiError);
    assert.equal(e.status, 409);
    assert.equal(e.code, "duplicate");
    assert.equal(e.message, "Ya está en la cola");
    return true;
  });
});

test("api rejects with network ApiError when fetch fails", async () => {
  global.fetch = async () => { throw new TypeError("failed"); };
  await assert.rejects(Common.api("GET", "/api/x"), (e) => {
    assert.ok(e instanceof Common.ApiError);
    assert.equal(e.status, 0);
    assert.equal(e.code, "network");
    return true;
  });
});

test("api tolerates non-JSON error bodies", async () => {
  global.fetch = async () => resp(500, "<html>boom</html>");
  await assert.rejects(Common.api("GET", "/api/x"), (e) => e.status === 500 && typeof e.message === "string");
});

test("startPolling runs now, never overlaps, survives errors, stops", async () => {
  const realSetInterval = global.setInterval;
  const realClear = global.clearInterval;
  let tick;
  let cleared = false;
  global.setInterval = (f) => { tick = f; return 1; };
  global.clearInterval = () => { cleared = true; };
  try {
    let calls = 0;
    let release;
    const fn = () => { calls++; return new Promise((r) => { release = r; }); };
    const stop = Common.startPolling(fn, 1000);
    assert.equal(calls, 1);
    tick(); // previous still pending
    assert.equal(calls, 1);
    release();
    await new Promise((r) => setImmediate(r));
    document.hidden = true;
    tick();
    assert.equal(calls, 1);
    document.hidden = false;
    tick();
    assert.equal(calls, 2);
    release();
    await new Promise((r) => setImmediate(r));

    let n = 0;
    Common.startPolling(() => { n++; return Promise.reject(new Error("x")); }, 1000);
    await new Promise((r) => setImmediate(r));
    tick();
    assert.equal(n, 2);
    stop();
    assert.equal(cleared, true);
  } finally {
    global.setInterval = realSetInterval;
    global.clearInterval = realClear;
  }
});

test("toast adds a Bulma notification and auto-dismisses", () => {
  const realSetTimeout = global.setTimeout;
  let delay, cb;
  global.setTimeout = (f, d) => { cb = f; delay = d; return 1; };
  try {
    Common.toast("Hola <b>", "danger");
    assert.equal(delay, 4000);
    const holder = document.body.children[document.body.children.length - 1];
    const box = holder.children[holder.children.length - 1];
    assert.match(box.className, /notification is-danger/);
    assert.equal(box.textContent, "Hola <b>");
    cb();
    assert.equal(box.removed, true);
  } finally {
    global.setTimeout = realSetTimeout;
  }
});
