// Shared frontend helpers: fetch wrapper, safe DOM builder, polling, toasts.
// Classic script: defines the global `Common`. It never uses innerHTML.
var Common = (function () {
  function ApiError(status, code, message) {
    var err = new Error(message);
    err.name = "ApiError";
    err.status = status;
    err.code = code;
    Object.setPrototypeOf(err, ApiError.prototype);
    return err;
  }
  ApiError.prototype = Object.create(Error.prototype, {
    constructor: { value: ApiError, writable: true, configurable: true },
  });

  function isFormData(body) {
    return typeof FormData !== "undefined" && body instanceof FormData;
  }

  function parseBody(text) {
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch (e) {
      return text;
    }
  }

  // api("POST", "/api/queue", {song: "x"}) -> parsed JSON, or rejects with ApiError.
  function api(method, url, body) {
    var opts = { method: method, credentials: "same-origin", headers: {} };
    if (body !== undefined && body !== null) {
      if (isFormData(body)) {
        opts.body = body; // the browser sets the multipart boundary itself
      } else {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
      }
    }
    return fetch(url, opts).then(
      function (res) {
        return res.text().then(function (text) {
          var data = parseBody(text);
          if (res.ok) return data;
          var obj = data && typeof data === "object" ? data : {};
          throw new ApiError(
            res.status,
            typeof obj.code === "string" ? obj.code : "http_" + res.status,
            typeof obj.error === "string" ? obj.error : "Error " + res.status
          );
        });
      },
      function () {
        throw new ApiError(0, "network", "No se pudo conectar con el servidor");
      }
    );
  }

  function appendChild(node, child) {
    if (child === null || child === undefined || child === false || child === true) return;
    if (Array.isArray(child)) {
      child.forEach(function (c) { appendChild(node, c); });
    } else if (typeof child === "string" || typeof child === "number") {
      node.appendChild(document.createTextNode(String(child)));
    } else {
      node.appendChild(child);
    }
  }

  // el("div", {class: "box", onclick: fn, dataset: {id: 1}}, "texto", childNode)
  function el(tag, props) {
    var node = document.createElement(tag);
    var p = props || {};
    Object.keys(p).forEach(function (key) {
      var value = p[key];
      if (value === null || value === undefined || value === false) return;
      if (key === "class") {
        node.className = String(value);
      } else if (key === "dataset") {
        Object.keys(value).forEach(function (k) { node.dataset[k] = String(value[k]); });
      } else if (key.indexOf("on") === 0 && typeof value === "function") {
        node[key.toLowerCase()] = value;
      } else {
        node.setAttribute(key, value === true ? "" : String(value));
      }
    });
    for (var i = 2; i < arguments.length; i++) appendChild(node, arguments[i]);
    return node;
  }

  // Runs fn now and every `ms`; skips ticks while the previous run is pending
  // or the tab is hidden; errors never stop the loop. Returns a stop function.
  function startPolling(fn, ms) {
    var running = false;
    function tick() {
      if (running) return;
      if (typeof document !== "undefined" && document.hidden) return;
      running = true;
      var result;
      try {
        result = Promise.resolve(fn());
      } catch (e) {
        result = Promise.reject(e);
      }
      result.then(
        function () { running = false; },
        function () { running = false; }
      );
    }
    tick();
    var handle = setInterval(tick, ms);
    return function stop() { clearInterval(handle); };
  }

  var toastHolder = null;

  function toast(message, kind) {
    if (!toastHolder) {
      toastHolder = el("div", { class: "toast-holder" });
      document.body.appendChild(toastHolder);
    }
    var box = el("div", { class: "notification is-" + (kind || "info") });
    box.textContent = String(message);
    toastHolder.appendChild(box);
    setTimeout(function () { box.remove(); }, 4000);
  }

  return { api: api, el: el, startPolling: startPolling, toast: toast, ApiError: ApiError };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Common;
}
