(function () {
  "use strict";

  const statusBar = document.getElementById("statusBar");
  const pointsBody = document.getElementById("pointsBody");
  const pointsFilter = document.getElementById("pointsFilter");
  const queueBody = document.getElementById("queueBody");
  const queuePlaying = document.getElementById("queuePlaying");
  const queueTogglePause = document.getElementById("queueTogglePause");
  const queueSkip = document.getElementById("queueSkip");
  const ordersStatus = document.getElementById("ordersStatus");
  const ordersToggle = document.getElementById("ordersToggle");
  const blockYmExplicit = document.getElementById("blockYmExplicit");
  const queueMaxSize = document.getElementById("queueMaxSize");
  const queueMaxDurationSec = document.getElementById("queueMaxDurationSec");
  const queueWatchdogExtraSec = document.getElementById("queueWatchdogExtraSec");
  const queueUserCooldownSec = document.getElementById("queueUserCooldownSec");
  const queueSrCost = document.getElementById("queueSrCost");
  const rouletteAuto = document.getElementById("rouletteAuto");
  const rouletteCollectSec = document.getElementById("rouletteCollectSec");
  const rouletteCooldownSec = document.getElementById("rouletteCooldownSec");
  const rouletteStatusLine = document.getElementById("rouletteStatusLine");
  const rouletteBank = document.getElementById("rouletteBank");
  const rouletteBetsBody = document.getElementById("rouletteBetsBody");
  const rouletteLastResult = document.getElementById("rouletteLastResult");
  const rouletteOpen = document.getElementById("rouletteOpen");
  const rouletteSpin = document.getElementById("rouletteSpin");
  const rouletteTopUp = document.getElementById("rouletteTopUp");
  const rouletteCancel = document.getElementById("rouletteCancel");
  const racesAuto = document.getElementById("racesAuto");
  const racesCollectSec = document.getElementById("racesCollectSec");
  const racesRaceDelaySec = document.getElementById("racesRaceDelaySec");
  const racesCooldownSec = document.getElementById("racesCooldownSec");
  const racesStatusLine = document.getElementById("racesStatusLine");
  const racesBank = document.getElementById("racesBank");
  const racesLineupBody = document.getElementById("racesLineupBody");
  const racesBetsBody = document.getElementById("racesBetsBody");
  const racesLastResult = document.getElementById("racesLastResult");
  const racesPrincessStatsBody = document.getElementById("racesPrincessStatsBody");
  const racesOpen = document.getElementById("racesOpen");
  const racesStart = document.getElementById("racesStart");
  const racesTopUp = document.getElementById("racesTopUp");
  const racesCancel = document.getElementById("racesCancel");
  const pollTitle = document.getElementById("pollTitle");
  const pollDurationMin = document.getElementById("pollDurationMin");
  const pollOptionsList = document.getElementById("pollOptionsList");
  const pollStatusLine = document.getElementById("pollStatusLine");
  const pollPool = document.getElementById("pollPool");
  const pollOptionsBody = document.getElementById("pollOptionsBody");
  const pollBetsBody = document.getElementById("pollBetsBody");
  const pollLastResult = document.getElementById("pollLastResult");
  const pollCreateCard = document.getElementById("pollCreateCard");
  const pollResolveRow = document.getElementById("pollResolveRow");
  const pollResolveSelect = document.getElementById("pollResolveSelect");
  const pollLock = document.getElementById("pollLock");
  const pollResolve = document.getElementById("pollResolve");
  const pollResolveConfirm = document.getElementById("pollResolveConfirm");
  const pollCancel = document.getElementById("pollCancel");
  const pollCreate = document.getElementById("pollCreate");
  const pollAddOption = document.getElementById("pollAddOption");

  let allPoints = [];
  let ordersEnabled = true;
  let blockYmExplicitEnabled = true;
  let queuePaused = false;
  let roulettePollTimer = null;
  let racesPollTimer = null;
  let pollsPollTimer = null;
  let pollOptionCount = 0;

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

  function displayName(p) {
    const name = p.user_name == null ? "" : String(p.user_name).trim();
    return name || "—";
  }

  function renderPoints() {
    const q = pointsFilter.value.trim().toLowerCase();
    const items = q
      ? allPoints.filter(
          (p) =>
            p.user_id.toLowerCase().includes(q) ||
            (p.user_name && p.user_name.toLowerCase().includes(q))
        )
      : allPoints;

    if (!items.length) {
      pointsBody.innerHTML =
        '<tr><td colspan="4" class="empty">' +
        (q ? "Ничего не найдено" : "Нет записей") +
        "</td></tr>";
      return;
    }

    pointsBody.innerHTML = items
      .map(
        (p) => `
      <tr data-user-id="${esc(p.user_id)}">
        <td class="mono">${esc(p.user_id)}</td>
        <td>${esc(displayName(p))}</td>
        <td>
          <input type="number" class="balance-input" min="0" value="${esc(p.balance)}" data-user-id="${esc(p.user_id)}" />
        </td>
        <td class="actions">
          <button type="button" class="small primary btn-save" data-user-id="${esc(p.user_id)}">Сохранить</button>
          <button type="button" class="small danger btn-delete" data-user-id="${esc(p.user_id)}">Удалить</button>
        </td>
      </tr>`
      )
      .join("");
  }

  async function loadPoints() {
    setStatus("Загрузка points…");
    try {
      const data = await api("GET", "/api/points");
      allPoints = data.items || [];
      renderPoints();
      setStatus(`Загружено записей: ${allPoints.length}`, "ok");
    } catch (e) {
      pointsBody.innerHTML =
        '<tr><td colspan="4" class="empty">Ошибка загрузки</td></tr>';
      setStatus(e.message, "err");
    }
  }

  async function saveBalance(userId, input) {
    const balance = parseInt(input.value, 10);
    if (Number.isNaN(balance) || balance < 0) {
      setStatus("balance должен быть >= 0", "err");
      return;
    }
    setStatus(`Сохранение ${userId}…`);
    try {
      const data = await api("PUT", `/api/points/${encodeURIComponent(userId)}`, {
        balance,
      });
      const idx = allPoints.findIndex((p) => p.user_id === userId);
      if (idx >= 0) allPoints[idx].balance = data.balance;
      setStatus(`Сохранено: ${userId} → ${data.balance}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  async function deletePoint(userId) {
    if (!confirm(`Удалить пользователя ${userId}?`)) return;
    setStatus(`Удаление ${userId}…`);
    try {
      await api("DELETE", `/api/points/${encodeURIComponent(userId)}`);
      allPoints = allPoints.filter((p) => p.user_id !== userId);
      renderPoints();
      setStatus(`Удалено: ${userId}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  document.getElementById("pointsAddForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const userId = document.getElementById("addUserId").value.trim();
    const userName = document.getElementById("addUserName").value.trim();
    const balance = parseInt(document.getElementById("addBalance").value, 10);
    if (!userId) {
      setStatus("user_id обязателен", "err");
      return;
    }
    if (Number.isNaN(balance) || balance < 0) {
      setStatus("balance должен быть >= 0", "err");
      return;
    }
    setStatus(`Создание ${userId}…`);
    try {
      const body = { user_id: userId, balance };
      if (userName) body.user_name = userName;
      const data = await api("POST", "/api/points", body);
      allPoints.push({
        user_id: data.user_id,
        user_name: data.user_name || "",
        balance: data.balance,
      });
      allPoints.sort(
        (a, b) => b.balance - a.balance || a.user_id.localeCompare(b.user_id)
      );
      renderPoints();
      document.getElementById("addUserId").value = "";
      document.getElementById("addUserName").value = "";
      document.getElementById("addBalance").value = "0";
      setStatus(`Добавлено: ${data.user_id} → ${data.balance}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  pointsBody.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const userId = btn.dataset.userId;
    if (!userId) return;
    if (btn.classList.contains("btn-save")) {
      const input = pointsBody.querySelector(
        `.balance-input[data-user-id="${CSS.escape(userId)}"]`
      );
      if (input) saveBalance(userId, input);
    } else if (btn.classList.contains("btn-delete")) {
      deletePoint(userId);
    }
  });

  pointsFilter.addEventListener("input", renderPoints);
  document.getElementById("pointsRefresh").addEventListener("click", loadPoints);

  function renderOrdersControl() {
    if (ordersEnabled) {
      ordersStatus.textContent = "Статус: заказы включены";
      ordersStatus.className = "orders-status on";
      ordersToggle.textContent = "ОТКЛЮЧИТЬ ЗАКАЗ МУЗЫКИ";
      ordersToggle.className = "danger";
    } else {
      ordersStatus.textContent = "Статус: заказы отключены";
      ordersStatus.className = "orders-status off";
      ordersToggle.textContent = "Включить заказы музыки";
      ordersToggle.className = "primary";
    }
    if (blockYmExplicit) {
      blockYmExplicit.checked = blockYmExplicitEnabled;
    }
  }

  async function loadOrdersState() {
    const data = await api("GET", "/api/song-request");
    ordersEnabled = !!data.orders_enabled;
    blockYmExplicitEnabled = data.block_ym_explicit !== false;
    renderOrdersControl();
    renderQueueSettings(data);
  }

  function renderQueueSettings(data) {
    if (queueMaxSize && data.max_queue_size != null) {
      queueMaxSize.value = data.max_queue_size;
    }
    if (queueMaxDurationSec && data.max_duration_sec != null) {
      queueMaxDurationSec.value = data.max_duration_sec;
    }
    if (queueWatchdogExtraSec && data.track_watchdog_extra_sec != null) {
      queueWatchdogExtraSec.value = data.track_watchdog_extra_sec;
    }
    if (queueUserCooldownSec && data.user_cooldown_sec != null) {
      queueUserCooldownSec.value = data.user_cooldown_sec;
    }
    if (queueSrCost && data.sr_cost != null) {
      queueSrCost.value = data.sr_cost;
    }
  }

  async function saveQueueSettings() {
    const maxSize = parseInt(queueMaxSize.value, 10);
    const maxDur = parseInt(queueMaxDurationSec.value, 10);
    const watchdogExtra = parseInt(queueWatchdogExtraSec.value, 10);
    const cooldown = parseInt(queueUserCooldownSec.value, 10);
    const srCost = parseInt(queueSrCost.value, 10);
    if (Number.isNaN(maxSize) || maxSize < 1) {
      setStatus("Макс. очередь >= 1", "err");
      return;
    }
    if (Number.isNaN(maxDur) || maxDur < 1) {
      setStatus("Макс. длительность >= 1", "err");
      return;
    }
    if (Number.isNaN(watchdogExtra) || watchdogExtra < 0) {
      setStatus("Watchdog запас >= 0", "err");
      return;
    }
    if (Number.isNaN(cooldown) || cooldown < 0) {
      setStatus("Кулдаун !sr >= 0", "err");
      return;
    }
    if (Number.isNaN(srCost) || srCost < 0) {
      setStatus("Стоимость !sr >= 0", "err");
      return;
    }
    setStatus("Сохранение настроек очереди…");
    try {
      const data = await api("PUT", "/api/song-request", {
        max_queue_size: maxSize,
        max_duration_sec: maxDur,
        track_watchdog_extra_sec: watchdogExtra,
        user_cooldown_sec: cooldown,
        sr_cost: srCost,
      });
      renderQueueSettings(data);
      setStatus("Настройки очереди сохранены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  async function toggleOrders() {
    const next = !ordersEnabled;
    if (!next) {
      const ok = confirm(
        "Отключить заказы музыки?\n\nОчередь будет очищена, принцессы вернутся заказчикам."
      );
      if (!ok) return;
    }
    setStatus(next ? "Включение заказов…" : "Отключение заказов…");
    try {
      const data = await api("PUT", "/api/song-request", { orders_enabled: next });
      ordersEnabled = !!data.orders_enabled;
      if (typeof data.block_ym_explicit === "boolean") {
        blockYmExplicitEnabled = data.block_ym_explicit;
      }
      renderOrdersControl();
      await loadQueue();
      setStatus(ordersEnabled ? "Заказы включены" : "Заказы отключены, очередь очищена", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  async function toggleBlockYmExplicit() {
    if (!blockYmExplicit) return;
    const next = !!blockYmExplicit.checked;
    setStatus(next ? "Включение блокировки explicit…" : "Отключение блокировки explicit…");
    try {
      const data = await api("PUT", "/api/song-request", { block_ym_explicit: next });
      blockYmExplicitEnabled = data.block_ym_explicit !== false;
      renderOrdersControl();
      setStatus(
        blockYmExplicitEnabled
          ? "Блокировка explicit включена"
          : "Блокировка explicit отключена",
        "ok"
      );
    } catch (e) {
      blockYmExplicit.checked = blockYmExplicitEnabled;
      setStatus(e.message, "err");
    }
  }

  async function syncUserNames() {
    setStatus("Запрос списка зрителей из чата…");
    try {
      const data = await api("POST", "/api/user-names/sync");
      await loadPoints();
      setStatus(
        `Ники обновлены: ${data.updated} из ${data.total_online} онлайн`,
        "ok"
      );
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  function formatPlaying(track) {
    if (!track) return '<span class="empty">ничего не играет</span>';
    const who = track.requested_by_name || track.requested_by || "?";
    const title = track.title || track.video_id || "—";
    return `<strong>${esc(who)}</strong> — ${esc(title)} <span class="mono">(${esc(track.video_id)})</span>`;
  }

  function renderPauseButton(playing, paused) {
    queuePaused = !!paused;
    if (!playing) {
      queueTogglePause.disabled = true;
      queueTogglePause.textContent = "Пауза";
      queueSkip.disabled = true;
      return;
    }
    queueTogglePause.disabled = false;
    queueTogglePause.textContent = paused ? "Продолжить" : "Пауза";
    queueSkip.disabled = false;
  }

  async function loadQueue() {
    setStatus("Загрузка очереди…");
    try {
      await loadOrdersState();
      const data = await api("GET", "/api/queue");
      queuePlaying.innerHTML = formatPlaying(data.playing);
      renderPauseButton(data.playing, data.paused);
      const waiting = data.waiting || [];
      if (!waiting.length) {
        queueBody.innerHTML =
          '<tr><td colspan="5" class="empty">Очередь пуста</td></tr>';
      } else {
        queueBody.innerHTML = waiting
          .map(
            (t) => `
          <tr>
            <td>${esc(t.index)}</td>
            <td>${esc(t.title || "—")}</td>
            <td>${esc(t.requested_by_name || t.requested_by)}</td>
            <td class="mono">${esc(t.video_id)}</td>
            <td>
              <button type="button" class="small danger btn-queue-del" data-index="${esc(t.index)}">Удалить</button>
            </td>
          </tr>`
          )
          .join("");
      }
      setStatus(`Очередь: ${waiting.length} в ожидании`, "ok");
    } catch (e) {
      queueBody.innerHTML =
        '<tr><td colspan="5" class="empty">Ошибка загрузки</td></tr>';
      setStatus(e.message, "err");
    }
  }

  queueBody.addEventListener("click", async (e) => {
    const btn = e.target.closest(".btn-queue-del");
    if (!btn) return;
    const index = btn.dataset.index;
    if (!confirm(`Удалить трек #${index} из очереди?`)) return;
    setStatus(`Удаление трека #${index}…`);
    try {
      await api("DELETE", `/api/queue/waiting/${index}`);
      await loadQueue();
      setStatus(`Трек #${index} удалён`, "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  document.getElementById("queueRefresh").addEventListener("click", loadQueue);
  queueTogglePause.addEventListener("click", async () => {
    setStatus(queuePaused ? "Продолжение…" : "Пауза…");
    try {
      const data = await api("POST", "/api/queue/toggle-pause");
      renderPauseButton(true, data.paused);
      setStatus(data.paused ? "Воспроизведение на паузе" : "Воспроизведение продолжено", "ok");
    } catch (err) {
      setStatus(err.message, "err");
      await loadQueue();
    }
  });
  queueSkip.addEventListener("click", async () => {
    setStatus("Пропуск трека…");
    try {
      await api("POST", "/api/queue/skip");
      await loadQueue();
      setStatus("Трек пропущен", "ok");
    } catch (err) {
      setStatus(err.message, "err");
      await loadQueue();
    }
  });
  document.getElementById("syncUserNames").addEventListener("click", syncUserNames);
  ordersToggle.addEventListener("click", toggleOrders);
  if (blockYmExplicit) {
    blockYmExplicit.addEventListener("change", toggleBlockYmExplicit);
  }
  const queueSaveSettings = document.getElementById("queueSaveSettings");
  if (queueSaveSettings) {
    queueSaveSettings.addEventListener("click", saveQueueSettings);
  }

  function formatLastResult(last) {
    if (!last) return '<span class="empty">ещё не было спинов</span>';
    const winners = (last.winners || [])
      .filter((w) => w.actual > 0)
      .map((w) => `${esc(w.user_name)}: ${esc(w.actual)}`)
      .join(", ");
    const bankNote = last.bankrupted ? " (выплаты урезаны)" : "";
    return `<strong>${esc(last.label)}</strong>${bankNote}${
      winners ? `<br/>Победители: ${winners}` : "<br/>Без победителей"
    }`;
  }

  function renderRoulette(data) {
    const state = data.state || "IDLE";
    const timer = data.timer_sec || 0;
    rouletteAuto.checked = !!data.auto_enabled;
    rouletteCollectSec.value = data.collect_sec || 60;
    rouletteCooldownSec.value = data.cooldown_sec || 180;
    rouletteBank.textContent = String(data.bank ?? "—");
    rouletteStatusLine.textContent =
      timer > 0
        ? `Состояние: ${state}, осталось ~${timer} сек`
        : `Состояние: ${state}`;

    const manual = !data.auto_enabled;
    const isOpen = state === "OPEN";
    const isSpinWait = state === "SPIN_WAIT";
    const isIdle = state === "IDLE";
    rouletteOpen.disabled = !manual || !isIdle;
    rouletteSpin.disabled = !isOpen && !isSpinWait;
    rouletteCancel.disabled = !isOpen && !isSpinWait;

    const bets = data.bets || [];
    if (!bets.length) {
      rouletteBetsBody.innerHTML =
        '<tr><td colspan="3" class="empty">Нет ставок</td></tr>';
    } else {
      rouletteBetsBody.innerHTML = bets
        .map(
          (b) => `
        <tr>
          <td>${esc(b.user_name || b.user_id)}</td>
          <td>${esc(b.label || b.bet_type)}</td>
          <td>${esc(b.amount)}</td>
        </tr>`
        )
        .join("");
    }

    rouletteLastResult.innerHTML = formatLastResult(data.last_result);
  }

  function stopRoulettePoll() {
    if (roulettePollTimer) {
      clearInterval(roulettePollTimer);
      roulettePollTimer = null;
    }
  }

  function startRoulettePollIfNeeded(data) {
    stopRoulettePoll();
    if (data.state === "OPEN" || data.state === "SPIN_WAIT" || data.state === "COOLDOWN") {
      roulettePollTimer = setInterval(() => loadRoulette(true), 2500);
    }
  }

  async function loadRoulette(silent) {
    if (!silent) setStatus("Загрузка рулетки…");
    try {
      const data = await api("GET", "/api/roulette");
      renderRoulette(data);
      startRoulettePollIfNeeded(data);
      if (!silent) setStatus(`Рулетка: ${data.state}`, "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  async function saveRouletteSettings() {
    const collect = parseInt(rouletteCollectSec.value, 10);
    const cooldown = parseInt(rouletteCooldownSec.value, 10);
    if (Number.isNaN(collect) || collect < 10) {
      setStatus("collect_sec >= 10", "err");
      return;
    }
    if (Number.isNaN(cooldown) || cooldown < 10) {
      setStatus("cooldown_sec >= 10", "err");
      return;
    }
    setStatus("Сохранение настроек рулетки…");
    try {
      const data = await api("PUT", "/api/roulette", {
        auto_enabled: rouletteAuto.checked,
        collect_sec: collect,
        cooldown_sec: cooldown,
      });
      renderRoulette(data);
      setStatus("Настройки рулетки сохранены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  document.getElementById("rouletteSaveSettings").addEventListener("click", saveRouletteSettings);
  document.getElementById("rouletteRefresh").addEventListener("click", () => loadRoulette(false));

  rouletteOpen.addEventListener("click", async () => {
    setStatus("Открытие стола…");
    try {
      const data = await api("POST", "/api/roulette/open");
      renderRoulette(data);
      startRoulettePollIfNeeded(data);
      setStatus("Стол открыт", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  rouletteSpin.addEventListener("click", async () => {
    if (!confirm("Крутить рулетку сейчас?")) return;
    setStatus("Спин…");
    try {
      const data = await api("POST", "/api/roulette/spin");
      renderRoulette(data);
      startRoulettePollIfNeeded(data);
      setStatus("Спин выполнен", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  rouletteTopUp.addEventListener("click", async () => {
    const raw = prompt("Сколько баллов добавить в казну?", "5000");
    if (raw == null) return;
    const amount = parseInt(raw, 10);
    if (Number.isNaN(amount) || amount <= 0) {
      setStatus("Сумма должна быть > 0", "err");
      return;
    }
    setStatus("Пополнение казны…");
    try {
      const data = await api("POST", "/api/roulette/bank", { amount });
      renderRoulette(data);
      setStatus(`Казна пополнена на ${amount}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  rouletteCancel.addEventListener("click", async () => {
    if (!confirm("Отменить раунд и вернуть ставки?")) return;
    setStatus("Отмена раунда…");
    try {
      const data = await api("POST", "/api/roulette/cancel");
      renderRoulette(data);
      stopRoulettePoll();
      setStatus("Раунд отменён", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  function formatRacesLastResult(last) {
    if (!last) return '<span class="empty">ещё не было забегов</span>';
    const winners = (last.winners || [])
      .filter((w) => w.actual > 0)
      .map((w) => `${esc(w.user_name)}: ${esc(w.actual)}`)
      .join(", ");
    const bankNote = last.bankrupted ? " (выплаты урезаны)" : "";
    return `<strong>№${esc(last.winner_horse)} ${esc(last.winner_name)}</strong>${bankNote}${
      winners ? `<br/>Победители: ${winners}` : "<br/>Без победителей"
    }`;
  }

  function renderRaces(data) {
    const state = data.state || "IDLE";
    const timer = data.timer_sec || 0;
    racesAuto.checked = !!data.auto_enabled;
    racesCollectSec.value = data.collect_sec || 60;
    racesCooldownSec.value = data.cooldown_sec || 180;
    racesRaceDelaySec.value = data.race_delay_sec ?? 10;
    racesBank.textContent = String(data.bank ?? "—");
    racesStatusLine.textContent =
      timer > 0
        ? `Состояние: ${state}, осталось ~${timer} сек`
        : `Состояние: ${state}`;

    const manual = !data.auto_enabled;
    const isOpen = state === "OPEN";
    const isRaceWait = state === "RACE_WAIT";
    const isIdle = state === "IDLE";
    racesOpen.disabled = !manual || !isIdle;
    racesStart.disabled = !isOpen && !isRaceWait;
    racesCancel.disabled = !isOpen && !isRaceWait;

    const lineup = data.lineup || [];
    if (!lineup.length) {
      racesLineupBody.innerHTML =
        '<tr><td colspan="4" class="empty">Нет состава</td></tr>';
    } else {
      racesLineupBody.innerHTML = lineup
        .map(
          (row) => `
        <tr>
          <td>${esc(row.horse_number)}</td>
          <td>${esc(row.princess_name)}</td>
          <td>${row.coefficient != null ? esc(row.coefficient) : "—"}</td>
          <td>${esc(row.bet_total || 0)}</td>
        </tr>`
        )
        .join("");
    }

    const bets = data.bets || [];
    if (!bets.length) {
      racesBetsBody.innerHTML =
        '<tr><td colspan="3" class="empty">Нет ставок</td></tr>';
    } else {
      racesBetsBody.innerHTML = bets
        .map(
          (b) => `
        <tr>
          <td>${esc(b.user_name || b.user_id)}</td>
          <td>${esc(b.horse_number)}</td>
          <td>${esc(b.amount)}</td>
        </tr>`
        )
        .join("");
    }

    racesLastResult.innerHTML = formatRacesLastResult(data.last_result);

    const princessStats = data.princess_stats || [];
    if (!princessStats.length) {
      racesPrincessStatsBody.innerHTML =
        '<tr><td colspan="4" class="empty">Нет данных</td></tr>';
    } else {
      racesPrincessStatsBody.innerHTML = princessStats
        .map((row) => {
          const pct =
            row.races_count > 0
              ? (100 * (row.win_rate != null ? row.win_rate : row.wins_count / row.races_count)).toFixed(1) + "%"
              : "—";
          return `
        <tr>
          <td>${esc(row.princess_name)}</td>
          <td>${esc(row.races_count)}</td>
          <td>${esc(row.wins_count)}</td>
          <td>${esc(pct)}</td>
        </tr>`;
        })
        .join("");
    }
  }

  function stopRacesPoll() {
    if (racesPollTimer) {
      clearInterval(racesPollTimer);
      racesPollTimer = null;
    }
  }

  function startRacesPollIfNeeded(data) {
    stopRacesPoll();
    if (
      data.state === "OPEN" ||
      data.state === "RACE_WAIT" ||
      data.state === "RACE" ||
      data.state === "COOLDOWN"
    ) {
      racesPollTimer = setInterval(() => loadRaces(true), 2500);
    }
  }

  async function loadRaces(silent) {
    if (!silent) setStatus("Загрузка скачек…");
    try {
      const data = await api("GET", "/api/races");
      renderRaces(data);
      startRacesPollIfNeeded(data);
      if (!silent) setStatus(`Скачки: ${data.state}`, "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  async function saveRacesSettings() {
    const collect = parseInt(racesCollectSec.value, 10);
    const cooldown = parseInt(racesCooldownSec.value, 10);
    const raceDelay = parseInt(racesRaceDelaySec.value, 10);
    if (Number.isNaN(collect) || collect < 10) {
      setStatus("collect_sec >= 10", "err");
      return;
    }
    if (Number.isNaN(cooldown) || cooldown < 10) {
      setStatus("cooldown_sec >= 10", "err");
      return;
    }
    if (Number.isNaN(raceDelay) || raceDelay < 0) {
      setStatus("race_delay_sec >= 0", "err");
      return;
    }
    setStatus("Сохранение настроек скачек…");
    try {
      const data = await api("PUT", "/api/races", {
        auto_enabled: racesAuto.checked,
        collect_sec: collect,
        cooldown_sec: cooldown,
        race_delay_sec: raceDelay,
      });
      renderRaces(data);
      setStatus("Настройки скачек сохранены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  document.getElementById("racesSaveSettings").addEventListener("click", saveRacesSettings);
  document.getElementById("racesRefresh").addEventListener("click", () => loadRaces(false));

  racesOpen.addEventListener("click", async () => {
    setStatus("Открытие ставок…");
    try {
      const data = await api("POST", "/api/races/open");
      renderRaces(data);
      startRacesPollIfNeeded(data);
      setStatus("Ставки открыты", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  racesStart.addEventListener("click", async () => {
    if (!confirm("Запустить забег сейчас?")) return;
    setStatus("Старт забега…");
    try {
      const data = await api("POST", "/api/races/start");
      renderRaces(data);
      startRacesPollIfNeeded(data);
      setStatus("Забег запущен", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  racesTopUp.addEventListener("click", async () => {
    const raw = prompt("Сколько баллов добавить в казну?", "5000");
    if (raw == null) return;
    const amount = parseInt(raw, 10);
    if (Number.isNaN(amount) || amount <= 0) {
      setStatus("Сумма должна быть > 0", "err");
      return;
    }
    setStatus("Пополнение казны…");
    try {
      const data = await api("POST", "/api/races/bank", { amount });
      renderRaces(data);
      setStatus(`Казна пополнена на ${amount}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  racesCancel.addEventListener("click", async () => {
    if (!confirm("Отменить забег и вернуть ставки?")) return;
    setStatus("Отмена забега…");
    try {
      const data = await api("POST", "/api/races/cancel");
      renderRaces(data);
      stopRacesPoll();
      setStatus("Забег отменён", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  function addPollOptionInput(value) {
    if (pollOptionCount >= 8) return;
    pollOptionCount += 1;
    const idx = pollOptionCount;
    const row = document.createElement("div");
    row.className = "toolbar";
    row.style.gap = "8px";
    row.dataset.pollOpt = String(idx);
    row.innerHTML = `
      <label style="flex:1">
        Вариант ${idx}
        <input type="text" class="poll-option-input" placeholder="Вариант ${idx}" value="${esc(value || "")}" />
      </label>
      <button type="button" class="small danger poll-option-remove">−</button>
    `;
    const removeBtn = row.querySelector(".poll-option-remove");
    removeBtn.addEventListener("click", () => {
      if (pollOptionsList.querySelectorAll("[data-poll-opt]").length <= 2) {
        setStatus("Нужно минимум 2 варианта", "err");
        return;
      }
      row.remove();
      renumberPollOptions();
    });
    pollOptionsList.appendChild(row);
  }

  function renumberPollOptions() {
    const rows = [...pollOptionsList.querySelectorAll("[data-poll-opt]")];
    pollOptionCount = rows.length;
    rows.forEach((row, i) => {
      row.dataset.pollOpt = String(i + 1);
      const label = row.querySelector("label");
      const input = row.querySelector(".poll-option-input");
      if (label && input) {
        label.innerHTML = "";
        label.appendChild(document.createTextNode(`Вариант ${i + 1} `));
        input.placeholder = `Вариант ${i + 1}`;
        label.appendChild(input);
      }
    });
  }

  function resetPollCreateForm() {
    pollTitle.value = "";
    pollDurationMin.value = "5";
    pollOptionsList.innerHTML = "";
    pollOptionCount = 0;
    addPollOptionInput("Да");
    addPollOptionInput("Нет");
  }

  function formatPollLastResult(lr) {
    if (!lr) return '<span class="empty">—</span>';
    const win = lr.winning_label || "?";
    const pool = lr.total_pool != null ? lr.total_pool : "—";
    const winners = lr.winners || [];
    const top = winners
      .slice()
      .sort((a, b) => (b.payout || 0) - (a.payout || 0))
      .slice(0, 8)
      .map((w) => `${esc(w.user_name)} +${esc(w.payout)}`)
      .join(", ");
    return `<strong>Победил:</strong> ${esc(win)} · банк ${esc(pool)}`
      + (top ? `<br/><span>Выплаты: ${top}</span>` : "");
  }

  function renderPolls(data) {
    const state = data.state || "IDLE";
    const timer = data.timer_sec || 0;
    pollPool.textContent = String(data.total_pool ?? "—");
    if (state === "OPEN" && timer > 0) {
      pollStatusLine.textContent = `Состояние: ${state}, до закрытия приёма ~${timer} сек`;
    } else if (state === "RESOLVED" && timer > 0) {
      pollStatusLine.textContent = `Состояние: ${state}, сброс через ~${timer} сек`;
    } else {
      pollStatusLine.textContent = `Состояние: ${state}`
        + (data.title ? ` — ${data.title}` : "");
    }

    const isIdle = state === "IDLE";
    const isOpen = state === "OPEN";
    const isLocked = state === "LOCKED";
    pollCreateCard.style.opacity = isIdle ? "1" : "0.55";
    pollCreate.disabled = !isIdle;
    pollLock.disabled = !isOpen;
    pollResolve.disabled = !isLocked;
    pollCancel.disabled = !isOpen && !isLocked;
    if (!isLocked) {
      pollResolveRow.style.display = "none";
    }

    const options = data.options || [];
    if (!options.length) {
      pollOptionsBody.innerHTML =
        '<tr><td colspan="5" class="empty">Нет вариантов</td></tr>';
      pollResolveSelect.innerHTML = "";
    } else {
      pollOptionsBody.innerHTML = options
        .map(
          (o) => `
        <tr>
          <td>${esc(o.index + 1)}</td>
          <td>${esc(o.label)}</td>
          <td>${esc(o.total)}</td>
          <td>${esc(o.bets_count)}</td>
          <td>×${esc(o.coefficient)}</td>
        </tr>`
        )
        .join("");
      pollResolveSelect.innerHTML = options
        .map(
          (o) =>
            `<option value="${esc(o.index)}">${esc(o.index + 1)}. ${esc(o.label)} (${esc(o.total)})</option>`
        )
        .join("");
    }

    const bets = data.bets || [];
    if (!bets.length) {
      pollBetsBody.innerHTML =
        '<tr><td colspan="3" class="empty">Нет ставок</td></tr>';
    } else {
      pollBetsBody.innerHTML = bets
        .map(
          (b) => `
        <tr>
          <td>${esc(b.user_name || b.user_id)}</td>
          <td>${esc(b.option_label || b.option_index + 1)}</td>
          <td>${esc(b.amount)}</td>
        </tr>`
        )
        .join("");
    }

    pollLastResult.innerHTML = formatPollLastResult(data.last_result);

    if (isOpen || isLocked || state === "RESOLVED") {
      startPollsPoll();
    } else {
      stopPollsPoll();
    }
  }

  function stopPollsPoll() {
    if (pollsPollTimer) {
      clearInterval(pollsPollTimer);
      pollsPollTimer = null;
    }
  }

  function startPollsPoll() {
    stopPollsPoll();
    pollsPollTimer = setInterval(() => loadPolls(true), 2500);
  }

  async function loadPolls(silent) {
    if (!silent) setStatus("Загрузка опроса…");
    try {
      const data = await api("GET", "/api/poll");
      renderPolls(data);
      if (!silent) setStatus("Опрос обновлён", "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  pollAddOption.addEventListener("click", () => {
    if (pollOptionCount >= 8) {
      setStatus("Максимум 8 вариантов", "err");
      return;
    }
    addPollOptionInput("");
  });

  pollCreate.addEventListener("click", async () => {
    const title = (pollTitle.value || "").trim();
    const mins = parseInt(pollDurationMin.value, 10);
    const options = [...pollOptionsList.querySelectorAll(".poll-option-input")]
      .map((el) => (el.value || "").trim())
      .filter(Boolean);
    if (!title) {
      setStatus("Укажите вопрос", "err");
      return;
    }
    if (options.length < 2) {
      setStatus("Нужно минимум 2 варианта", "err");
      return;
    }
    if (Number.isNaN(mins) || mins < 1 || mins > 10) {
      setStatus("Длительность: 1–10 минут", "err");
      return;
    }
    setStatus("Создание опроса…");
    try {
      const data = await api("POST", "/api/poll/create", {
        title,
        options,
        collect_sec: mins * 60,
      });
      renderPolls(data);
      setStatus("Опрос открыт", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  document.getElementById("pollRefresh").addEventListener("click", () => loadPolls(false));

  pollLock.addEventListener("click", async () => {
    setStatus("Закрытие приёма…");
    try {
      const data = await api("POST", "/api/poll/lock");
      renderPolls(data);
      setStatus("Приём ставок закрыт", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  pollResolve.addEventListener("click", () => {
    pollResolveRow.style.display = "flex";
  });

  pollResolveConfirm.addEventListener("click", async () => {
    const option_index = parseInt(pollResolveSelect.value, 10);
    if (Number.isNaN(option_index)) {
      setStatus("Выберите вариант", "err");
      return;
    }
    const label = pollResolveSelect.options[pollResolveSelect.selectedIndex]?.text || "";
    if (!confirm(`Подтвердить победу: ${label}?`)) return;
    setStatus("Резолв опроса…");
    try {
      const data = await api("POST", "/api/poll/resolve", { option_index });
      renderPolls(data);
      pollResolveRow.style.display = "none";
      setStatus("Победитель выбран", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  pollCancel.addEventListener("click", async () => {
    if (!confirm("Отменить опрос и вернуть баллы всем участникам?")) return;
    setStatus("Отмена опроса…");
    try {
      const data = await api("POST", "/api/poll/cancel");
      renderPolls(data);
      pollResolveRow.style.display = "none";
      setStatus("Опрос отменён, баллы возвращены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  const fishingStatusLine = document.getElementById("fishingStatusLine");
  const fishingDay = document.getElementById("fishingDay");
  const fishingWeek = document.getElementById("fishingWeek");
  const fishingPlayers = document.getElementById("fishingPlayers");
  const fishingPendingLine = document.getElementById("fishingPendingLine");
  const fishingLeadersBody = document.getElementById("fishingLeadersBody");
  const fishingFowLine = document.getElementById("fishingFowLine");
  const fishingRestoreEnergy = document.getElementById("fishingRestoreEnergy");
  const fishingPayRewards = document.getElementById("fishingPayRewards");
  const fishingRewardsFields = document.getElementById("fishingRewardsFields");
  const fishingFowBonus = document.getElementById("fishingFowBonus");
  const fishingRewardsPreview = document.getElementById("fishingRewardsPreview");
  const fishingSaveRewards = document.getElementById("fishingSaveRewards");
  const fishingResetRewards = document.getElementById("fishingResetRewards");
  const fishingSaveSettings = document.getElementById("fishingSaveSettings");
  const fishingResetSettings = document.getElementById("fishingResetSettings");
  const fishingSettingsHint = document.getElementById("fishingSettingsHint");
  const fishSettingsInputs = {
    energy_max: document.getElementById("fishEnergyMax"),
    energy_regen_interval_sec: document.getElementById("fishRegenSec"),
    cast_energy_cost: document.getElementById("fishCastEnergy"),
    worms_energy_cost: document.getElementById("fishWormsEnergy"),
    worms_gain: document.getElementById("fishWormsGain"),
    maggot_cost: document.getElementById("fishMaggotCost"),
    maggot_gain: document.getElementById("fishMaggotGain"),
    rod_cost: document.getElementById("fishRodCost"),
    cast_cooldown_sec: document.getElementById("fishCastCooldown"),
    worms_dig_shield_chance: document.getElementById("fishDigShield"),
    worms_dig_bite_chance: document.getElementById("fishDigBite"),
    worms_dig_safe_chance: document.getElementById("fishDigSafe"),
    bite_boost_casts: document.getElementById("fishBiteBoostCasts"),
    bite_boost_miss_trash_div: document.getElementById("fishBiteBoostDiv"),
    miss_chance: document.getElementById("fishMissChance"),
    trash_chance: document.getElementById("fishTrashChance"),
  };
  const fishFloatKeys = new Set([
    "worms_dig_shield_chance",
    "worms_dig_bite_chance",
    "worms_dig_safe_chance",
    "miss_chance",
    "trash_chance",
  ]);
  let fishingLastData = null;
  let fishingRewardsBuilt = false;

  function fishingFillRuntimeSettings(data) {
    const rt = data.runtime_settings || {};
    Object.keys(fishSettingsInputs).forEach((key) => {
      const el = fishSettingsInputs[key];
      if (!el || rt[key] == null) return;
      el.value = String(rt[key]);
    });
    const em = rt.energy_max != null ? rt.energy_max : 100;
    if (fishingRestoreEnergy) {
      fishingRestoreEnergy.textContent = `Энергия всем = ${em}`;
    }
    if (fishingSettingsHint) {
      fishingSettingsHint.textContent = data.runtime_settings_is_default
        ? "Сейчас defaults из settings.py (override в БД пуст)."
        : "Сохранено в БД (override активен).";
    }
  }

  function fishingReadRuntimeSettingsFromForm() {
    const out = {};
    for (const key of Object.keys(fishSettingsInputs)) {
      const el = fishSettingsInputs[key];
      if (!el) continue;
      if (fishFloatKeys.has(key)) {
        const n = parseFloat(el.value);
        if (Number.isNaN(n)) throw new Error(`${key}: число`);
        out[key] = n;
      } else {
        const n = parseInt(el.value, 10);
        if (Number.isNaN(n)) throw new Error(`${key}: целое число`);
        out[key] = n;
      }
    }
    return out;
  }

  function fishingReadRewardsFromForm() {
    const species = {};
    fishingRewardsFields.querySelectorAll("input[data-species]").forEach((input) => {
      const name = input.getAttribute("data-species");
      const n = parseInt(input.value, 10);
      species[name] = Number.isFinite(n) && n >= 0 ? n : 0;
    });
    const enabled = {};
    fishingRewardsFields.querySelectorAll("input[data-enabled-species]").forEach((input) => {
      const name = input.getAttribute("data-enabled-species");
      enabled[name] = !!input.checked;
    });
    const fow = parseInt(fishingFowBonus.value, 10);
    return {
      species,
      enabled,
      fish_of_week_bonus: Number.isFinite(fow) && fow >= 0 ? fow : 0,
    };
  }

  function fishingApplyEnabledStyles() {
    fishingRewardsFields.querySelectorAll("label[data-species-row]").forEach((label) => {
      const name = label.getAttribute("data-species-row");
      const cb = label.querySelector(`input[data-enabled-species="${CSS.escape(name)}"]`);
      const on = cb ? cb.checked : true;
      label.style.opacity = on ? "1" : "0.55";
    });
  }

  function fishingFillRewardInputs(rewards, fowBonus, enabledMap) {
    const species = rewards || {};
    const names = Object.keys(species);
    const enabled = enabledMap || {};
    if (!fishingRewardsBuilt || fishingRewardsFields.querySelectorAll("label[data-species-row]").length !== names.length) {
      fishingRewardsFields.innerHTML = names
        .map((name) => {
          const on = enabled[name] !== false;
          return `
        <label data-species-row="${esc(name)}" style="display:inline-flex;align-items:center;gap:6px;font-size:13px;opacity:${on ? "1" : "0.55"}">
          <input type="checkbox" data-enabled-species="${esc(name)}" ${on ? "checked" : ""} title="В дропе заброса" />
          <span style="min-width:4.5em">${esc(name)}</span>
          <input type="number" data-species="${esc(name)}" min="0" step="1"
            style="width:90px" value="${esc(species[name])}" />
        </label>`;
        })
        .join("");
      fishingRewardsBuilt = true;
      fishingRewardsFields.querySelectorAll("input[data-species]").forEach((input) => {
        input.addEventListener("input", () => fishingUpdatePreview(fishingLastData));
      });
      fishingRewardsFields.querySelectorAll("input[data-enabled-species]").forEach((input) => {
        input.addEventListener("change", () => {
          fishingApplyEnabledStyles();
          fishingUpdatePreview(fishingLastData);
        });
      });
    } else {
      fishingRewardsFields.querySelectorAll("input[data-species]").forEach((input) => {
        const name = input.getAttribute("data-species");
        if (name in species) input.value = String(species[name]);
      });
      fishingRewardsFields.querySelectorAll("input[data-enabled-species]").forEach((input) => {
        const name = input.getAttribute("data-enabled-species");
        input.checked = enabled[name] !== false;
      });
      fishingApplyEnabledStyles();
    }
    fishingFowBonus.value = String(fowBonus ?? 0);
  }

  function fishingUpdatePreview(data) {
    if (!data) {
      fishingRewardsPreview.textContent = "—";
      return;
    }
    const cfg = fishingReadRewardsFromForm();
    const pending = data.has_pending_rewards;
    const leaders = pending
      ? data.pending_week_leaders || []
      : data.week_leaders || [];
    const fow = pending ? data.pending_fish_of_week : data.fish_of_week;
    let total = 0;
    const parts = [];
    leaders.forEach((row) => {
      const reward = cfg.species[row.species] || 0;
      total += reward;
      if (reward > 0) {
        parts.push(`${row.species}: ${reward}`);
      }
    });
    if (fow && cfg.fish_of_week_bonus > 0) {
      total += cfg.fish_of_week_bonus;
      parts.push(`рыба недели: +${cfg.fish_of_week_bonus}`);
    }
    const scope = pending
      ? `закрытой недели ${data.pending_rewards_week_id}`
      : "текущего топа";
    if (!parts.length) {
      fishingRewardsPreview.textContent =
        `По ${scope} выплат нет (или награды = 0).`;
      return;
    }
    fishingRewardsPreview.textContent =
      `Превью выплат (${scope}): ${total} (${parts.join(", ")})`;
  }

  function renderFishing(data) {
    fishingLastData = data;
    fishingDay.textContent = data.day_key || "—";
    fishingWeek.textContent = data.current_week_id || "—";
    fishingPlayers.textContent = String(data.players ?? 0);
    fishingStatusLine.textContent = data.first_fish_claimed
      ? "Первая рыба дня уже поймана"
      : "Первая рыба дня ещё доступна";
    if (data.has_pending_rewards && data.pending_rewards_week_id) {
      fishingPendingLine.textContent =
        `Ожидающие награды: неделя ${data.pending_rewards_week_id}`;
      fishingPendingLine.style.color = "#c62828";
      fishingPayRewards.disabled = false;
      fishingPayRewards.title = "Выдать награды закрытой недели";
    } else {
      fishingPendingLine.textContent = "Ожидающие награды: нет";
      fishingPendingLine.style.color = "";
      // Кнопка кликабельна — покажем alert, почему нельзя
      fishingPayRewards.disabled = false;
      fishingPayRewards.title =
        "Сейчас нечего выдавать: нет закрытой недели с ожидающими наградами";
    }

    fishingFillRewardInputs(
      data.week_rewards || {},
      data.fish_of_week_bonus ?? 0,
      data.species_enabled || {}
    );
    fishingFillRuntimeSettings(data);
    const cfg = fishingReadRewardsFromForm();

    const leaders = data.week_leaders || [];
    if (!leaders.length) {
      fishingLeadersBody.innerHTML =
        '<tr><td colspan="4" class="empty">Пока пусто</td></tr>';
    } else {
      fishingLeadersBody.innerHTML = leaders
        .map(
          (row) => `
        <tr>
          <td>${esc(row.species)}</td>
          <td>${esc(row.user_name || row.user_id)}</td>
          <td>${esc(Number(row.weight).toFixed(2))}</td>
          <td>${esc(cfg.species[row.species] ?? 0)}</td>
        </tr>`
        )
        .join("");
    }
    const fow = data.fish_of_week;
    fishingFowLine.textContent = fow
      ? `Рыба недели: ${fow.user_name || fow.user_id} — ${fow.species} (${Number(fow.weight).toFixed(2)} кг), бонус +${cfg.fish_of_week_bonus}`
      : "Рыба недели: —";
    fishingUpdatePreview(data);
  }

  async function loadFishing(silent) {
    if (!silent) setStatus("Загрузка рыбалки…");
    try {
      const data = await api("GET", "/api/fishing");
      renderFishing(data);
      if (!silent) setStatus("Рыбалка обновлена", "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  document.getElementById("fishingRefresh").addEventListener("click", () => loadFishing(false));

  fishingFowBonus.addEventListener("input", () => fishingUpdatePreview(fishingLastData));

  fishingRestoreEnergy.addEventListener("click", async () => {
    setStatus("Восстановление энергии…");
    try {
      const data = await api("POST", "/api/fishing/restore-energy");
      renderFishing(data);
      setStatus(`Энергия восстановлена (${data.restored ?? 0} игроков)`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  if (fishingSaveSettings) {
    fishingSaveSettings.addEventListener("click", async () => {
      let payload;
      try {
        payload = fishingReadRuntimeSettingsFromForm();
      } catch (e) {
        setStatus(e.message, "err");
        return;
      }
      setStatus("Сохранение настроек рыбалки…");
      try {
        const data = await api("PUT", "/api/fishing/settings", payload);
        renderFishing(data);
        setStatus("Настройки рыбалки сохранены", "ok");
      } catch (e) {
        setStatus(e.message, "err");
      }
    });
  }

  if (fishingResetSettings) {
    fishingResetSettings.addEventListener("click", async () => {
      const ok = confirm("Сбросить настройки рыбалки к defaults из settings.py?");
      if (!ok) return;
      setStatus("Сброс настроек рыбалки…");
      try {
        const data = await api("POST", "/api/fishing/settings/reset");
        renderFishing(data);
        setStatus("Настройки рыбалки сброшены", "ok");
      } catch (e) {
        setStatus(e.message, "err");
      }
    });
  }

  fishingSaveRewards.addEventListener("click", async () => {
    const body = fishingReadRewardsFromForm();
    setStatus("Сохранение наград…");
    try {
      const data = await api("POST", "/api/fishing/rewards", body);
      renderFishing(data);
      setStatus("Награды недели сохранены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  fishingResetRewards.addEventListener("click", async () => {
    const defaults = (fishingLastData && fishingLastData.week_rewards_defaults) || null;
    if (!defaults) {
      setStatus("Нет defaults — обновите вкладку", "err");
      return;
    }
    fishingFillRewardInputs(defaults.species || {}, defaults.fish_of_week_bonus ?? 0, defaults.enabled || {});
    const body = fishingReadRewardsFromForm();
    setStatus("Сброс наград к defaults…");
    try {
      const data = await api("POST", "/api/fishing/rewards", body);
      renderFishing(data);
      setStatus("Награды сброшены к defaults из settings", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  fishingPayRewards.addEventListener("click", async () => {
    if (!fishingLastData || !fishingLastData.has_pending_rewards) {
      const msg =
        "Сейчас нет закрытой недели с ожидающими наградами.\n\n" +
        "Выдача появится после смены недели (понедельник по МСК), " +
        "когда бот закроет прошлую неделю.";
      alert(msg);
      setStatus("Нет ожидающих наград недели", "err");
      return;
    }
    const body = fishingReadRewardsFromForm();
    if (!confirm("Выдать награды закрытой недели победителям по суммам из формы?")) return;
    setStatus("Выдача наград…");
    try {
      const data = await api("POST", "/api/fishing/pay-rewards", body);
      renderFishing(data);
      const details = data.details || [];
      const fowBonus = data.fish_of_week_bonus_paid || 0;
      const fow = data.fish_of_week;
      const bits = details.map(
        (row) => `${row.user_name || row.user_id}: ${row.species} +${row.reward}`
      );
      if (fow && fowBonus > 0) {
        bits.push(
          `рыба недели ${fow.user_name || fow.user_id} +${fowBonus}`
        );
      }
      const summary = bits.length
        ? bits.join("; ")
        : "выплат не было (суммы 0)";
      setStatus(
        `Награды выданы (неделя ${data.paid_week || ""}): ${summary}`,
        "ok"
      );
    } catch (e) {
      alert(e.message);
      setStatus(e.message, "err");
    }
  });

  const stealStatusLine = document.getElementById("stealStatusLine");
  const stealDetailLine = document.getElementById("stealDetailLine");
  const stealOpen = document.getElementById("stealOpen");
  const stealClose = document.getElementById("stealClose");
  const stealOpenTimed = document.getElementById("stealOpenTimed");
  const stealHours = document.getElementById("stealHours");
  const stealLootBody = document.getElementById("stealLootBody");
  const stealLootMeta = document.getElementById("stealLootMeta");
  const stealStatsBody = document.getElementById("stealStatsBody");
  const stealStatsMeta = document.getElementById("stealStatsMeta");

  const STEAL_LOOT_LABELS = {
    meloch: "Мелочь",
    normal: "Норма",
    zhir: "Жир",
    kush: "Куш",
  };
  const STEAL_LOOT_KEYS = ["meloch", "normal", "zhir", "kush"];

  function formatStealRemaining(untilTs) {
    const sec = Math.max(0, Math.floor(untilTs - Date.now() / 1000));
    if (sec <= 0) return "0 мин";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (h > 0) return `${h} ч ${m} мин`;
    return `${m} мин`;
  }

  function renderSteal(data) {
    const schedule = !!data.schedule_allowed;
    const enabled = !!data.override_enabled;
    const until = data.override_until != null ? Number(data.override_until) : null;
    const timed = until != null && until * 1000 > Date.now();
    const effective = !!data.effective_allowed;

    if (enabled) {
      stealStatusLine.textContent = "Статус: открыта вручную (бессрочно)";
      stealStatusLine.className = "orders-status on";
    } else if (timed) {
      stealStatusLine.textContent =
        "Статус: открыта ещё " + formatStealRemaining(until);
      stealStatusLine.className = "orders-status on";
    } else if (schedule) {
      stealStatusLine.textContent = "Статус: доступна по расписанию";
      stealStatusLine.className = "orders-status on";
    } else {
      stealStatusLine.textContent = "Статус: закрыта";
      stealStatusLine.className = "orders-status off";
    }

    const nextDay = data.next_steal_day || "—";
    stealDetailLine.textContent = effective
      ? `Эффективно: доступна · следующий день расписания после закрытия — ${nextDay}`
      : `Эффективно: недоступна · следующий день расписания — ${nextDay}`;

    stealClose.disabled = !enabled && !timed;
  }

  function refreshLootPercents() {
    let total = 0;
    STEAL_LOOT_KEYS.forEach((key) => {
      const input = document.getElementById(`stealLootW_${key}`);
      total += Math.max(0, Number(input && input.value) || 0);
    });
    STEAL_LOOT_KEYS.forEach((key) => {
      const pctEl = document.getElementById(`stealLootPct_${key}`);
      const input = document.getElementById(`stealLootW_${key}`);
      if (!pctEl || !input) return;
      const w = Math.max(0, Number(input.value) || 0);
      pctEl.textContent = total > 0 ? ((100 * w) / total).toFixed(1) + "%" : "—";
    });
  }

  function renderStealLoot(data) {
    const tiers = (data && data.tiers) || {};
    stealLootMeta.textContent = data && data.is_default
      ? "Источник: дефолты settings"
      : "Источник: override из БД";
    stealLootBody.innerHTML = "";
    STEAL_LOOT_KEYS.forEach((key) => {
      const t = tiers[key] || { weight: 0, min: 0, max: 0, pct: 0 };
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${STEAL_LOOT_LABELS[key] || key}</td>` +
        `<td><input type="number" id="stealLootW_${key}" min="0" step="1" value="${Number(t.weight) || 0}" style="width:80px" /></td>` +
        `<td id="stealLootPct_${key}">${t.pct != null ? Number(t.pct).toFixed(1) + "%" : "—"}</td>` +
        `<td><input type="number" id="stealLootMin_${key}" step="1" value="${Number(t.min) || 0}" style="width:80px" /></td>` +
        `<td><input type="number" id="stealLootMax_${key}" step="1" value="${Number(t.max) || 0}" style="width:80px" /></td>`;
      stealLootBody.appendChild(tr);
      const wInput = document.getElementById(`stealLootW_${key}`);
      if (wInput) wInput.addEventListener("input", refreshLootPercents);
    });
    refreshLootPercents();
  }

  function readStealLootFromForm() {
    const tiers = {};
    STEAL_LOOT_KEYS.forEach((key) => {
      tiers[key] = {
        weight: Number(document.getElementById(`stealLootW_${key}`).value),
        min: Number(document.getElementById(`stealLootMin_${key}`).value),
        max: Number(document.getElementById(`stealLootMax_${key}`).value),
      };
    });
    return tiers;
  }

  function renderStealStats(data) {
    const players = (data && data.players) || [];
    stealStatsMeta.textContent = `Игроков: ${players.length}`;
    if (!players.length) {
      stealStatsBody.innerHTML = `<tr><td colspan="7" class="empty">Пока пусто (после вайпа или никто не крал)</td></tr>`;
      return;
    }
    stealStatsBody.innerHTML = players
      .map((p) => {
        const name = p.user_name || p.user_id || "—";
        return (
          `<tr>` +
          `<td>${escapeHtml(name)}</td>` +
          `<td class="mono">${p.attempts}</td>` +
          `<td class="mono">${p.success}</td>` +
          `<td class="mono">${p.stolen_total}</td>` +
          `<td class="mono">${p.chance}%</td>` +
          `<td class="mono">${p.times_in_jail}</td>` +
          `<td class="mono">${p.last_steal_day_key || "—"}</td>` +
          `</tr>`
        );
      })
      .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadSteal(silent) {
    if (!silent) setStatus("Загрузка кражи…");
    try {
      const [status, loot, stats] = await Promise.all([
        api("GET", "/api/steal"),
        api("GET", "/api/steal/loot-tiers"),
        api("GET", "/api/steal/stats"),
      ]);
      renderSteal(status);
      renderStealLoot(loot);
      renderStealStats(stats);
      if (!silent) setStatus("Кража обновлена", "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  document.getElementById("stealRefresh").addEventListener("click", () => loadSteal(false));

  document.getElementById("stealLootSave").addEventListener("click", async () => {
    const tiers = readStealLootFromForm();
    const sum = STEAL_LOOT_KEYS.reduce((acc, k) => acc + Math.max(0, Number(tiers[k].weight) || 0), 0);
    if (sum <= 0) {
      setStatus("Сумма весов должна быть > 0", "err");
      return;
    }
    setStatus("Сохранение тиров…");
    try {
      const data = await api("PUT", "/api/steal/loot-tiers", { tiers });
      renderStealLoot(data);
      setStatus("Тиры сохранены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  document.getElementById("stealLootReset").addEventListener("click", async () => {
    if (!confirm("Сбросить тиры к дефолтам settings?")) return;
    setStatus("Сброс тиров…");
    try {
      const data = await api("POST", "/api/steal/loot-tiers/reset");
      renderStealLoot(data);
      setStatus("Тиры сброшены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  stealOpen.addEventListener("click", async () => {
    setStatus("Открытие кражи…");
    try {
      const data = await api("PUT", "/api/steal", { override_enabled: true });
      renderSteal(data);
      setStatus("Кража открыта вручную", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  stealClose.addEventListener("click", async () => {
    if (!confirm("Закрыть ручное окно кражи?")) return;
    setStatus("Закрытие кражи…");
    try {
      const data = await api("PUT", "/api/steal", { override_enabled: false });
      renderSteal(data);
      setStatus("Ручное окно кражи закрыто", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  stealOpenTimed.addEventListener("click", async () => {
    const hours = Number(stealHours.value);
    if (!Number.isFinite(hours) || hours <= 0) {
      setStatus("Укажите число часов > 0", "err");
      return;
    }
    setStatus(`Открытие кражи на ${hours} ч…`);
    try {
      const data = await api("PUT", "/api/steal", { duration_hours: hours });
      renderSteal(data);
      setStatus(`Кража открыта на ${hours} ч`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  // --- Ивенты ---
  const EVENT_ITEM_LABELS = {
    bite_boost: "Буст клёва",
    mermaid_shield: "Щит от русалки",
    steal_safe: "Карманный сейф",
  };
  let eventsUsers = [];
  let eventsSelected = new Set();

  function eventsReadWeekdays() {
    return Array.from(
      document.querySelectorAll("#eventsWeekdays input[type=checkbox]:checked")
    ).map((el) => parseInt(el.value, 10));
  }

  function eventsFillSchedule(schedule) {
    const s = schedule || {};
    document.getElementById("eventsBoostEnabled").checked = !!s.boost_enabled;
    document.getElementById("eventsBoostCasts").value =
      s.boost_casts != null ? s.boost_casts : 30;
    const days = new Set(
      Array.isArray(s.boost_weekdays) ? s.boost_weekdays.map(Number) : [3]
    );
    document.querySelectorAll("#eventsWeekdays input[type=checkbox]").forEach((el) => {
      el.checked = days.has(parseInt(el.value, 10));
    });
  }

  function eventsFormatTs(ts) {
    const d = new Date(Number(ts) * 1000);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("ru-RU", { hour12: false });
  }

  function renderEventsLog(rows) {
    const body = document.getElementById("eventsLogBody");
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="5" class="empty">Пока пусто</td></tr>';
      return;
    }
    body.innerHTML = rows
      .map(
        (r) => `
      <tr>
        <td>${esc(eventsFormatTs(r.created_at))}</td>
        <td class="mono">${esc(r.user_id)}</td>
        <td>${esc(r.user_name || "—")}</td>
        <td>${esc(EVENT_ITEM_LABELS[r.item] || r.item)}</td>
        <td>${esc(r.amount)}</td>
      </tr>`
      )
      .join("");
  }

  function renderEventsUsers() {
    const body = document.getElementById("eventsUsersBody");
    const q = document.getElementById("eventsUsersFilter").value.trim().toLowerCase();
    const items = q
      ? eventsUsers.filter(
          (p) =>
            String(p.user_id).toLowerCase().includes(q) ||
            (p.user_name && String(p.user_name).toLowerCase().includes(q))
        )
      : eventsUsers;

    if (!items.length) {
      body.innerHTML =
        '<tr><td colspan="3" class="empty">' +
        (q ? "Ничего не найдено" : "Нет пользователей") +
        "</td></tr>";
      return;
    }

    body.innerHTML = items
      .map((p) => {
        const id = String(p.user_id);
        const checked = eventsSelected.has(id) ? " checked" : "";
        return `
      <tr data-user-id="${esc(id)}">
        <td><input type="checkbox" class="events-user-cb" data-user-id="${esc(id)}"${checked} /></td>
        <td class="mono">${esc(id)}</td>
        <td>${esc(displayName(p))}</td>
      </tr>`;
      })
      .join("");
  }

  async function loadEventsUsers(silent) {
    try {
      const data = await api("GET", "/api/points");
      eventsUsers = data.items || [];
      renderEventsUsers();
      if (!silent) setStatus(`Пользователей: ${eventsUsers.length}`, "ok");
    } catch (e) {
      document.getElementById("eventsUsersBody").innerHTML =
        '<tr><td colspan="3" class="empty">Ошибка загрузки</td></tr>';
      if (!silent) setStatus(e.message, "err");
    }
  }

  async function loadEvents(silent) {
    if (!silent) setStatus("Загрузка ивентов…");
    try {
      const data = await api("GET", "/api/events");
      eventsFillSchedule(data.schedule);
      renderEventsLog(data.grant_log || []);
      await loadEventsUsers(true);
      if (!silent) setStatus("Ивенты загружены", "ok");
    } catch (e) {
      if (!silent) setStatus(e.message, "err");
    }
  }

  document.getElementById("eventsScheduleSave").addEventListener("click", async () => {
    const payload = {
      boost_enabled: document.getElementById("eventsBoostEnabled").checked,
      boost_weekdays: eventsReadWeekdays(),
      boost_casts: parseInt(document.getElementById("eventsBoostCasts").value, 10),
    };
    if (Number.isNaN(payload.boost_casts) || payload.boost_casts < 0) {
      setStatus("Зарядов: целое число >= 0", "err");
      return;
    }
    setStatus("Сохранение расписания…");
    try {
      const data = await api("PUT", "/api/events/schedule", payload);
      eventsFillSchedule(data.schedule);
      renderEventsLog(data.grant_log || []);
      setStatus("Расписание сохранено", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  document.getElementById("eventsUsersFilter").addEventListener("input", renderEventsUsers);
  document.getElementById("eventsUsersRefresh").addEventListener("click", () =>
    loadEventsUsers(false)
  );

  document.getElementById("eventsUsersBody").addEventListener("change", (e) => {
    const t = e.target;
    if (!t.classList || !t.classList.contains("events-user-cb")) return;
    const id = t.getAttribute("data-user-id");
    if (!id) return;
    if (t.checked) eventsSelected.add(id);
    else eventsSelected.delete(id);
  });

  document.getElementById("eventsSelectAll").addEventListener("change", (e) => {
    const on = e.target.checked;
    document.querySelectorAll("#eventsUsersBody .events-user-cb").forEach((cb) => {
      cb.checked = on;
      const id = cb.getAttribute("data-user-id");
      if (!id) return;
      if (on) eventsSelected.add(id);
      else eventsSelected.delete(id);
    });
  });

  document.getElementById("eventsClearSelection").addEventListener("click", () => {
    eventsSelected.clear();
    document.getElementById("eventsSelectAll").checked = false;
    renderEventsUsers();
  });

  document.getElementById("eventsGrantItem").addEventListener("change", () => {
    const item = document.getElementById("eventsGrantItem").value;
    const amountEl = document.getElementById("eventsGrantAmount");
    if (item === "bite_boost") amountEl.value = 30;
    else if (item === "mermaid_shield") amountEl.value = 1;
    else amountEl.value = 1;
    amountEl.disabled = item === "steal_safe";
  });

  document.getElementById("eventsGrantSelected").addEventListener("click", async () => {
    const ids = Array.from(eventsSelected);
    if (!ids.length) {
      setStatus("Выберите хотя бы одного пользователя", "err");
      return;
    }
    const item = document.getElementById("eventsGrantItem").value;
    const amountRaw = parseInt(document.getElementById("eventsGrantAmount").value, 10);
    const body = { user_ids: ids, item };
    if (item !== "steal_safe") {
      if (Number.isNaN(amountRaw)) {
        setStatus("Кол-во: целое число", "err");
        return;
      }
      body.amount = amountRaw;
    }
    setStatus(`Выдача ${item} × ${ids.length}…`);
    try {
      const data = await api("POST", "/api/events/grant", body);
      renderEventsLog(data.grant_log || []);
      setStatus(`Выдано: ${data.granted}`, "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  document.querySelectorAll(".tab[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const id = tab.dataset.tab;
      document.getElementById(`panel-${id}`).classList.add("active");
      if (id === "queue") loadQueue();
      if (id === "roulette") loadRoulette(false);
      else stopRoulettePoll();
      if (id === "races") loadRaces(false);
      else stopRacesPoll();
      if (id === "polls") loadPolls(false);
      else stopPollsPoll();
      if (id === "fishing") loadFishing(false);
      if (id === "events") loadEvents(false);
      if (id === "steal") loadSteal(false);
    });
  });

  function parseSortCellValue(text) {
    const t = String(text || "")
      .replace(/\u00a0/g, " ")
      .trim();
    if (!t || t === "—" || t === "-" || t === "…") {
      return { kind: "empty", num: 0, str: "" };
    }
    const pct = t.replace(",", ".").match(/^(-?\d+(?:\.\d+)?)\s*%$/);
    if (pct) {
      return { kind: "num", num: parseFloat(pct[1]), str: t.toLowerCase() };
    }
    const cleaned = t.replace(/\s/g, "").replace(",", ".");
    if (/^-?\d+(?:\.\d+)?$/.test(cleaned)) {
      return { kind: "num", num: parseFloat(cleaned), str: t.toLowerCase() };
    }
    return { kind: "str", num: 0, str: t.toLowerCase() };
  }

  function cellSortText(cell) {
    if (!cell) return "";
    const input = cell.querySelector("input, select, textarea");
    if (input) return String(input.value ?? "");
    return cell.textContent || "";
  }

  function sortTableByColumn(table, colIndex, th) {
    const tbody = table.tBodies[0];
    if (!tbody) return;
    const prev = th.getAttribute("data-sort");
    const dir = prev === "asc" ? "desc" : "asc";
    table.querySelectorAll("th.sortable-th").forEach((h) => h.removeAttribute("data-sort"));
    th.setAttribute("data-sort", dir);

    const rows = Array.from(tbody.rows).filter((row) => {
      if (row.cells.length === 0) return false;
      if (row.cells[0].colSpan > 1) return false;
      return true;
    });
    const placeholders = Array.from(tbody.rows).filter((row) => !rows.includes(row));

    rows.sort((a, b) => {
      const va = parseSortCellValue(cellSortText(a.cells[colIndex]));
      const vb = parseSortCellValue(cellSortText(b.cells[colIndex]));
      let cmp = 0;
      if (va.kind === "empty" && vb.kind !== "empty") cmp = 1;
      else if (vb.kind === "empty" && va.kind !== "empty") cmp = -1;
      else if (va.kind === "num" && vb.kind === "num") cmp = va.num - vb.num;
      else cmp = va.str.localeCompare(vb.str, "ru");
      return dir === "asc" ? cmp : -cmp;
    });

    rows.forEach((row) => tbody.appendChild(row));
    placeholders.forEach((row) => tbody.appendChild(row));
  }

  function initSortableTables() {
    document.querySelectorAll("table.sortable").forEach((table) => {
      if (table.dataset.sortBound === "1") return;
      table.dataset.sortBound = "1";
      const heads = table.tHead ? table.tHead.querySelectorAll("th") : [];
      heads.forEach((th, colIndex) => {
        if (th.hasAttribute("data-nosort")) return;
        th.classList.add("sortable-th");
        th.title = "Сортировать";
        th.tabIndex = 0;
        th.addEventListener("click", () => sortTableByColumn(table, colIndex, th));
        th.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            sortTableByColumn(table, colIndex, th);
          }
        });
      });
    });
  }

  resetPollCreateForm();
  initSortableTables();
  loadPoints();
})();
