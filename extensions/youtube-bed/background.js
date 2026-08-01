"use strict";

/**
 * Service worker: клик иконки = activate/deactivate bed-вкладки,
 * badge, очистка при закрытии / уходе с YouTube.
 */

const YT_HOST_RE = /^(?:www\.|m\.)?youtube\.com$|^music\.youtube\.com$/i;

let bedTabId = null;
/** @type {"off"|"connected"|"reconnecting"} */
let wsState = "off";

function isYoutubeUrl(url) {
  if (!url) return false;
  try {
    const u = new URL(url);
    return YT_HOST_RE.test(u.hostname);
  } catch (_) {
    return false;
  }
}

async function setBadge() {
  if (bedTabId == null) {
    await chrome.action.setBadgeText({ text: "" });
    await chrome.action.setTitle({
      title: "YouTube Bed: активировать эту вкладку",
    });
    return;
  }
  if (wsState === "connected") {
    await chrome.action.setBadgeBackgroundColor({ color: "#4caf50" });
    await chrome.action.setBadgeText({ text: "ON" });
    await chrome.action.setTitle({
      title: "YouTube Bed: активен (клик — снять)",
    });
    return;
  }
  if (wsState === "reconnecting") {
    await chrome.action.setBadgeBackgroundColor({ color: "#f0a500" });
    await chrome.action.setBadgeText({ text: "…" });
    await chrome.action.setTitle({
      title: "YouTube Bed: переподключение к боту…",
    });
    return;
  }
  await chrome.action.setBadgeBackgroundColor({ color: "#888" });
  await chrome.action.setBadgeText({ text: "ON" });
  await chrome.action.setTitle({
    title: "YouTube Bed: вкладка выбрана, WS выкл",
  });
}

async function clearBed(reason) {
  const prev = bedTabId;
  bedTabId = null;
  wsState = "off";
  if (prev != null) {
    try {
      await chrome.tabs.sendMessage(prev, { type: "deactivate" });
    } catch (_) {
      /* вкладка уже закрыта / нет content script */
    }
  }
  await setBadge();
  if (reason) {
    console.debug("[youtube-bed] cleared:", reason);
  }
}

async function sendActivate(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "activate" });
    return true;
  } catch (_) {
    return false;
  }
}

async function activateTab(tab) {
  if (!tab || tab.id == null) return;
  if (!isYoutubeUrl(tab.url)) {
    await chrome.action.setTitle({
      title: "YouTube Bed: откройте вкладку YouTube / Music",
    });
    return;
  }

  if (bedTabId === tab.id) {
    await clearBed("toggle-off");
    return;
  }

  if (bedTabId != null && bedTabId !== tab.id) {
    const prev = bedTabId;
    bedTabId = null;
    try {
      await chrome.tabs.sendMessage(prev, { type: "deactivate" });
    } catch (_) {
      /* ignore */
    }
  }

  bedTabId = tab.id;
  wsState = "reconnecting";
  await setBadge();

  const ok = await sendActivate(tab.id);
  if (!ok) {
    // Content script ещё не загружен (только что открыли вкладку) — подождём hello.
    console.debug("[youtube-bed] activate pending content_hello");
  }
}

chrome.action.onClicked.addListener((tab) => {
  activateTab(tab).catch((err) => console.warn("[youtube-bed]", err));
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === bedTabId) {
    bedTabId = null;
    wsState = "off";
    setBadge();
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (tabId !== bedTabId) return;
  if (changeInfo.url != null && !isYoutubeUrl(changeInfo.url)) {
    clearBed("left-youtube");
    return;
  }
  if (changeInfo.status === "complete" && isYoutubeUrl(tab.url)) {
    // SPA / reload — content script новый, нужно снова activate.
    sendActivate(tabId).then((ok) => {
      if (ok) wsState = wsState === "connected" ? "connected" : "reconnecting";
      setBadge();
    });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return;

  if (msg.type === "content_hello") {
    const tabId = sender.tab && sender.tab.id;
    const should = tabId != null && tabId === bedTabId;
    sendResponse({ shouldActivate: should });
    if (should) {
      wsState = "reconnecting";
      setBadge();
    }
    return true;
  }

  if (msg.type === "ws_state") {
    if (sender.tab && sender.tab.id === bedTabId) {
      wsState = msg.state === "connected"
        ? "connected"
        : msg.state === "reconnecting"
          ? "reconnecting"
          : "off";
      setBadge();
    }
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "config_updated") {
    // Content сам переподключится через storage.onChanged;
    // если bed активен — подтолкнём reconnect.
    if (bedTabId != null) {
      chrome.tabs.sendMessage(bedTabId, { type: "activate" }).catch(() => {});
    }
    sendResponse({ ok: true });
    return true;
  }
});

setBadge();
