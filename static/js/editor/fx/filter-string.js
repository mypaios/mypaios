/**
 * Pure helpers that translate between the editor's adjustment-slider
 * UI and CSS `filter` strings / canvas-filter multipliers.
 */

/**
 * Build a CSS `filter` string from a layer's `adjustments` object.
 * Returns '' when every value is at identity so the composite path
 * can skip the filter entirely.
 *
 * @param {{
 *   brightness?: number, contrast?: number,
 *   saturation?: number, hue?: number,
 * }|null|undefined} adj
 */
export function layerFilterString(adj) {
  if (!adj) return '';
  const parts = [];
  if (adj.brightness !== undefined && adj.brightness !== 1) parts.push(`brightness(${adj.brightness})`);
  if (adj.contrast !== undefined && adj.contrast !== 1) parts.push(`contrast(${adj.contrast})`);
  if (adj.saturation !== undefined && adj.saturation !== 1) parts.push(`saturate(${adj.saturation})`);
  if (adj.hue !== undefined && adj.hue !== 0) parts.push(`hue-rotate(${adj.hue}deg)`);
  return parts.join(' ');
}


/**
 * Convert a stored filter multiplier (brightness/contrast/saturation
 * are 0..2 with 1.0 = identity; hue is degrees, -180..+180) into the
 * UI slider's -100..+100 (or -180..+180 for hue) range.
 */
export function fxFilterToSlider(key, value) {
  if (key === 'brightness' || key === 'contrast' || key === 'saturation') {
    return Math.round(((value ?? 1) - 1) * 100);
  }
  if (key === 'hue') return Math.round(value ?? 0);
  return 0;
}
