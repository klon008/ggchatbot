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
    });
  });

  loadPoints();
})();
