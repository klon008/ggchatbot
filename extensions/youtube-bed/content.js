"use strict";

/**
 * Content script на вкладках YouTube / YouTube Music.
 * WS к боту живёт здесь только пока вкладка — активный bed.
 *
 * Протокол:
 *   → {status:"ready", overlay:"bed"}
 *   ← {action:"play", ...}              → pause, pausedByBot=true
 *   ← {action:"queue_state", playing}   → pause if playing; resume if !playing && pausedByBot
 *   ← skip / toggle_pause               → ignore
 */

const WS_PATH = "/ws";
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 15000;
const VIDEO_RETRY_MS = 250;
const VIDEO_RETRY_MAX = 20;

let active = false;
let ws = null;
let reconnectTimer = null;
let reconnectDelay = RECONNECT_MIN_MS;
let pausedByBot = false;
let storageListener = null;

function findVideo() {
  return document.querySelector("video");
}

function pauseVideo() {
  const tryPause = (attempt) => {
    const video = findVideo();
    if (video) {
      // pausedByBot только если реально остановили играющее видео;
      // ручную паузу стримера не перехватываем (не форсим play потом).
      if (!video.paused) {
        video.pause();
        pausedByBot = true;
      }
      return;
    }
    if (attempt < VIDEO_RETRY_MAX) {
      setTimeout(() => tryPause(attempt + 1), VIDEO_RETRY_MS);
    }
  };
  tryPause(0);
}

function resumeVideo() {
  if (!pausedByBot) return;
  const video = findVideo();
  pausedByBot = false;
  if (!video) return;
  const p = video.play();
  if (p && typeof p.catch === "function") {
    p.catch(() => {});
  }
}

function applyPlaying(playing) {
  if (playing) {
    pauseVideo();
  } else {
    resumeVideo();
  }
}

function handleMessage(data) {
  if (!data || typeof data !== "object") return;
  const action = data.action;
  if (action === "play") {
    pauseVideo();
    return;
  }
  if (action === "queue_state") {
    applyPlaying(Boolean(data.playing));
    return;
  }
  // skip / toggle_pause / overlays — игнор
}

function reportWsState(state) {
  try {
    chrome.runtime.sendMessage({ type: "ws_state", state }).catch(() => {});
  } catch (_) {
    /* extension context invalidated */
  }
}

function clearReconnect() {
  if (reconnectTimer != null) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

function scheduleReconnect() {
  if (!active) return;
  clearReconnect();
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWs();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
  reportWsState("reconnecting");
}

async function readConfig() {
  const data = await chrome.storage.local.get({
    wsHost: DEFAULT_HOST,
    wsPort: DEFAULT_PORT,
  });
  const host = String(data.wsHost || DEFAULT_HOST).trim() || DEFAULT_HOST;
  let port = parseInt(String(data.wsPort), 10);
  if (!Number.isFinite(port) || port < 1 || port > 65535) {
    port = DEFAULT_PORT;
  }
  return { host, port };
}

function closeWs() {
  clearReconnect();
  if (ws) {
    try {
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.close();
    } catch (_) {
      /* ignore */
    }
    ws = null;
  }
}

async function connectWs() {
  if (!active) return;
  closeWs();
  reportWsState("reconnecting");

  let host;
  let port;
  try {
    ({ host, port } = await readConfig());
  } catch (_) {
    scheduleReconnect();
    return;
  }

  const url = `ws://${host}:${port}${WS_PATH}`;
  let socket;
  try {
    socket = new WebSocket(url);
  } catch (_) {
    scheduleReconnect();
    return;
  }
  ws = socket;

  socket.onopen = () => {
    reconnectDelay = RECONNECT_MIN_MS;
    reportWsState("connected");
    try {
      socket.send(JSON.stringify({ status: "ready", overlay: "bed" }));
    } catch (_) {
      /* ignore */
    }
  };

  socket.onmessage = (ev) => {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch (_) {
      return;
    }
    handleMessage(data);
  };

  socket.onerror = () => {
    /* onclose follow-up */
  };

  socket.onclose = () => {
    if (ws === socket) ws = null;
    if (active) scheduleReconnect();
    else reportWsState("off");
  };
}

function activate() {
  if (active) return;
  active = true;
  reconnectDelay = RECONNECT_MIN_MS;
  if (!storageListener) {
    storageListener = (changes, area) => {
      if (area !== "local") return;
      if (changes.wsHost || changes.wsPort) {
        if (active) connectWs();
      }
    };
    chrome.storage.onChanged.addListener(storageListener);
  }
  connectWs();
}

function deactivate() {
  active = false;
  clearReconnect();
  closeWs();
  // Не resume при deactivate — стример сам управляет вкладкой.
  pausedByBot = false;
  reportWsState("off");
  if (storageListener) {
    chrome.storage.onChanged.removeListener(storageListener);
    storageListener = null;
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;
  if (msg.type === "activate") {
    activate();
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "deactivate") {
    deactivate();
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "ping") {
    sendResponse({ ok: true, active });
    return true;
  }
});

// Если background уже пометил эту вкладку bed до inject — синхронизируемся.
chrome.runtime.sendMessage({ type: "content_hello" }).then((resp) => {
  if (resp && resp.shouldActivate) activate();
}).catch(() => {});
