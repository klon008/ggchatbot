/* OBS Roulette — SVG-колесо, синхронизация с ботом через GET /api/roulette.
 *
 * Раздаётся Python-сервером: http://127.0.0.1:PORT/roulette.html
 * В OBS: Browser Source, прозрачный фон, размер ~600×600.
 *
 * Режим отладки: ?debug=1 — тёмная подложка и логи.
 *
 * Логика:
 *   SPIN_WAIT  → показать колесо, быстрое вращение (пауза перед спином бота)
 *   новый last_result → плавная остановка на выпавшем числе
 *   COOLDOWN   → показать результат, затем скрыть оверлей
 */
(function () {
  "use strict";

  var API_PATH = "/api/roulette";
  var POLL_FAST_MS = 280;
  var POLL_IDLE_MS = 2000;
  var SPIN_SPEED_DEG = 11.5;
  var LAND_MS = 3600;
  var RESULT_HOLD_MS = 4500;

  var WHEEL_ORDER = [
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10, 5,
    24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
  ];
  var RED = {
    1: 1, 3: 1, 5: 1, 7: 1, 9: 1, 12: 1, 14: 1, 16: 1, 18: 1, 19: 1,
    21: 1, 23: 1, 25: 1, 27: 1, 30: 1, 32: 1, 34: 1, 36: 1,
  };
  var POCKETS = WHEEL_ORDER.length;
  var SEG = 360 / POCKETS;
  var CX = 250;
  var CY = 250;
  var R_OUT = 228;
  var R_IN = 92;

  var wheelWrap = document.getElementById("wheelWrap");
  var wheelRotor = document.getElementById("wheelRotor");
  var pocketsEl = document.getElementById("pockets");
  var resultBanner = document.getElementById("resultBanner");
  var debugPanel = document.getElementById("debugPanel");
  var debugStatus = document.getElementById("debugStatus");
  var debugLogEl = document.getElementById("debugLog");

  var isDebug = false;
  var pollTimer = null;

  var prevState = "IDLE";
  var spinSession = null;
  var rotationDeg = 0;
  var animFrame = null;
  var landTimer = null;
  var hideTimer = null;
  var phase = "idle"; // idle | spinning | landing | result

  function parseDebugMode() {
    try {
      var v = (new URLSearchParams(location.search).get("debug") || "").toLowerCase();
      return v === "1" || v === "true" || v === "yes";
    } catch (e) {
      return false;
    }
  }

  function pocketColor(num) {
    if (num === 0) return "#187a44";
    return RED[num] ? "#c62828" : "#171717";
  }

  function polar(cx, cy, r, deg) {
    var rad = (deg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }

  function sectorPath(cx, cy, rIn, rOut, a0, a1) {
    var p0o = polar(cx, cy, rOut, a0);
    var p1o = polar(cx, cy, rOut, a1);
    var p0i = polar(cx, cy, rIn, a1);
    var p1i = polar(cx, cy, rIn, a0);
    var large = (a1 - a0) > 180 ? 1 : 0;
    return [
      "M", p0o.x, p0o.y,
      "A", rOut, rOut, 0, large, 1, p1o.x, p1o.y,
      "L", p0i.x, p0i.y,
      "A", rIn, rIn, 0, large, 0, p1i.x, p1i.y,
      "Z",
    ].join(" ");
  }

  function buildWheel() {
    if (!pocketsEl) return;
    var frag = document.createDocumentFragment();
    for (var i = 0; i < POCKETS; i++) {
      var num = WHEEL_ORDER[i];
      var a0 = i * SEG;
      var a1 = (i + 1) * SEG;
      var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", sectorPath(CX, CY, R_IN, R_OUT, a0, a1));
      path.setAttribute("fill", pocketColor(num));
      path.setAttribute("stroke", "rgba(255,255,255,0.12)");
      path.setAttribute("stroke-width", "1");
      frag.appendChild(path);

      var mid = a0 + SEG / 2;
      var labelPos = polar(CX, CY, (R_IN + R_OUT) / 2, mid);
      var text = document.createElementNS("http://www.w3.org/2000/svg", "text");
      text.setAttribute("x", String(labelPos.x));
      text.setAttribute("y", String(labelPos.y));
      text.setAttribute("class", "pocket-text");
      text.setAttribute("transform", "rotate(" + mid + " " + labelPos.x + " " + labelPos.y + ")");
      text.textContent = String(num);
      frag.appendChild(text);
    }
    pocketsEl.appendChild(frag);
  }

  function applyRotation() {
    if (wheelRotor) {
      wheelRotor.style.transform = "rotate(" + rotationDeg + "deg)";
    }
  }

  function rotationForNumber(num) {
    var idx = WHEEL_ORDER.indexOf(num);
    if (idx < 0) return 0;
    var pocketCenter = idx * SEG + SEG / 2;
    return 360 - pocketCenter;
  }

  function easeOutCubic(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  function resultSignature(result) {
    if (!result) return "";
    return String(result.number) + "|" + (result.label || "");
  }

  function nowStamp() {
    var d = new Date();
    function p(n) { return n < 10 ? "0" + n : String(n); }
    return p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  function debugLog(level, msg) {
    if (isDebug && debugLogEl) {
      var li = document.createElement("li");
      li.style.color = level === "error" ? "#ff7b7b" : level === "warn" ? "#ffd966" : "#9ecbff";
      li.textContent = nowStamp() + " " + msg;
      debugLogEl.appendChild(li);
      while (debugLogEl.children.length > 120) {
        debugLogEl.removeChild(debugLogEl.firstChild);
      }
      debugLogEl.scrollTop = debugLogEl.scrollHeight;
    }
    if (level === "error") console.error("[roulette obs]", msg);
    else if (level === "warn") console.warn("[roulette obs]", msg);
    else console.log("[roulette obs]", msg);
  }

  function setDebugStatus(text) {
    if (isDebug && debugStatus) debugStatus.textContent = text;
  }

  function clearTimers() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    if (landTimer) {
      clearTimeout(landTimer);
      landTimer = null;
    }
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    stopAnimFrame();
  }

  function stopAnimFrame() {
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
  }

  function showOverlay() {
    if (!wheelWrap) return;
    wheelWrap.classList.add("is-visible");
    wheelWrap.setAttribute("aria-hidden", "false");
  }

  function hideOverlay() {
    if (!wheelWrap) return;
    wheelWrap.classList.remove("is-visible");
    wheelWrap.setAttribute("aria-hidden", "true");
    hideResultBanner();
    phase = "idle";
    spinSession = null;
  }

  function showResultBanner(label) {
    if (!resultBanner) return;
    resultBanner.textContent = label || "";
    resultBanner.style.opacity = "1";
    resultBanner.style.transform = "translateX(-50%) translateY(0)";
  }

  function hideResultBanner() {
    if (!resultBanner) return;
    resultBanner.style.opacity = "0";
    resultBanner.style.transform = "translateX(-50%) translateY(12px)";
    resultBanner.textContent = "";
  }

  function startSpinning(session) {
    phase = "spinning";
    showOverlay();
    hideResultBanner();
    stopAnimFrame();

    var lastTs = performance.now();
    function tick(ts) {
      if (phase !== "spinning") return;
      var dt = ts - lastTs;
      lastTs = ts;
      rotationDeg += SPIN_SPEED_DEG * (dt / 16.67);
      applyRotation();
      animFrame = requestAnimationFrame(tick);
    }
    animFrame = requestAnimationFrame(tick);
    debugLog("info", "Старт вращения, раунд " + session.roundId);
    setDebugStatus("phase=spinning round=" + session.roundId);
  }

  function landOnNumber(num, label) {
    if (phase === "landing" || phase === "result") return;
    phase = "landing";
    stopAnimFrame();

    var from = rotationDeg;
    var targetMod = rotationForNumber(num);
    var currentMod = ((from % 360) + 360) % 360;
    var delta = targetMod - currentMod;
    if (delta <= 0) delta += 360;
    delta += 360 * (3 + Math.floor(Math.random() * 2));
    var to = from + delta;
    var t0 = performance.now();

    debugLog("info", "Остановка на " + num + " (" + label + ")");
    setDebugStatus("phase=landing number=" + num);

    function landFrame(now) {
      var t = Math.min(1, (now - t0) / LAND_MS);
      rotationDeg = from + (to - from) * easeOutCubic(t);
      applyRotation();
      if (t < 1) {
        animFrame = requestAnimationFrame(landFrame);
      } else {
        rotationDeg = to;
        applyRotation();
        phase = "result";
        showResultBanner(label || String(num));
        setDebugStatus("phase=result number=" + num);
        hideTimer = setTimeout(function () {
          hideOverlay();
          schedulePoll(POLL_IDLE_MS);
        }, RESULT_HOLD_MS);
      }
    }
    animFrame = requestAnimationFrame(landFrame);
  }

  function abortSpin() {
    debugLog("warn", "Раунд отменён или сброшен");
    clearTimers();
    hideOverlay();
    schedulePoll(POLL_IDLE_MS);
  }

  function beginSpinSession(data) {
    spinSession = {
      roundId: data.round_id,
      resultBefore: resultSignature(data.last_result),
    };
    startSpinning(spinSession);
  }

  function handleStatus(data) {
    var state = data.state || "IDLE";
    setDebugStatus(
      "state=" + state +
      " round=" + data.round_id +
      " timer=" + (data.timer_sec || 0) +
      " phase=" + phase
    );

    if (state === "SPIN_WAIT" && prevState !== "SPIN_WAIT") {
      beginSpinSession(data);
    } else if (state === "SPIN" && prevState === "OPEN" && phase === "idle") {
      beginSpinSession(data);
    }

    if (spinSession && phase === "spinning") {
      var sig = resultSignature(data.last_result);
      if (sig && sig !== spinSession.resultBefore) {
        var num = data.last_result.number;
        var label = data.last_result.label || String(num);
        landOnNumber(num, label);
      }
    }

    if (spinSession && (state === "IDLE" || state === "OPEN") && prevState !== state) {
      if (phase === "spinning") {
        abortSpin();
      }
    }

    if (state === "IDLE" && prevState === "COOLDOWN" && phase === "result") {
      hideOverlay();
    }

    prevState = state;
    var delay = (state === "IDLE" || state === "OPEN") ? POLL_IDLE_MS : POLL_FAST_MS;
    schedulePoll(delay);
  }

  function schedulePoll(delay) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(pollOnce, delay);
  }

  function pollOnce() {
    fetch(API_PATH, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        handleStatus(data);
      })
      .catch(function (err) {
        debugLog("error", "poll: " + err.message);
        setDebugStatus("poll error: " + err.message);
        schedulePoll(POLL_IDLE_MS);
      });
  }

  function initDebug() {
    if (!isDebug) return;
    document.body.classList.add("debug-mode");
    if (debugPanel) debugPanel.style.display = "block";
    debugLog("info", "debug=1, URL: " + location.href);
  }

  buildWheel();
  applyRotation();
  isDebug = parseDebugMode();
  initDebug();
  hideOverlay();
  pollOnce();
})();
