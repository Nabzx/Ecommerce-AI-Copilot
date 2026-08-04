/** Small formatting helpers, kept together so the UI reads cleanly. */

const gbp = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  maximumFractionDigits: 0,
});

const gbpPence = new Intl.NumberFormat('en-GB', {
  style: 'currency',
  currency: 'GBP',
  minimumFractionDigits: 2,
});

export const money = (value: number) => gbp.format(value);
export const moneyExact = (value: number) => gbpPence.format(value);
export const number = (value: number) => new Intl.NumberFormat('en-GB').format(value);

/** "4 Aug" — short enough for an axis tick. */
export function shortDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

/**
 * A change shown as an arrow and a percentage.
 *
 * Deliberately not coloured — the arrow says which way it went, and keeping it
 * monochrome is what stops the dashboard turning into a traffic light.
 */
export function changeLabel(change: number | null) {
  if (change === null) return null;
  const arrow = change >= 0 ? '↑' : '↓';
  return `${arrow} ${Math.abs(change).toFixed(1)}%`;
}
