(() => {
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
  const SLUG_RE = /^[a-z][a-z0-9_-]*$/;
  const BACK_RE = /^card-back(?:-[a-z0-9_-]+)?$/;

  /** @type {{ file: File, card_id: string, name: string, rarity: string, story: string, url: string }[]} */
  let cards = [];
  let step = 0;
  const STEP_COUNT = 4;

  const $ = (id) => document.getElementById(id);
  const statusBar = $("statusBar");

  function setStatus(msg, kind) {
    statusBar.textContent = msg;
    statusBar.className = kind || "";
  }

  function slugGuess(filename) {
    let stem = filename.replace(/\.[^.]+$/, "").trim().toLowerCase();
    stem = stem
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/-{2,}/g, "-")
      .replace(/^[-_]+|[-_]+$/g, "");
    if (!stem) return "";
    if (/^\d/.test(stem)) stem = "c-" + stem;
    return stem;
  }

  function titleCase(slug) {
    return slug
      .split(/[-_]/)
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  function validateSlug(label, value) {
    const v = String(value || "").trim();
    if (!v) return [`${label}: обязательное поле`];
    const errs = [];
    if (/\s/.test(v)) errs.push(`${label}: без пробелов`);
    if (v !== v.toLowerCase()) errs.push(`${label}: только нижний регистр`);
    if (!SLUG_RE.test(v)) {
      errs.push(`${label}: латиница, начинается с буквы; a-z 0-9 - _`);
    }
    return errs;
  }

  let backIdAuto = false;

  function suggestedBackId() {
    const sid = $("seriesId").value.trim().toLowerCase();
    return sid ? "card-back-" + sid : "";
  }

  function applyAutoBackId() {
    if (!$("backFile").files?.length) return;
    const suggested = suggestedBackId();
    if (!suggested) return;
    const cur = $("cardBackId").value.trim().toLowerCase();
    if (!cur || backIdAuto || cur === "card-back" || /^card-back-/.test(cur)) {
      $("cardBackId").value = suggested;
      backIdAuto = true;
    }
  }

  function syncBackFileUi() {
    const file = $("backFile").files?.[0];
    const nameEl = $("backFileName");
    const clearBtn = $("backClearBtn");
    if (file) {
      nameEl.textContent = file.name;
      nameEl.classList.remove("is-empty");
      clearBtn.hidden = false;
    } else {
      nameEl.textContent = "файл не выбран — будет дефолт";
      nameEl.classList.add("is-empty");
      clearBtn.hidden = true;
    }
  }

  function clearBackFile() {
    $("backFile").value = "";
    syncBackFileUi();
    if (backIdAuto) {
      $("cardBackId").value = "";
      backIdAuto = false;
    }
  }

  function syncBoosterDefaults() {
    const sid = $("seriesId").value.trim().toLowerCase();
    const sname = $("seriesName").value.trim();
    if (sid && !$("boosterId").value) $("boosterId").value = sid;
    if (sname && !$("boosterName").value) $("boosterName").value = sname;
    if (sid && !$("drawId").value) $("drawId").value = "draw-" + sid + "-001";
  }

  function renderPills() {
    const labels = ["Серия", "Карты", "Бустер", "Тираж"];
    $("stepPills").innerHTML = labels
      .map(
        (lab, i) =>
          `<span class="step-pill${i === step ? " on" : ""}">${i + 1}. ${lab}</span>`
      )
      .join("");
  }

  function syncWeightsToCards() {
    const present = new Set(cards.map((c) => c.rarity));
    RARITIES.forEach((r) => {
      const el = document.querySelector(`[data-weight="${r}"]`);
      if (!el) return;
      if (!present.has(r)) {
        el.value = "0";
      } else if (Number(el.value) === 0) {
        el.value = String(DEFAULT_WEIGHTS[r] || 1);
      }
    });
    updatePercents();
  }

  function showStep() {
    document.querySelectorAll(".step").forEach((el) => {
      el.classList.toggle("active", Number(el.dataset.step) === step);
    });
    $("btnPrev").disabled = step === 0;
    $("btnNext").hidden = step === STEP_COUNT - 1;
    $("btnBuild").hidden = step !== STEP_COUNT - 1;
    if (step === 2) syncBoosterDefaults();
    if (step === 3) {
      syncWeightsToCards();
      updatePercents();
    }
    renderPills();
  }

  function renderCards() {
    const root = $("cardsList");
    root.innerHTML = cards
      .map(
        (c, i) => `
      <div class="card-row" data-i="${i}">
        <img class="thumb" src="${c.url}" alt="" />
        <div class="card-fields">
          <label class="field">ID карты
            <input type="text" data-f="card_id" value="${escapeAttr(c.card_id)}" spellcheck="false" />
          </label>
          <label class="field">Имя
            <input type="text" data-f="name" value="${escapeAttr(c.name)}" />
          </label>
          <label class="field">Редкость
            <select data-f="rarity">
              ${RARITIES.map(
                (r) =>
                  `<option value="${r}"${r === c.rarity ? " selected" : ""}>${r}</option>`
              ).join("")}
            </select>
          </label>
          <label class="field">
            <button type="button" class="danger" data-rm="${i}">Удалить</button>
          </label>
          <label class="field full">Описание (лор)
            <textarea data-f="story">${escapeHtml(c.story)}</textarea>
          </label>
        </div>
      </div>`
      )
      .join("");
  }

  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }
  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;");
  }

  function addFiles(fileList) {
    for (const file of fileList) {
      if (!file.type.startsWith("image/")) continue;
      const id = slugGuess(file.name);
      cards.push({
        file,
        card_id: id,
        name: titleCase(id) || file.name,
        rarity: "common",
        story: "",
        url: URL.createObjectURL(file),
      });
    }
    renderCards();
    setStatus(`Карт: ${cards.length}`);
  }

  function collectMeta() {
    const weights = {};
    RARITIES.forEach((r) => {
      const el = document.querySelector(`[data-weight="${r}"]`);
      weights[r] = el ? Number(el.value) || 0 : DEFAULT_WEIGHTS[r];
    });
    return {
      series: {
        series_id: $("seriesId").value.trim().toLowerCase(),
        name: $("seriesName").value.trim(),
        card_back_id: $("cardBackId").value.trim().toLowerCase(),
        sort_order: Number($("sortOrder").value) || 0,
      },
      booster: {
        booster_id: $("boosterId").value.trim().toLowerCase(),
        name: $("boosterName").value.trim(),
        promo_image_url: $("promoUrl").value.trim(),
      },
      draw: {
        draw_id: $("drawId").value.trim().toLowerCase(),
        name: $("drawName").value.trim(),
        cost_points: Number($("costPoints").value) || 0,
        cards_per_open: Number($("cardsPerOpen").value) || 1,
        daily_limit: Number($("dailyLimit").value) || 0,
        rarity_weights: weights,
        status: "queued",
      },
      cards: cards.map((c) => ({
        card_id: c.card_id.trim().toLowerCase(),
        name: c.name.trim(),
        rarity: c.rarity,
        story: c.story.trim(),
      })),
    };
  }

  function validateLocalStep(stepIdx) {
    const errs = [];
    if (stepIdx === 0) {
      errs.push(...validateSlug("ID серии", $("seriesId").value));
      if (!$("seriesName").value.trim()) errs.push("Название серии: обязательное поле");
      const back = $("cardBackId").value.trim().toLowerCase();
      if (back && !BACK_RE.test(back)) {
        errs.push("ID рубашки: card-back или card-back-…");
      }
      const file = $("backFile").files?.[0];
      if (file && !/\.svg$/i.test(file.name)) {
        errs.push("Рубашка: только .svg");
      }
    } else if (stepIdx === 1) {
      if (!cards.length) errs.push("Добавьте хотя бы одну карту");
      const seen = new Set();
      cards.forEach((c, i) => {
        const prefix = `Карта #${i + 1}`;
        errs.push(...validateSlug(`${prefix} ID`, c.card_id));
        const cid = c.card_id.trim().toLowerCase();
        if (cid) {
          if (seen.has(cid)) errs.push(`${prefix}: дубль ID «${cid}»`);
          seen.add(cid);
        }
        if (!c.name.trim()) errs.push(`${prefix}: имя обязательно`);
        if (!c.story.trim()) errs.push(`${prefix}: описание обязательно`);
      });
    } else if (stepIdx === 2) {
      errs.push(...validateSlug("ID бустера", $("boosterId").value));
      if (!$("boosterName").value.trim()) errs.push("Название бустера: обязательное поле");
    } else if (stepIdx === 3) {
      errs.push(...validateSlug("ID тиража", $("drawId").value));
      if (!$("drawName").value.trim()) errs.push("Название тиража: обязательное поле");
      if (Number($("costPoints").value) <= 0) errs.push("Цена: должна быть > 0");
    }
    return errs;
  }

  function payloadForStep(stepIdx) {
    if (stepIdx === 0) {
      return {
        series_id: $("seriesId").value.trim().toLowerCase(),
        name: $("seriesName").value.trim(),
      };
    }
    if (stepIdx === 1) {
      return {
        cards: cards.map((c) => ({
          card_id: c.card_id.trim().toLowerCase(),
          name: c.name.trim(),
        })),
      };
    }
    if (stepIdx === 2) {
      return {
        booster_id: $("boosterId").value.trim().toLowerCase(),
        name: $("boosterName").value.trim(),
      };
    }
    return {
      draw_id: $("drawId").value.trim().toLowerCase(),
      name: $("drawName").value.trim(),
    };
  }

  async function checkConflicts(stepIdx) {
    const res = await fetch("/api/cards/series-pack/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step: stepIdx, payload: payloadForStep(stepIdx) }),
    });
    const j = await res.json();
    if (!res.ok) {
      return [j.error || "Ошибка проверки дублей"];
    }
    return j.errors || [];
  }

  async function goNext() {
    const localErrs = validateLocalStep(step);
    if (localErrs.length) {
      setStatus(localErrs.join("\n"), "err");
      return;
    }
    $("btnNext").disabled = true;
    setStatus("Проверка дублей в БД…");
    try {
      const dbErrs = await checkConflicts(step);
      if (dbErrs.length) {
        setStatus(dbErrs.join("\n"), "err");
        return;
      }
      if (step < STEP_COUNT - 1) {
        step += 1;
        showStep();
        setStatus("OK");
      }
    } catch (e) {
      setStatus(String(e), "err");
    } finally {
      $("btnNext").disabled = false;
    }
  }

  function updatePercents() {
    let total = 0;
    const vals = {};
    RARITIES.forEach((r) => {
      const el = document.querySelector(`[data-weight="${r}"]`);
      vals[r] = el ? Number(el.value) || 0 : 0;
      total += vals[r];
    });
    RARITIES.forEach((r) => {
      const pct = document.querySelector(`[data-pct="${r}"]`);
      if (pct) {
        pct.textContent =
          total > 0 ? ((vals[r] / total) * 100).toFixed(1) + "%" : "0%";
      }
    });
  }

  function renderWeights() {
    $("weights").innerHTML = RARITIES.map(
      (r) => `
      <div class="weight-row">
        <span style="min-width:88px">${r}</span>
        <input type="number" min="0" step="0.1" data-weight="${r}" value="${DEFAULT_WEIGHTS[r]}" />
        <span class="pct" data-pct="${r}">0%</span>
      </div>`
    ).join("");
    $("weights").addEventListener("input", updatePercents);
    updatePercents();
  }

  async function buildZip() {
    for (let s = 0; s < STEP_COUNT; s++) {
      const localErrs = validateLocalStep(s);
      if (localErrs.length) {
        step = s;
        showStep();
        setStatus(localErrs.join("\n"), "err");
        return;
      }
    }
    setStatus("Проверка дублей…");
    for (let s = 0; s < STEP_COUNT; s++) {
      try {
        const dbErrs = await checkConflicts(s);
        if (dbErrs.length) {
          step = s;
          showStep();
          setStatus(dbErrs.join("\n"), "err");
          return;
        }
      } catch (e) {
        setStatus(String(e), "err");
        return;
      }
    }

    const meta = collectMeta();
    const fd = new FormData();
    fd.append("meta", JSON.stringify(meta));
    const back = $("backFile").files?.[0];
    if (back) fd.append("back", back, back.name);
    for (const c of cards) {
      fd.append("card_" + c.card_id.trim().toLowerCase(), c.file, c.file.name);
    }

    setStatus("Сборка ZIP…");
    $("btnBuild").disabled = true;
    try {
      const res = await fetch("/api/cards/series-pack/build", {
        method: "POST",
        body: fd,
      });
      if (!res.ok) {
        let msg = "Ошибка " + res.status;
        try {
          const j = await res.json();
          if (j.errors) msg = j.errors.join("\n");
          else if (j.error) msg = j.error;
        } catch (_) {
          /* ignore */
        }
        setStatus(msg, "err");
        return;
      }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") || "";
      const m = /filename="([^"]+)"/.exec(cd);
      const name = m ? m[1] : "series-pack.zip";
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
      setStatus(
        "ZIP скачан: " +
          name +
          "\nОбязательно отправьте архив: https://t.me/klon_008",
        "ok"
      );
    } catch (e) {
      setStatus(String(e), "err");
    } finally {
      $("btnBuild").disabled = false;
    }
  }

  async function runImport(dryRun) {
    const file = $("importFile").files?.[0];
    if (!file) {
      setStatus("Выберите ZIP", "err");
      return;
    }
    const fd = new FormData();
    fd.append("file", file, file.name);
    fd.append("dry_run", dryRun ? "1" : "0");
    const applyFe = $("applyFrontend").checked;
    fd.append("apply_frontend", applyFe ? "1" : "0");
    if (applyFe) {
      fd.append("frontend_root", $("frontendRoot").value.trim());
    }

    setStatus(dryRun ? "Dry-run…" : "Импорт…");
    $("importLog").textContent = "…";
    try {
      const res = await fetch("/api/cards/series-pack/import", {
        method: "POST",
        body: fd,
      });
      const j = await res.json();
      const log = (j.log || []).join("\n") || "—";
      const errs = j.errors || [];
      const warns = j.warnings || [];
      let text = log;
      if (errs.length) text += "\n\nОшибки:\n" + errs.join("\n");
      if (warns.length) text += "\n\nПредупреждения:\n" + warns.join("\n");
      if (j.ok && j.draw_id) {
        text += `\n\nseries=${j.series_id} draw=${j.draw_id} cards=${j.cards_count}`;
        if (!dryRun) text += "\n→ Активируйте тираж в cards-admin";
      }
      $("importLog").textContent = text;
      setStatus(
        j.ok ? (dryRun ? "Dry-run OK" : "Импорт OK") : "Ошибка импорта",
        j.ok ? "ok" : "err"
      );
    } catch (e) {
      setStatus(String(e), "err");
      $("importLog").textContent = String(e);
    }
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.mode;
      $("panel-build").classList.toggle("active", mode === "build");
      $("panel-import").classList.toggle("active", mode === "import");
    });
  });

  $("btnPrev").addEventListener("click", () => {
    if (step > 0) {
      step -= 1;
      showStep();
    }
  });
  $("btnNext").addEventListener("click", () => {
    goNext();
  });
  $("btnBuild").addEventListener("click", buildZip);

  $("backPickBtn").addEventListener("click", () => $("backFile").click());
  $("backClearBtn").addEventListener("click", clearBackFile);
  $("backFile").addEventListener("change", () => {
    syncBackFileUi();
    if ($("backFile").files?.length) {
      const suggested = suggestedBackId();
      if (suggested) {
        $("cardBackId").value = suggested;
        backIdAuto = true;
      } else {
        // серии ещё нет — ждём заполнения ID серии
        backIdAuto = true;
      }
    }
  });
  $("seriesId").addEventListener("input", () => {
    if ($("backFile").files?.length) applyAutoBackId();
  });
  $("cardBackId").addEventListener("input", () => {
    // ручной ввод — больше не перезаписываем автоматом, пока не сменится файл
    const suggested = suggestedBackId();
    const cur = $("cardBackId").value.trim().toLowerCase();
    backIdAuto = Boolean(suggested && cur === suggested);
  });

  const drop = $("cardDrop");
  drop.addEventListener("click", () => $("cardFiles").click());
  $("cardFiles").addEventListener("change", (e) => {
    addFiles(e.target.files || []);
    e.target.value = "";
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    addFiles(e.dataTransfer.files || []);
  });
  document.addEventListener("paste", (e) => {
    if (!$("panel-build").classList.contains("active") || step !== 1) return;
    const items = e.clipboardData?.items;
    if (!items) return;
    const files = [];
    for (const it of items) {
      if (it.type.startsWith("image/")) {
        const f = it.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) addFiles(files);
  });

  $("cardsList").addEventListener("input", (e) => {
    const row = e.target.closest(".card-row");
    if (!row) return;
    const i = Number(row.dataset.i);
    const f = e.target.dataset.f;
    if (!f || !cards[i]) return;
    cards[i][f] = e.target.value;
  });
  $("cardsList").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-rm]");
    if (!btn) return;
    const i = Number(btn.dataset.rm);
    if (cards[i]?.url) URL.revokeObjectURL(cards[i].url);
    cards.splice(i, 1);
    renderCards();
  });

  $("btnDryRun").addEventListener("click", () => runImport(true));
  $("btnImport").addEventListener("click", () => runImport(false));

  function syncImportFileUi() {
    const file = $("importFile").files?.[0];
    const nameEl = $("importFileName");
    const clearBtn = $("importClearBtn");
    if (file) {
      nameEl.textContent = file.name;
      nameEl.classList.remove("is-empty");
      clearBtn.hidden = false;
    } else {
      nameEl.textContent = "файл не выбран";
      nameEl.classList.add("is-empty");
      clearBtn.hidden = true;
    }
  }
  $("importPickBtn").addEventListener("click", () => $("importFile").click());
  $("importClearBtn").addEventListener("click", () => {
    $("importFile").value = "";
    syncImportFileUi();
  });
  $("importFile").addEventListener("change", syncImportFileUi);

  $("applyFrontend").addEventListener("change", () => {
    $("feRootWrap").style.opacity = $("applyFrontend").checked ? "1" : "0.5";
  });

  renderWeights();
  showStep();
  $("feRootWrap").style.opacity = "0.5";

  fetch("/api/cards/series-pack/config")
    .then((r) => r.json())
    .then((cfg) => {
      if (cfg.frontend_root) $("frontendRoot").value = cfg.frontend_root;
      if (cfg.default_card_back_id && !$("cardBackId").placeholder) {
        $("cardBackId").placeholder = cfg.default_card_back_id;
      }
    })
    .catch(() => {});
})();
