/**
 * KPI / goal weight arithmetic — the server enforces "active weights sum to
 * exactly 100.00" (Module 2); the UI mirrors that check to gate the create form.
 * Kept as a pure, tested helper so the rule lives in one place.
 */
export const WEIGHT_EPSILON = 0.005;

/** Sum a list of weight-bearing items, tolerating string or numeric weights. */
export function sumWeights(items: Array<{ weight: string | number }>): number {
  return items.reduce((acc, item) => acc + (Number(item.weight) || 0), 0);
}

/** True iff the items' weights sum to 100 within the rounding epsilon. */
export function weightsSumTo100(items: Array<{ weight: string | number }>): boolean {
  return Math.abs(sumWeights(items) - 100) < WEIGHT_EPSILON;
}
