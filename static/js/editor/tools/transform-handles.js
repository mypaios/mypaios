/**
 * Transform-tool handle rendering + hit-testing + overlay sync.
 *
 * Lives separately from `transform-drag.js` (which owns the drag
 * STATE MACHINE) because these three helpers are pure geometry that
 * happens to read shared state — they don't track in-progress drags,
 * they just paint and hit-test.
 *
 *  - `syncOverlay(margin)`  positions the overlay canvas + sizes its
 *                           bitmap based on the main canvas + zoom.
 *  - `drawHandles(margin)`  draws the rotated bounding outline + 4
 *                           corner handles + the rotation knob (with
 *                           hover / active visual states).
 *  - `getHandleAt(x, y)`    returns the handle id under (x, y), or
 *                           null. Geometry MUST mirror `drawHandles`
 *                           exactly or the user grabs phantom points.
 *
 * No event listeners attached here — the dispatcher in
 * editor/tools/transform-drag.js calls `getHandleAt` and routes
 * pointer events.
 */
import { state } from '../state.js';

/**
 * Position the transform overlay canvas + size its backing bitmap.
 * Margin is the image-space slack each side so handles can render
 * outside the main canvas (matches _TRANSFORM_OVERLAY_MARGIN in
 * galleryEditor.js — kept as a parameter so this module has no
 * dependency on a magic number defined elsewhere).
 */
export function syncOverlay(margin) {
  if (!state.transformOverlay || !state.mainCanvas) return;
  if (!state.transformActive) {
    state.transformOverlay.style.display = 'none';
    return;
  }
  const W = state.mainCanvas.width + 2 * margin;
  const H = state.mainCanvas.height + 2 * margin;
  if (state.transformOverlay.width !== W) state.transformOverlay.width = W;
  if (state.transformOverlay.height !== H) state.transformOverlay.height = H;
  // Overlay must scale with state.zoom so its handles render at the
  // SAME on-screen size as the main canvas content. Without this, the
  // overlay renders at full bitmap size while main canvas shrinks
  // (zoomed-out), making handles look massive.
  state.transformOverlay.style.display = '';
  state.transformOverlay.style.position = 'absolute';
  state.transformOverlay.style.width  = (W * state.zoom) + 'px';
  state.transformOverlay.style.height = (H * state.zoom) + 'px';
  state.transformOverlay.style.pointerEvents = 'none';
  state.transformOverlay.style.zIndex = '5';
  // Position the overlay at the main canvas's LAYOUT position
  // (offsetLeft/Top — unaffected by CSS transforms), shifted up-left by
  // the overlay's `margin` image-px of handle slack. Then SHARE the
  // canvas's transform (the pan handler writes the same translate3d to
  // both canvas + overlay), so pan moves them together. Reading the
  // layout offset (not getBoundingClientRect, which includes the pan
  // transform) is what avoids the double-pan "bounce".
  state.transformOverlay.style.left = Math.round(state.mainCanvas.offsetLeft - margin * state.zoom) + 'px';
  state.transformOverlay.style.top  = Math.round(state.mainCanvas.offsetTop  - margin * state.zoom) + 'px';
  state.transformOverlay.style.transform = state.mainCanvas.style.transform || 'none';
}


/**
 * Compute the on-screen position of the rotation knob given the
 * layer's bbox center + rotation. The knob normally sits OUTSIDE the
 * top edge of the rotated layer; if that would land beyond the canvas
 * viewport, flip it INSIDE.
 *
 * Returned by `_knobPosition` and shared by drawHandles + getHandleAt
 * so both compute the same point.
 */
function knobPosition(cxh, cyh, rotRad, baseInnerR, rotOffset) {
  let rotInside = false;
  const outsideR = baseInnerR + rotOffset;
  const knobLocalX = cxh + Math.sin(rotRad) * outsideR;
  const knobLocalY = cyh - Math.cos(rotRad) * outsideR;
  // Primary check: anything drawn outside the main canvas's pixel
  // buffer is invisible (canvas operations clip silently).
  if (
    knobLocalX < 0 || knobLocalY < 0 ||
    knobLocalX > state.mainCanvas.width || knobLocalY > state.mainCanvas.height
  ) {
    rotInside = true;
  }
  // Secondary check: even if the knob is inside the canvas bitmap, the
  // viewport may have scrolled the canvas such that the knob falls
  // outside the visible canvas-area window.
  try {
    const area = state.container && state.container.querySelector('.ge-canvas-area');
    if (area && !rotInside) {
      const aRect = area.getBoundingClientRect();
      const mRect = state.mainCanvas.getBoundingClientRect();
      const scaleX = mRect.width / state.mainCanvas.width;
      const scaleY = mRect.height / state.mainCanvas.height;
      const knobClientX = mRect.left + knobLocalX * scaleX;
      const knobClientY = mRect.top + knobLocalY * scaleY;
      if (knobClientY < aRect.top + 6) rotInside = true;
      if (knobClientX < aRect.left + 6 || knobClientX > aRect.right - 6) rotInside = true;
    }
  } catch {}
  const innerR = rotInside ? Math.max(4, baseInnerR - rotOffset) : baseInnerR;
  const rotR = rotInside ? innerR : baseInnerR + rotOffset;
  return {
    rotInside,
    innerR,
    rotX: cxh + Math.sin(rotRad) * rotR,
    rotY: cyh - Math.cos(rotRad) * rotR,
  };
}


/**
 * Draw the rotated bounding outline + 4 corner handles + the rotation
 * knob into the overlay canvas. The overlay is translated by `margin`
 * so image (0,0) maps to overlay (margin, margin).
 */
export function drawHandles(margin) {
  if (!state.transformActive || !state.transformLayer) return;
  syncOverlay(margin);
  if (!state.transformOverlayCtx) return;
  const layer = state.transformLayer;
  const off = state.layerOffsets.get(layer.id) || { x: 0, y: 0 };
  const w = layer.canvas.width;
  const h = layer.canvas.height;
  const ctx = state.transformOverlayCtx;
  // Clear + shift drawing by margin so image (0,0) maps to overlay (M,M).
  ctx.clearRect(0, 0, state.transformOverlay.width, state.transformOverlay.height);
  ctx.save();
  ctx.translate(margin, margin);
  // Zoom-corrected handle size + stroke so they stay readable at any zoom.
  const sz = 10 / state.zoom;
  const stroke = 1.5 / state.zoom;

  // Pre-rotation rectangle dims (what the user sees the layer as).
  // Falls back to layer bbox before any popup values exist.
  const preW = state.transformPendingW || w;
  const preH = state.transformPendingH || h;
  const cxBox = off.x + w / 2;
  const cyBox = off.y + h / 2;
  const rotRadBox = ((state.transformPendingRot || 0) * Math.PI) / 180;
  const cosBox = Math.cos(rotRadBox);
  const sinBox = Math.sin(rotRadBox);
  const rotPt = (dx, dy) => ({
    x: cxBox + dx * cosBox - dy * sinBox,
    y: cyBox + dx * sinBox + dy * cosBox,
  });
  const tl = rotPt(-preW / 2, -preH / 2);
  const tr = rotPt( preW / 2, -preH / 2);
  const br = rotPt( preW / 2,  preH / 2);
  const bl = rotPt(-preW / 2,  preH / 2);

  // Outline of the rotated rectangle — solid white inner line with a
  // thin black halo for contrast on light AND dark backgrounds.
  const drawRectOutline = () => {
    ctx.beginPath();
    ctx.moveTo(tl.x, tl.y);
    ctx.lineTo(tr.x, tr.y);
    ctx.lineTo(br.x, br.y);
    ctx.lineTo(bl.x, bl.y);
    ctx.closePath();
    ctx.stroke();
  };
  ctx.lineWidth = 1 / state.zoom;
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.45)';
  ctx.setLineDash([6 / state.zoom, 4 / state.zoom]);
  ctx.lineDashOffset = 1 / state.zoom;
  drawRectOutline();
  ctx.strokeStyle = '#fff';
  ctx.lineDashOffset = 0;
  drawRectOutline();
  ctx.setLineDash([]);

  // Corner handles + rotation knob anchored to the rotated layer's
  // top-center (not bbox top), so the knob stays attached to the
  // visible content as it spins.
  const rotOffset = 24 / state.zoom;
  const cxh = off.x + w / 2;
  const cyh = off.y + h / 2;
  const rotRad = ((state.transformPendingRot || 0) * Math.PI) / 180;
  const baseInnerR = (state.transformPendingH || h) / 2;
  const knob = knobPosition(cxh, cyh, rotRad, baseInnerR, rotOffset);
  // Tether line collapses to a point when knob is inside the layer.
  const drawTether = !knob.rotInside;
  const innerX = cxh + Math.sin(rotRad) * baseInnerR;
  const innerY = cyh - Math.cos(rotRad) * baseInnerR;
  const corners = [
    { x: tl.x, y: tl.y, id: 'tl' },
    { x: tr.x, y: tr.y, id: 'tr' },
    { x: br.x, y: br.y, id: 'br' },
    { x: bl.x, y: bl.y, id: 'bl' },
    { x: knob.rotX, y: knob.rotY, id: 'rot' },
  ];
  if (drawTether) {
    ctx.beginPath();
    ctx.moveTo(innerX, innerY);
    ctx.lineTo(knob.rotX, knob.rotY);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.lineWidth = 1 / state.zoom;
    ctx.stroke();
  }
  for (const c of corners) {
    const active = c.id === state.transformHandle;
    const hovered = !active && c.id === state.hoveredHandle;
    const radius = (active ? sz * 0.75 : hovered ? sz * 0.6 : sz / 2);
    ctx.beginPath();
    ctx.arc(c.x, c.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = active ? '#e06c75' : hovered ? '#ffd' : '#fff';
    ctx.fill();
    ctx.lineWidth = stroke;
    ctx.strokeStyle = active ? '#fff' : 'rgba(0, 0, 0, 0.5)';
    ctx.stroke();
    if (hovered) {
      // Subtle red ring around the hovered handle for visual feedback.
      ctx.beginPath();
      ctx.arc(c.x, c.y, radius + 2 / state.zoom, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(224, 108, 117, 0.7)';
      ctx.lineWidth = stroke;
      ctx.stroke();
    }
  }
  ctx.restore();
}


/**
 * Hit-test (x, y) against the transform handles. Returns the handle
 * id ('tl' | 'tr' | 'br' | 'bl' | 'rot') or null.
 *
 * Geometry MUST mirror `drawHandles` exactly, otherwise the user
 * grabs phantom points.
 */
export function getHandleAt(x, y) {
  if (!state.transformLayer) return null;
  const layer = state.transformLayer;
  const off = state.layerOffsets.get(layer.id) || { x: 0, y: 0 };
  const w = layer.canvas.width;
  const h = layer.canvas.height;
  const threshold = 8 / state.zoom;
  const rotOffset = 24 / state.zoom;
  const cxh = off.x + w / 2;
  const cyh = off.y + h / 2;
  const rotRad = ((state.transformPendingRot || 0) * Math.PI) / 180;
  const baseInnerR = (state.transformPendingH || h) / 2;
  const knob = knobPosition(cxh, cyh, rotRad, baseInnerR, rotOffset);

  // Rotate corners around centre — must match drawHandles.
  const preW = state.transformPendingW || w;
  const preH = state.transformPendingH || h;
  const cosA = Math.cos(rotRad);
  const sinA = Math.sin(rotRad);
  const rotCorner = (dx, dy) => ({
    x: cxh + dx * cosA - dy * sinA,
    y: cyh + dx * sinA + dy * cosA,
  });
  const tlH = rotCorner(-preW / 2, -preH / 2);
  const trH = rotCorner( preW / 2, -preH / 2);
  const brH = rotCorner( preW / 2,  preH / 2);
  const blH = rotCorner(-preW / 2,  preH / 2);
  const handles = [
    { x: tlH.x,    y: tlH.y,    id: 'tl' },
    { x: trH.x,    y: trH.y,    id: 'tr' },
    { x: brH.x,    y: brH.y,    id: 'br' },
    { x: blH.x,    y: blH.y,    id: 'bl' },
    { x: knob.rotX, y: knob.rotY, id: 'rot' },
  ];
  for (const c of handles) {
    if (Math.abs(x - c.x) < threshold && Math.abs(y - c.y) < threshold) return c.id;
  }
  return null;
}
