(function () {
  "use strict";

  const RARITIES = [
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
    "mythic",
    "secretRare",
  ];

  const DEFAULT_WEIGHTS = {
    common: 48,
    uncommon: 24,
    rare: 12,
    epic: 7,
    legendary: 5,
    mythic: 1,
    secretRare: 1,
  };

  const statusBar = document.getElementById("statusBar");
  const cardsEnabled = document.getElementById("cardsEnabled");
  const cardsDailyLimit = document.getElementById("cardsDailyLimit");
  const cardsAnimSpeed = document.getElementById("cardsAnimSpeed");
  const boostersBody = document.getElementById("boostersBody");
  const drawsBody = document.getElementById("drawsBody");
  const catalogBody = document.getElementById("catalogBody");
  const boosterPoolChips = document.getElementById("boosterPoolChips");
  const drawBooster = document.getElementById("drawBooster");
  const boosterForm = document.getElementById("boosterForm");
  const drawForm = document.getElementById("drawForm");
  const seriesList = document.getElementById("seriesList");
  const seriesForm = document.getElementById("seriesForm");
  const seriesEditEmpty = document.getElementById("seriesEditEmpty");
  const seriesGallery = document.getElementById("seriesGallery");
  const seriesGalleryTitle = document.getElementById("seriesGalleryTitle");
  const drawWeightsEditor = document.getElementById("drawWeightsEditor");
  const boosterGalleryWrap = document.getElementById("boosterGalleryWrap");
  const boosterGallery = document.getElementById("boosterGallery");
  const boosterGalleryTitle = document.getElementById("boosterGalleryTitle");

  let cardsCatalog = [];
  let cardsStoriesMeta = {
    loaded: false,
    count: 0,
    source: "data/card-assets-repo/src/app/cardDetails.json",
  };
  let cardsBoosters = [];
  let cardsDraws = [];
  let cardsSeries = [];
  let selectedPoolIds = new Set();
  let editingBoosterId = null;
  let selectedSeriesId = null;
  let selectedBoosterId = null;
  let boosterGalleryOpen = false;
  let openOddsDrawId = null;

  function setStatus(text, kind) {
    statusBar.textContent = text;
    statusBar.className = kind === "ok" ? "ok" : kind === "err" ? "err" : "";
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      data = await res.json();
    } else {
      data = { error: await res.text() };
    }
    if (!res.ok) {
      const msg = (data && data.error) || `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function cardById(id) {
    return cardsCatalog.find((c) => c.id === id);
  }

  function cardThumb(c) {
    const src = c.image_url || `/assets/cards/${c.id}.webp`;
    return `<img class="thumb" src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />`;
  }

  function galleryHtml(cards) {
    if (!cards.length) {
      return '<span class="empty">Нет карт</span>';
    }
    return cards
      .map((c) => {
        const src = c.image_url || `/assets/cards/${c.id}.webp`;
        return `<button type="button" class="gallery-card" data-full-src="${esc(src)}" data-card-name="${esc(c.name)}" data-card-id="${esc(c.id)}" title="Открыть в полном размере">
          <img src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />
          <div class="name">${esc(c.name)}</div>
          <div class="rarity mono">${esc(c.rarity)}</div>
        </button>`;
      })
      .join("");
  }

  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightboxImg");
  const lightboxCaption = document.getElementById("lightboxCaption");
  const lightboxClose = document.getElementById("lightboxClose");

  function openLightbox(src, name, cardId) {
    if (!src) return;
    lightboxImg.src = src;
    lightboxImg.alt = name || cardId || "";
    lightboxCaption.textContent = name
      ? `${name}${cardId ? ` (${cardId})` : ""}`
      : cardId || src;
    lightbox.hidden = false;
    lightbox.classList.add("open");
  }

  function closeLightbox() {
    lightbox.classList.remove("open");
    lightbox.hidden = true;
    lightboxImg.removeAttribute("src");
    lightboxImg.alt = "";
    lightboxCaption.textContent = "";
  }

  function onGalleryClick(e) {
    const card = e.target.closest(".gallery-card");
    if (!card || !e.currentTarget.contains(card)) return;
    openLightbox(card.dataset.fullSrc, card.dataset.cardName, card.dataset.cardId);
  }

  seriesGallery.addEventListener("click", onGalleryClick);
  document.getElementById("boosterGallery").addEventListener("click", onGalleryClick);
  lightboxClose.addEventListener("click", (e) => {
    e.stopPropagation();
    closeLightbox();
  });
  lightbox.addEventListener("click", (e) => {
    if (e.target === lightbox) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && lightbox.classList.contains("open")) {
      closeLightbox();
    }
  });

  function weightsPercentMap(weights) {
    const sum = RARITIES.reduce((acc, k) => acc + (Number(weights[k]) || 0), 0);
    const pct = {};
    RARITIES.forEach((k) => {
      const w = Number(weights[k]) || 0;
      pct[k] = sum > 0 ? ((w / sum) * 100).toFixed(1) : "0.0";
    });
    return pct;
  }

  function renderWeightsEditor(weights) {
    const w = weights || DEFAULT_WEIGHTS;
    const pct = weightsPercentMap(w);
    drawWeightsEditor.innerHTML = RARITIES.map(
      (k) => `<label>
        ${esc(k)}
        <input type="number" class="weight-input" data-rarity="${esc(k)}" min="0" step="0.1" value="${esc(w[k] ?? 0)}" />
        <span class="pct" data-pct-for="${esc(k)}">${pct[k]}%</span>
      </label>`
    ).join("");
    drawWeightsEditor.querySelectorAll(".weight-input").forEach((input) => {
      input.addEventListener("input", refreshWeightPercents);
    });
  }

  function readWeightsFromEditor() {
    const out = {};
    RARITIES.forEach((k) => {
      const el = drawWeightsEditor.querySelector(`.weight-input[data-rarity="${k}"]`);
      out[k] = el ? parseFloat(el.value) : 0;
      if (Number.isNaN(out[k]) || out[k] < 0) out[k] = 0;
    });
    return out;
  }

  function refreshWeightPercents() {
    const pct = weightsPercentMap(readWeightsFromEditor());
    RARITIES.forEach((k) => {
      const el = drawWeightsEditor.querySelector(`[data-pct-for="${k}"]`);
      if (el) el.textContent = `${pct[k]}%`;
    });
  }

  function weightsReadonlyHtml(weights) {
    const pct = weightsPercentMap(weights || {});
    const rows = RARITIES.map(
      (k) => `<tr>
        <td class="mono">${esc(k)}</td>
        <td>${esc(weights[k] ?? 0)}</td>
        <td>${pct[k]}%</td>
      </tr>`
    ).join("");
    return `<div class="weights-readonly">
      <table>
        <thead><tr><th>редкость</th><th>вес</th><th>шанс</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function statusPill(status) {
    const known = ["active", "paused", "queued", "closed", "inactive"];
    const cls = known.includes(status) ? status : "inactive";
    return `<span class="status-pill ${cls}">${esc(status)}</span>`;
  }

  function drawActionButtons(d) {
    const parts = [];
    if (d.status === "active") {
      parts.push(
        `<button type="button" class="small btn-draw-pause" data-id="${esc(d.id)}">Пауза</button>`
      );
      parts.push(
        `<button type="button" class="small danger btn-draw-close" data-id="${esc(d.id)}">Завершить</button>`
      );
    } else if (d.status === "paused") {
      parts.push(
        `<button type="button" class="small primary btn-draw-activate" data-id="${esc(d.id)}">Возобновить</button>`
      );
      parts.push(
        `<button type="button" class="small danger btn-draw-close" data-id="${esc(d.id)}">Завершить</button>`
      );
    } else if (d.can_activate) {
      parts.push(
        `<button type="button" class="small primary btn-draw-activate" data-id="${esc(d.id)}">Активировать</button>`
      );
    }
    parts.push(
      `<button type="button" class="small btn-draw-odds" data-id="${esc(d.id)}">${
        openOddsDrawId === d.id ? "Скрыть шансы" : "Шансы"
      }</button>`
    );
    parts.push(
      `<button type="button" class="small btn-draw-copy" data-id="${esc(d.id)}">Копия</button>`
    );
    return parts.join("");
  }

  function renderCatalog() {
    const metaEl = document.getElementById("catalogStoriesMeta");
    if (metaEl) {
      if (cardsStoriesMeta.loaded) {
        metaEl.textContent = `Лор: загружено ${cardsStoriesMeta.count} описаний из ${cardsStoriesMeta.source}`;
      } else {
        metaEl.textContent =
          "Лор: файл описаний не найден - запустите update.cmd (sync cardDetails.json)";
      }
    }
    if (!cardsCatalog.length) {
      catalogBody.innerHTML = '<tr><td colspan="6" class="empty">Нет карт</td></tr>';
      return;
    }
    catalogBody.innerHTML = cardsCatalog
      .map((c) => {
        const src = c.image_url || `/assets/cards/${c.id}.webp`;
        const story = (c.story || "").trim();
        const storyCell = story
          ? `<td class="catalog-story">${esc(story)}</td>`
          : `<td class="catalog-story empty-story">нет в JSON</td>`;
        return `<tr>
          <td><img class="catalog-thumb" src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" /></td>
          <td class="mono">${esc(c.id)}</td>
          <td>${esc(c.name)}</td>
          <td>${esc(c.rarity)}</td>
          <td>${esc(c.series_name || c.series_id || "-")}</td>
          ${storyCell}
        </tr>`;
      })
      .join("");
  }

  function renderBoosterPoolChips() {
    if (!cardsCatalog.length) {
      boosterPoolChips.innerHTML = '<span class="empty">Нет каталога</span>';
      return;
    }
    boosterPoolChips.innerHTML = cardsCatalog
      .map((c) => {
        const on = selectedPoolIds.has(c.id);
        return `<span class="chip${on ? " selected" : ""}" data-card-id="${esc(c.id)}">${cardThumb(c)}<span>${esc(c.name)} <span class="mono">(${esc(c.rarity)})</span></span></span>`;
      })
      .join("");
    boosterPoolChips.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const id = chip.dataset.cardId;
        if (selectedPoolIds.has(id)) selectedPoolIds.delete(id);
        else selectedPoolIds.add(id);
        renderBoosterPoolChips();
      });
    });
  }

  function hideBoosterGallery() {
    boosterGalleryOpen = false;
    boosterGalleryWrap.style.display = "none";
    boostersBody.querySelectorAll("tr.booster-row").forEach((tr) => {
      tr.classList.remove("selected");
    });
    updateBoosterViewButtons();
  }

  function showBoosterGallery(boosterId) {
    const booster = cardsBoosters.find((b) => b.id === boosterId);
    if (!booster) {
      hideBoosterGallery();
      return;
    }
    selectedBoosterId = boosterId;
    boosterGalleryOpen = true;
    editingBoosterId = boosterId;
    selectedPoolIds = new Set(booster.card_ids || []);
    renderBoosterPoolChips();
    const cards = (booster.card_ids || [])
      .map((id) => cardById(id))
      .filter(Boolean);
    boosterGalleryWrap.style.display = "block";
    boosterGalleryTitle.textContent = `Состав «${booster.name}» (${cards.length})`;
    boosterGallery.innerHTML = galleryHtml(cards);
    boostersBody.querySelectorAll("tr.booster-row").forEach((tr) => {
      tr.classList.toggle("selected", tr.dataset.boosterId === boosterId);
    });
    updateBoosterViewButtons();
  }

  function toggleBoosterGallery(boosterId) {
    if (boosterGalleryOpen && selectedBoosterId === boosterId) {
      hideBoosterGallery();
      return;
    }
    showBoosterGallery(boosterId);
  }

  function updateBoosterViewButtons() {
    boostersBody.querySelectorAll(".btn-booster-view").forEach((btn) => {
      const open = boosterGalleryOpen && btn.dataset.id === selectedBoosterId;
      btn.textContent = open ? "Скрыть состав" : "Показать состав";
    });
  }

  function renderBoosters() {
    drawBooster.innerHTML = cardsBoosters
      .map((b) => `<option value="${esc(b.id)}">${esc(b.name)} (${esc(b.id)})</option>`)
      .join("");

    if (!cardsBoosters.length) {
      boostersBody.innerHTML = '<tr><td colspan="5" class="empty">Нет бустеров</td></tr>';
      hideBoosterGallery();
      return;
    }

    boostersBody.innerHTML = cardsBoosters
      .map((b) => {
        const promoUrl = b.promo_image_url || "";
        const promoLink = promoUrl
          ? `<a class="promo-link" href="${esc(promoUrl)}" target="_blank" rel="noopener">открыть</a>`
          : "";
        const open = boosterGalleryOpen && b.id === selectedBoosterId;
        const selected = open ? " selected" : "";
        const viewLabel = open ? "Скрыть состав" : "Показать состав";
        return `<tr class="booster-row${selected}" data-booster-id="${esc(b.id)}">
          <td class="mono">${esc(b.id)}</td>
          <td>${esc(b.name)}</td>
          <td>${esc((b.card_ids || []).length)}</td>
          <td class="promo-cell">
            <div class="promo-row">
              <input type="text" class="promo-url" data-id="${esc(b.id)}" value="${esc(promoUrl)}" placeholder="https://… или /assets/…" />
              <a class="small btn-promo-gen" href="/promo-generator.html?booster=${encodeURIComponent(b.id)}" target="_blank" rel="noopener">Генерировать</a>
              <button type="button" class="small primary btn-booster-promo-save" data-id="${esc(b.id)}">Сохранить</button>
              <button type="button" class="small btn-booster-promo-clear" data-id="${esc(b.id)}">Очистить</button>
              ${promoLink}
            </div>
          </td>
          <td class="actions">
            <button type="button" class="small btn-booster-view" data-id="${esc(b.id)}">${viewLabel}</button>
            <button type="button" class="small btn-booster-edit" data-id="${esc(b.id)}">Переименовать</button>
          </td>
        </tr>`;
      })
      .join("");

    if (boosterGalleryOpen && selectedBoosterId) {
      showBoosterGallery(selectedBoosterId);
    } else {
      boosterGalleryWrap.style.display = "none";
    }
  }

  function renderDraws() {
    if (!cardsDraws.length) {
      drawsBody.innerHTML = '<tr><td colspan="7" class="empty">Нет тиражей</td></tr>';
      return;
    }
    drawsBody.innerHTML = cardsDraws
      .map((d) => {
        const oddsOpen = openOddsDrawId === d.id;
        const queueMark =
          d.status === "queued" && d.queue_position
            ? `<span class="queue-pos">#${esc(d.queue_position)}</span>`
            : "";
        const main = `<tr data-draw-id="${esc(d.id)}">
        <td class="mono">${esc(d.id)}</td>
        <td>${esc(d.name)}</td>
        <td>${esc(d.booster_name)}</td>
        <td>${esc(d.cost_points)}</td>
        <td>${esc(d.cards_per_open)}</td>
        <td>${statusPill(d.status)}${queueMark}</td>
        <td class="actions">${drawActionButtons(d)}</td>
      </tr>`;
        const odds = oddsOpen
          ? `<tr class="odds-row"><td colspan="7">${weightsReadonlyHtml(d.rarity_weights || {})}</td></tr>`
          : "";
        return main + odds;
      })
      .join("");
  }

  function cardBackUrl(cardBackId) {
    const id = (cardBackId || "card-back").trim() || "card-back";
    return `/assets/cards/${id}.svg`;
  }

  function updateSeriesBackPreview(cardBackId, seriesName) {
    const src = cardBackUrl(cardBackId);
    const img = document.getElementById("seriesBackPreviewImg");
    const btn = document.getElementById("seriesBackPreview");
    if (!img || !btn) return;
    img.src = src;
    img.onerror = () => {
      img.style.visibility = "hidden";
    };
    img.onload = () => {
      img.style.visibility = "visible";
    };
    btn.dataset.fullSrc = src;
    btn.dataset.cardName = seriesName
      ? `Рубашка «${seriesName}»`
      : "Рубашка серии";
    btn.dataset.cardId = (cardBackId || "card-back").trim() || "card-back";
  }

  function renderSeriesList() {
    if (!cardsSeries.length) {
      seriesList.innerHTML = '<span class="empty">Нет серий</span>';
      return;
    }
    seriesList.innerHTML = cardsSeries
      .map((s) => {
        const back = cardBackUrl(s.card_back_id);
        const active = s.id === selectedSeriesId ? " active" : "";
        return `<button type="button" class="series-item${active}" data-series-id="${esc(s.id)}">
          <img class="back" src="${esc(back)}" alt="" data-full-src="${esc(back)}" data-card-name="Рубашка «${esc(s.name)}»" data-card-id="${esc(s.card_back_id || "card-back")}" title="Предпросмотр рубашки" onerror="this.style.visibility='hidden'" />
          <div class="meta">
            <strong>${esc(s.name)}</strong>
            <span class="mono">${esc(s.id)}</span> · <span>${esc(s.cards_count)} карт</span>
          </div>
        </button>`;
      })
      .join("");
  }

  function selectSeries(seriesId) {
    selectedSeriesId = seriesId;
    const series = cardsSeries.find((s) => s.id === seriesId);
    renderSeriesList();
    if (!series) {
      seriesForm.style.display = "none";
      seriesEditEmpty.style.display = "block";
      seriesGalleryTitle.textContent = "Карты серии";
      seriesGallery.innerHTML = '<span class="empty">Выберите серию</span>';
      return;
    }
    seriesEditEmpty.style.display = "none";
    seriesForm.style.display = "flex";
    document.getElementById("seriesId").value = series.id;
    document.getElementById("seriesName").value = series.name;
    document.getElementById("seriesSort").value = series.sort_order ?? 0;
    document.getElementById("seriesCardBack").value = series.card_back_id || "card-back";
    updateSeriesBackPreview(series.card_back_id, series.name);
    const cards = cardsCatalog.filter((c) => c.series_id === seriesId);
    seriesGalleryTitle.textContent = `Карты серии «${series.name}» (${cards.length})`;
    seriesGallery.innerHTML = galleryHtml(cards);
  }

  function prefillDrawForm(draw) {
    document.getElementById("drawId").value = `${draw.id}_copy`;
    document.getElementById("drawName").value = `${draw.name} (копия)`;
    drawBooster.value = draw.booster_id;
    document.getElementById("drawCost").value = draw.cost_points;
    document.getElementById("drawCards").value = draw.cards_per_open;
    document.getElementById("drawDailyLimit").value = draw.daily_limit ?? 0;
    document.getElementById("drawActivate").checked = false;
    renderWeightsEditor(draw.rarity_weights || DEFAULT_WEIGHTS);
    document.querySelector('.tab[data-tab="draws"]').click();
    document.getElementById("drawId").focus();
    setStatus("Форма заполнена из тиража - поправьте id/шансы и создайте", "ok");
  }

  async function loadAll() {
    setStatus("Загрузка…");
    try {
      const [catalog, boosters, draws, meta, series] = await Promise.all([
        api("GET", "/api/cards/catalog"),
        api("GET", "/api/cards/boosters"),
        api("GET", "/api/cards/draws"),
        api("GET", "/api/cards/meta"),
        api("GET", "/api/cards/series"),
      ]);
      cardsCatalog = catalog.items || [];
      cardsStoriesMeta = {
        loaded: Boolean(catalog.stories_loaded),
        count: catalog.stories_count || 0,
        source: catalog.stories_source || "data/card-assets-repo/src/app/cardDetails.json",
      };
      cardsBoosters = boosters.items || [];
      cardsDraws = draws.items || [];
      cardsSeries = series.items || [];
      cardsDailyLimit.value = meta.daily_open_limit ?? 0;
      cardsEnabled.checked = meta.enabled !== false;
      cardsAnimSpeed.value =
        meta.anim_speed != null ? Number(meta.anim_speed) : 1;
      if (!editingBoosterId && cardsBoosters.length) {
        selectedPoolIds = new Set(cardsBoosters[0].card_ids || []);
        editingBoosterId = cardsBoosters[0].id;
      }
      renderBoosterPoolChips();
      renderCatalog();
      renderBoosters();
      renderDraws();
      renderSeriesList();
      if (selectedSeriesId) {
        selectSeries(selectedSeriesId);
      } else if (cardsSeries.length) {
        selectSeries(cardsSeries[0].id);
      }
      setStatus("Данные загружены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    });
  });

  document.getElementById("cardsSaveMeta").addEventListener("click", async () => {
    const limit = parseInt(cardsDailyLimit.value, 10);
    if (Number.isNaN(limit) || limit < 0) {
      setStatus("Лимит >= 0", "err");
      return;
    }
    const speed = parseFloat(cardsAnimSpeed.value);
    if (Number.isNaN(speed) || speed < 0.5 || speed > 3) {
      setStatus("Скорость анимации: 0.5–3.0", "err");
      return;
    }
    try {
      await api("PUT", "/api/cards/meta", {
        daily_open_limit: limit,
        enabled: cardsEnabled.checked,
        anim_speed: speed,
      });
      setStatus(
        cardsEnabled.checked ? "Настройки сохранены" : "Модуль карт выключен",
        "ok"
      );
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  document.getElementById("cardsRefresh").addEventListener("click", () => {
    loadAll();
  });

  seriesList.addEventListener("click", (e) => {
    const backImg = e.target.closest("img.back");
    if (backImg && backImg.dataset.fullSrc) {
      e.preventDefault();
      e.stopPropagation();
      const item = backImg.closest(".series-item");
      if (item) selectSeries(item.dataset.seriesId);
      openLightbox(backImg.dataset.fullSrc, backImg.dataset.cardName, backImg.dataset.cardId);
      return;
    }
    const btn = e.target.closest(".series-item");
    if (!btn) return;
    selectSeries(btn.dataset.seriesId);
  });

  document.getElementById("seriesCardBack").addEventListener("input", () => {
    const series = cardsSeries.find((s) => s.id === selectedSeriesId);
    updateSeriesBackPreview(
      document.getElementById("seriesCardBack").value,
      series ? series.name : ""
    );
  });

  document.getElementById("seriesBackPreview").addEventListener("click", () => {
    const btn = document.getElementById("seriesBackPreview");
    openLightbox(btn.dataset.fullSrc, btn.dataset.cardName, btn.dataset.cardId);
  });

  seriesForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("seriesId").value.trim();
    const name = document.getElementById("seriesName").value.trim();
    const sort_order = parseInt(document.getElementById("seriesSort").value, 10);
    const card_back_id = document.getElementById("seriesCardBack").value.trim();
    if (!id || !name || !card_back_id) {
      setStatus("Заполните поля серии", "err");
      return;
    }
    try {
      await api("PUT", `/api/cards/series/${encodeURIComponent(id)}`, {
        name,
        sort_order: Number.isNaN(sort_order) ? 0 : sort_order,
        card_back_id,
      });
      await loadAll();
      selectSeries(id);
      setStatus("Серия сохранена", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  boosterForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("boosterId").value.trim().toLowerCase();
    const name = document.getElementById("boosterName").value.trim();
    if (!selectedPoolIds.size) {
      setStatus("Выберите хотя бы одну карту в составе", "err");
      return;
    }
    try {
      await api("POST", "/api/cards/boosters", {
        id,
        name,
        card_ids: Array.from(selectedPoolIds),
      });
      document.getElementById("boosterId").value = "";
      document.getElementById("boosterName").value = "";
      await loadAll();
      selectedBoosterId = id;
      showBoosterGallery(id);
      setStatus("Бустер создан", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  drawForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("drawId").value.trim().toLowerCase();
    const name = document.getElementById("drawName").value.trim();
    const booster_id = drawBooster.value;
    const cost_points = parseInt(document.getElementById("drawCost").value, 10);
    const cards_per_open = parseInt(document.getElementById("drawCards").value, 10);
    const daily_limit = parseInt(document.getElementById("drawDailyLimit").value, 10);
    const activate = document.getElementById("drawActivate").checked;
    const rarity_weights = readWeightsFromEditor();
    try {
      await api("POST", "/api/cards/draws", {
        id,
        name,
        booster_id,
        cost_points,
        cards_per_open,
        daily_limit: Number.isNaN(daily_limit) ? 0 : daily_limit,
        activate,
        rarity_weights,
      });
      document.getElementById("drawId").value = "";
      document.getElementById("drawName").value = "";
      document.getElementById("drawActivate").checked = false;
      renderWeightsEditor(DEFAULT_WEIGHTS);
      await loadAll();
      setStatus("Тираж создан", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  boostersBody.addEventListener("click", async (e) => {
    const viewBtn = e.target.closest(".btn-booster-view");
    if (viewBtn) {
      toggleBoosterGallery(viewBtn.dataset.id);
      return;
    }
    const promoSave = e.target.closest(".btn-booster-promo-save");
    if (promoSave) {
      const id = promoSave.dataset.id;
      const input = boostersBody.querySelector(`.promo-url[data-id="${CSS.escape(id)}"]`);
      const url = input ? input.value.trim() : "";
      setStatus("Сохранение promo…");
      try {
        await api("PUT", `/api/cards/boosters/${encodeURIComponent(id)}/promo`, {
          promo_image_url: url,
        });
        await loadAll();
        setStatus(url ? "Promo сохранён" : "Promo очищен", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
      return;
    }
    const promoClear = e.target.closest(".btn-booster-promo-clear");
    if (promoClear) {
      const id = promoClear.dataset.id;
      setStatus("Очистка promo…");
      try {
        await api("PUT", `/api/cards/boosters/${encodeURIComponent(id)}/promo`, {
          promo_image_url: "",
        });
        await loadAll();
        setStatus("Promo очищен", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
      return;
    }
    const editBtn = e.target.closest(".btn-booster-edit");
    if (editBtn) {
      const id = editBtn.dataset.id;
      const booster = cardsBoosters.find((b) => b.id === id);
      if (!booster) return;
      editingBoosterId = id;
      selectedPoolIds = new Set(booster.card_ids || []);
      renderBoosterPoolChips();
      showBoosterGallery(id);
      const name = prompt("Название бустера", booster.name);
      if (name == null) return;
      if (!selectedPoolIds.size) {
        setStatus("Состав не может быть пустым", "err");
        return;
      }
      setStatus("Сохранение бустера…");
      try {
        await api("PUT", `/api/cards/boosters/${encodeURIComponent(id)}`, {
          name: name.trim(),
          card_ids: Array.from(selectedPoolIds),
        });
        await loadAll();
        showBoosterGallery(id);
        setStatus("Бустер обновлён", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    }
  });

  drawsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    if (btn.classList.contains("btn-draw-odds")) {
      openOddsDrawId = openOddsDrawId === id ? null : id;
      renderDraws();
      return;
    }
    if (btn.classList.contains("btn-draw-copy")) {
      const src = cardsDraws.find((d) => d.id === id);
      if (!src) return;
      prefillDrawForm(src);
      return;
    }
    if (btn.classList.contains("btn-draw-activate")) {
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/activate`);
        await loadAll();
        setStatus("Тираж активирован", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    } else if (btn.classList.contains("btn-draw-pause")) {
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/pause`);
        await loadAll();
        setStatus("Тираж на паузе", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    } else if (btn.classList.contains("btn-draw-close")) {
      if (!confirm("Завершить тираж навсегда? Следующий из очереди станет активным.")) {
        return;
      }
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/close`);
        await loadAll();
        setStatus("Тираж завершён", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    }
  });

  renderWeightsEditor(DEFAULT_WEIGHTS);
  loadAll();
})();
