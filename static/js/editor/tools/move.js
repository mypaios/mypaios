/**
 * Move tool — drag a layer around the canvas, with optional snap-on-Ctrl
 * to other layers' edges/centers and to canvas edges/center.
 *
 * Owns its own input handlers (begin/drag/end) and reads/writes the
 * shared `state` store directly. The factory takes a small dependency
 * bag for things that still live in galleryEditor.js — `activeLayer`,
 * `saveState`, `composite` — so this module doesn't have to know about
 * the orchestrator.
 *
 * @param {{
 *   activeLayer: () => {id: string, canvas: HTMLCanvasElement, locked?: boolean} | null,
 *   saveState:   (label?: string) => void,
 *   composite:   () => void,
 * }} deps
 * @returns {{ begin: (e: Event) => void, drag: (e: Event) => void, end: () => void }}
 */
import { state } from '../state.js';
import { canvasCoords } from '../canvas-coords.js';
import { computeSnap as computeSnapImpl } from '../snap.js';

export function createMoveTool({ activeLayer, saveState, composite }) {
  function computeSnap(layer, nx, ny) {
    return computeSnapImpl(layer, nx, ny, {
      zoom: state.zoom,
      canvasW: state.imgWidth,
      canvasH: state.imgHeight,
      otherLayers: state.layers.map(l => ({
        visible: l.visible,
        id: l.id,
        canvas: l.canvas,
        offset: state.layerOffsets.get(l.id) || { x: 0, y: 0 },
      })),
    });
  }

  return {
    begin(e) {
      const layer = activeLayer();
      if (!layer || layer.locked) return;
      saveState();
      state.moving = true;
      const coords = canvasCoords(e, state.mainCanvas);
      const off = state.layerOffsets.get(layer.id) || { x: 0, y: 0 };
      state.moveStartX = coords.x;
      state.moveStartY = coords.y;
      state.moveLayerOffsetX = off.x;
      state.moveLayerOffsetY = off.y;
    },
    drag(e) {
      if (!state.moving) return;
      e.preventDefault();
      const layer = activeLayer();
      if (!layer) return;
      const coords = canvasCoords(e, state.mainCanvas);
      const dx = coords.x - state.moveStartX;
      const dy = coords.y - state.moveStartY;
      let nx = state.moveLayerOffsetX + dx;
      let ny = state.moveLayerOffsetY + dy;
      // Ctrl held = snap to canvas edges/center and to every other
      // visible layer's edges/center. Opt-in to avoid a "sticky" feel
      // during normal drags.
      if (e.ctrlKey || e.metaKey) {
        const snapped = computeSnap(layer, nx, ny);
        nx = snapped.x;
        ny = snapped.y;
        state.activeSnapGuides = snapped.guides;
      } else {
        state.activeSnapGuides = null;
      }
      state.layerOffsets.set(layer.id, { x: nx, y: ny });
      composite();
    },
    end() {
      state.moving = false;
      state.activeSnapGuides = null;
    },
  };
}
