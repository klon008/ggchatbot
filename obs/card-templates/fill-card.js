/**
 * Fill an empty card SVG template (no React).
 *
 * @param {SVGElement|ParentNode} root - SVG root or a container that holds it
 * @param {{ name?: string, portraitUrl?: string }} data
 */
export function fillCardTemplate(root, data = {}) {
  const svg = root instanceof SVGElement ? root : root.querySelector("svg.card-svg, svg[data-rarity]");
  if (!svg) throw new Error("card template SVG not found");

  if (data.name != null) {
    const el = svg.querySelector('[data-slot="name"]');
    if (el) {
      el.textContent = String(data.name).toUpperCase();
      el.setAttribute("opacity", "0.95");
    }
  }

  if (data.portraitUrl) {
    const img = svg.querySelector('[data-slot="portrait"]');
    if (img) {
      img.setAttribute("href", data.portraitUrl);
      img.setAttributeNS("http://www.w3.org/1999/xlink", "href", data.portraitUrl);
    }
    // hide placeholder dashed label once art is set
    const hint = svg.querySelector('text');
    // leave NAME alone; only hide PORTRAIT hint if present as sibling text near slot
    for (const t of svg.querySelectorAll("text")) {
      if (t.getAttribute("data-slot") === "name") continue;
      if ((t.textContent || "").trim() === "PORTRAIT") t.style.display = "none";
    }
    const dash = svg.querySelector('[data-slot="portrait-bg"]');
    if (dash) dash.style.display = "none";
  }

  return svg;
}

/** Convenience: fetch SVG text and inject into a host element. */
export async function mountCardTemplate(host, rarity, data) {
  const url = new URL(`./${rarity}.svg`, import.meta.url);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`failed to load ${rarity}.svg`);
  host.innerHTML = await res.text();
  return fillCardTemplate(host, data);
}
