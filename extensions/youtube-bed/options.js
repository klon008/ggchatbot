"use strict";

const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 8765;

const hostEl = document.getElementById("host");
const portEl = document.getElementById("port");
const statusEl = document.getElementById("status");
const saveBtn = document.getElementById("save");

function showStatus(text) {
  statusEl.textContent = text;
}

async function load() {
  const data = await chrome.storage.local.get({
    wsHost: DEFAULT_HOST,
    wsPort: DEFAULT_PORT,
  });
  hostEl.value = String(data.wsHost || DEFAULT_HOST);
  portEl.value = String(data.wsPort || DEFAULT_PORT);
}

async function save() {
  const host = (hostEl.value || "").trim() || DEFAULT_HOST;
  let port = parseInt(String(portEl.value).trim(), 10);
  if (!Number.isFinite(port) || port < 1 || port > 65535) {
    showStatus("Порт: число 1–65535");
    return;
  }
  await chrome.storage.local.set({ wsHost: host, wsPort: port });
  hostEl.value = host;
  portEl.value = String(port);
  showStatus("Сохранено");
  chrome.runtime.sendMessage({ type: "config_updated" }).catch(() => {});
}

saveBtn.addEventListener("click", () => {
  save().catch((err) => showStatus(String(err)));
});

load().catch((err) => showStatus(String(err)));
