/**
 * Fishing board — WS client + render + pulse/count/fade animations.
 * URL: http://127.0.0.1:PORT/fishing/board.html
 */
(function () {
  "use strict";

  var WS_PATH = "/ws";
  var RECONNECT_MS = 2000;

  var FISH_ART = {
    Осётр: "/assets/fishing/fish/osyotr.png",
    Сазан: "/assets/fishing/fish/sazan.png",
    Сом: "/assets/fishing/fish/som.png",
    Щука: "/assets/fishing/fish/shchuka.png",
    Судак: "/assets/fishing/fish/sudak.png",
    Жерех: "/assets/fishing/fish/zherekh.png",
    Линь: "/assets/fishing/fish/lin.png",
    Лещ: "/assets/fishing/fish/leshch.png",
    Окунь: "/assets/fishing/fish/okun.png",
    Карась: "/assets/fishing/fish/karas.png",
    Плотва: "/assets/fishing/fish/plotva.png",
    Язь: "/assets/fishing/fish/yaz.png",
  };

  var SPECIES_ORDER = [
    "Карась",
    "Плотва",
    "Окунь",
    "Линь",
    "Язь",
    "Лещ",
    "Сазан",
    "Жерех",
    "Судак",
    "Щука",
    "Сом",
    "Осётр",
  ];

  /** w_max вида — как FISH_SPECIES[*][2] в bot/fishing/settings.py. Трофей: weight > w_max. */
  var FISH_W_MAX = {
    Карась: 0.8,
    Плотва: 0.55,
    Окунь: 1.2,
    Линь: 3.0,
    Язь: 2.8,
    Лещ: 2.0,
    Сазан: 8.0,
    Жерех: 4.0,
    Судак: 5.0,
    Щука: 4.0,
    Сом: 8.0,
    Осётр: 12.0,
  };

  function isCatchTrophy(species, weight) {
    var max = FISH_W_MAX[species];
    if (max == null || !isFinite(weight)) return false;
    return weight > max + 1e-6;
  }

  var TROPHY_BADGE_HTML =
    '<div class="card-trophy-badge" title="Трофейный улов" aria-label="Трофейный улов">' +
    '<svg viewBox="0 0 24 24" aria-hidden="true">' +
    '<path fill="currentColor" d="M7 3h10v2h2.2A2.3 2.3 0 0 1 21.5 7.3c0 2.4-1.8 4.3-4.2 4.6L16.4 14.5H18v2.2H6v-2.2h1.6l-.9-2.6A4.6 4.6 0 0 1 2.5 7.3 2.3 2.3 0 0 1 4.8 5H7V3Zm1.6 2v4.1c-1.6-.25-2.7-1.4-2.7-2.7 0-.7.5-1.4 1.2-1.4h1.5Zm8.8 0h1.5c.7 0 1.2.7 1.2 1.4 0 1.3-1.1 2.45-2.7 2.7V5ZM8.2 18.2h7.6V21H8.2v-2.8Z"/>' +
    "</svg></div>";

  /**
   * Порядок слотов в сетке.
   * "weight"  — пойманные по убыванию веса, пустые в конце (по SPECIES_ORDER)
   * "species" — фиксированный порядок видов (старое поведение)
   * Переключение: константа ниже или ?sort=species / ?sort=weight
   */
  var SORT_MODE = "weight";
  (function () {
    var q = new URLSearchParams(location.search).get("sort");
    if (q === "weight" || q === "species") SORT_MODE = q;
  })();

  /** @returns {string[]} */
  function slotSpeciesOrder(bySpecies) {
    if (SORT_MODE === "species") {
      return SPECIES_ORDER.slice();
    }
    // Пойманные: от большего веса к меньшему; пустые — в конце
    var filled = SPECIES_ORDER.filter(function (sp) {
      return !!bySpecies[sp];
    }).sort(function (a, b) {
      var wa = Number(bySpecies[a].weight) || 0;
      var wb = Number(bySpecies[b].weight) || 0;
      if (wb !== wa) return wb - wa;
      return SPECIES_ORDER.indexOf(a) - SPECIES_ORDER.indexOf(b);
    });
    var empty = SPECIES_ORDER.filter(function (sp) {
      return !bySpecies[sp];
    });
    return filled.concat(empty);
  }

  /** Гарантированно выставить порядок детей сетки по списку ключей. */
  function applyGridOrder(parent, prefix, speciesList) {
    var frag = document.createDocumentFragment();
    speciesList.forEach(function (sp) {
      var el = findCard(parent, prefix + sp);
      if (el) frag.appendChild(el);
    });
    parent.appendChild(frag);
  }

  var weekLabel = document.getElementById("week-label");
  var weekHero = document.getElementById("week-hero");
  var weekGrid = document.getElementById("week-grid");
  var trophyGrid = document.getElementById("trophy-grid");
  var statusEl = document.getElementById("status");

  /** @type {Record<string, {species:string,user_name:string,weight:number}>} */
  var weekBySpecies = {};
  /** @type {Record<string, {species:string,user_name:string,weight:number}>} */
  var trophyBySpecies = {};
  /** @type {{species:string,user_name:string,weight:number}|null} */
  var fishOfWeek = null;

  var ws = null;
  var reconnectTimer = null;
  var reduceMotion =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setStatus(text, show) {
    if (!statusEl) return;
    if (!show) {
      statusEl.hidden = true;
      return;
    }
    statusEl.hidden = false;
    statusEl.textContent = text;
  }

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + WS_PATH;
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function connect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    setStatus("Подключение…", true);
    try {
      ws = new WebSocket(wsUrl());
    } catch (e) {
      setStatus("Ошибка WS", true);
      scheduleReconnect();
      return;
    }
    ws.onopen = function () {
      setStatus("Онлайн", false);
      send({ status: "ready", overlay: "fishing_board" });
    };
    ws.onmessage = function (ev) {
      var data;
      try {
        data = JSON.parse(ev.data);
      } catch (e) {
        return;
      }
      if (!data || data.action !== "fishing_board") return;
      applyPayload(data);
    };
    ws.onclose = function () {
      setStatus("Переподключение…", true);
      scheduleReconnect();
    };
    ws.onerror = function () {
      try {
        ws.close();
      } catch (e) {}
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(connect, RECONNECT_MS);
  }

  function publicCatch(row) {
    if (!row) return null;
    return {
      species: String(row.species || ""),
      user_name: String(row.user_name || ""),
      weight: Number(row.weight) || 0,
    };
  }

  function indexBySpecies(list) {
    var map = {};
    (list || []).forEach(function (raw) {
      var row = publicCatch(raw);
      if (row && row.species) map[row.species] = row;
    });
    return map;
  }

  function applyPayload(data) {
    var animate = data.kind === "update" && !reduceMotion;
    var changed = data.changed || {};
    var changedWeek = new Set(changed.week || []);
    var changedTrophies = new Set(changed.trophies || []);
    var fowChanged = !!changed.fish_of_week;

    var prevWeek = weekBySpecies;
    var prevTrophy = trophyBySpecies;
    var prevFow = fishOfWeek;

    weekBySpecies = indexBySpecies(data.week_leaders);
    trophyBySpecies = indexBySpecies(data.trophies);
    fishOfWeek = publicCatch(data.fish_of_week);

    if (weekLabel) {
      weekLabel.textContent = data.week_id ? "Неделя " + data.week_id : "—";
    }

    renderWeek(animate, changedWeek, fowChanged, prevWeek, prevFow);
    renderTrophies(animate, changedTrophies, prevTrophy);
  }

  function rankClass(rank) {
    if (rank === 1) return "card-rank card-rank--1";
    if (rank === 2) return "card-rank card-rank--2";
    if (rank === 3) return "card-rank card-rank--3";
    return "card-rank card-rank--n";
  }

  function cardMod(rank) {
    if (rank === 1) return "card--rank1";
    if (rank === 2) return "card--rank2";
    if (rank === 3) return "card--rank3";
    return "";
  }

  function findCard(parent, key) {
    var cards = parent.querySelectorAll(".card[data-key]");
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].getAttribute("data-key") === key) return cards[i];
    }
    return null;
  }

  function ensureCard(parent, key, hero) {
    var el = findCard(parent, key);
    if (el) return el;
    el = document.createElement("div");
    el.className = "card" + (hero ? " card--hero" : "");
    el.setAttribute("data-key", key);
    el.innerHTML =
      '<div class="card-fish" aria-hidden="true"></div>' +
      TROPHY_BADGE_HTML +
      '<div class="card-rank"></div>' +
      '<div class="card-species"></div>' +
      '<div class="card-weight-row"><span class="card-weight">0.00</span><span class="card-unit">кг</span></div>' +
      '<div class="card-player-row"><span class="card-dot"></span><span class="card-player"></span></div>';
    parent.appendChild(el);
    return el;
  }

  function setFishArt(card, species) {
    var wrap = card.querySelector(".card-fish");
    if (!wrap) return;
    var src = FISH_ART[species];
    if (!src) {
      wrap.innerHTML = "";
      return;
    }
    var img = wrap.querySelector("img");
    if (!img) {
      img = document.createElement("img");
      img.alt = "";
      img.draggable = false;
      wrap.appendChild(img);
    }
    if (img.getAttribute("src") !== src) img.src = src;
  }

  function animateWeight(el, from, to, ms) {
    ms = ms || 750;
    if (reduceMotion || from === to) {
      el.textContent = to.toFixed(2);
      el.dataset.value = String(to);
      return;
    }
    var start = performance.now();
    function frame(now) {
      var t = Math.min(1, (now - start) / ms);
      var eased = 1 - Math.pow(1 - t, 3);
      var v = from + (to - from) * eased;
      el.textContent = v.toFixed(2);
      if (t < 1) requestAnimationFrame(frame);
      else {
        el.textContent = to.toFixed(2);
        el.dataset.value = String(to);
      }
    }
    requestAnimationFrame(frame);
  }

  function setPlayer(el, name, fade) {
    if (!el) return;
    var next = name || "—";
    if (!fade || reduceMotion || el.textContent === next) {
      el.textContent = next;
      el.classList.remove("is-fading");
      return;
    }
    el.classList.add("is-fading");
    setTimeout(function () {
      el.textContent = next;
      el.classList.remove("is-fading");
    }, 280);
  }

  function pulse(card) {
    if (!card || reduceMotion) return;
    card.classList.remove("is-pulse");
    void card.offsetWidth;
    card.classList.add("is-pulse");
    setTimeout(function () {
      card.classList.remove("is-pulse");
    }, 1300);
  }

  function updateCard(card, entry, rank, doAnim, prevEntry) {
    var weightEl = card.querySelector(".card-weight");
    var playerEl = card.querySelector(".card-player");
    var rankEl = card.querySelector(".card-rank");
    var speciesEl = card.querySelector(".card-species");

    var prevW =
      prevEntry && typeof prevEntry.weight === "number"
        ? prevEntry.weight
        : Number(weightEl.dataset.value || 0);
    var prevName =
      prevEntry && prevEntry.user_name
        ? prevEntry.user_name
        : playerEl.textContent || "";

    var isHero =
      card.classList.contains("card--hero") ||
      card.getAttribute("data-key").indexOf("hero:") === 0 ||
      card.getAttribute("data-key") === "hero";
    card.className =
      "card" +
      (isHero ? " card--hero" : "") +
      " " +
      cardMod(rank) +
      (isCatchTrophy(entry.species, entry.weight) ? " card--catch-trophy" : "");

    rankEl.className = rankClass(rank);
    rankEl.textContent = String(rank);
    speciesEl.textContent = entry.species;
    setFishArt(card, entry.species);

    var nameChanged = !!prevName && prevName !== "—" && prevName !== entry.user_name;
    var weightChanged = Math.abs(prevW - entry.weight) > 1e-6 && prevW > 0;
    var isNew = doAnim && prevW <= 0 && !prevName;

    if (doAnim && (weightChanged || nameChanged || isNew)) {
      if (weightChanged) animateWeight(weightEl, prevW, entry.weight);
      else {
        weightEl.textContent = entry.weight.toFixed(2);
        weightEl.dataset.value = String(entry.weight);
      }
      setPlayer(playerEl, entry.user_name, nameChanged);
      pulse(card);
    } else {
      weightEl.textContent = entry.weight.toFixed(2);
      weightEl.dataset.value = String(entry.weight);
      setPlayer(playerEl, entry.user_name, false);
    }
  }

  function renderWeek(animate, changedSet, fowChanged, prevWeek, prevFow) {
    var entries = Object.keys(weekBySpecies)
      .map(function (k) {
        return weekBySpecies[k];
      })
      .sort(function (a, b) {
        return (Number(b.weight) || 0) - (Number(a.weight) || 0);
      });

    var rankOf = {};
    entries.forEach(function (e, i) {
      rankOf[e.species] = i + 1;
    });

    // Hero: рыба недели или самый тяжёлый; если пусто — плейсхолдер
    Array.prototype.slice.call(weekHero.querySelectorAll(".card--empty")).forEach(function (n) {
      n.remove();
    });

    if (!entries.length) {
      weekHero.innerHTML = "";
      var emptyHero = document.createElement("div");
      emptyHero.className = "card card--hero card--empty";
      emptyHero.setAttribute("data-key", "hero-empty");
      emptyHero.textContent = "Рыба недели пока не определена";
      weekHero.appendChild(emptyHero);
    } else {
      var hero = fishOfWeek || entries[0];
      var heroCard = ensureCard(weekHero, "hero", true);
      Array.prototype.slice.call(weekHero.children).forEach(function (ch) {
        if (ch !== heroCard) ch.remove();
      });
      var prevHero =
        (prevFow && prevFow.species === hero.species && prevFow) ||
        (prevWeek && prevWeek[hero.species]) ||
        null;
      updateCard(
        heroCard,
        hero,
        1,
        animate && (fowChanged || changedSet.has(hero.species)),
        prevHero
      );
    }

    // Сетка: 12 слотов; пойманные — от большого веса к малому
    var weekOrder = slotSpeciesOrder(weekBySpecies);
    var keep = {};
    weekOrder.forEach(function (sp) {
      var entry = weekBySpecies[sp];
      var key = "week:" + sp;
      keep[key] = true;
      if (!entry) {
        var empty = findCard(weekGrid, key);
        if (empty && !empty.classList.contains("card--empty")) {
          empty.remove();
          empty = null;
        }
        if (!empty) {
          empty = document.createElement("div");
          empty.className = "card card--empty";
          empty.setAttribute("data-key", key);
          weekGrid.appendChild(empty);
        }
        empty.textContent = sp;
        return;
      }
      var staleEmpty = findCard(weekGrid, key);
      if (staleEmpty && staleEmpty.classList.contains("card--empty")) {
        staleEmpty.remove();
      }
      var card = ensureCard(weekGrid, key, false);
      updateCard(
        card,
        entry,
        rankOf[sp] || 99,
        animate && changedSet.has(sp),
        prevWeek && prevWeek[sp]
      );
    });
    Array.prototype.slice.call(weekGrid.querySelectorAll(".card[data-key]")).forEach(function (ch) {
      if (!keep[ch.getAttribute("data-key")]) ch.remove();
    });
    applyGridOrder(weekGrid, "week:", weekOrder);
  }

  function renderTrophies(animate, changedSet, prevTrophy) {
    var list = SPECIES_ORDER.map(function (sp) {
      return trophyBySpecies[sp];
    }).filter(Boolean);

    var byWeight = list.slice().sort(function (a, b) {
      var wa = Number(a.weight) || 0;
      var wb = Number(b.weight) || 0;
      return wb - wa;
    });
    var rankOf = {};
    byWeight.forEach(function (e, i) {
      rankOf[e.species] = i + 1;
    });

    if (!list.length) {
      trophyGrid.innerHTML = "";
      SPECIES_ORDER.forEach(function (sp) {
        var empty = document.createElement("div");
        empty.className = "card card--empty";
        empty.setAttribute("data-key", "trophy:" + sp);
        empty.textContent = sp;
        trophyGrid.appendChild(empty);
      });
      return;
    }

    var trophyOrder = slotSpeciesOrder(trophyBySpecies);
    var keep = {};
    trophyOrder.forEach(function (sp) {
      var entry = trophyBySpecies[sp];
      var key = "trophy:" + sp;
      keep[key] = true;
      if (!entry) {
        var empty = findCard(trophyGrid, key);
        if (empty && !empty.classList.contains("card--empty")) {
          empty.remove();
          empty = null;
        }
        if (!empty) {
          empty = document.createElement("div");
          empty.className = "card card--empty";
          empty.setAttribute("data-key", key);
          trophyGrid.appendChild(empty);
        }
        empty.textContent = sp;
        return;
      }
      var staleEmpty = findCard(trophyGrid, key);
      if (staleEmpty && staleEmpty.classList.contains("card--empty")) {
        staleEmpty.remove();
      }
      var card = ensureCard(trophyGrid, key, false);
      updateCard(
        card,
        entry,
        rankOf[sp] || 99,
        animate && changedSet.has(sp),
        prevTrophy && prevTrophy[sp]
      );
    });
    Array.prototype.slice.call(trophyGrid.querySelectorAll(".card[data-key]")).forEach(function (ch) {
      if (!keep[ch.getAttribute("data-key")]) ch.remove();
    });
    applyGridOrder(trophyGrid, "trophy:", trophyOrder);
  }

  // Boot
  var host = document.getElementById("pixi-host");
  if (host && typeof mountFishingPixiBg === "function") {
    mountFishingPixiBg(host, { focusY: 0.4, strength: 18 }).catch(function (err) {
      console.error("[fishing-board] pixi", err);
      host.style.backgroundImage = "url(/assets/fishing/bg.jpg)";
      host.style.backgroundSize = "cover";
      host.style.backgroundPosition = "center 40%";
    });
  }

  connect();
})();
