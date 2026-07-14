(function () {
  "use strict";

  const statusBar = document.getElementById("statusBar");
  const pointsBody = document.getElementById("pointsBody");
  const pointsFilter = document.getElementById("pointsFilter");
  const queueBody = document.getElementById("queueBody");
  const queuePlaying = document.getElementById("queuePlaying");
  const queueTogglePause = document.getElementById("queueTogglePause");
  const ordersStatus = document.getElementById("ordersStatus");
  const ordersToggle = document.getElementById("ordersToggle");
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

  const cardsDailyLimit = document.getElementById("cardsDailyLimit");
  const boostersBody = document.getElementById("boostersBody");
  const drawsBody = document.getElementById("drawsBody");
  const catalogBody = document.getElementById("catalogBody");
  const boosterPoolChips = document.getElementById("boosterPoolChips");
  const drawBooster = document.getElementById("drawBooster");
  const boosterForm = document.getElementById("boosterForm");
  const drawForm = document.getElementById("drawForm");

  let allPoints = [];
  let ordersEnabled = true;
  let queuePaused = false;
  let roulettePollTimer = null;
  let racesPollTimer = null;

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
  }

  async function loadOrdersState() {
    const data = await api("GET", "/api/song-request");
    ordersEnabled = !!data.orders_enabled;
    renderOrdersControl();
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
      renderOrdersControl();
      await loadQueue();
      setStatus(ordersEnabled ? "Заказы включены" : "Заказы отключены, очередь очищена", "ok");
    } catch (e) {
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
      return;
    }
    queueTogglePause.disabled = false;
    queueTogglePause.textContent = paused ? "Продолжить" : "Пауза";
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
  document.getElementById("syncUserNames").addEventListener("click", syncUserNames);
  ordersToggle.addEventListener("click", toggleOrders);

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

  let cardsCatalog = [];
  let cardsStoriesMeta = { loaded: false, count: 0, source: "data/card-assets-repo/src/app/cardDetails.json" };
  let cardsBoosters = [];
  let cardsDraws = [];
  let selectedPoolIds = new Set();
  let editingBoosterId = null;

  function cardThumb(c) {
    const src = c.image_url || `/assets/cards/${c.id}.webp`;
    return `<img class="thumb" src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" />`;
  }

  function renderCatalog() {
    if (!catalogBody) return;
    const metaEl = document.getElementById("catalogStoriesMeta");
    if (metaEl) {
      if (cardsStoriesMeta.loaded) {
        metaEl.textContent = `Лор: загружено ${cardsStoriesMeta.count} описаний из ${cardsStoriesMeta.source}`;
      } else {
        metaEl.textContent =
          "Лор: файл описаний не найден — запустите update.cmd (sync cardDetails.json)";
      }
    }
    if (!cardsCatalog.length) {
      catalogBody.innerHTML = '<tr><td colspan="5" class="empty">Нет карт</td></tr>';
      return;
    }
    catalogBody.innerHTML = cardsCatalog
      .map((c) => {
        const src = c.image_url || `/assets/cards/${c.id}.webp`;
        const story = (c.story || "").trim();
        const storyCell = story
          ? `<td class="catalog-story" title="${esc(story)}">${esc(story)}</td>`
          : `<td class="catalog-story empty-story">нет в JSON</td>`;
        return `<tr>
          <td><img class="catalog-thumb" src="${esc(src)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'" /></td>
          <td class="mono">${esc(c.id)}</td>
          <td>${esc(c.name)}</td>
          <td>${esc(c.rarity)}</td>
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

  function statusPill(status) {
    const cls = status === "active" ? "active" : status === "paused" ? "paused" : "inactive";
    return `<span class="status-pill ${cls}">${esc(status)}</span>`;
  }

  function renderBoosters() {
    drawBooster.innerHTML = cardsBoosters
      .map((b) => `<option value="${esc(b.id)}">${esc(b.name)} (${esc(b.id)})</option>`)
      .join("");

    if (!cardsBoosters.length) {
      boostersBody.innerHTML = '<tr><td colspan="5" class="empty">Нет бустеров</td></tr>';
      return;
    }

    boostersBody.innerHTML = cardsBoosters
      .map((b) => {
        const promo = b.promo_image_url
          ? `<a href="${esc(b.promo_image_url)}" target="_blank" rel="noopener">открыть</a>`
          : "—";
        return `<tr data-booster-id="${esc(b.id)}">
          <td class="mono">${esc(b.id)}</td>
          <td>${esc(b.name)}</td>
          <td>${esc((b.card_ids || []).length)}</td>
          <td>${promo}</td>
          <td class="actions">
            <button type="button" class="small btn-booster-edit" data-id="${esc(b.id)}">Пул</button>
            <label class="small" style="cursor:pointer">
              Promo <input type="file" accept="image/*" class="btn-booster-promo" data-id="${esc(b.id)}" hidden />
            </label>
          </td>
        </tr>`;
      })
      .join("");
  }

  function renderDraws() {
    if (!cardsDraws.length) {
      drawsBody.innerHTML = '<tr><td colspan="7" class="empty">Нет тиражей</td></tr>';
      return;
    }
    drawsBody.innerHTML = cardsDraws
      .map((d) => `<tr>
        <td class="mono">${esc(d.id)}</td>
        <td>${esc(d.name)}</td>
        <td>${esc(d.booster_name)}</td>
        <td>${esc(d.cost_points)}</td>
        <td>${esc(d.cards_per_open)}</td>
        <td>${statusPill(d.status)}</td>
        <td class="actions">
          ${d.status !== "active" ? `<button type="button" class="small primary btn-draw-activate" data-id="${esc(d.id)}">Активировать</button>` : ""}
          ${d.status === "active" ? `<button type="button" class="small btn-draw-pause" data-id="${esc(d.id)}">Пауза</button>` : ""}
          <button type="button" class="small btn-draw-copy" data-id="${esc(d.id)}">Копия</button>
        </td>
      </tr>`)
      .join("");
  }

  async function loadCards() {
    setStatus("Загрузка карт…");
    try {
      const [catalog, boosters, draws, meta] = await Promise.all([
        api("GET", "/api/cards/catalog"),
        api("GET", "/api/cards/boosters"),
        api("GET", "/api/cards/draws"),
        api("GET", "/api/cards/meta"),
      ]);
      cardsCatalog = catalog.items || [];
      cardsStoriesMeta = {
        loaded: Boolean(catalog.stories_loaded),
        count: catalog.stories_count || 0,
        source: catalog.stories_source || "data/card-assets-repo/src/app/cardDetails.json",
      };
      cardsBoosters = boosters.items || [];
      cardsDraws = draws.items || [];
      cardsDailyLimit.value = meta.daily_open_limit ?? 0;
      if (!editingBoosterId && cardsBoosters.length) {
        selectedPoolIds = new Set(cardsBoosters[0].card_ids || []);
        editingBoosterId = cardsBoosters[0].id;
      }
      renderBoosterPoolChips();
      renderCatalog();
      renderBoosters();
      renderDraws();
      setStatus("Карты загружены", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  }

  document.getElementById("cardsSaveMeta").addEventListener("click", async () => {
    const limit = parseInt(cardsDailyLimit.value, 10);
    if (Number.isNaN(limit) || limit < 0) {
      setStatus("Лимит >= 0", "err");
      return;
    }
    try {
      await api("PUT", "/api/cards/meta", { daily_open_limit: limit });
      setStatus("Лимит сохранён", "ok");
    } catch (e) {
      setStatus(e.message, "err");
    }
  });

  boosterForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("boosterId").value.trim().toLowerCase();
    const name = document.getElementById("boosterName").value.trim();
    if (!selectedPoolIds.size) {
      setStatus("Выберите хотя бы одну карту в пуле", "err");
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
      await loadCards();
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
    try {
      await api("POST", "/api/cards/draws", {
        id,
        name,
        booster_id,
        cost_points,
        cards_per_open,
        daily_limit: Number.isNaN(daily_limit) ? 0 : daily_limit,
        activate,
      });
      document.getElementById("drawId").value = "";
      document.getElementById("drawName").value = "";
      await loadCards();
      setStatus("Тираж создан", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
  });

  boostersBody.addEventListener("click", async (e) => {
    const editBtn = e.target.closest(".btn-booster-edit");
    if (editBtn) {
      const id = editBtn.dataset.id;
      const booster = cardsBoosters.find((b) => b.id === id);
      if (!booster) return;
      editingBoosterId = id;
      selectedPoolIds = new Set(booster.card_ids || []);
      renderBoosterPoolChips();
      const name = prompt("Название бустера", booster.name);
      if (name == null) return;
      if (!selectedPoolIds.size) {
        setStatus("Пул не может быть пустым", "err");
        return;
      }
      setStatus("Сохранение бустера…");
      try {
        await api("PUT", `/api/cards/boosters/${encodeURIComponent(id)}`, {
          name: name.trim(),
          card_ids: Array.from(selectedPoolIds),
        });
        await loadCards();
        setStatus("Бустер обновлён", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
      return;
    }
  });

  boostersBody.addEventListener("change", async (e) => {
    const fileInput = e.target.closest(".btn-booster-promo");
    if (!fileInput || !fileInput.files || !fileInput.files[0]) return;
    const id = fileInput.dataset.id;
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    setStatus("Загрузка promo…");
    try {
      const res = await fetch(`/api/cards/boosters/${encodeURIComponent(id)}/promo`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      await loadCards();
      setStatus("Promo загружен", "ok");
    } catch (err) {
      setStatus(err.message, "err");
    }
    fileInput.value = "";
  });

  drawsBody.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const id = btn.dataset.id;
    if (!id) return;
    if (btn.classList.contains("btn-draw-activate")) {
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/activate`);
        await loadCards();
        setStatus("Тираж активирован", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    } else if (btn.classList.contains("btn-draw-pause")) {
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/pause`);
        await loadCards();
        setStatus("Тираж на паузе", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    } else if (btn.classList.contains("btn-draw-copy")) {
      const src = cardsDraws.find((d) => d.id === id);
      const newId = prompt("id нового тиража", `${id}_copy`);
      if (!newId) return;
      const newName = prompt("Название", src ? `${src.name} (копия)` : "Новый тираж");
      if (!newName) return;
      const activate = confirm("Сразу активировать новый тираж?");
      try {
        await api("POST", `/api/cards/draws/${encodeURIComponent(id)}/copy`, {
          id: newId.trim().toLowerCase(),
          name: newName.trim(),
          activate,
        });
        await loadCards();
        setStatus("Тираж скопирован", "ok");
      } catch (err) {
        setStatus(err.message, "err");
      }
    }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
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
      if (id === "cards") loadCards();
    });
  });

  loadPoints();
})();
