/**
 * OBS Browser Source — анимация открытия бустера.
 *
 * URL: http://127.0.0.1:PORT/booster.html  (~384×560)
 * Debug: ?debug=1
 *
 * Python -> overlay: {action:"booster_open", openingId, animSpeed, cards:[...]}
 * overlay -> Python: {status:"ready", overlay:"booster"}
 *                    {status:"booster_done", openingId}
 *
 * animSpeed: 1.0 = норма, больше = быстрее (длительности / speed).
 */
import { mountCardTemplate } from "/card-templates/fill-card.js";

const WS_PATH = "/ws";
const BASE = {
  enter: 520,
  preFlip: 320,
  flip: 1250,
  holdNew: 750,
  holdDup: 520,
  exit: 480,
  shatter: 850,
  gap: 280,
  afterShatter: 280,
  stageIn: 200,
  stageOut: 280,
};
const SHATTER_GRID = 9;
const SPEED_MIN = 0.5;
const SPEED_MAX = 3;

const stage = document.getElementById("stage");
const scene = document.getElementById("scene");
const cardSlot = document.getElementById("cardSlot");
const card3d = document.getElementById("card3d");
const cardBackImg = document.getElementById("cardBackImg");
const frontHost = document.getElementById("frontHost");
const userLabel = document.getElementById("userLabel");
const fxOverlay = document.getElementById("fxOverlay");
const refundPop = document.getElementById("refundPop");
const shatterLayer = document.getElementById("shatterLayer");
const debugPanel = document.getElementById("debugPanel");

let ws = null;
let wsReconnectDelay = 1000;
/** @type {object[]} */
const queue = [];
let busy = false;
/** @type {typeof BASE} */
let t = { ...BASE };
const isDebug = parseDebugMode();

if (isDebug) {
  document.body.classList.add("debug-mode");
}

function parseDebugMode() {
  try {
    const params = new URLSearchParams(location.search);
    const v = (params.get("debug") || "").toLowerCase();
    return v === "1" || v === "true" || v === "yes";
  } catch {
    return false;
  }
}

function clampSpeed(raw) {
  const n = Number(raw);
  if (!Number.isFinite(n)) return 1;
  return Math.max(SPEED_MIN, Math.min(SPEED_MAX, n));
}

function applySpeed(speed) {
  const s = clampSpeed(speed);
  const scaled = {};
  for (const key of Object.keys(BASE)) {
    scaled[key] = Math.max(1, Math.round(BASE[key] / s));
  }
  t = scaled;
  const root = document.documentElement;
  root.style.setProperty("--enter-ms", `${t.enter}ms`);
  root.style.setProperty("--enter-opacity-ms", `${Math.round(t.enter * 0.75)}ms`);
  root.style.setProperty("--exit-ms", `${t.exit}ms`);
  root.style.setProperty("--exit-opacity-ms", `${Math.round(t.exit * 0.85)}ms`);
  root.style.setProperty("--flip-ms", `${t.flip}ms`);
  root.style.setProperty("--shatter-ms", `${Math.round(t.shatter * 0.96)}ms`);
  root.style.setProperty(
    "--shatter-opacity-ms",
    `${Math.round(t.shatter * 0.88)}ms`
  );
  log(`animSpeed=${s} flip=${t.flip}ms`);
  return s;
}

function log(msg) {
  if (!isDebug || !debugPanel) return;
  const line = document.createElement("div");
  line.textContent = `${new Date().toLocaleTimeString()} ${msg}`;
  debugPanel.prepend(line);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }
}

async function fetchMetaSpeed() {
  try {
    const res = await fetch("/api/cards/meta");
    if (!res.ok) return 1;
    const meta = await res.json();
    return clampSpeed(meta.anim_speed);
  } catch {
    return 1;
  }
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}${WS_PATH}`;
  log(`ws connect ${url}`);
  ws = new WebSocket(url);
  ws.onopen = () => {
    wsReconnectDelay = 1000;
    send({ status: "ready", overlay: "booster", debug: isDebug });
    log("ws open");
  };
  ws.onclose = () => {
    log("ws close, reconnect…");
    setTimeout(connectWs, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 1.6, 10000);
  };
  ws.onerror = () => log("ws error");
  ws.onmessage = (ev) => {
    let data;
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!data || data.action !== "booster_open") return;
    log(`booster_open ${data.openingId} N=${(data.cards || []).length}`);
    queue.push(data);
    pump();
  };
}

function showStage(label) {
  userLabel.textContent = label || "";
  stage.classList.add("is-visible");
}

function hideStage() {
  stage.classList.remove("is-visible");
}

function resetCardUi() {
  cardSlot.classList.remove("is-enter", "is-exit-down", "is-hidden");
  cardSlot.style.transition = "none";
  cardSlot.style.transform = "";
  cardSlot.style.opacity = "";
  card3d.classList.remove("is-face");
  card3d.style.visibility = "";
  scene.classList.remove("is-new-glow");
  fxOverlay.classList.remove("is-on");
  refundPop.classList.remove("is-on");
  refundPop.textContent = "";
  shatterLayer.innerHTML = "";
  frontHost.innerHTML = "";
  void cardSlot.offsetWidth;
  cardSlot.style.transition = "";
}

async function frontToDataUrl() {
  const svg = frontHost.querySelector("svg");
  if (!svg) return null;
  const clone = svg.cloneNode(true);
  if (!clone.getAttribute("xmlns")) {
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  }
  if (!clone.getAttribute("xmlns:xlink")) {
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  }
  const vb = clone.viewBox && clone.viewBox.baseVal;
  const w = (vb && vb.width) || 350;
  const h = (vb && vb.height) || 490;
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));

  const xml = new XMLSerializer().serializeToString(clone);
  const svgUrl =
    "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  const img = new Image();
  img.decoding = "async";
  img.src = svgUrl;
  try {
    await img.decode();
  } catch {
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = reject;
    });
  }
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return svgUrl;
  ctx.drawImage(img, 0, 0, w, h);
  try {
    return canvas.toDataURL("image/png");
  } catch {
    return svgUrl;
  }
}

async function runShatter() {
  shatterLayer.innerHTML = "";
  const cols = SHATTER_GRID;
  const rows = SHATTER_GRID;
  const dataUrl = await frontToDataUrl();
  if (!dataUrl) return;

  const cellW = 100 / cols;
  const cellH = 100 / rows;
  const mid = (cols - 1) / 2;

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const shard = document.createElement("div");
      shard.className = "shard";
      shard.style.left = `${col * cellW}%`;
      shard.style.top = `${row * cellH}%`;
      shard.style.width = `${cellW}%`;
      shard.style.height = `${cellH}%`;
      shard.style.backgroundImage = `url("${dataUrl}")`;
      shard.style.backgroundSize = `${cols * 100}% ${rows * 100}%`;
      const bx = cols === 1 ? 0 : (col / (cols - 1)) * 100;
      const by = rows === 1 ? 0 : (row / (rows - 1)) * 100;
      shard.style.backgroundPosition = `${bx}% ${by}%`;
      shatterLayer.appendChild(shard);
    }
  }

  card3d.style.visibility = "hidden";
  fxOverlay.classList.remove("is-on");

  void shatterLayer.offsetWidth;

  const shards = shatterLayer.querySelectorAll(".shard");
  shards.forEach((shard, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const dx = (col - mid) * (14 + Math.random() * 22);
    const dy = (row - mid) * (16 + Math.random() * 26) + 36;
    const rot = (Math.random() - 0.5) * 70;
    const sc = 0.45 + Math.random() * 0.4;
    shard.style.transform =
      `translate(${dx}px, ${dy}px) rotate(${rot}deg) scale(${sc})`;
    shard.classList.add("is-fly");
  });

  await sleep(t.shatter);
  shatterLayer.innerHTML = "";
}

async function revealCard(card) {
  resetCardUi();

  cardBackImg.src = card.cardBackUrl || "/assets/cards/card-back.svg";
  const rarity = card.rarity || "common";
  await mountCardTemplate(frontHost, rarity, {
    name: card.name || "",
    portraitUrl: card.imageUrl || "",
  });

  void cardSlot.offsetWidth;
  cardSlot.classList.add("is-enter");
  await sleep(t.enter + t.preFlip);

  card3d.classList.add("is-face");
  await sleep(t.flip);

  if (card.isDuplicate) {
    fxOverlay.classList.add("is-on");
    if (card.refund > 0) {
      refundPop.textContent = `+${card.refund}`;
      refundPop.classList.add("is-on");
    }
    await sleep(t.holdDup);
    await runShatter();
    await sleep(t.afterShatter);
  } else {
    scene.classList.add("is-new-glow");
    await sleep(t.holdNew);
    cardSlot.classList.add("is-exit-down");
    await sleep(t.exit);
  }
}

async function playOpening(payload) {
  applySpeed(payload.animSpeed != null ? payload.animSpeed : 1);
  const cards = Array.isArray(payload.cards) ? payload.cards : [];
  const label = payload.userName
    ? `${payload.userName} · ${payload.boosterName || "бустер"}`
    : payload.boosterName || "";
  showStage(label);
  await sleep(t.stageIn);

  for (let i = 0; i < cards.length; i++) {
    await revealCard(cards[i]);
    if (i < cards.length - 1) {
      resetCardUi();
      await sleep(t.gap);
    }
  }

  await sleep(t.stageOut);
  hideStage();
  resetCardUi();
  send({ status: "booster_done", openingId: payload.openingId });
  log(`booster_done ${payload.openingId}`);
}

async function pump() {
  if (busy) return;
  busy = true;
  try {
    while (queue.length) {
      const job = queue.shift();
      try {
        await playOpening(job);
      } catch (err) {
        log(`play error: ${err && err.message ? err.message : err}`);
        send({ status: "booster_done", openingId: job.openingId });
        hideStage();
        resetCardUi();
      }
    }
  } finally {
    busy = false;
  }
}

applySpeed(1);
connectWs();

if (isDebug) {
  (async () => {
    const speed = await fetchMetaSpeed();
    setTimeout(() => {
      queue.push({
        openingId: "debug-fixture",
        userName: "debug_user",
        boosterName: "Читерный бустер",
        drawName: "Летний2",
        costPoints: 1000,
        animSpeed: speed,
        cards: [
          {
            id: "elsa",
            name: "Эльза",
            rarity: "mythic",
            isDuplicate: false,
            refund: 0,
            imageUrl: "/assets/cards/elsa.webp",
            cardBackUrl: "/assets/cards/card-back.svg",
          },
          {
            id: "elsa",
            name: "Эльза",
            rarity: "mythic",
            isDuplicate: true,
            refund: 42,
            imageUrl: "/assets/cards/elsa.webp",
            cardBackUrl: "/assets/cards/card-back.svg",
          },
        ],
      });
      pump();
    }, 400);
  })();
}
