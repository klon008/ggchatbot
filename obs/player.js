/* OBS Song Request — плеер на YouTube IFrame API.
 *
 * Раздаётся Python-сервером по http://127.0.0.1:PORT/player.html
 * (важно: НЕ открывать через file:// — YouTube вернёт error 153).
 *
 * Режим отладки: ?debug=1 — тёмная подложка и панель логов/ошибок на экране.
 *
 * В idle (очередь пуста) оверлей полностью прозрачен — iframe не создаётся
 * до первого play (lazy-init), после ENDED плеер скрывается и очищается.
 *
 * Протокол с Python:
 *   Python -> плеер: {action:"play", videoId, token, maxDurationSec, requestedBy, title}
 *                    {action:"skip", token}
 *                    {action:"queue_state", playing, queueLength, current}
 *   плеер  -> Python: {status:"ready", youtubeApi, youtubeApiState, youtubeApiError?}
 *                     {status:"api_error", code, message}
 *                     {status:"ended",    token, videoId}
 *                     {status:"error",    token, videoId, code, message?}
 *                     {status:"too_long", token, videoId, durationSec}
 */
(function () {
  "use strict";

  var WS_PATH = "/ws";
  var API_LOAD_TIMEOUT_MS = 15000;
  var YT_API_URL = "https://www.youtube.com/iframe_api";

  var playerWrap = document.getElementById("playerWrap");
  var playerInner = document.getElementById("playerInner");
  var npUser = document.getElementById("npUser");
  var npTitle = document.getElementById("npTitle");
  var debugPanel = document.getElementById("debugPanel");
  var debugStatus = document.getElementById("debugStatus");
  var debugLogEl = document.getElementById("debugLog");

  var ANIM_MS = 480;
  var hideTimer = null;
  var hideListener = null;

  var player = null;
  var playerReady = false;
  var playerCreating = false;
  var pendingPlay = null;

  /** @type {"idle"|"loading"|"ready"|"failed"} */
  var apiState = "idle";
  var apiFailReason = "";
  var apiLoadTimer = null;
  var apiErrorSent = false;

  var ws = null;
  var wsReconnectDelay = 1000;
  var wsState = "disconnected";

  var isDebug = false;

  var current = {
    token: null,
    videoId: null,
    maxDurationSec: 0,
    requestedBy: "",
    title: ""
  };
  var durationChecked = false;

  var YT_ERROR_LABELS = {
    2: "неверный параметр запроса",
    5: "ошибка HTML5-плеера",
    100: "видео удалено или приватное",
    101: "встраивание запрещено владельцем",
    150: "встраивание запрещено владельцем",
    153: "нужен HTTP-URL (не file://) и валидный Referer"
  };

  function parseDebugMode() {
    try {
      var params = new URLSearchParams(location.search);
      var v = (params.get("debug") || "").toLowerCase();
      return v === "1" || v === "true" || v === "yes";
    } catch (e) {
      return false;
    }
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function nowStamp() {
    var d = new Date();
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
  }

  function debugLog(level, message) {
    if (isDebug && debugLogEl) {
      var li = document.createElement("li");
      li.className = "log-" + level;
      li.innerHTML =
        '<span class="log-time">' + nowStamp() + "</span>" +
        "<span>" + escapeHtml(String(message)) + "</span>";
      debugLogEl.appendChild(li);
      while (debugLogEl.children.length > 200) {
        debugLogEl.removeChild(debugLogEl.firstChild);
      }
      debugLogEl.scrollTop = debugLogEl.scrollHeight;
    }
    if (level === "error") {
      console.error("[OBS player]", message);
    } else if (level === "warn") {
      console.warn("[OBS player]", message);
    } else {
      console.log("[OBS player]", message);
    }
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function updateDebugStatus() {
    if (!isDebug || !debugStatus) return;
    var lines = [
      "WebSocket: " + wsState,
      "YouTube API: " + apiState + (apiFailReason ? " — " + apiFailReason : ""),
      "Плеер: " + (playerReady ? "готов" : playerCreating ? "создаётся" : "нет")
    ];
    if (current.videoId) {
      lines.push("Трек: " + current.videoId + " (token " + (current.token || "—") + ")");
    }
    debugStatus.textContent = lines.join(" · ");
  }

  function initDebugMode() {
    if (!isDebug) return;
    document.body.classList.add("debug-mode");
    debugLog("info", "Режим debug=1: подложка и логи на экране.");
    debugLog("info", "URL: " + location.href);

    window.addEventListener("error", function (evt) {
      var msg = evt.message || "Неизвестная ошибка";
      if (evt.filename) {
        msg += " (" + evt.filename;
        if (evt.lineno) msg += ":" + evt.lineno;
        msg += ")";
      }
      debugLog("error", msg);
      updateDebugStatus();
    });

    window.addEventListener("unhandledrejection", function (evt) {
      var reason = evt.reason;
      var text = reason && reason.message ? reason.message : String(reason);
      debugLog("error", "Unhandled rejection: " + text);
      updateDebugStatus();
    });

    updateDebugStatus();
  }

  function updateNowPlaying(requestedBy, title) {
    if (npUser) {
      npUser.textContent = requestedBy || "Зритель";
    }
    if (npTitle) {
      npTitle.textContent = title || "Загрузка…";
    }
  }

  function refreshTitleFromPlayer() {
    if (!player || !player.getVideoData) return;
    try {
      var data = player.getVideoData();
      if (data && data.title) {
        current.title = data.title;
        updateNowPlaying(current.requestedBy, current.title);
      }
    } catch (e) {}
  }

  function showPlayer() {
    cancelHide();
    document.body.classList.add("playing");
    if (!playerWrap) return;
    playerWrap.style.visibility = "visible";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        playerWrap.classList.add("is-visible");
      });
    });
  }

  function cancelHide() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    if (hideListener && playerInner) {
      playerInner.removeEventListener("transitionend", hideListener);
      hideListener = null;
    }
  }

  function finishHide() {
    cancelHide();
    document.body.classList.remove("playing");
    if (playerWrap) {
      playerWrap.classList.remove("is-visible");
      if (!isDebug) {
        playerWrap.style.visibility = "hidden";
      }
    }
    if (player) {
      try {
        player.stopVideo();
        player.clearVideo();
      } catch (e) {}
    }
  }

  function hidePlayer(immediate) {
    if (immediate || !playerWrap || !document.body.classList.contains("playing")) {
      finishHide();
      return;
    }
    cancelHide();
    playerWrap.classList.remove("is-visible");
    hideListener = function (e) {
      if (e.target !== playerInner || e.propertyName !== "transform") return;
      finishHide();
    };
    if (playerInner) {
      playerInner.addEventListener("transitionend", hideListener);
    }
    hideTimer = setTimeout(finishHide, ANIM_MS + 80);
  }

  function readyPayload() {
    return {
      status: "ready",
      youtubeApi: apiState === "ready",
      youtubeApiState: apiState,
      youtubeApiError: apiFailReason || null,
      debug: isDebug
    };
  }

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + WS_PATH;
  }

  function connectWs() {
    wsState = "connecting";
    updateDebugStatus();
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      wsState = "error";
      debugLog("error", "WebSocket: " + e.message);
      updateDebugStatus();
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      wsState = "connected";
      wsReconnectDelay = 1000;
      debugLog("info", "WebSocket подключён.");
      hidePlayer(true);
      send(readyPayload());
      updateDebugStatus();
    };

    ws.onmessage = function (evt) {
      var data;
      try {
        data = JSON.parse(evt.data);
      } catch (e) {
        debugLog("warn", "Некорректный JSON от бота: " + String(evt.data).slice(0, 120));
        return;
      }
      debugLog("info", "Команда: " + (data.action || JSON.stringify(data)));
      handleCommand(data);
      updateDebugStatus();
    };

    ws.onclose = function () {
      wsState = "disconnected";
      debugLog("warn", "WebSocket отключён, переподключение…");
      updateDebugStatus();
      scheduleReconnect();
    };

    ws.onerror = function () {
      wsState = "error";
      debugLog("error", "WebSocket ошибка.");
      updateDebugStatus();
      try { ws.close(); } catch (e) {}
    };
  }

  function scheduleReconnect() {
    setTimeout(connectWs, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 10000);
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function handleCommand(data) {
    switch (data.action) {
      case "play":
        playVideo(data);
        break;
      case "skip":
        skipVideo();
        break;
      case "queue_state":
        if (!data.playing) {
          hidePlayer();
        }
        break;
    }
  }

  function startPlayback() {
    updateNowPlaying(current.requestedBy, current.title || "Загрузка…");
    showPlayer();
    try {
      player.mute();
      player.loadVideoById(current.videoId);
    } catch (e) {
      reportError(2, "loadVideoById: " + e.message);
    }
  }

  function playVideo(cmd) {
    current = {
      token: cmd.token || null,
      videoId: cmd.videoId || null,
      maxDurationSec: cmd.maxDurationSec || 0,
      requestedBy: cmd.requestedBy || "",
      title: cmd.title || ""
    };
    durationChecked = false;
    updateDebugStatus();

    if (apiState === "failed") {
      reportApiUnavailableForPlay();
      return;
    }

    ensureYouTubeApi();
    ensurePlayer(startPlayback);
  }

  function reportApiUnavailableForPlay() {
    var msg = apiFailReason || "YouTube IFrame API недоступен";
    debugLog("error", "Заказ не открыт: " + msg);
    send({
      status: "error",
      token: current.token,
      videoId: current.videoId,
      code: "youtube_api_unavailable",
      message: msg
    });
  }

  function skipVideo() {
    hidePlayer();
    send({ status: "ended", token: current.token, videoId: current.videoId, skipped: true });
  }

  function checkDuration(attempt) {
    if (durationChecked || !player) return;
    var dur = 0;
    try { dur = player.getDuration(); } catch (e) { dur = 0; }

    if (!dur || dur <= 0) {
      if (attempt < 6) {
        setTimeout(function () { checkDuration(attempt + 1); }, 1000);
      } else {
        durationChecked = true;
        var msg = "не удалось получить длительность (live или сеть)";
        debugLog("warn", msg);
        hidePlayer();
        send({ status: "too_long", token: current.token, videoId: current.videoId, durationSec: 0, message: msg });
      }
      return;
    }

    durationChecked = true;
    if (current.maxDurationSec > 0 && dur > current.maxDurationSec) {
      var longMsg = "трек длиннее лимита (" + Math.round(dur) + "с)";
      debugLog("warn", longMsg);
      hidePlayer();
      send({
        status: "too_long",
        token: current.token,
        videoId: current.videoId,
        durationSec: Math.round(dur),
        message: longMsg
      });
    }
  }

  function youtubeErrorLabel(code) {
    return YT_ERROR_LABELS[code] || "код YouTube " + code;
  }

  function reportError(code, extraMessage) {
    var label = typeof code === "number" ? youtubeErrorLabel(code) : String(code);
    var msg = extraMessage ? label + ": " + extraMessage : label;
    debugLog("error", "Ошибка воспроизведения: " + msg);
    hidePlayer();
    send({
      status: "error",
      token: current.token,
      videoId: current.videoId,
      code: code,
      message: msg
    });
    updateDebugStatus();
  }

  function clearApiLoadTimer() {
    if (apiLoadTimer) {
      clearTimeout(apiLoadTimer);
      apiLoadTimer = null;
    }
  }

  function ensureYouTubeApi() {
    if (apiState === "ready" || apiState === "loading") {
      return;
    }
    loadYouTubeApi();
  }

  function loadYouTubeApi() {
    if (apiState === "ready" || apiState === "loading") {
      return;
    }
    apiState = "loading";
    apiFailReason = "";
    apiErrorSent = false;
    updateDebugStatus();
    debugLog("info", "Загрузка " + YT_API_URL + " …");

    var tag = document.createElement("script");
    tag.src = YT_API_URL;
    tag.async = true;
    tag.onerror = function () {
      failYouTubeApi(
        "script_error",
        "Не удалось загрузить youtube.com/iframe_api (сеть, блокировка или ERR_CONNECTION_RESET)"
      );
    };
    document.head.appendChild(tag);

    clearApiLoadTimer();
    apiLoadTimer = setTimeout(function () {
      if (apiState === "loading") {
        failYouTubeApi("timeout", "YouTube IFrame API не ответил за " + (API_LOAD_TIMEOUT_MS / 1000) + " с");
      }
    }, API_LOAD_TIMEOUT_MS);
  }

  function failYouTubeApi(code, message) {
    if (apiState === "ready" || apiState === "failed") {
      return;
    }
    clearApiLoadTimer();
    apiState = "failed";
    apiFailReason = message;
    updateDebugStatus();
    debugLog("error", message);

    if (!apiErrorSent) {
      apiErrorSent = true;
      send({ status: "api_error", code: code, message: message });
    }

    if (pendingPlay) {
      reportApiUnavailableForPlay();
      pendingPlay = null;
    }
  }

  function markYouTubeApiReady() {
    if (apiState === "ready") {
      return;
    }
    clearApiLoadTimer();
    apiState = "ready";
    apiFailReason = "";
    updateDebugStatus();
    debugLog("info", "YouTube IFrame API готов.");
    if (pendingPlay) {
      createPlayer();
    }
  }

  function ensurePlayer(callback) {
    if (playerReady && player) {
      callback();
      return;
    }
    pendingPlay = callback;
    if (apiState === "failed") {
      reportApiUnavailableForPlay();
      pendingPlay = null;
      return;
    }
    if (apiState !== "ready") {
      return;
    }
    createPlayer();
  }

  function createPlayer() {
    if (player || playerCreating) return;
    if (!window.YT || !window.YT.Player) {
      failYouTubeApi("api_missing", "YT.Player не найден после загрузки скрипта");
      return;
    }
    playerCreating = true;
    debugLog("info", "Создание YT.Player…");
    player = new YT.Player("player", {
      width: "100%",
      height: "100%",
      playerVars: {
        autoplay: 1,
        controls: isDebug ? 1 : 0,
        disablekb: 1,
        fs: 0,
        modestbranding: 1,
        rel: 0,
        playsinline: 1,
        enablejsapi: 1,
        cc_load_policy: 0,
        origin: location.origin
      },
      events: {
        onReady: onPlayerReady,
        onStateChange: onPlayerStateChange,
        onError: onPlayerError
      }
    });
  }

  window.onYouTubeIframeAPIReady = function () {
    markYouTubeApiReady();
  };

  function onPlayerReady() {
    playerReady = true;
    playerCreating = false;
    debugLog("info", "YT.Player готов.");
    hidePlayer(true);
    if (pendingPlay) {
      var cb = pendingPlay;
      pendingPlay = null;
      cb();
    }
    updateDebugStatus();
  }

  function stateName(state) {
    switch (state) {
      case -1: return "UNSTARTED";
      case 0: return "ENDED";
      case 1: return "PLAYING";
      case 2: return "PAUSED";
      case 3: return "BUFFERING";
      case 5: return "CUED";
      default: return String(state);
    }
  }

  function onPlayerStateChange(evt) {
    debugLog("info", "Состояние плеера: " + stateName(evt.data));
    switch (evt.data) {
      case YT.PlayerState.PLAYING:
        refreshTitleFromPlayer();
        try {
          player.unMute();
          player.setVolume(100);
          player.setOption("captions", "track", {});
        } catch (e) {}
        checkDuration(0);
        break;
      case YT.PlayerState.BUFFERING:
        refreshTitleFromPlayer();
        break;
      case YT.PlayerState.ENDED:
        hidePlayer();
        send({ status: "ended", token: current.token, videoId: current.videoId });
        break;
    }
    updateDebugStatus();
  }

  function onPlayerError(evt) {
    reportError(evt.data);
  }

  // ---- старт ----------------------------------------------------------
  isDebug = parseDebugMode();
  initDebugMode();
  hidePlayer(true);

  if (isDebug) {
    loadYouTubeApi();
  } else if (window.YT && window.YT.Player) {
    markYouTubeApiReady();
  }

  connectWs();
})();
