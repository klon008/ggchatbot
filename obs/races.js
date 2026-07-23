/* OBS Races — lineup по API, гонка по WS-сценарию + RAF (бэк фиксирует победителя). */
(function () {
  "use strict";

  // --- Сеть / опрос API ---
  var API_PATH = "/api/races"; // HTTP snapshot состояния забега
  var WS_PATH = "/ws"; // WebSocket: race_start / race_done
  var POLL_IDLE_MS = 2000; // Интервал poll, когда забега нет
  var POLL_ACTIVE_MS = 900; // Интервал poll во время OPEN / RACE
  var RECONNECT_MS = 1500; // Пауза перед переподключением WS

  // --- Геометрия трека ---
  var TRACK_PAD_LEFT = 8; // Отступ дорожки слева (px), как в CSS
  var TRACK_PAD_RIGHT = 40; // Отступ справа под финишную линию
  var ICON_SIZE = 40; // Базовый размер иконки принцессы (px)
  var finishLine = 375; // Дистанция финиша в единицах симуляции (перезаписывается скриптом)

  // --- Отсчёт перед стартом ---
  var COUNTDOWN_BEAT_MS = 900; // Длительность цифры 10…1
  var COUNTDOWN_GO_MS = 750; // Длительность «Старт!»
  var COUNTDOWN_STEPS = ["10", "9", "8", "7", "6", "5", "4", "3", "2", "1", "Старт!"];
  var SIM_COUNTDOWN_STEPS = ["3", "2", "1", "Старт!"]; // Короткий отсчёт для ?sim=1

  // --- Локальная симуляция (?sim=1) ---
  var SIM_LINEUP = [
    { horse_number: 1, princess_name: "Эльза", icon_slug: "elza" },
    { horse_number: 2, princess_name: "Моана", icon_slug: "moana" },
    { horse_number: 3, princess_name: "Мулан", icon_slug: "mulan" },
    { horse_number: 4, princess_name: "Рапунцель", icon_slug: "rapuntsel" },
    { horse_number: 5, princess_name: "Жасмин", icon_slug: "zhasmin" },
    { horse_number: 6, princess_name: "Мерида", icon_slug: "merida" },
  ];

  var raceWrap = document.getElementById("raceWrap");
  var runnersEl = document.getElementById("runners");
  var countdownEl = document.getElementById("countdown");
  var debugPanel = document.getElementById("debugPanel");
  var debugStatus = document.getElementById("debugStatus");
  var debugLogEl = document.getElementById("debugLog");

  // --- Режим страницы ---
  var isDebug = false; // ?debug=1 — панель логов
  var alwaysVisible = false; // ?visible=1 — оверлей всегда показан
  var isSim = false; // ?sim=1 — локальный забег без бэка

  // --- Состояние раунда / анимации ---
  var pollTimer = null;
  var ws = null;
  var prevRoundId = 0;
  var prevState = "IDLE";
  var lineupCache = []; // Текущий состав для DOM
  var animRaf = 0; // requestAnimationFrame id
  var animPlaying = false; // Идёт RAF-проигрывание сценария
  var countdownTimer = null;
  var chaosByHorse = {}; // Лёгкий вертикальный «виляж» по лошади
  var statusByHorse = {}; // boost / slow / stun / normal
  var fxLastSpawn = {}; // Троттлинг всплывающих △ ▽ x_x

  // --- Следы за бегунами ---
  var trailByHorse = {}; // accDx / чередование L–R шага
  var FX_PULSE_MS = 720; // Как часто повторять статус-FX, пока эффект активен
  var TRAIL_MIN_MS = 120; // Мин. пауза между точками-следами
  var TRAIL_ACC_DX = 5; // Сколько px пробежать, прежде чем поставить след
  var TRAIL_SIZE = 4; // Диаметр точки-следа (px)
  var TRAIL_STEP_Y = 5; // Разнос «левый / правый» шаг по вертикали
  var FX_LABEL = { boost: "△", slow: "▽", stun: "x_x" };

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

  function buildRunner(row) {
    var slug = row.icon_slug || "unknown";
    var url = row.icon_url || "/assets/princesses/" + slug + ".webp";
    var wrap = document.createElement("div");
    wrap.className = "runner";
    wrap.dataset.horse = String(row.horse_number);

    var img = document.createElement("img");
    img.className = "runner-icon";
    img.src = url;
    img.alt = row.princess_name || "";
    img.onerror = function () {
      var div = document.createElement("div");
      div.className = "runner-icon";
      div.style.display = "flex";
      div.style.alignItems = "center";
      div.style.justifyContent = "center";
      div.style.color = "#fff";
      div.style.font = '700 14px "Segoe UI", system-ui, sans-serif';
      div.textContent = runnerFallback(row.princess_name);
      img.replaceWith(div);
    };
    wrap.appendChild(img);

    var num = document.createElement("span");
    num.className = "runner-num";
    num.textContent = String(row.horse_number);
    wrap.appendChild(num);

    return wrap;
  }

  function trackWidth() {
    var track = document.getElementById("track");
    return Math.max(120, track.clientWidth - TRACK_PAD_LEFT - TRACK_PAD_RIGHT);
  }

  function trackHeight() {
    return Math.max(1, runnersEl.clientHeight || 0);
  }

  function positionToLeft(pos) {
    var w = trackWidth();
    return Math.min(w, Math.max(0, (pos / finishLine) * w));
  }

  function laneIconSize(count) {
    var h = trackHeight();
    // Не ужимаем под «без наезда» — наложение по Y нормально.
    // Чуть меньше max — чтобы низ (бейдж номера) не упирался в край.
    return Math.max(26, Math.min(ICON_SIZE, Math.floor(h * 0.34)));
  }

  function laneTops(count, iconSize) {
    var h = trackHeight();
    var n = Math.max(1, count | 0);
    var size = iconSize || laneIconSize(n);
    // border-box иконка + бейдж снизу (~bottom:-4 + высота 16)
    var outer = size + 8;
    var tops = [];
    if (n === 1) {
      tops.push(Math.max(0, (h - outer) / 2));
      return tops;
    }
    var span = Math.max(0, h - outer);
    for (var i = 0; i < n; i++) {
      tops.push((span * i) / (n - 1));
    }
    return tops;
  }

  function sortedLineup() {
    return lineupCache.slice().sort(function (a, b) {
      return (a.horse_number || 0) - (b.horse_number || 0);
    });
  }

  function applyLanes() {
    var rows = sortedLineup();
    var n = rows.length;
    var size = laneIconSize(n);
    var tops = laneTops(n, size);
    rows.forEach(function (row, idx) {
      var runner = runnersEl.querySelector(
        '.runner[data-horse="' + row.horse_number + '"]'
      );
      if (!runner) return;
      runner.dataset.lane = String(idx);
      runner.dataset.baseTop = String(tops[idx]);
      var icon = runner.querySelector(".runner-icon");
      if (icon) {
        icon.style.width = size + "px";
        icon.style.height = size + "px";
      }
      if (!animPlaying) {
        setRunnerTransform(runner, 0, 0);
      }
    });
  }

  function setRunnerTransform(runner, leftPx, chaosY) {
    var baseTop = parseFloat(runner.dataset.baseTop) || 0;
    runner.style.transform =
      "translate3d(" + leftPx + "px," + (baseTop + chaosY) + "px,0)";
  }

  function clampChaosY(runner, y) {
    var baseTop = parseFloat(runner.dataset.baseTop) || 0;
    var icon = runner.querySelector(".runner-icon");
    var size = (icon && icon.offsetHeight) || laneIconSize(lineupCache.length);
    var outer = size + 8; // бейдж номера снизу
    var maxUp = -baseTop;
    var maxDown = Math.max(0, trackHeight() - outer - baseTop);
    return Math.max(maxUp, Math.min(maxDown, y));
  }

  function chaosOffset(horse, pos) {
    // Только свой виляж около дорожки — без ухода на чужую полосу и без «разъезда».
    // Наложение иконок ок; кто впереди по X — выше по z-index в applySample.
    var h = Number(horse) || 0;
    var amp = Math.min(14, trackHeight() * 0.1);
    return Math.sin(pos / 18 + h * 2.1) * amp
      + Math.sin(pos / 41 + h * 0.7) * (amp * 0.45);
  }

  function spawnTrail(leftPx, topPx, st) {
    if (!runnersEl) return;
    var el = document.createElement("span");
    el.className = "runner-trail";
    if (st === "boost" || st === "slow") {
      el.classList.add("is-" + st);
    }
    el.style.left = Math.max(0, leftPx) + "px";
    el.style.top = Math.max(0, topPx) + "px";
    el.style.width = TRAIL_SIZE + "px";
    el.style.height = TRAIL_SIZE + "px";
    el.setAttribute("aria-hidden", "true");
    runnersEl.appendChild(el);
    el.addEventListener("animationend", function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  }

  function maybeSpawnTrail(horse, runner, leftPx, topPx, iconSize) {
    if (!animPlaying) return;
    var st = statusByHorse[horse] || "normal";
    if (st === "stun") return;

    var now = performance.now();
    var state = trailByHorse[horse];
    if (!state) {
      trailByHorse[horse] = {
        lastT: now,
        lastX: leftPx,
        accDx: 0,
        foot: 0,
      };
      return;
    }

    var dx = leftPx - state.lastX;
    state.lastX = leftPx;
    if (dx <= 0) return;

    state.accDx += dx;
    if (state.accDx < TRAIL_ACC_DX || now - state.lastT < TRAIL_MIN_MS) {
      return;
    }

    // Шашечка: чётный шаг выше центра, нечётный ниже (левый / правый)
    var isLeft = (state.foot % 2) === 0;
    var cx = leftPx + iconSize * 0.2 - TRAIL_SIZE * 0.5;
    var cy = topPx + iconSize * 0.5 - TRAIL_SIZE * 0.5;
    var trailTop = cy + (isLeft ? -TRAIL_STEP_Y : TRAIL_STEP_Y);
    spawnTrail(cx, trailTop, st);
    state.foot += 1;
    state.accDx = 0;
    state.lastT = now;
  }

  function spawnStatusFx(runner, st) {
    var label = FX_LABEL[st];
    if (!label || !runner) return;
    var el = document.createElement("span");
    el.className = "runner-fx is-" + st;
    el.textContent = label;
    el.setAttribute("aria-hidden", "true");
    // Лёгкий джиттер только у △/▽, x_x остаётся справа сверху
    if (st === "boost" || st === "slow") {
      el.style.top = (st === "boost" ? 4 : -6) + Math.floor(Math.random() * 8) + "%";
    }
    runner.appendChild(el);
    el.addEventListener("animationend", function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    });
  }

  function updateStatuses(statuses) {
    var map = statuses || {};
    var now = performance.now();
    runnersEl.querySelectorAll(".runner").forEach(function (runner) {
      var horse = runner.dataset.horse;
      var icon = runner.querySelector(".runner-icon");
      if (!icon) return;
      icon.classList.remove("is-boost", "is-slow", "is-stun");
      var st = map[horse] || "normal";
      if (st === "boost") icon.classList.add("is-boost");
      else if (st === "slow") icon.classList.add("is-slow");
      else if (st === "stun") icon.classList.add("is-stun");

      var prev = statusByHorse[horse] || "normal";
      var last = fxLastSpawn[horse] || 0;
      var entered = st !== "normal" && st !== prev;
      var pulse = st !== "normal" && now - last >= FX_PULSE_MS;
      if (entered || pulse) {
        spawnStatusFx(runner, st);
        fxLastSpawn[horse] = now;
      }
      statusByHorse[horse] = st;
    });
  }

  function renderLineup(lineup) {
    lineupCache = lineup || [];
    chaosByHorse = {};
    statusByHorse = {};
    fxLastSpawn = {};
    trailByHorse = {};
    runnersEl.innerHTML = "";
    sortedLineup().forEach(function (row) {
      runnersEl.appendChild(buildRunner(row));
    });
    applyLanes();
  }

  function stopAnim() {
    if (animRaf) {
      cancelAnimationFrame(animRaf);
      animRaf = 0;
    }
    if (countdownTimer) {
      clearTimeout(countdownTimer);
      countdownTimer = null;
    }
    hideCountdown();
    animPlaying = false;
  }

  function hideCountdown() {
    if (!countdownEl) return;
    countdownEl.classList.remove("is-visible", "is-anim", "is-go");
    countdownEl.textContent = "";
    countdownEl.setAttribute("aria-hidden", "true");
  }

  function runCountdown() {
    return new Promise(function (resolve) {
      if (!countdownEl) {
        resolve();
        return;
      }
      var steps = isSim ? SIM_COUNTDOWN_STEPS : COUNTDOWN_STEPS;
      var i = 0;

      function beat() {
        if (i >= steps.length) {
          hideCountdown();
          countdownTimer = null;
          resolve();
          return;
        }
        var label = steps[i];
        var isGo = i === steps.length - 1;
        countdownEl.classList.remove("is-anim", "is-go", "is-visible");
        void countdownEl.offsetWidth;
        countdownEl.textContent = label;
        countdownEl.classList.add("is-visible");
        if (isGo) countdownEl.classList.add("is-go");
        countdownEl.classList.add("is-anim");
        countdownEl.setAttribute("aria-hidden", "false");
        i += 1;
        countdownTimer = setTimeout(beat, isGo ? COUNTDOWN_GO_MS : COUNTDOWN_BEAT_MS);
      }

      beat();
    });
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function sampleKeyframe(keyframes, t) {
    if (!keyframes || !keyframes.length) {
      return { positions: {}, statuses: {} };
    }
    if (t <= keyframes[0].t) return keyframes[0];
    var last = keyframes[keyframes.length - 1];
    if (t >= last.t) return last;

    var i = 1;
    while (i < keyframes.length && keyframes[i].t < t) i++;
    var a = keyframes[i - 1];
    var b = keyframes[i];
    var span = b.t - a.t || 1;
    var u = (t - a.t) / span;

    var positions = {};
    var horses = Object.keys(a.positions);
    for (var h = 0; h < horses.length; h++) {
      var key = horses[h];
      var pa = Number(a.positions[key]) || 0;
      var pb = Number((b.positions && b.positions[key]) != null ? b.positions[key] : pa);
      positions[key] = lerp(pa, pb, u);
    }
    // Статусы — дискретные, берём из ближайшего прошедшего кадра
    return { positions: positions, statuses: a.statuses || {} };
  }

  function applySample(sample, winnerHorse) {
    var positions = sample.positions || {};
    updateStatuses(sample.statuses);
    var entries = Object.keys(positions).map(function (horse) {
      return { horse: horse, pos: Number(positions[horse]) || 0 };
    });
    entries.sort(function (a, b) {
      if (b.pos !== a.pos) return b.pos - a.pos;
      return Number(a.horse) - Number(b.horse);
    });

    entries.forEach(function (entry, idx) {
      var runner = runnersEl.querySelector('.runner[data-horse="' + entry.horse + '"]');
      if (!runner) return;
      var left = positionToLeft(entry.pos);
      runner.style.zIndex = String(10 + (entries.length - idx));

      var state = chaosByHorse[entry.horse];
      if (!state) {
        state = { y: 0 };
        chaosByHorse[entry.horse] = state;
      }
      var target = chaosOffset(entry.horse, entry.pos);
      state.y += (target - state.y) * 0.18;
      state.y = clampChaosY(runner, state.y);
      setRunnerTransform(runner, left, state.y);

      var baseTop = parseFloat(runner.dataset.baseTop) || 0;
      var icon = runner.querySelector(".runner-icon");
      var iconSize = (icon && icon.offsetHeight) || laneIconSize(lineupCache.length);
      maybeSpawnTrail(entry.horse, runner, left, baseTop + state.y, iconSize);

      if (winnerHorse && String(winnerHorse) === entry.horse && entry.pos >= finishLine * 0.98) {
        runner.classList.add("is-winner");
      }
    });
  }

  function playRaceScript(script) {
    stopAnim();
    if (!script || !script.keyframes) return;

    finishLine = Number(script.finishLine) || finishLine;
    if (script.lineup && script.lineup.length) {
      renderLineup(script.lineup);
    }
    runnersEl.querySelectorAll(".runner").forEach(function (r) {
      r.classList.remove("is-winner");
    });
    chaosByHorse = {};
    setVisible(true);
    animPlaying = true;

    var durationMs = Math.max(500, (Number(script.durationSec) || 20) * 1000);
    var roundId = script.roundId;
    var winnerHorse = script.winnerHorse;
    var doneSent = false;
    var safetyTimer = null;

    function finish() {
      if (doneSent) return;
      doneSent = true;
      animPlaying = false;
      if (safetyTimer) clearTimeout(safetyTimer);
      applySample(script.keyframes[script.keyframes.length - 1], winnerHorse);
      if (!isSim) {
        wsSend({ status: "race_done", roundId: roundId });
      }
      dbg("race_done round=" + roundId + (isSim ? " (sim)" : ""));
    }

    function startRaceAnim() {
      var start = performance.now();
      function frame(now) {
        var t = (now - start) / 1000;
        var sample = sampleKeyframe(script.keyframes, t);
        applySample(sample, winnerHorse);
        if (t >= script.durationSec) {
          finish();
          return;
        }
        animRaf = requestAnimationFrame(frame);
      }
      dbg("race_anim round=" + roundId + " dur=" + script.durationSec);
      animRaf = requestAnimationFrame(frame);
      safetyTimer = setTimeout(function () {
        if (animPlaying) finish();
      }, durationMs + 2000);
    }

    dbg("race_start round=" + roundId + " countdown");
    runCountdown().then(startRaceAnim);
  }

  function handleStatus(data) {
    var state = data.state || "IDLE";
    var roundId = data.round_id || 0;

    if (data.finish_line) {
      finishLine = Number(data.finish_line) || finishLine;
    }

    if (isDebug) {
      debugStatus.textContent =
        "state=" + state + " round=" + roundId + " timer=" + (data.timer_sec || 0) +
        (animPlaying ? " · anim" : "");
    }

    if (data.lineup && data.lineup.length) {
      if (roundId !== prevRoundId || !lineupCache.length) {
        if (!animPlaying) renderLineup(data.lineup);
        prevRoundId = roundId;
      }
    }

    if (state === "OPEN" && prevState !== "OPEN") {
      if (typeof window.playObsSfx === "function") {
        window.playObsSfx("/assets/sounds/race.mp3");
      }
    }

    if (state === "OPEN" || state === "RACE_WAIT" || state === "RACE") {
      setVisible(true);
      if ((state === "OPEN" || state === "RACE_WAIT") && !animPlaying) {
        runnersEl.querySelectorAll(".runner").forEach(function (runner) {
          runner.classList.remove("is-winner");
          setRunnerTransform(runner, 0, 0);
        });
        updateStatuses({});
      }
    } else if (!alwaysVisible && !animPlaying) {
      setVisible(false);
    }

    prevState = state;
  }

  function pollInterval(state) {
    if (state === "OPEN" || state === "RACE_WAIT" || state === "RACE") {
      return POLL_ACTIVE_MS;
    }
    return POLL_IDLE_MS;
  }

  function schedulePoll(delay) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(tickPoll, delay);
  }

  function tickPoll() {
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

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + WS_PATH;
  }

  function wsSend(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function connectWs() {
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      dbg("ws create fail");
      setTimeout(connectWs, RECONNECT_MS);
      return;
    }
    ws.onopen = function () {
      dbg("ws open");
      wsSend({ status: "ready", overlay: "races", debug: isDebug });
    };
    ws.onmessage = function (ev) {
      var data;
      try {
        data = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (!data || typeof data !== "object") return;
      if (data.action === "race_start") {
        playRaceScript(data);
      }
    };
    ws.onclose = function () {
      dbg("ws close");
      setTimeout(connectWs, RECONNECT_MS);
    };
    ws.onerror = function () {
      try {
        ws.close();
      } catch (e) {}
    };
  }

  function buildSimScript() {
    var lineup = SIM_LINEUP.map(function (row) {
      return {
        horse_number: row.horse_number,
        princess_name: row.princess_name,
        icon_slug: row.icon_slug,
        icon_url: "/assets/princesses/" + row.icon_slug + ".webp",
      };
    });
    var n = lineup.length;
    var durationSec = 40;
    var step = 0.15;
    var fl = finishLine;
    var speeds = [];
    var statuses = [];
    var statusLeft = [];
    var i;
    for (i = 0; i < n; i++) {
      speeds.push(2.1 + Math.random() * 0.9);
      statuses.push("normal");
      statusLeft.push(0);
    }

    var positions = {};
    for (i = 0; i < n; i++) {
      positions[String(lineup[i].horse_number)] = 0;
    }

    var keyframes = [];
    var t = 0;
    while (t <= durationSec + 0.001) {
      var statusMap = {};
      for (i = 0; i < n; i++) {
        var horse = String(lineup[i].horse_number);
        if (statusLeft[i] > 0) {
          statusLeft[i] -= step;
          if (statusLeft[i] <= 0) statuses[i] = "normal";
        } else if (t > 1.5 && Math.random() < 0.04) {
          var roll = Math.random();
          if (roll < 0.45) {
            statuses[i] = "boost";
            statusLeft[i] = 1.2 + Math.random() * 1.2;
          } else if (roll < 0.8) {
            statuses[i] = "slow";
            statusLeft[i] = 1.0 + Math.random() * 1.0;
          } else {
            statuses[i] = "stun";
            statusLeft[i] = 0.6 + Math.random() * 0.8;
          }
        }

        var mult = 1;
        if (statuses[i] === "boost") mult = 1.65;
        else if (statuses[i] === "slow") mult = 0.45;
        else if (statuses[i] === "stun") mult = 0;

        var tick = (speeds[i] * mult * step) / 0.4;
        positions[horse] = Math.min(fl, (positions[horse] || 0) + tick);
        statusMap[horse] = statuses[i];
      }

      var posCopy = {};
      Object.keys(positions).forEach(function (k) {
        posCopy[k] = Math.round(positions[k] * 100) / 100;
      });
      keyframes.push({
        t: Math.round(t * 1000) / 1000,
        positions: posCopy,
        statuses: statusMap,
      });
      t += step;
    }

    var order = lineup
      .map(function (row) {
        return {
          horse: row.horse_number,
          pos: positions[String(row.horse_number)] || 0,
        };
      })
      .sort(function (a, b) {
        return b.pos - a.pos;
      });

    return {
      roundId: 0,
      durationSec: durationSec,
      finishLine: fl,
      winnerHorse: order[0].horse,
      winnerName: lineup.filter(function (r) {
        return r.horse_number === order[0].horse;
      })[0].princess_name,
      finishOrder: order.map(function (o) {
        return o.horse;
      }),
      lineup: lineup,
      keyframes: keyframes,
    };
  }

  function startSim() {
    var script = buildSimScript();
    dbg("sim start winner=№" + script.winnerHorse + " " + script.winnerName);
    if (debugStatus) {
      debugStatus.textContent =
        "SIM · R = restart · winner №" + script.winnerHorse + " " + script.winnerName;
    }
    playRaceScript(script);
  }

  function setupSimUi() {
    // Тёмный фон в браузере; панель — только при ?debug=1
    document.body.classList.add("debug-mode");
    if (isDebug && debugPanel) {
      debugPanel.style.display = "block";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = "↻ Restart sim (R)";
      btn.style.cssText =
        "margin-top:8px;display:block;width:100%;padding:6px 8px;" +
        "background:#2a3a55;color:#cfe3ff;border:1px solid #4a6a9a;" +
        "border-radius:4px;cursor:pointer;font:600 12px 'Segoe UI',system-ui,sans-serif;";
      btn.addEventListener("click", function () {
        startSim();
      });
      debugPanel.insertBefore(btn, debugStatus);
    }
    window.addEventListener("keydown", function (ev) {
      if (ev.key === "r" || ev.key === "R") {
        if (ev.target && /input|textarea/i.test(ev.target.tagName)) return;
        startSim();
      }
    });
  }

  function init() {
    isDebug = parseQueryFlag("debug");
    alwaysVisible = parseQueryFlag("visible");
    isSim = parseQueryFlag("sim");
    if (isSim) {
      alwaysVisible = true;
    }
    if (isDebug) {
      document.body.classList.add("debug-mode");
      debugPanel.style.display = "block";
    }
    if (alwaysVisible) setVisible(true);
    window.addEventListener("resize", function () {
      applyLanes();
    });

    if (isSim) {
      setupSimUi();
      setVisible(true);
      startSim();
      return;
    }

    connectWs();
    tickPoll();
  }

  init();
})();
