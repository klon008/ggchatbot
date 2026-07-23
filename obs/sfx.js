/* Shared OBS overlay SFX — one Audio instance per URL, restart on replay. */
(function (global) {
  "use strict";

  var cache = Object.create(null);

  function playObsSfx(url) {
    if (!url) return;
    var audio = cache[url];
    if (!audio) {
      audio = new Audio(url);
      cache[url] = audio;
    }
    try {
      audio.currentTime = 0;
    } catch (e) {
      /* ignore seek before metadata */
    }
    var p = audio.play();
    if (p && typeof p.catch === "function") {
      p.catch(function () {});
    }
  }

  global.playObsSfx = playObsSfx;
})(typeof window !== "undefined" ? window : this);
