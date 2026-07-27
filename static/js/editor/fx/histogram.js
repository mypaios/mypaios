/**
 * Draw a luminance histogram of a layer's pixels onto the given
 * canvas. Sampling is capped at ~400×400 so the call stays cheap on
 * very large images.
 *
 * If the layer has a staged Levels adjustment
 * (`layer._stagedAdj.params` with `inBlack` / `inWhite`), the two
 * endpoint markers are drawn over the bars.
 *
 * @param {HTMLCanvasElement} canvas  The histogram canvas to render into.
 * @param {{
 *   canvas: HTMLCanvasElement,
 *   _stagedAdj?: {params?: {inBlack?: number, inWhite?: number}}
 * }} layer                            Source layer.
 */
export function drawHistogram(canvas, layer) {
  if (!canvas) return;
  const w = canvas.width, h = canvas.height;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, w, h);

  // Down-sample huge images so the histogram stays interactive on 8k+
  // photos. ~400×400 is enough to characterise the distribution.
  const src = layer.canvas;
  const sw = src.width, sh = src.height;
  const maxSamples = 400;
  const sampleW = Math.min(maxSamples, sw);
  const sampleH = Math.min(maxSamples, sh);
  const tmp = document.createElement('canvas');
  tmp.width = sampleW; tmp.height = sampleH;
  const tctx = tmp.getContext('2d');
  tctx.drawImage(src, 0, 0, sampleW, sampleH);
  const img = tctx.getImageData(0, 0, sampleW, sampleH).data;

  const hist = new Uint32Array(256);
  for (let i = 0; i < img.length; i += 4) {
    if (img[i + 3] < 8) continue; // skip near-transparent
    // Rec. 709 luminance — common choice for histograms in photo editors.
    const Y = (0.2126 * img[i] + 0.7152 * img[i + 1] + 0.0722 * img[i + 2]) | 0;
    hist[Math.min(255, Y)]++;
  }
  let peak = 1;
  for (let i = 0; i < 256; i++) if (hist[i] > peak) peak = hist[i];

  // Background.
  ctx.fillStyle = 'rgba(255,255,255,0.05)';
  ctx.fillRect(0, 0, w, h);

  // Bars. sqrt-scaled so the long tails (specular highlights, deep
  // shadows) stay visible even when the central mass dominates.
  ctx.fillStyle = 'rgba(255,255,255,0.55)';
  for (let i = 0; i < 256; i++) {
    const x = (i / 256) * w;
    const bh = Math.pow(hist[i] / peak, 0.5) * h;
    ctx.fillRect(x, h - bh, w / 256 + 0.5, bh);
  }

  // Endpoint markers (input black / input white) from a staged Levels
  // adjustment, if one is in flight.
  const p = layer._stagedAdj?.params;
  if (p) {
    ctx.fillStyle = 'rgba(0,0,0,0.9)';
    ctx.fillRect((p.inBlack / 256) * w, 0, 1, h);
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.fillRect((p.inWhite / 256) * w, 0, 1, h);
  }
}
