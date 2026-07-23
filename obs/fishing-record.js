/**
 * OBS Browser Source — плашка недельного рекорда рыбалки.
 *
 * URL: http://127.0.0.1:PORT/fishing-record.html
 * Рекомендуемый размер: 1200×450 (прозрачный фон).
 * Debug: ?debug=1
 * Превью: ?preview=1  (или ?preview=shuka)
 *
 * Python -> overlay: {action:"fishing_record", userName, species, weight, imageUrl}
 * overlay -> Python: {status:"ready", overlay:"fishing_record"}
 */
(function () {
  "use strict";

  var WS_PATH = "/ws";
  var HOLD_MS = 6500;
  var ENTER_MS = 650;
  var EXIT_MS = 480;

  var stage = document.getElementById("stage");
  var fishArt = document.getElementById("fishArt");
  var caption = document.getElementById("caption");
  var debugLogEl = document.getElementById("debugLog");

  var ws = null;
  var wsReconnectDelay = 1000;
  var queue = [];
  var busy = false;
  var isDebug = parseFlag("debug");
  var previewSlug = parsePreview();

  if (isDebug) {
    document.body.classList.add("debug-mode");
  }

  function parseFlag(name) {
    try {
      var v = (new URLSearchParams(location.search).get(name) || "").toLowerCase();
      return v === "1" || v === "true" || v === "yes";
    } catch (e) {
      return false;
    }
  }

  function parsePreview() {
    try {
      var v = (new URLSearchParams(location.search).get("preview") || "").trim();
      if (!v) return "";
      if (v === "1" || v.toLowerCase() === "true" || v.toLowerCase() === "yes") {
        return "shuka";
      }
      return v.toLowerCase();
    } catch (e) {
      return "";
    }
  }

  function log(msg) {
    if (!isDebug || !debugLogEl) return;
    var line = document.createElement("div");
    line.textContent = new Date().toLocaleTimeString() + " " + msg;
    debugLogEl.prepend(line);
    while (debugLogEl.children.length > 40) {
      debugLogEl.removeChild(debugLogEl.lastChild);
    }
  }

  function sleep(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function send(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Винительный падеж для подписи «выловил …». */
  var SPECIES_ACCUSATIVE = {
    Карась: "Карася",
    Плотва: "Плотву",
    Окунь: "Окуня",
    Лещ: "Леща",
    Щука: "Щуку",
    Сом: "Сома",
    Осётр: "Осетра",
  };

  function formatWeight(w) {
    var n = Number(w);
    if (!Number.isFinite(n)) return String(w);
    return n.toFixed(2);
  }

  function speciesAccusative(species) {
    return SPECIES_ACCUSATIVE[species] || species;
  }

  function setCaption(userName, weight, species) {
    var fish = speciesAccusative(species);
    caption.innerHTML =
      '<div class="cap-nick">' +
      escapeHtml(userName) +
      "</div>" +
      '<div class="cap-verb-row"><span class="cap-verb">Выловил</span></div>' +
      '<div class="cap-catch">' +
      '<span class="cap-weight">' +
      escapeHtml(formatWeight(weight)) +
      '</span><span class="cap-unit"> кг</span>' +
      '<span class="cap-fish">' +
      escapeHtml(fish) +
      "!</span>" +
      "</div>" +
      '<div class="cap-record">Новый недельный рекорд</div>';
  }

  function waitImage(url) {
    return new Promise(function (resolve) {
      if (!url) {
        resolve(false);
        return;
      }
      var done = false;
      function finish(ok) {
        if (done) return;
        done = true;
        resolve(ok);
      }
      fishArt.onload = function () {
        finish(true);
      };
      fishArt.onerror = function () {
        finish(false);
      };
      fishArt.src = url;
      if (fishArt.complete && fishArt.naturalWidth > 0) {
        finish(true);
      }
    });
  }

  async function showAlert(data) {
    var userName = data.userName || data.user_name || "?";
    var species = data.species || "";
    var weight = data.weight;
    var imageUrl = data.imageUrl || data.image_url || "";

    log(
      "show " +
        userName +
        " / " +
        species +
        " / " +
        formatWeight(weight) +
        " → " +
        imageUrl
    );

    setCaption(userName, weight, species);
    var ok = await waitImage(imageUrl);
    if (!ok) {
      log("image failed: " + imageUrl);
    }

    stage.classList.remove("is-leaving");
    stage.classList.add("is-visible");
    stage.setAttribute("aria-hidden", "false");
    if (typeof window.playObsSfx === "function") {
      window.playObsSfx("/assets/sounds/fish.mp3");
    }

    await sleep(ENTER_MS + HOLD_MS);

    stage.classList.add("is-leaving");
    await sleep(EXIT_MS);

    stage.classList.remove("is-visible", "is-leaving");
    stage.setAttribute("aria-hidden", "true");
    fishArt.removeAttribute("src");
    caption.textContent = "";
  }

  async function pump() {
    if (busy) return;
    busy = true;
    try {
      while (queue.length) {
        var next = queue.shift();
        await showAlert(next);
        if (queue.length) {
          await sleep(280);
        }
      }
    } finally {
      busy = false;
    }
  }

  function enqueue(data) {
    queue.push(data);
    pump();
  }

  function connectWs() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var url = proto + "//" + location.host + WS_PATH;
    log("ws connect " + url);
    ws = new WebSocket(url);
    ws.onopen = function () {
      wsReconnectDelay = 1000;
      send({ status: "ready", overlay: "fishing_record", debug: isDebug });
      log("ws open");
    };
    ws.onclose = function () {
      log("ws close, reconnect…");
      setTimeout(connectWs, wsReconnectDelay);
      wsReconnectDelay = Math.min(wsReconnectDelay * 1.6, 10000);
    };
    ws.onerror = function () {
      log("ws error");
    };
    ws.onmessage = function (ev) {
      var data;
      try {
        data = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (!data || data.action !== "fishing_record") return;
      log("fishing_record " + (data.species || ""));
      enqueue(data);
    };
  }

  connectWs();

  if (previewSlug) {
    enqueue({
      userName: "RiverDragon",
      species: "Щука",
      weight: 3.42,
      imageUrl: "/assets/fishing/" + previewSlug + ".png",
    });
  }
})();
