/**
 * Promo generator — Three.js стол с картами бустера.
 * URL: /promo-generator.html?booster=<id>
 * Экспорт: renderer.domElement.toBlob (тот же кадр, что на превью).
 */
import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js";
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
const CARD_ASPECT = 5 / 7;
/** World units for card width at scale slider = 148 */
const BASE_CARD_W = 1.35;

const catalogById = new Map();
const seriesBackById = new Map();
/** @type {Map<string, THREE.Texture>} */
const frontTexCache = new Map();
/** @type {Map<string, THREE.Texture>} */
const backTexCache = new Map();

let booster = null;
/** @type {object[]} */
let poolCards = [];
const faceUpIds = new Set();
let renderToken = 0;
let previewScale = 1;

/** @type {THREE.WebGLRenderer | null} */
let renderer = null;
/** @type {THREE.Scene | null} */
let scene = null;
/** @type {THREE.PerspectiveCamera | null} */
let camera = null;
/** @type {THREE.Group | null} */
let tableGroup = null;
/** @type {THREE.Mesh | null} */
let tableMesh = null;
/** @type {THREE.Group | null} */
let cardsGroup = null;
/** @type {THREE.AmbientLight | null} */
let ambient = null;
/** @type {THREE.DirectionalLight | null} */
let keyLight = null;

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
  threeHost: document.getElementById("threeHost"),
  bakeHost: document.getElementById("bakeHost"),
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
  els.statusLine.className =
    kind === "err" ? "hint err" : kind === "ok" ? "hint ok" : "hint";
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
    return (
      (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
      a.name.localeCompare(b.name, "ru")
    );
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

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function frameSizePx() {
  const [w, h] = (els.frameSize.value || "1920x1080").split("x").map(Number);
  return { w: w || 1920, h: h || 1080 };
}

function fitPreview() {
  const { w, h } = frameSizePx();
  els.exportRoot.dataset.size = els.frameSize.value;
  const frame = els.stageFrame;
  const pad = 24;
  const availW = Math.max(200, frame.clientWidth - pad);
  const availH = Math.max(200, frame.clientHeight - pad);
  previewScale = Math.min(1, availW / w, availH / h);
  els.exportRoot.style.transform = `scale(${previewScale})`;
  els.stageMeta.textContent = `${w}×${h} · ${Math.round(previewScale * 100)}% · лицом ${faceUpIds.size} · рубашек ${els.backsCount.value}`;
}

function initThree() {
  const { w, h } = frameSizePx();
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, w / h, 0.1, 100);
  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(w, h, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  els.threeHost.innerHTML = "";
  els.threeHost.appendChild(renderer.domElement);

  ambient = new THREE.AmbientLight(0xffffff, 1.35);
  keyLight = new THREE.DirectionalLight(0xffffff, 1.1);
  keyLight.position.set(4, 12, 6);
  const fill = new THREE.DirectionalLight(0xfff2e0, 0.55);
  fill.position.set(-5, 6, -3);
  const rim = new THREE.HemisphereLight(0xffffff, 0x2a3348, 0.45);
  scene.add(ambient);
  scene.add(keyLight);
  scene.add(fill);
  scene.add(rim);

  tableGroup = new THREE.Group();
  scene.add(tableGroup);

  const tableGeo = new THREE.PlaneGeometry(14, 9);
  const tableMat = new THREE.MeshStandardMaterial({
    color: 0x152032,
    roughness: 0.92,
    metalness: 0.05,
  });
  tableMesh = new THREE.Mesh(tableGeo, tableMat);
  tableMesh.rotation.x = -Math.PI / 2;
  tableMesh.position.y = -0.02;
  tableGroup.add(tableMesh);

  cardsGroup = new THREE.Group();
  tableGroup.add(cardsGroup);

  updateCamera();
  applyBackground();
  renderFrame();
}

function applyBackground() {
  if (!scene || !renderer) return;
  if (els.bgWhite.checked) {
    scene.background = new THREE.Color(0xffffff);
    els.exportRoot.classList.add("is-bg-white");
  } else {
    scene.background = new THREE.Color(0x080a10);
    els.exportRoot.classList.remove("is-bg-white");
  }
}

function applyTableColor() {
  if (!tableMesh) return;
  const mat = tableMesh.material;
  mat.color.set(els.tableWhite.checked ? 0xffffff : 0x152032);
  mat.needsUpdate = true;
}

function updateCamera() {
  if (!camera || !renderer) return;
  const { w, h } = frameSizePx();
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);

  const tiltDeg = Number(els.tilt.value) || 0;
  const spinDeg = Number(els.spin.value) || 0;
  // tilt 0 = top-down, 72 = low side angle
  const elev = THREE.MathUtils.degToRad(90 - tiltDeg);
  const dist = 11.5;
  const spin = THREE.MathUtils.degToRad(spinDeg);
  camera.position.set(
    Math.sin(spin) * Math.cos(elev) * dist,
    Math.sin(elev) * dist,
    Math.cos(spin) * Math.cos(elev) * dist
  );
  // Keep upright-ish: look at table center
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  // Avoid singularity when tilt≈0 (camera on +Y)
  if (tiltDeg < 2) {
    camera.position.set(0.001, dist, 0.001);
    camera.lookAt(0, 0, 0);
    camera.up.set(0, 0, -1);
  }
}

function renderFrame() {
  if (!renderer || !scene || !camera) return;
  renderer.render(scene, camera);
}

function clearCards() {
  if (!cardsGroup) return;
  while (cardsGroup.children.length) {
    const obj = cardsGroup.children[0];
    cardsGroup.remove(obj);
    obj.traverse((ch) => {
      if (ch.geometry) ch.geometry.dispose();
      // textures kept in cache — don't dispose maps
      if (ch.material) {
        if (Array.isArray(ch.material)) ch.material.forEach((m) => m.dispose());
        else ch.material.dispose();
      }
    });
  }
}

function cardWorldSize() {
  const scale = Number(els.cardScale.value) || 148;
  const w = BASE_CARD_W * (scale / 148);
  const h = w / CARD_ASPECT;
  return { w, h };
}

/**
 * @returns {{ kind: 'face'|'back', card?: object, x: number, z: number, rot: number, y: number }[]}
 */
function computeLayout(faces, backsCount) {
  const rand = mulberry32(Number(els.seed.value) || 0);
  const squeeze = 1 - Number(els.overlap.value) / 200;
  const { w: cardW } = cardWorldSize();
  const items = [];
  for (let i = 0; i < backsCount; i++) items.push({ kind: "back", i });
  for (const card of faces) items.push({ kind: "face", card });

  const placed = [];
  const layout = els.layout.value;

  if (layout === "row") {
    const n = items.length;
    const span = Math.min(10, n * cardW * 0.72 * squeeze + 0.5);
    items.forEach((it, idx) => {
      const t = n === 1 ? 0.5 : idx / (n - 1);
      placed.push({
        ...it,
        x: (t - 0.5) * span,
        z: (rand() - 0.5) * 0.25,
        rot: (rand() - 0.5) * 0.14,
        y: 0.01 + idx * 0.004,
      });
    });
  } else if (layout === "arc" || layout === "fan") {
    const n = items.length;
    const spread = layout === "fan" ? 70 : 110;
    const radius = (layout === "fan" ? 2.8 : 4.2) * squeeze + 1.2;
    items.forEach((it, idx) => {
      const t = n === 1 ? 0.5 : idx / (n - 1);
      const ang = THREE.MathUtils.degToRad((t - 0.5) * spread);
      placed.push({
        ...it,
        x: Math.sin(ang) * radius,
        z: -Math.cos(ang) * radius * 0.35 + radius * 0.15,
        rot: ang * 0.85,
        y: 0.01 + idx * 0.004,
      });
    });
  } else {
    items.forEach((it, idx) => {
      const angle = rand() * Math.PI * 2;
      const radius = Math.sqrt(rand()) * (2.6 + faces.length * 0.12) * squeeze;
      placed.push({
        ...it,
        x: Math.cos(angle) * radius * 1.35,
        z: Math.sin(angle) * radius * 0.85,
        rot: (rand() - 0.5) * 0.9,
        y: 0.01 + idx * 0.005,
      });
    });
  }
  return placed;
}

async function textureFromImageUrl(url) {
  const loader = new THREE.TextureLoader();
  const tex = await new Promise((resolve, reject) => {
    loader.load(url, resolve, undefined, reject);
  });
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer ? renderer.capabilities.getMaxAnisotropy() : 4;
  tex.needsUpdate = true;
  return tex;
}

/** SVG/image → canvas data URL (for backs and fallbacks). */
async function rasterizeUrl(url, w, h) {
  const abs = new URL(url, location.origin).href;
  const res = await fetch(abs);
  const blob = await res.blob();
  const dataUrl = await new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(fr.result);
    fr.onerror = reject;
    fr.readAsDataURL(blob);
  });
  const img = new Image();
  img.src = dataUrl;
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
  if (!ctx) throw new Error("no 2d ctx");
  ctx.fillStyle = "#0e1220";
  ctx.fillRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);
  return canvas.toDataURL("image/png");
}

async function bakeFrontTexture(card) {
  const cacheKey = card.id;
  if (frontTexCache.has(cacheKey)) return frontTexCache.get(cacheKey);

  const host = els.bakeHost;
  host.innerHTML = "";
  await mountCardTemplate(host, card.rarity || "common", {
    name: card.name || "",
    portraitUrl: portraitUrl(card),
  });
  const svg = host.querySelector("svg");
  if (!svg) throw new Error(`no svg for ${card.id}`);

  // Inline portrait so drawImage works offline
  const imgEl = svg.querySelector('[data-slot="portrait"]');
  if (imgEl) {
    const href =
      imgEl.getAttribute("href") ||
      imgEl.getAttributeNS("http://www.w3.org/1999/xlink", "href") ||
      "";
    if (href && !href.startsWith("data:")) {
      try {
        const png = await rasterizeUrl(href, 620, 660);
        imgEl.setAttribute("href", png);
        imgEl.setAttributeNS("http://www.w3.org/1999/xlink", "href", png);
      } catch (e) {
        console.warn("portrait bake", card.id, e);
      }
    }
  }

  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", "350");
  svg.setAttribute("height", "490");
  const xml = new XMLSerializer().serializeToString(svg);
  const svgUrl =
    "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
  const dataUrl = await rasterizeUrl(svgUrl, 700, 980);
  const tex = await textureFromImageUrl(dataUrl);
  frontTexCache.set(cacheKey, tex);
  host.innerHTML = "";
  return tex;
}

async function bakeBackTexture(card) {
  const url = backUrlForCard(card || poolCards[0] || { series_id: "" });
  if (backTexCache.has(url)) return backTexCache.get(url);
  const dataUrl = await rasterizeUrl(url, 700, 980);
  const tex = await textureFromImageUrl(dataUrl);
  backTexCache.set(url, tex);
  return tex;
}

function makeCardMesh(frontTex, backTex) {
  const { w, h } = cardWorldSize();
  const group = new THREE.Group();
  const geo = new THREE.PlaneGeometry(w, h);

  const frontMat = new THREE.MeshBasicMaterial({
    map: frontTex,
    side: THREE.FrontSide,
  });
  const backMat = new THREE.MeshBasicMaterial({
    map: backTex,
    side: THREE.FrontSide,
  });

  const front = new THREE.Mesh(geo, frontMat);
  front.position.z = 0.008;

  const back = new THREE.Mesh(geo.clone(), backMat);
  back.rotation.y = Math.PI;
  back.position.z = -0.008;

  group.add(front);
  group.add(back);
  return group;
}

async function rebuildScene() {
  const token = ++renderToken;
  if (!renderer) initThree();

  applyBackground();
  applyTableColor();
  els.exportRoot.classList.toggle("is-bg-white", els.bgWhite.checked);
  els.titleOverlay.classList.toggle("hidden", !els.showTitle.checked);

  if (booster) {
    els.overlayName.textContent = booster.name || booster.id;
    const seriesNames = [
      ...new Set(poolCards.map((c) => c.series_name).filter(Boolean)),
    ];
    els.overlayPool.textContent = `${
      seriesNames.length ? seriesNames.join(" · ") : "бустер"
    } · ${poolCards.length} карт в пуле`;
  }

  const faces = sortPool(poolCards.filter((c) => faceUpIds.has(c.id)));
  let backs = Number(els.backsCount.value) || 0;
  if (backs > 40) backs = 40;

  const layout = computeLayout(faces, backs);
  clearCards();

  const sample = poolCards[0] || faces[0];
  let sharedBack = null;
  try {
    sharedBack = await bakeBackTexture(sample);
  } catch (e) {
    console.warn(e);
  }

  for (const pos of layout) {
    if (token !== renderToken) return;
    try {
      let frontTex;
      let backTex = sharedBack;
      const faceUp = pos.kind === "face";
      if (faceUp && pos.card) {
        frontTex = await bakeFrontTexture(pos.card);
        backTex = (await bakeBackTexture(pos.card)) || sharedBack;
      } else {
        frontTex = sharedBack;
        backTex = sharedBack;
      }
      if (!frontTex || !backTex) continue;

      const mesh = makeCardMesh(frontTex, backTex);
      mesh.position.set(pos.x, pos.y, pos.z);
      // YXZ: yaw на столе, затем наклон плоскости
      mesh.rotation.order = "YXZ";
      mesh.rotation.y = pos.rot;
      mesh.rotation.x = faceUp ? -Math.PI / 2 : Math.PI / 2;
      mesh.rotation.z = 0;
      cardsGroup.add(mesh);
    } catch (e) {
      console.warn("card place", e);
    }
  }

  if (token !== renderToken) return;
  updateCamera();
  if (tableMesh) tableMesh.visible = true;
  renderFrame();
  fitPreview();
  setStatus(
    `Three.js: ${faces.length} лицом · ${backs} рубашкой · «${els.layout.value}»`,
    "ok"
  );
}

let renderTimer = null;
function scheduleRebuild() {
  syncRangeLabels();
  fitPreview();
  clearTimeout(renderTimer);
  renderTimer = setTimeout(() => {
    rebuildScene().catch((e) => {
      console.error(e);
      setStatus(String(e.message || e), "err");
    });
  }, 100);
}

/**
 * Composite WebGL canvas + optional HTML title into one image.
 * @param {{ format: 'jpeg'|'png', cutout?: boolean }} opts
 */
async function downloadScene(opts) {
  const format = opts.format || "jpeg";
  const cutout = Boolean(opts.cutout);
  if (!renderer || !scene || !camera) {
    setStatus("Сцена ещё не готова", "err");
    return;
  }
  const btns = [els.btnDownload, els.btnDownloadCutout];
  btns.forEach((b) => {
    b.disabled = true;
  });
  setStatus(cutout ? "PNG cutout…" : `Рендер ${format.toUpperCase()}…`, "");

  const prevBg = scene.background;
  const prevTableVis = tableMesh ? tableMesh.visible : true;
  const titleWasHidden = els.titleOverlay.classList.contains("hidden");

  try {
    if (cutout) {
      scene.background = null;
      renderer.setClearColor(0x000000, 0);
      if (tableMesh) tableMesh.visible = false;
      els.exportRoot.classList.add("is-cutout");
      els.titleOverlay.classList.add("hidden");
    } else {
      applyBackground();
      applyTableColor();
      if (tableMesh) tableMesh.visible = true;
      renderer.setClearColor(
        els.bgWhite.checked ? 0xffffff : 0x080a10,
        1
      );
    }

    updateCamera();
    renderFrame();

    const glCanvas = renderer.domElement;
    const { w, h } = frameSizePx();
    const out = document.createElement("canvas");
    out.width = w;
    out.height = h;
    const ctx = out.getContext("2d");
    if (!ctx) throw new Error("no 2d ctx");

    if (!cutout) {
      ctx.fillStyle = els.bgWhite.checked ? "#ffffff" : "#080a10";
      ctx.fillRect(0, 0, w, h);
    }
    ctx.drawImage(glCanvas, 0, 0, w, h);

    // Burn title overlay if visible
    if (!cutout && els.showTitle.checked && !els.titleOverlay.classList.contains("hidden")) {
      ctx.fillStyle = els.bgWhite.checked ? "#1a1e28" : "#f2f0ea";
      ctx.font = `700 ${Math.round(w * 0.028)}px "Segoe UI", system-ui, sans-serif`;
      ctx.textBaseline = "top";
      ctx.fillText(els.overlayName.textContent || "", 48, 36);
      ctx.fillStyle = els.bgWhite.checked ? "#4a5568" : "#c8d0e0";
      ctx.font = `400 ${Math.round(w * 0.012)}px "Segoe UI", system-ui, sans-serif`;
      ctx.fillText(els.overlayPool.textContent || "", 48, 36 + Math.round(w * 0.036));
    }

    const mime = format === "png" ? "image/png" : "image/jpeg";
    const quality = format === "png" ? undefined : 0.92;
    const blob = await new Promise((resolve) =>
      out.toBlob((b) => resolve(b), mime, quality)
    );
    if (!blob) throw new Error("toBlob failed");

    const a = document.createElement("a");
    const id = booster?.id || "booster";
    a.href = URL.createObjectURL(blob);
    a.download = `${cutout ? "cutout" : "promo"}-${id}.${format === "png" ? "png" : "jpg"}`;
    a.click();
    URL.revokeObjectURL(a.href);
    setStatus(
      cutout
        ? "PNG cutout скачан (прозрачный фон)."
        : "JPG скачан — тот же кадр, что на превью.",
      "ok"
    );
  } catch (err) {
    console.error(err);
    setStatus(`Ошибка экспорта: ${err.message || err}`, "err");
  } finally {
    scene.background = prevBg;
    if (tableMesh) tableMesh.visible = prevTableVis;
    els.exportRoot.classList.remove("is-cutout");
    if (!titleWasHidden && els.showTitle.checked) {
      els.titleOverlay.classList.remove("hidden");
    }
    renderer.setClearColor(0x080a10, 1);
    applyBackground();
    renderFrame();
    btns.forEach((b) => {
      b.disabled = false;
    });
  }
}

function renderFaceList() {
  const sorted = sortPool(poolCards);
  els.faceList.innerHTML = sorted
    .map((c) => {
      const checked = faceUpIds.has(c.id) ? "checked" : "";
      return `<label class="face-item">
        <input type="checkbox" data-id="${escapeHtml(c.id)}" ${checked} />
        <img src="${escapeHtml(portraitUrl(c))}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />
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
      scheduleRebuild();
    });
  });
}

async function load() {
  const boosterId = boosterIdFromUrl();
  if (!boosterId) {
    els.loadError.hidden = false;
    els.loadError.textContent =
      "Укажите id: /promo-generator.html?booster=start";
    els.boosterSub.textContent = "нет ?booster=";
    return;
  }

  try {
    initThree();
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

    poolCards = (booster.card_ids || [])
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
    await rebuildScene();
  } catch (err) {
    console.error(err);
    els.loadError.hidden = false;
    els.loadError.textContent = `Ошибка: ${err.message || err}`;
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
    el.addEventListener("input", scheduleRebuild);
    el.addEventListener("change", scheduleRebuild);
  });

  els.btnSelectTop.addEventListener("click", () => {
    pickDefaultFaceUp(poolCards);
    renderFaceList();
    scheduleRebuild();
  });
  els.btnSelectNone.addEventListener("click", () => {
    faceUpIds.clear();
    renderFaceList();
    scheduleRebuild();
  });
  els.btnSelectAll.addEventListener("click", () => {
    faceUpIds.clear();
    for (const c of poolCards) faceUpIds.add(c.id);
    renderFaceList();
    scheduleRebuild();
  });
  els.btnReseed.addEventListener("click", () => {
    els.seed.value = String(Math.floor(Math.random() * 1e9));
    scheduleRebuild();
  });
  els.btnDownload.addEventListener("click", () => {
    downloadScene({ format: "jpeg", cutout: false });
  });
  els.btnDownloadCutout.addEventListener("click", () => {
    downloadScene({ format: "png", cutout: true });
  });

  window.addEventListener("resize", () => {
    fitPreview();
    renderFrame();
  });
}

bind();
load();
