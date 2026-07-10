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

  let allPoints = [];
  let ordersEnabled = true;
  let queuePaused = false;

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

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      const id = tab.dataset.tab;
      document.getElementById(`panel-${id}`).classList.add("active");
      if (id === "queue") loadQueue();
    });
  });

  loadPoints();
})();
