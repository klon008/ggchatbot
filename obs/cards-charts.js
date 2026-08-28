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
  const RARITY_LABELS = {
    common: "common",
    uncommon: "uncommon",
    rare: "rare",
    epic: "epic",
    legendary: "legendary",
    mythic: "mythic",
    secretRare: "secretRare",
  };
  const RARITY_COLORS = {
    common: "#9A8050",
    uncommon: "#7AD868",
    rare: "#5898FF",
    epic: "#9070F0",
    legendary: "#FFB020",
    mythic: "#c45a48",
    secretRare: "#D4567A",
  };
  const STATUS_LABELS = {
    active: "активный",
    paused: "пауза",
    queued: "очередь",
    closed: "завершён",
    inactive: "неактивен",
  };

  const fmt = new Intl.NumberFormat("ru-RU");
  const params = new URLSearchParams(location.search);
  const drawId = (params.get("draw") || "").trim();
  const statusEl = document.getElementById("status");
  const contentEl = document.getElementById("content");
  const charts = [];

  function setStatus(text, isErr) {
    statusEl.textContent = text;
    statusEl.className = isErr ? "status err" : "status";
    statusEl.hidden = !text;
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function axisColor() {
    return "#8888a0";
  }

  function gridColor() {
    return "rgba(255,255,255,0.06)";
  }

  function tooltipTheme() {
    return {
      backgroundColor: "#1c1c2e",
      titleColor: "#9ecbff",
      bodyColor: "#e8e8f0",
      borderColor: "#3d3d5c",
      borderWidth: 1,
      padding: 10,
    };
  }

  function fmtBucketLabel(iso, bucketSec) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    if (bucketSec >= 86400) {
      return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short" });
    }
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function makeChart(canvasId, config) {
    const el = document.getElementById(canvasId);
    const chart = new Chart(el, config);
    charts.push(chart);
    return chart;
  }

  function renderKpis(totals) {
    const net = totals.spent - totals.refund;
    const dupRate =
      totals.cards > 0 ? Math.round((1000 * totals.dup_count) / totals.cards) / 10 : 0;
    const items = [
      { label: "Круток", value: fmt.format(totals.opens), hint: `${fmt.format(totals.players)} игроков` },
      { label: "Потрачено", value: fmt.format(totals.spent), hint: "принцесс" },
      { label: "Компенсация", value: fmt.format(totals.refund), hint: "возврат за повторы" },
      { label: "Чисто", value: fmt.format(net), hint: "потрачено − возврат" },
      { label: "Карт", value: fmt.format(totals.cards), hint: `${fmt.format(totals.new_count)} новых` },
      { label: "Повторы", value: `${dupRate}%`, hint: `${fmt.format(totals.dup_count)} дублей` },
    ];
    document.getElementById("kpis").innerHTML = items
      .map(
        (k) => `<div class="kpi">
        <div class="label">${esc(k.label)}</div>
        <div class="value">${esc(k.value)}</div>
        <div class="hint">${esc(k.hint)}</div>
      </div>`
      )
      .join("");
  }

  function commonOptions(extra) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: "#c8c8dc", boxWidth: 12, boxHeight: 12 },
        },
        tooltip: tooltipTheme(),
      },
      scales: extra && extra.scales ? extra.scales : undefined,
    };
  }

  function renderCharts(data) {
    const bucketSec = data.bucket_seconds || 3600;
    const labels = (data.timeline || []).map((row) => fmtBucketLabel(row.t, bucketSec));
    const opens = (data.timeline || []).map((row) => row.opens);
    const spent = (data.timeline || []).map((row) => row.spent);
    const refund = (data.timeline || []).map((row) => row.refund);
    const news = (data.timeline || []).map((row) => row.new_count);
    const dups = (data.timeline || []).map((row) => row.dup_count);

    makeChart("chartFlow", {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Крутки",
            data: opens,
            yAxisID: "y",
            borderColor: "#9ecbff",
            backgroundColor: "rgba(158,203,255,0.12)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: "Потрачено",
            data: spent,
            yAxisID: "y1",
            borderColor: "#FFB020",
            backgroundColor: "transparent",
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: "Компенсация",
            data: refund,
            yAxisID: "y1",
            borderColor: "#7AD868",
            borderDash: [5, 4],
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
        ],
      },
      options: {
        ...commonOptions(),
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            ticks: { color: axisColor(), maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
            grid: { color: gridColor() },
          },
          y: {
            position: "left",
            ticks: { color: axisColor() },
            grid: { color: gridColor() },
            title: { display: true, text: "крутки", color: axisColor() },
          },
          y1: {
            position: "right",
            ticks: { color: axisColor(), callback: (v) => fmt.format(v) },
            grid: { drawOnChartArea: false },
            title: { display: true, text: "принцессы", color: axisColor() },
          },
        },
      },
    });

    makeChart("chartRarityTime", {
      type: "bar",
      data: {
        labels,
        datasets: RARITIES.map((id) => ({
          label: RARITY_LABELS[id],
          data: (data.timeline || []).map((row) => (row.rarity && row.rarity[id]) || 0),
          backgroundColor: RARITY_COLORS[id],
          stack: "r",
          borderWidth: 0,
        })),
      },
      options: {
        ...commonOptions(),
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            stacked: true,
            ticks: { color: axisColor(), maxRotation: 0, autoSkip: true, maxTicksLimit: 12 },
            grid: { display: false },
          },
          y: {
            stacked: true,
            ticks: { color: axisColor() },
            grid: { color: gridColor() },
          },
        },
      },
    });

    const rarityRows = (data.rarity || []).filter((r) => r.count > 0);
    makeChart("chartRarityPie", {
      type: "doughnut",
      data: {
        labels: rarityRows.map((r) => RARITY_LABELS[r.id] || r.id),
        datasets: [
          {
            data: rarityRows.map((r) => r.count),
            backgroundColor: rarityRows.map((r) => RARITY_COLORS[r.id] || "#666"),
            borderWidth: 0,
          },
        ],
      },
      options: {
        ...commonOptions(),
        cutout: "62%",
        plugins: {
          legend: {
            position: "right",
            labels: { color: "#c8c8dc", boxWidth: 12 },
          },
          tooltip: {
            ...tooltipTheme(),
            callbacks: {
              label(ctx) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = total ? Math.round((1000 * ctx.raw) / total) / 10 : 0;
                return ` ${ctx.label}: ${fmt.format(ctx.raw)} (${pct}%)`;
              },
            },
          },
        },
      },
    });

    const weights = data.draw.rarity_weights || {};
    const weightSum = RARITIES.reduce((s, id) => s + (Number(weights[id]) || 0), 0);
    const dropTotal = (data.rarity || []).reduce((s, r) => s + r.count, 0);
    makeChart("chartExpected", {
      type: "bar",
      data: {
        labels: RARITIES.map((id) => RARITY_LABELS[id]),
        datasets: [
          {
            label: "Факт, %",
            data: RARITIES.map((id) => {
              const row = (data.rarity || []).find((r) => r.id === id);
              const n = row ? row.count : 0;
              return dropTotal ? Math.round((1000 * n) / dropTotal) / 10 : 0;
            }),
            backgroundColor: RARITIES.map((id) => RARITY_COLORS[id]),
          },
          {
            label: "Веса тиража, %",
            data: RARITIES.map((id) => {
              const w = Number(weights[id]) || 0;
              return weightSum ? Math.round((1000 * w) / weightSum) / 10 : 0;
            }),
            backgroundColor: "rgba(158,203,255,0.35)",
            borderColor: "#9ecbff",
            borderWidth: 1,
          },
        ],
      },
      options: {
        ...commonOptions(),
        scales: {
          x: { ticks: { color: axisColor() }, grid: { display: false } },
          y: {
            ticks: { color: axisColor(), callback: (v) => `${v}%` },
            grid: { color: gridColor() },
            beginAtZero: true,
          },
        },
      },
    });

    makeChart("chartNewDup", {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Новые",
            data: news,
            borderColor: "#7AD868",
            backgroundColor: "rgba(122,216,104,0.18)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
          {
            label: "Повторы",
            data: dups,
            borderColor: "#D4567A",
            backgroundColor: "rgba(212,86,122,0.16)",
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 2,
          },
        ],
      },
      options: {
        ...commonOptions(),
        interaction: { mode: "index", intersect: false },
        scales: {
          x: {
            ticks: { color: axisColor(), maxRotation: 0, autoSkip: true, maxTicksLimit: 10 },
            grid: { color: gridColor() },
          },
          y: {
            stacked: true,
            ticks: { color: axisColor() },
            grid: { color: gridColor() },
          },
        },
      },
    });

    const topPlayers = (data.players || []).slice(0, 12);
    makeChart("chartPlayers", {
      type: "bar",
      data: {
        labels: topPlayers.map((p) => p.user_name || p.user_id),
        datasets: [
          {
            label: "Потрачено",
            data: topPlayers.map((p) => p.spent_points),
            backgroundColor: "#4a7ab0",
          },
          {
            label: "Компенсация",
            data: topPlayers.map((p) => p.refund_points),
            backgroundColor: "#7AD868",
          },
        ],
      },
      options: {
        ...commonOptions(),
        indexAxis: "y",
        scales: {
          x: {
            ticks: { color: axisColor(), callback: (v) => fmt.format(v) },
            grid: { color: gridColor() },
          },
          y: { ticks: { color: axisColor() }, grid: { display: false } },
        },
      },
    });

    function makeCardAppearChart(canvasId, cards) {
      makeChart(canvasId, {
        type: "bar",
        data: {
          labels: cards.map((c) => c.name),
          datasets: [
            {
              label: "Выпадения",
              data: cards.map((c) => c.appear_count),
              backgroundColor: cards.map((c) => RARITY_COLORS[c.rarity] || "#666"),
            },
          ],
        },
        options: {
          ...commonOptions(),
          plugins: {
            legend: { display: false },
            tooltip: {
              ...tooltipTheme(),
              callbacks: {
                afterLabel(ctx) {
                  const card = cards[ctx.dataIndex];
                  if (!card) return "";
                  return `${card.rarity} · новых ${card.new_count} · повторов ${card.dup_count}`;
                },
              },
            },
          },
          scales: {
            x: {
              ticks: {
                color: cards.map((c) => RARITY_COLORS[c.rarity] || "#e8e8f0"),
                font: { weight: "600" },
                maxRotation: 40,
                minRotation: 40,
                autoSkip: false,
              },
              grid: { display: false },
            },
            y: {
              ticks: { color: axisColor() },
              grid: { color: gridColor() },
              beginAtZero: true,
            },
          },
        },
      });
    }

    const allCards = data.cards || [];
    const topCards = allCards.slice(0, 18);
    const rarityRank = Object.fromEntries(RARITIES.map((id, i) => [id, i]));
    const rareCards = allCards
      .slice()
      .sort((a, b) => {
        const d = a.appear_count - b.appear_count;
        if (d !== 0) return d;
        return (rarityRank[b.rarity] ?? 0) - (rarityRank[a.rarity] ?? 0);
      })
      .slice(0, 18);
    makeCardAppearChart("chartCards", topCards);
    makeCardAppearChart("chartCardsRare", rareCards);
  }

  async function main() {
    if (typeof Chart === "undefined") {
      setStatus("Не удалось загрузить Chart.js (нужен интернет к CDN).", true);
      return;
    }
    Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
    Chart.defaults.color = "#c8c8dc";
    if (!drawId) {
      document.getElementById("subtitle").textContent = "Тираж не указан";
      setStatus("Откройте графики кнопкой на вкладке Статистика, выбрав тираж.", true);
      return;
    }
    try {
      const res = await fetch(`/api/cards/draws/${encodeURIComponent(drawId)}/stats/charts`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || data.message || `HTTP ${res.status}`);
      }
      const draw = data.draw || {};
      document.title = `Графики · ${draw.name || drawId}`;
      document.getElementById("title").textContent = `Тираж «${draw.name || drawId}»`;
      document.getElementById("subtitle").innerHTML =
        `<span class="mono">${esc(draw.id || drawId)}</span> · ${esc(draw.booster_name || "—")} · ${esc(
          STATUS_LABELS[draw.status] || draw.status || ""
        )} · ${fmt.format(data.totals.opens)} круток`;
      renderKpis(data.totals || {});
      renderCharts(data);
      contentEl.hidden = false;
      if (!data.totals.opens) {
        setStatus("В этом тираже пока нет круток — графики пустые.", false);
      } else {
        setStatus("");
      }
    } catch (err) {
      setStatus(err.message || String(err), true);
    }
  }

  main();
})();
