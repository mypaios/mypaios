/**
 * Pure blur renderers shared by the editor's live-preview popups.
 *
 * Each export matches the `renderer(snap, params, dst)` signature
 * expected by `_applyLiveBlur` in galleryEditor.js — `snap` is the
 * pre-blur snapshot canvas, `params` is the slider values object, and
 * `dst` is the 2D context to draw the final result into. No module
 * state.
 */

/**
 * Gaussian blur with clamp-to-edge sampling.
 *
 * Canvas `filter: blur()` naively blends with TRANSPARENT pixels outside
 * the image which fades the borders out. To match Photoshop's
 * "Edge: Clamp" Gaussian we pad the source onto a larger buffer with
 * the edge pixels stretched into the margin (4 strips + 4 corners),
 * blur the padded buffer, then copy only the original-size centre back.
 *
 * @param {HTMLCanvasElement} snap
 * @param {{ radius: number }} v
 * @param {CanvasRenderingContext2D} dst
 */
export function gaussianBlur(snap, v, dst) {
  if (!v.radius || v.radius <= 0) { dst.drawImage(snap, 0, 0); return; }
  const r = v.radius;
  const w = snap.width, h = snap.height;
  // Margin needs to cover the kernel's effective reach — most
  // engines saturate within ~2× the radius.
  const m = Math.ceil(r * 2 + 4);
  const pad = document.createElement('canvas');
  pad.width = w + m * 2;
  pad.height = h + m * 2;
  const pctx = pad.getContext('2d');
  pctx.drawImage(snap, m, m);
  // Edge strips: drawImage with src height=1 (or width=1) into a
  // dst region of size `m` stretches the edge pixels into the
  // margin — same effect as clamp-to-edge sampling.
  pctx.drawImage(snap, 0, 0, w, 1, m, 0, w, m);
  pctx.drawImage(snap, 0, h - 1, w, 1, m, m + h, w, m);
  pctx.drawImage(snap, 0, 0, 1, h, 0, m, m, h);
  pctx.drawImage(snap, w - 1, 0, 1, h, m + w, m, m, h);
  // Corners — stretch the corner pixel into an m×m block.
  pctx.drawImage(snap, 0, 0, 1, 1, 0, 0, m, m);
  pctx.drawImage(snap, w - 1, 0, 1, 1, m + w, 0, m, m);
  pctx.drawImage(snap, 0, h - 1, 1, 1, 0, m + h, m, m);
  pctx.drawImage(snap, w - 1, h - 1, 1, 1, m + w, m + h, m, m);
  // Blur the padded buffer and crop the original-size centre back.
  const out = document.createElement('canvas');
  out.width = pad.width;
  out.height = pad.height;
  const octx = out.getContext('2d');
  octx.filter = `blur(${r}px)`;
  octx.drawImage(pad, 0, 0);
  octx.filter = 'none';
  dst.drawImage(out, m, m, w, h, 0, 0, w, h);
}


/**
 * Zoom blur — radial smear from the canvas centre. 16 scaled copies at
 * low alpha approximate a Gaussian zoom blur.
 *
 * @param {HTMLCanvasElement} snap
 * @param {{ strength: number }} v
 * @param {CanvasRenderingContext2D} dst
 */
export function zoomBlur(snap, v, dst) {
  const w = snap.width, h = snap.height;
  const steps = 16;
  dst.drawImage(snap, 0, 0);
  dst.globalAlpha = 0.18;
  for (let s = 1; s <= steps; s++) {
    const t = s / steps;
    const scale = 1 + (v.strength / 200) * t;
    const sw = w * scale, sh = h * scale;
    dst.drawImage(snap, (w - sw) / 2, (h - sh) / 2, sw, sh);
  }
  dst.globalAlpha = 1;
}


/**
 * Motion blur — directional smear along a user-chosen angle.
 *
 * Each shifted stamp is rendered at globalAlpha = 1/steps with
 * globalCompositeOperation = 'lighter' (additive) into an offscreen
 * accumulator, then blitted onto `dst`. Lighter adds premultiplied src
 * to dst, so N stamps each contributing snap.RGB/N sum to snap.RGB and
 * alpha sums to 1. Source-over blending would cause colour wash-out
 * because each stamp would blend over the dst instead of summing into
 * it. Using an accumulator keeps `dst` clean if anything throws mid-way.
 *
 * @param {HTMLCanvasElement} snap
 * @param {{ length: number, angle: number }} v
 * @param {CanvasRenderingContext2D} dst
 */
export function motionBlur(snap, v, dst) {
  const w = snap.width, h = snap.height;
  const rad = (v.angle * Math.PI) / 180;
  const dx = Math.cos(rad);
  const dy = Math.sin(rad);
  // Step count = roughly one sample per pixel of length, capped
  // so very long blurs don't tank performance.
  const steps = Math.max(4, Math.min(80, Math.round(v.length)));
  const acc = document.createElement('canvas');
  acc.width = w; acc.height = h;
  const actx = acc.getContext('2d');
  actx.globalCompositeOperation = 'lighter';
  actx.globalAlpha = 1 / steps;
  for (let i = 0; i < steps; i++) {
    const t = (i / Math.max(1, steps - 1)) - 0.5;
    actx.drawImage(snap, dx * v.length * t, dy * v.length * t);
  }
  actx.globalCompositeOperation = 'source-over';
  actx.globalAlpha = 1;
  dst.drawImage(acc, 0, 0);
}
