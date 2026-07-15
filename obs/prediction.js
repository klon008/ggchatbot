/* OBS Predictions overlay — GET /api/poll */
(function () {
  "use strict";

  var API_PATH = "/api/poll";
  var POLL_FAST_MS = 800;
  var POLL_IDLE_MS = 2500;

  var pollWrap = document.getElementById("pollWrap");
  var pollTitle = document.getElementById("pollTitle");
  var pollMeta = document.getElementById("pollMeta");
  var pollOptions = document.getElementById("pollOptions");
  var pollBanner = document.getElementById("pollBanner");
  var debugStatus = document.getElementById("debugStatus");

  var isDebug = false;
  var alwaysVisible = false;
  var pollTimer = null;
  var lastState = "IDLE";

  var COLORS = [
    "#5b9fd4",
    "#c47ad0",
    "#e0a85c",
    "#6bc4a0",
    "#e07a7a",
    "#8a9be8",
    "#d4c35b",
    "#9ecbff",
  ];

  function parseQueryFlag(name) {
    try {
      var v = (new URLSearchParams(location.search).get(name) || "").toLowerCase();
      return v === "1" || v === "true" || v === "yes";
    } catch (e) {
      return false;
    }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setVisible(on) {
    if (alwaysVisible) on = true;
    if (on) pollWrap.classList.add("is-visible");
    else pollWrap.classList.remove("is-visible");
  }

  function formatTimer(sec) {
    sec = Math.max(0, sec | 0);
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function render(data) {
    var state = data.state || "IDLE";
    lastState = state;
    if (debugStatus) {
      debugStatus.textContent =
        "state=" + state + " pool=" + (data.total_pool || 0) + " t=" + (data.timer_sec || 0);
    }

    if (state === "IDLE" && !alwaysVisible) {
      setVisible(false);
      return;
    }

    var title = data.title || (data.last_result && data.last_result.title) || "Опрос";
    pollTitle.textContent = title;

    var options = data.options || [];
    var total = data.total_pool || 0;
    if (!options.length && data.last_result) {
      options = data.last_result.options_stats || [];
      total = data.last_result.total_pool || 0;
    }

    var winning = data.winning_option;
    if (winning == null && data.last_result) {
      winning = data.last_result.winning_option;
    }

    var metaParts = ["Банк: " + total];
    if (state === "OPEN") {
      metaParts.push("Приём: " + formatTimer(data.timer_sec || 0));
    } else if (state === "LOCKED") {
      metaParts.push("Приём закрыт");
    } else if (state === "RESOLVED") {
      metaParts.push("Результат");
    }
    pollMeta.textContent = metaParts.join(" · ");

    var html = "";
    for (var i = 0; i < options.length; i++) {
      var o = options[i];
      var pct = total > 0 ? Math.round((100 * (o.total || 0)) / total) : 0;
      var isWin = winning != null && Number(o.index) === Number(winning);
      var color = COLORS[i % COLORS.length];
      html +=
        '<div class="opt' +
        (isWin ? " is-winner" : "") +
        '">' +
        '<div class="opt-head">' +
        '<span class="label">' +
        esc(o.index + 1) +
        ". " +
        esc(o.label) +
        "</span>" +
        '<span class="stats">' +
        esc(o.total || 0) +
        " · ×" +
        esc(o.coefficient != null ? o.coefficient : "—") +
        " · " +
        pct +
        "%</span>" +
        "</div>" +
        '<div class="bar"><span style="width:' +
        pct +
        "%;background:linear-gradient(90deg," +
        color +
        "," +
        color +
        ')"></span></div>' +
        "</div>";
    }
    pollOptions.innerHTML = html || '<div class="opt">Нет данных</div>';

    if (state === "RESOLVED" && data.last_result) {
      pollBanner.classList.add("is-on");
      pollBanner.textContent =
        "Победил: «" + (data.last_result.winning_label || "?") + "»";
    } else {
      pollBanner.classList.remove("is-on");
      pollBanner.textContent = "";
    }

    setVisible(true);
  }

  async function tick() {
    try {
      var res = await fetch(API_PATH);
      if (!res.ok) throw new Error("HTTP " + res.status);
      var data = await res.json();
      render(data);
      schedule(data.state === "IDLE" ? POLL_IDLE_MS : POLL_FAST_MS);
    } catch (e) {
      if (debugStatus) debugStatus.textContent = "err: " + e.message;
      schedule(POLL_IDLE_MS);
    }
  }

  function schedule(ms) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(tick, ms);
  }

  isDebug = parseQueryFlag("debug");
  alwaysVisible = parseQueryFlag("visible");
  if (isDebug) document.body.classList.add("debug-mode");
  tick();
})();
