/**
 * Pixi water displacement background (vanilla port of FishingPixiBg).
 * Expects global PIXI from /fishing/pixi.min.js
 */
(function (global) {
  "use strict";

  var BG_URL = "/assets/fishing/bg.jpg";
  var MASK_URL = "/assets/fishing/water-mask.png";

  function prefersReducedMotion() {
    return !!(
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function loadLuminanceMask(url) {
    return new Promise(function (resolve, reject) {
      var el = new Image();
      el.decoding = "async";
      el.onload = function () {
        var w = el.naturalWidth || el.width;
        var h = el.naturalHeight || el.height;
        var canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        var ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (!ctx) {
          resolve(PIXI.Texture.from(el));
          return;
        }
        ctx.drawImage(el, 0, 0, w, h);
        var data = ctx.getImageData(0, 0, w, h);
        var d = data.data;
        for (var i = 0; i < d.length; i += 4) {
          var lum = (d[i] + d[i + 1] + d[i + 2]) / 3;
          d[i] = 255;
          d[i + 1] = 255;
          d[i + 2] = 255;
          d[i + 3] = lum;
        }
        ctx.putImageData(data, 0, 0);
        resolve(PIXI.Texture.from(canvas));
      };
      el.onerror = function () {
        reject(new Error("Failed to load mask: " + url));
      };
      el.src = url;
    });
  }

  function createNoiseTexture(size) {
    size = size || 256;
    var canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    var ctx = canvas.getContext("2d");
    if (!ctx) return PIXI.Texture.WHITE;
    var img = ctx.createImageData(size, size);
    for (var i = 0; i < img.data.length; i += 4) {
      img.data[i] = 100 + Math.random() * 55;
      img.data[i + 1] = 100 + Math.random() * 55;
      img.data[i + 2] = 128;
      img.data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    var texture = PIXI.Texture.from(canvas);
    if (texture.source) texture.source.addressMode = "repeat";
    return texture;
  }

  function fitCover(sprite, viewW, viewH, focusX, focusY) {
    focusX = focusX == null ? 0.5 : focusX;
    focusY = focusY == null ? 0.4 : focusY;
    var tw = sprite.texture.width;
    var th = sprite.texture.height;
    if (!tw || !th) return;
    var scale = Math.max(viewW / tw, viewH / th);
    sprite.scale.set(scale);
    sprite.x = viewW * 0.5 - tw * scale * focusX;
    sprite.y = viewH * 0.5 - th * scale * focusY;
  }

  /**
   * @param {HTMLElement} host
   * @param {{ focusY?: number, strength?: number }} opts
   * @returns {Promise<() => void>} destroy fn
   */
  async function mountFishingPixiBg(host, opts) {
    opts = opts || {};
    var focusY = opts.focusY == null ? 0.4 : opts.focusY;
    var strength = opts.strength == null ? 18 : opts.strength;

    if (!host || prefersReducedMotion() || typeof PIXI === "undefined") {
      host.style.backgroundImage = "url(" + BG_URL + ")";
      host.style.backgroundSize = "cover";
      host.style.backgroundPosition = "center 40%";
      return function () {};
    }

    var destroyed = false;
    var app = new PIXI.Application();
    await app.init({
      resizeTo: host,
      backgroundAlpha: 0,
      antialias: true,
      resolution: Math.min(window.devicePixelRatio || 1, 2),
      autoDensity: true,
      powerPreference: "low-power",
    });
    if (destroyed) {
      app.destroy(true);
      return function () {};
    }
    host.appendChild(app.canvas);
    app.canvas.className = "fishing-pixi-canvas";

    var bgTex = await PIXI.Assets.load(BG_URL);
    var maskTex = await loadLuminanceMask(MASK_URL);
    if (destroyed) return function () {};

    var noiseTex = createNoiseTexture(256);
    var root = new PIXI.Container();
    app.stage.addChild(root);

    var base = new PIXI.Sprite(bgTex);
    var water = new PIXI.Sprite(bgTex);
    var mask = new PIXI.Sprite(maskTex);
    var noise = new PIXI.Sprite(noiseTex);
    noise.scale.set(7.4);

    var displacement = new PIXI.DisplacementFilter({
      sprite: noise,
      scale: { x: strength, y: strength * 0.65 },
    });
    water.filters = [displacement];
    water.mask = mask;
    noise.renderable = false;
    root.addChild(base, water, mask, noise);

    function layout() {
      var w = app.screen.width;
      var h = app.screen.height;
      fitCover(base, w, h, 0.5, focusY);
      fitCover(water, w, h, 0.5, focusY);
      fitCover(mask, w, h, 0.5, focusY);
    }
    layout();
    app.renderer.on("resize", layout);
    app.ticker.add(function () {
      noise.x += 0.35;
      noise.y += 0.12;
    });

    return function destroy() {
      destroyed = true;
      try {
        app.renderer.off("resize", layout);
      } catch (e) {}
      app.destroy(true, { children: true });
      host.replaceChildren();
    };
  }

  global.mountFishingPixiBg = mountFishingPixiBg;
})(window);
