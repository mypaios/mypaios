/**
 * Paint a transparency-checkerboard pattern across the given canvas
 * context. The editor uses this beneath every layer pass so empty
 * (transparent) areas of the document are visible.
 *
 * Pure function — depends only on its arguments.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} w  Width in canvas pixels.
 * @param {number} h  Height in canvas pixels.
 */
export function drawCheckerboard(ctx, w, h) {
  const size = 10;
  ctx.fillStyle = '#ccc';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#fff';
  for (let y = 0; y < h; y += size) {
    for (let x = 0; x < w; x += size) {
      if ((Math.floor(x / size) + Math.floor(y / size)) % 2 === 0) {
        ctx.fillRect(x, y, size, size);
      }
    }
  }
}
