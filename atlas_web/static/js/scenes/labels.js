// HTML labels over a 3D stage: clamped inside the stage and greedily de-collided in priority order (pinned first:
// hovered / selected), so two labels never overlap and none is clipped at the stage edge. Widths are measured once
// per text (cached on the element) to avoid layout work every frame.
const PAD = 4;
export function placeLabels(list, W, H, placed = []) {
  placed.length = 0;
  for (const it of list) {
    const e = it.e;
    if (it.off) { e.hidden = true; continue; }
    if (e._t !== e.textContent) { e._t = e.textContent; e.hidden = false; e._w = e.offsetWidth; e._h = e.offsetHeight; }
    const w = e._w || 1, h = e._h || 1;
    if (w > W - 2 * PAD || h > H - 2 * PAD) { e.hidden = true; continue; }  // wider than the stage: never clipped
    const x = Math.min(Math.max(it.x - w / 2, PAD), W - w - PAD), y = Math.min(Math.max(it.below ? it.y : it.y - h, PAD), H - h - PAD);
    if (!it.pin && placed.some((q) => x < q[2] && q[0] < x + w && y < q[3] && q[1] < y + h)) { e.hidden = true; continue; }
    placed.push([x, y, x + w, y + h]);
    e.hidden = false;
    e.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
  }
}
