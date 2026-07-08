/* OBS Song Request — плеер на YouTube IFrame API.
 *
 * Раздаётся Python-сервером по http://127.0.0.1:PORT/player.html
 * (важно: НЕ открывать через file:// — YouTube вернёт error 153).
 *
 * В idle (очередь пуста) оверлей полностью прозрачен — iframe не создаётся
 * до первого play (lazy-init), после ENDED плеер скрывается и очищается.
 *
 * Протокол с Python:
 *   Python -> плеер: {action:"play", videoId, token, maxDurationSec, requestedBy, title}
 *                    {action:"skip", token}
 *                    {action:"queue_state", playing, queueLength, current}
 *   плеер  -> Python: {status:"ready"}
 *                     {status:"ended",    token, videoId}
 *                     {status:"error",    token, videoId, code}
 *                     {status:"too_long", token, videoId, durationSec}
 */
(function () {
  "use strict";

  var WS_PATH = "/ws";
  var playerWrap = document.getElementById("playerWrap");
  var playerInner = document.getElementById("playerInner");
  var npUser = document.getElementById("npUser");
  var npTitle = document.getElementById("npTitle");

  var ANIM_MS = 480;
  var hideTimer = null;
  var hideListener = null;

  var player = null;
  var playerReady = false;
  var apiReady = false;
  var playerCreating = false;
  var pendingPlay = null; // play, ожидающий готовности плеера/API

  var ws = null;
  var wsReconnectDelay = 1000;

  var current = {
    token: null,
    videoId: null,
    maxDurationSec: 0,
    requestedBy: "",
    title: ""
  };
  var durationChecked = false;

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
    // Два rAF — браузер успевает применить visibility до старта transition.
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
      playerWrap.style.visibility = "hidden";
    }
    if (player) {
      try {
        player.stopVideo();
        player.clearVideo();
      } catch (e) {}
    }
  }

  /** @param {boolean} [immediate] — без анимации (старт страницы, init) */
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

  // ---- WebSocket ------------------------------------------------------
  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + WS_PATH;
  }

  function connectWs() {
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      wsReconnectDelay = 1000;
      hidePlayer(true);
      send({ status: "ready" });
    };

    ws.onmessage = function (evt) {
      var data;
      try {
        data = JSON.parse(evt.data);
      } catch (e) {
        return;
      }
      handleCommand(data);
    };

    ws.onclose = function () {
      scheduleReconnect();
    };

    ws.onerror = function () {
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

  // ---- обработка команд от Python ------------------------------------
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
      reportError(2);
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
    ensurePlayer(startPlayback);
  }

  function skipVideo() {
    hidePlayer();
    send({ status: "ended", token: current.token, videoId: current.videoId, skipped: true });
  }

  // ---- проверка длительности / live ----------------------------------
  function checkDuration(attempt) {
    if (durationChecked || !player) return;
    var dur = 0;
    try { dur = player.getDuration(); } catch (e) { dur = 0; }

    if (!dur || dur <= 0) {
      if (attempt < 6) {
        setTimeout(function () { checkDuration(attempt + 1); }, 1000);
      } else {
        durationChecked = true;
        hidePlayer();
        send({ status: "too_long", token: current.token, videoId: current.videoId, durationSec: 0 });
      }
      return;
    }

    durationChecked = true;
    if (current.maxDurationSec > 0 && dur > current.maxDurationSec) {
      hidePlayer();
      send({ status: "too_long", token: current.token, videoId: current.videoId, durationSec: Math.round(dur) });
    }
  }

  function reportError(code) {
    hidePlayer();
    send({ status: "error", token: current.token, videoId: current.videoId, code: code });
  }

  // ---- YouTube IFrame API (lazy-init: только при первом play) ---------
  function ensurePlayer(callback) {
    if (playerReady && player) {
      callback();
      return;
    }
    pendingPlay = callback;
    if (!apiReady) {
      return;
    }
    createPlayer();
  }

  function createPlayer() {
    if (player || playerCreating) return;
    playerCreating = true;
    player = new YT.Player("player", {
      width: "100%",
      height: "100%",
      playerVars: {
        autoplay: 1,
        controls: 0,
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
    apiReady = true;
    if (pendingPlay) {
      createPlayer();
    }
  };

  function onPlayerReady() {
    playerReady = true;
    playerCreating = false;
    hidePlayer(true);
    if (pendingPlay) {
      var cb = pendingPlay;
      pendingPlay = null;
      cb();
    }
  }

  function onPlayerStateChange(evt) {
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
  }

  function onPlayerError(evt) {
    reportError(evt.data);
  }

  // ---- старт ----------------------------------------------------------
  hidePlayer(true);
  if (window.YT && window.YT.Player && !apiReady) {
    window.onYouTubeIframeAPIReady();
  }
  connectWs();
})();
