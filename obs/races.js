/* OBS Races — компактная нижняя полоска, одна дорожка, текст только в чате. */
(function () {
  "use strict";

  var API_PATH = "/api/races";
  var POLL_FAST_MS = 280;
  var POLL_IDLE_MS = 2000;
  var FINISH_LINE = 375;
  var TRACK_PAD_LEFT = 8;
  var TRACK_PAD_RIGHT = 40;

  var raceWrap = document.getElementById("raceWrap");
  var runnersEl = document.getElementById("runners");
  var debugPanel = document.getElementById("debugPanel");
  var debugStatus = document.getElementById("debugStatus");
  var debugLogEl = document.getElementById("debugLog");

  var isDebug = false;
  var alwaysVisible = false;
  var pollTimer = null;
  var prevState = "IDLE";
  var prevRoundId = 0;
  var lineupCache = [];

  function parseQueryFlag(name) {
    try {
      var v = (new URLSearchParams(location.search).get(name) || "").toLowerCase();
      return v === "1" || v === "true" || v === "yes";
    } catch (e) {
      return false;
    }
  }

  function dbg(msg) {
    if (!isDebug) return;
    var li = document.createElement("li");
    li.textContent = new Date().toLocaleTimeString() + " " + msg;
    debugLogEl.insertBefore(li, debugLogEl.firstChild);
    while (debugLogEl.children.length > 30) {
      debugLogEl.removeChild(debugLogEl.lastChild);
    }
  }

  function setVisible(on) {
    if (alwaysVisible) on = true;
    raceWrap.classList.toggle("is-visible", on);
    raceWrap.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function runnerFallback(name) {
    return (name && name[0]) || "?";
  }

  function buildRunnerIcon(row) {
    var slug = row.icon_slug || "unknown";
    var url = row.icon_url || "/assets/princesses/" + slug + ".svg";
    var img = document.createElement("img");
    img.className = "runner-icon";
    img.src = url;
    img.alt = row.princess_name || "";
    img.onerror = function () {
      var div = document.createElement("div");
      div.className = "runner-icon";
      div.textContent = runnerFallback(row.princess_name);
      img.replaceWith(div);
    };
    return img;
  }

  function trackWidth() {
    var track = document.getElementById("track");
    return Math.max(120, track.clientWidth - TRACK_PAD_LEFT - TRACK_PAD_RIGHT);
  }

  function positionToLeft(pos) {
    var w = trackWidth();
    return Math.min(w, Math.max(0, (pos / FINISH_LINE) * w));
  }

  function renderLineup(lineup) {
    lineupCache = lineup || [];
    runnersEl.innerHTML = "";
    lineupCache.forEach(function (row) {
      var runner = document.createElement("div");
      runner.className = "runner";
      runner.dataset.horse = String(row.horse_number);
      runner.appendChild(buildRunnerIcon(row));
      runner.style.left = "0px";
      runnersEl.appendChild(runner);
    });
  }

  function updatePositions(progress) {
    if (!progress || !progress.positions) return;

    var entries = [];
    Object.keys(progress.positions).forEach(function (horse) {
      entries.push({
        horse: horse,
        pos: Number(progress.positions[horse]) || 0,
      });
    });
    entries.sort(function (a, b) {
      if (b.pos !== a.pos) return b.pos - a.pos;
      return Number(a.horse) - Number(b.horse);
    });

    entries.forEach(function (entry, idx) {
      var runner = runnersEl.querySelector('.runner[data-horse="' + entry.horse + '"]');
      if (!runner) return;
      var left = positionToLeft(entry.pos);
      runner.style.left = left + "px";
      runner.style.zIndex = String(10 + (entries.length - idx));
      var stagger = ((Number(entry.horse) % 3) - 1) * 4;
      runner.style.transform = "translateY(" + stagger + "px)";
    });
  }

  function resetToStart() {
    runnersEl.querySelectorAll(".runner").forEach(function (runner) {
      runner.style.left = "0px";
      runner.style.zIndex = "1";
      runner.style.transform = "translateY(0)";
    });
  }

  function handleStatus(data) {
    var state = data.state || "IDLE";
    var roundId = data.round_id || 0;

    if (data.finish_line) {
      FINISH_LINE = Number(data.finish_line) || FINISH_LINE;
    }

    if (isDebug) {
      debugStatus.textContent =
        "state=" + state + " round=" + roundId + " timer=" + (data.timer_sec || 0);
    }

    if (roundId !== prevRoundId && data.lineup && data.lineup.length) {
      renderLineup(data.lineup);
      prevRoundId = roundId;
    } else if (data.lineup && data.lineup.length && !lineupCache.length) {
      renderLineup(data.lineup);
    }

    if (state === "RACE_WAIT" || state === "RACE") {
      setVisible(true);
      if (state === "RACE_WAIT" && prevState !== "RACE_WAIT") {
        resetToStart();
        dbg("race wait");
      }
    } else if (!alwaysVisible) {
      setVisible(false);
    }

    if (state === "RACE" && data.race_progress) {
      updatePositions(data.race_progress);
    }

    prevState = state;
  }

  function pollInterval(state) {
    if (state === "RACE_WAIT" || state === "RACE") {
      return POLL_FAST_MS;
    }
    return POLL_IDLE_MS;
  }

  function schedulePoll(delay) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(tick, delay);
  }

  function tick() {
    fetch(API_PATH)
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        handleStatus(data);
        schedulePoll(pollInterval(data.state));
      })
      .catch(function (err) {
        dbg("poll error: " + err.message);
        schedulePoll(POLL_IDLE_MS);
      });
  }

  function init() {
    isDebug = parseQueryFlag("debug");
    alwaysVisible = parseQueryFlag("visible");
    if (isDebug) {
      document.body.classList.add("debug-mode");
      debugPanel.style.display = "block";
    }
    if (alwaysVisible) setVisible(true);
    window.addEventListener("resize", function () {
      var prog = { positions: {} };
      runnersEl.querySelectorAll(".runner").forEach(function (runner) {
        var horse = runner.dataset.horse;
        var left = parseFloat(runner.style.left) || 0;
        prog.positions[horse] = (left / trackWidth()) * FINISH_LINE;
      });
      updatePositions(prog);
    });
    tick();
  }

  init();
})();
