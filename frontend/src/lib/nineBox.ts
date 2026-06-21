/**
 * Bucket placements by the cell to DISPLAY (`effective_box` = human override when
 * set, else the computed box), so a repositioned person shows in the cell a human
 * dragged them to — not their computed one. Generic over any cell with a `box`
 * (and an optional `effective_box`), so it serves both the succession 9-box
 * (full placements) and the analytics calibration grid (a reduced shape).
 */
export function bucketByEffectiveBox<T extends { box: number; effective_box?: number }>(
  placements: T[],
): Map<number, T[]> {
  const map = new Map<number, T[]>();
  for (const p of placements) {
    const box = p.effective_box ?? p.box;
    const list = map.get(box) ?? [];
    list.push(p);
    map.set(box, list);
  }
  return map;
}
