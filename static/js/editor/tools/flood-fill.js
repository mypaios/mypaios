/**
 * Iterative 4-connected flood fill on RGBA pixel data.
 *
 * Pure function — takes the source pixel array + seed + tolerance and
 * returns a mask canvas with white where the fill landed. The legacy
 * gallery editor's magic-wand tool delegates to this.
 *
 * @param {Uint8ClampedArray|Uint8Array} src   RGBA bytes (length = w*h*4).
 * @param {number} w                           Pixel width.
 * @param {number} h                           Pixel height.
 * @param {number} seedX                       Floored seed X.
 * @param {number} seedY                       Floored seed Y.
 * @param {number} tolerance                   Tolerance 0..100. Internally
 *                                             squared and scaled to RGB+A
 *                                             space (max ≈ 195k at 100).
 * @returns {HTMLCanvasElement|null}           A `w × h` mask canvas with
 *                                             white-opaque pixels for
 *                                             visited cells, or null if
 *                                             the seed is out of bounds.
 */
export function floodFillMask(src, w, h, seedX, seedY, tolerance) {
  if (seedX < 0 || seedY < 0 || seedX >= w || seedY >= h) return null;

  const seedIdx = (seedY * w + seedX) * 4;
  const sr = src[seedIdx], sg = src[seedIdx + 1];
  const sb = src[seedIdx + 2], sa = src[seedIdx + 3];

  // 0..100 → squared RGB+A distance threshold. Max single-channel diff
  // is 255, so sqrt(4 * 255²) ≈ 510; squared cap ≈ 195k at tol = 100.
  const tol = Math.pow(tolerance * 4.42, 2);

  const visited = new Uint8Array(w * h);
  const stack = [seedX, seedY];
  visited[seedY * w + seedX] = 1;
  while (stack.length) {
    const y = stack.pop();
    const x = stack.pop();
    const nbrs = [
      [x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1],
    ];
    for (const [nx, ny] of nbrs) {
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      const idx = ny * w + nx;
      if (visited[idx]) continue;
      const o = idx * 4;
      const dr = src[o] - sr, dg = src[o + 1] - sg;
      const db = src[o + 2] - sb, da = src[o + 3] - sa;
      // RGB + alpha-aware so a click on a transparent pixel selects
      // the transparent region cleanly.
      if (dr * dr + dg * dg + db * db + da * da <= tol) {
        visited[idx] = 1;
        stack.push(nx, ny);
      }
    }
  }

  const mask = document.createElement('canvas');
  mask.width = w;
  mask.height = h;
  const mCtx = mask.getContext('2d');
  const mData = mCtx.createImageData(w, h);
  for (let i = 0; i < w * h; i++) {
    if (visited[i]) {
      mData.data[i * 4]     = 255;
      mData.data[i * 4 + 1] = 255;
      mData.data[i * 4 + 2] = 255;
      mData.data[i * 4 + 3] = 255;
    }
  }
  mCtx.putImageData(mData, 0, 0);
  return mask;
}
