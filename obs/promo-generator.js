/**
 * Promo JPG generator — 3D table of booster pool cards.
 * URL: /promo-generator.html?booster=<id>
 */
import { mountCardTemplate } from "/card-templates/fill-card.js";

const RARITY_RANK = {
  secretRare: 0,
  mythic: 1,
  legendary: 2,
  epic: 3,
  rare: 4,
  uncommon: 5,
  common: 6,
};

const DEFAULT_FACE_UP = 6;

/** @type {Map<string, object>} */
const catalogById = new Map();
/** @type {Map<string, string>} */
const seriesBackById = new Map();

let booster = null;
/** @type {object[]} */
let poolCards = [];
/** @type {Set<string>} */
const faceUpIds = new Set();
let renderToken = 0;
let previewScale = 1;

const els = {
  boosterTitle: document.getElementById("boosterTitle"),
  boosterSub: document.getElementById("boosterSub"),
  loadError: document.getElementById("loadError"),
  faceList: document.getElementById("faceList"),
  backsCount: document.getElementById("backsCount"),
  backsCountVal: document.getElementById("backsCountVal"),
  layout: document.getElementById("layout"),
  tilt: document.getElementById("tilt"),
  tiltVal: document.getElementById("tiltVal"),
  spin: document.getElementById("spin"),
  spinVal: document.getElementById("spinVal"),
  cardScale: document.getElementById("cardScale"),
  cardScaleVal: document.getElementById("cardScaleVal"),
  overlap: document.getElementById("overlap"),
  overlapVal: document.getElementById("overlapVal"),
  seed: document.getElementById("seed"),
  frameSize: document.getElementById("frameSize"),
  showTitle: document.getElementById("showTitle"),
  bgWhite: document.getElementById("bgWhite"),
  tableWhite: document.getElementById("tableWhite"),
  titleOverlay: document.getElementById("titleOverlay"),
  overlayName: document.getElementById("overlayName"),
  overlayPool: document.getElementById("overlayPool"),
  exportRoot: document.getElementById("exportRoot"),
  tableSurface: document.getElementById("tableSurface"),
  tableFelt: document.querySelector(".table-felt"),
  cardsLayer: document.getElementById("cardsLayer"),
  stageFrame: document.getElementById("stageFrame"),
  stageMeta: document.getElementById("stageMeta"),
  statusLine: document.getElementById("statusLine"),
  btnDownload: document.getElementById("btnDownload"),
  btnDownloadCutout: document.getElementById("btnDownloadCutout"),
  btnSelectTop: document.getElementById("btnSelectTop"),
  btnSelectNone: document.getElementById("btnSelectNone"),
  btnSelectAll: document.getElementById("btnSelectAll"),
  btnReseed: document.getElementById("btnReseed"),
};

function boosterIdFromUrl() {
  const p = new URLSearchParams(location.search);
  return (p.get("booster") || p.get("buster") || "").trim();
}

function mulberry32(seed) {
  let a = seed >>> 0;
  return function rand() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function setStatus(text, kind) {
  els.statusLine.textContent = text;
  els.statusLine.className = kind === "err" ? "err" : kind === "ok" ? "ok" : "hint";
}

function portraitUrl(card) {
  return card.image_url || `/assets/cards/${card.id}.webp`;
}

function backUrlForCard(card) {
  const backId = seriesBackById.get(card.series_id) || "card-back";
  return `/assets/cards/${backId}.svg`;
}

function sortPool(cards) {
  return [...cards].sort((a, b) => {
    const ra = RARITY_RANK[a.rarity] ?? 99;
    const rb = RARITY_RANK[b.rarity] ?? 99;
    if (ra !== rb) return ra - rb;
    return (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.name.localeCompare(b.name, "ru");
  });
}

function pickDefaultFaceUp(cards) {
  faceUpIds.clear();
  const sorted = sortPool(cards);
  for (const c of sorted.slice(0, Math.min(DEFAULT_FACE_UP, sorted.length))) {
    faceUpIds.add(c.id);
  }
}

function syncRangeLabels() {
  els.backsCountVal.textContent = String(els.backsCount.value);
  els.tiltVal.textContent = `${els.tilt.value}°`;
  els.spinVal.textContent = `${els.spin.value}°`;
  els.cardScaleVal.textContent = String(els.cardScale.value);
  els.overlapVal.textContent = `${els.overlap.value}%`;
}

function applyCameraCss() {
  const tiltDeg = Number(els.tilt.value) || 0;
  document.documentElement.style.setProperty("--tilt", `${tiltDeg}deg`);
  document.documentElement.style.setProperty("--spin", `${els.spin.value}deg`);
  document.documentElement.style.setProperty("--card-w", `${els.cardScale.value}px`);
  // 2D-форешортенинг для экспорта (cos наклона)
  const flat = Math.max(0.35, Math.cos((tiltDeg * Math.PI) / 180));
  document.documentElement.style.setProperty("--tilt-flat", String(Number(flat.toFixed(3))));
}

/**
 * Убираем 3D/filter/translateZ — html2canvas иначе рисует «аномалии» на столе.
 */
function flattenSceneForExport() {
  els.exportRoot.classList.add("is-export-flat");
  if (els.tableFelt && !els.tableFelt.classList.contains("is-hidden")) {
    // На всякий случай убиваем translateZ и сложный background inline
    els.tableFelt.style.transform = "none";
    if (!els.tableFelt.classList.contains("is-white")) {
      els.tableFelt.style.background = "#152032";
      els.tableFelt.style.backgroundImage = "none";
    } else {
      els.tableFelt.style.background = "#ffffff";
      els.tableFelt.style.backgroundImage = "none";
    }
  }
  if (els.tableSurface) {
    els.tableSurface.style.transformStyle = "flat";
  }
  const viewport = els.exportRoot.querySelector(".table-viewport");
  if (viewport) viewport.style.perspective = "none";
}

function applySceneChrome() {
  els.exportRoot.classList.toggle("is-bg-white", Boolean(els.bgWhite?.checked));
  els.exportRoot.classList.remove("is-cutout");
  if (els.tableFelt) {
    els.tableFelt.classList.toggle("is-white", Boolean(els.tableWhite?.checked));
    els.tableFelt.classList.remove("is-hidden");
  }
}

function applyFrameSize() {
  const size = els.frameSize.value;
  els.exportRoot.dataset.size = size;
  fitPreview();
}

function fitPreview() {
  const frame = els.stageFrame;
  const root = els.exportRoot;
  const pad = 24;
  const availW = Math.max(200, frame.clientWidth - pad);
  const availH = Math.max(200, frame.clientHeight - pad);
  const w = root.offsetWidth || 1920;
  const h = root.offsetHeight || 1080;
  previewScale = Math.min(1, availW / w, availH / h);
  root.style.transform = `scale(${previewScale})`;
  els.stageMeta.textContent = `${w}×${h} · масштаб ${Math.round(previewScale * 100)}% · лицом ${faceUpIds.size} · рубашек ${els.backsCount.value}`;
}

function renderFaceList() {
  const sorted = sortPool(poolCards);
  els.faceList.innerHTML = sorted
    .map((c) => {
      const checked = faceUpIds.has(c.id) ? "checked" : "";
      return `<label class="face-item">
        <input type="checkbox" data-id="${escapeAttr(c.id)}" ${checked} />
        <img src="${escapeAttr(portraitUrl(c))}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />
        <span>${escapeHtml(c.name)}<br/><span class="rarity">${escapeHtml(c.rarity)}</span></span>
      </label>`;
    })
    .join("");

  els.faceList.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.addEventListener("change", () => {
      const id = input.getAttribute("data-id");
      if (!id) return;
      if (input.checked) faceUpIds.add(id);
      else faceUpIds.delete(id);
      scheduleRender();
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(s) {
  return escapeHtml(s).replace(/'/g, "&#39;");
}

/**
 * Layout cards into positions relative to table center.
 * @returns {{ kind: 'face'|'back', card?: object, x: number, y: number, rot: number, z: number }[]}
 */
function computeLayout(faces, backsCount, layout, seed, overlapPct) {
  const rand = mulberry32(Number(seed) || 0);
  const items = [];
  const total = faces.length + backsCount;
  if (total === 0) return items;

  const squeeze = 1 - Number(overlapPct) / 200; // 0.5..1
  const cardW = Number(els.cardScale.value);
  const cardH = cardW * 1.4;

  // Backs first (under), then faces on top
  for (let i = 0; i < backsCount; i++) {
    items.push({ kind: "back", i });
  }
  for (const card of faces) {
    items.push({ kind: "face", card });
  }

  const placed = [];
  if (layout === "row") {
    const n = items.length;
    const span = Math.min(920, n * cardW * 0.72 * squeeze + 40);
    items.forEach((it, idx) => {
      const t = n === 1 ? 0.5 : idx / (n - 1);
      placed.push({
        ...it,
        x: (t - 0.5) * span,
        y: (rand() - 0.5) * 18,
        rot: (rand() - 0.5) * 8,
        z: idx,
      });
    });
  } else if (layout === "arc" || layout === "fan") {
    const n = items.length;
    const spread = layout === "fan" ? 70 : 110;
    const radius = layout === "fan" ? 220 * squeeze + 80 : 340 * squeeze + 60;
    items.forEach((it, idx) => {
      const t = n === 1 ? 0.5 : idx / (n - 1);
      const ang = ((t - 0.5) * spread * Math.PI) / 180;
      placed.push({
        ...it,
        x: Math.sin(ang) * radius,
        y: -Math.cos(ang) * radius * 0.35 + radius * 0.2,
        rot: (t - 0.5) * spread * 0.85,
        z: idx,
      });
    });
  } else {
    // heap
    items.forEach((it, idx) => {
      const angle = rand() * Math.PI * 2;
      const radius = Math.sqrt(rand()) * (220 + faces.length * 12) * squeeze;
      placed.push({
        ...it,
        x: Math.cos(angle) * radius * 1.35,
        y: Math.sin(angle) * radius * 0.75,
        rot: (rand() - 0.5) * 50,
        z: idx,
      });
    });
  }

  // Keep faces roughly toward viewer / center bias for backs
  return placed.map((p) => ({
    ...p,
    x: Math.max(-900, Math.min(900, p.x)),
    y: Math.max(-420, Math.min(420, p.y)),
  }));
}

function makeSlotEl(pos) {
  const slot = document.createElement("div");
  slot.className = "card-slot";
  slot.style.setProperty("--tx", `${pos.x}px`);
  slot.style.setProperty("--ty", `${pos.y}px`);
  slot.style.setProperty("--tz", `${pos.z}px`);
  slot.style.setProperty("--rot", `${pos.rot}deg`);
  slot.style.zIndex = String(10 + pos.z);

  const card3d = document.createElement("div");
  card3d.className = `card3d${pos.kind === "face" ? " is-face" : ""}`;

  const front = document.createElement("div");
  front.className = "face face-front";
  const frontHost = document.createElement("div");
  frontHost.className = "front-host";
  front.appendChild(frontHost);

  const back = document.createElement("div");
  back.className = "face face-back";
  const backImg = document.createElement("img");
  backImg.alt = "";
  backImg.decoding = "async";

  const sample = pos.card || poolCards[0];
  backImg.src = sample ? backUrlForCard(sample) : "/assets/cards/card-back.svg";
  back.appendChild(backImg);

  card3d.appendChild(front);
  card3d.appendChild(back);
  slot.appendChild(card3d);

  return { slot, frontHost, card: pos.card, kind: pos.kind };
}

async function renderScene() {
  const token = ++renderToken;
  applyCameraCss();
  applyFrameSize();
  applySceneChrome();

  const showTitle = els.showTitle.checked;
  els.titleOverlay.classList.toggle("hidden", !showTitle);
  if (booster) {
    els.overlayName.textContent = booster.name || booster.id;
    const seriesNames = [
      ...new Set(poolCards.map((c) => c.series_name).filter(Boolean)),
    ];
    const seriesPart = seriesNames.length
      ? seriesNames.join(" · ")
      : "бустер";
    els.overlayPool.textContent = `${seriesPart} · ${poolCards.length} карт в пуле`;
  }

  const faces = sortPool(poolCards.filter((c) => faceUpIds.has(c.id)));
  let backs = Number(els.backsCount.value) || 0;
  if (backs > 40) backs = 40;

  const layout = computeLayout(
    faces,
    backs,
    els.layout.value,
    els.seed.value,
    els.overlap.value
  );

  els.cardsLayer.innerHTML = "";
  const mounts = [];
  for (const pos of layout) {
    const built = makeSlotEl(pos);
    els.cardsLayer.appendChild(built.slot);
    if (built.kind === "face" && built.card) {
      mounts.push(
        mountCardTemplate(built.frontHost, built.card.rarity || "common", {
          name: built.card.name || "",
          portraitUrl: portraitUrl(built.card),
        }).catch((err) => {
          console.warn("card template", built.card.id, err);
        })
      );
    }
  }

  await Promise.all(mounts);
  if (token !== renderToken) return;

  fitPreview();
  setStatus(
    `Сцена: ${faces.length} лицом · ${backs} рубашкой · layout «${els.layout.value}»`,
    "ok"
  );
}

let renderTimer = null;
function scheduleRender() {
  syncRangeLabels();
  fitPreview();
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    renderScene().catch((e) => {
      console.error(e);
      setStatus(String(e.message || e), "err");
    });
  }, 80);
}

async function svgHostToPngDataUrl(host, w, h) {
  const svg = host.querySelector("svg");
  if (!svg) return null;
  const clone = svg.cloneNode(true);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  if (!clone.getAttribute("width")) clone.setAttribute("width", String(w));
  if (!clone.getAttribute("height")) clone.setAttribute("height", String(h));
  // Inline portrait as data URL so html2canvas / drawImage see pixels
  const imgEl = clone.querySelector('[data-slot="portrait"]');
  if (imgEl) {
    const href =
      imgEl.getAttribute("href") ||
      imgEl.getAttributeNS("http://www.w3.org/1999/xlink", "href") ||
      "";
    if (href && !href.startsWith("data:")) {
      try {
        const abs = new URL(href, location.origin).href;
        const res = await fetch(abs);
        const blob = await res.blob();
        const dataUrl = await new Promise((resolve, reject) => {
          const fr = new FileReader();
          fr.onload = () => resolve(fr.result);
          fr.onerror = reject;
          fr.readAsDataURL(blob);
        });
        imgEl.setAttribute("href", dataUrl);
        imgEl.setAttributeNS("http://www.w3.org/1999/xlink", "href", dataUrl);
      } catch (e) {
        console.warn("portrait inline failed", e);
      }
    }
  }
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
  if (!ctx) return null;
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/png");
}

async function loadImageDataUrl(src, w, h) {
  if (!src) return null;
  let dataUrl = src;
  if (!src.startsWith("data:")) {
    const abs = new URL(src, location.origin).href;
    const res = await fetch(abs);
    const blob = await res.blob();
    dataUrl = await new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => resolve(fr.result);
      fr.onerror = reject;
      fr.readAsDataURL(blob);
    });
  }
  const bitmap = new Image();
  bitmap.src = dataUrl;
  try {
    await bitmap.decode();
  } catch {
    await new Promise((resolve, reject) => {
      bitmap.onload = resolve;
      bitmap.onerror = reject;
    });
  }
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const ctx = c.getContext("2d");
  if (!ctx) return dataUrl;
  ctx.drawImage(bitmap, 0, 0, w, h);
  return c.toDataURL("image/png");
}

/**
 * html2canvas не умеет CSS 3D (rotateY + backface-visibility) —
 * оставляет только видимую сторону как плоский &lt;img&gt;.
 */
async function flattenCardsForExport() {
  const cardW = Number(els.cardScale.value) || 148;
  const cardH = Math.round(cardW * 1.4);
  const pxW = cardW * 2;
  const pxH = cardH * 2;
  const slots = [...els.cardsLayer.querySelectorAll(".card-slot")];

  await Promise.all(
    slots.map(async (slot) => {
      const card3d = slot.querySelector(".card3d");
      if (!card3d) return;
      const isFace = card3d.classList.contains("is-face");
      let dataUrl = null;

      if (isFace) {
        const host = card3d.querySelector(".front-host");
        if (host?.querySelector("svg")) {
          dataUrl = await svgHostToPngDataUrl(host, pxW, pxH);
        } else {
          const img = host?.querySelector("img");
          if (img?.src) dataUrl = await loadImageDataUrl(img.src, pxW, pxH);
        }
      } else {
        const backImg = card3d.querySelector(".face-back img");
        if (backImg?.src) dataUrl = await loadImageDataUrl(backImg.src, pxW, pxH);
      }

      if (!dataUrl) return;

      // Плоская карта — без preserve-3d / rotateY
      card3d.className = "card3d is-flat-export";
      card3d.style.transform = "none";
      card3d.innerHTML = "";
      const img = document.createElement("img");
      img.src = dataUrl;
      img.alt = "";
      img.decoding = "async";
      img.style.display = "block";
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "contain";
      img.style.borderRadius = "10px";
      card3d.appendChild(img);
    })
  );
}

/**
 * @param {{ format: 'jpeg'|'png', cutout?: boolean }} opts
 */
async function downloadScene(opts) {
  const format = opts.format || "jpeg";
  const cutout = Boolean(opts.cutout);
  if (typeof html2canvas !== "function") {
    setStatus("html2canvas не загрузился — сделайте скриншот Win+Shift+S", "err");
    return;
  }
  const btns = [els.btnDownload, els.btnDownloadCutout].filter(Boolean);
  btns.forEach((b) => {
    b.disabled = true;
  });
  setStatus(
    cutout
      ? "Вырезаю карты без стола и фона (PNG)…"
      : `Подготовка карт и рендер ${format.toUpperCase()}…`,
    ""
  );
  const root = els.exportRoot;
  const prevTransform = root.style.transform;
  const titleWasHidden = els.titleOverlay.classList.contains("hidden");
  root.style.transform = "none";
  try {
    if (cutout) {
      root.classList.add("is-cutout");
      root.classList.remove("is-bg-white");
      if (els.tableFelt) els.tableFelt.classList.add("is-hidden");
      els.titleOverlay.classList.add("hidden");
    } else {
      applySceneChrome();
    }

    await flattenCardsForExport();
    flattenSceneForExport();
    // Дать браузеру применить стили до съёмки
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

    let bgColor;
    if (cutout) bgColor = null;
    else if (els.bgWhite?.checked) bgColor = "#ffffff";
    else bgColor = "#080a10";

    const canvas = await html2canvas(root, {
      backgroundColor: bgColor,
      scale: 1,
      useCORS: true,
      allowTaint: true,
      logging: false,
      width: root.offsetWidth,
      height: root.offsetHeight,
      windowWidth: root.offsetWidth,
      windowHeight: root.offsetHeight,
      ignoreElements: (el) => el.classList?.contains?.("html2canvas-ignore"),
    });

    const mime = format === "png" ? "image/png" : "image/jpeg";
    const quality = format === "png" ? undefined : 0.92;
    const blob = await new Promise((resolve) =>
      canvas.toBlob((b) => resolve(b), mime, quality)
    );
    if (!blob) throw new Error(`Не удалось создать ${format.toUpperCase()}`);
    const a = document.createElement("a");
    const id = booster?.id || "booster";
    const suffix = cutout ? "cutout" : "promo";
    const ext = format === "png" ? "png" : "jpg";
    a.href = URL.createObjectURL(blob);
    a.download = `${suffix}-${id}.${ext}`;
    a.click();
    URL.revokeObjectURL(a.href);
    setStatus(
      cutout
        ? "PNG без стола/фона скачан (прозрачный фон). Загрузите на imgbb при необходимости."
        : "JPG скачан. Загрузите на imgbb и вставьте ссылку в Promo.",
      "ok"
    );
  } catch (err) {
    console.error(err);
    setStatus(
      `Не удалось снять сцену (${err.message || err}). Используйте Win+Shift+S.`,
      "err"
    );
  } finally {
    root.style.transform = prevTransform;
    root.classList.remove("is-cutout");
    root.classList.remove("is-export-flat");
    if (els.tableFelt) {
      els.tableFelt.classList.remove("is-hidden");
      els.tableFelt.style.transform = "";
      els.tableFelt.style.background = "";
      els.tableFelt.style.backgroundImage = "";
    }
    if (els.tableSurface) els.tableSurface.style.transformStyle = "";
    const viewport = root.querySelector(".table-viewport");
    if (viewport) viewport.style.perspective = "";
    if (!titleWasHidden && els.showTitle.checked) {
      els.titleOverlay.classList.remove("hidden");
    }
    btns.forEach((b) => {
      b.disabled = false;
    });
    await renderScene();
  }
}

async function load() {
  const boosterId = boosterIdFromUrl();
  if (!boosterId) {
    els.loadError.hidden = false;
    els.loadError.textContent =
      "Укажите id бустера в URL: /promo-generator.html?booster=start";
    els.boosterSub.textContent = "нет ?booster=";
    return;
  }

  try {
    const [boostersRes, catalogRes, seriesRes] = await Promise.all([
      fetch("/api/cards/boosters").then((r) => r.json()),
      fetch("/api/cards/catalog").then((r) => r.json()),
      fetch("/api/cards/series").then((r) => r.json()),
    ]);

    for (const s of seriesRes.items || []) {
      seriesBackById.set(s.id, s.card_back_id || "card-back");
    }
    for (const c of catalogRes.items || []) {
      catalogById.set(c.id, c);
    }

    booster = (boostersRes.items || []).find((b) => b.id === boosterId) || null;
    if (!booster) {
      els.loadError.hidden = false;
      els.loadError.textContent = `Бустер «${boosterId}» не найден.`;
      els.boosterSub.textContent = boosterId;
      return;
    }

    const ids = booster.card_ids || [];
    poolCards = ids
      .map((id) => catalogById.get(id))
      .filter(Boolean);

    els.boosterTitle.textContent = booster.name || booster.id;
    els.boosterSub.textContent = `id: ${booster.id} · карт в пуле: ${poolCards.length}`;

    const maxBacks = Math.min(24, Math.max(8, poolCards.length));
    els.backsCount.max = String(Math.max(24, poolCards.length));
    els.backsCount.value = String(Math.min(10, maxBacks));

    pickDefaultFaceUp(poolCards);
    renderFaceList();
    syncRangeLabels();
    await renderScene();
  } catch (err) {
    console.error(err);
    els.loadError.hidden = false;
    els.loadError.textContent = `Ошибка загрузки: ${err.message || err}`;
  }
}

function bind() {
  [
    els.backsCount,
    els.layout,
    els.tilt,
    els.spin,
    els.cardScale,
    els.overlap,
    els.seed,
    els.frameSize,
    els.showTitle,
    els.bgWhite,
    els.tableWhite,
  ].forEach((el) => {
    el.addEventListener("input", scheduleRender);
    el.addEventListener("change", scheduleRender);
  });

  els.btnSelectTop.addEventListener("click", () => {
    pickDefaultFaceUp(poolCards);
    renderFaceList();
    scheduleRender();
  });
  els.btnSelectNone.addEventListener("click", () => {
    faceUpIds.clear();
    renderFaceList();
    scheduleRender();
  });
  els.btnSelectAll.addEventListener("click", () => {
    faceUpIds.clear();
    for (const c of poolCards) faceUpIds.add(c.id);
    renderFaceList();
    scheduleRender();
  });
  els.btnReseed.addEventListener("click", () => {
    els.seed.value = String(Math.floor(Math.random() * 1e9));
    scheduleRender();
  });
  els.btnDownload.addEventListener("click", () => {
    downloadScene({ format: "jpeg", cutout: false });
  });
  els.btnDownloadCutout.addEventListener("click", () => {
    downloadScene({ format: "png", cutout: true });
  });

  window.addEventListener("resize", () => fitPreview());
}

bind();
load();
