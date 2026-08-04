import type { LowStockRow } from '@/lib/api';
import { number } from '@/lib/format';

/**
 * Sizes that are out or running out.
 *
 * This is the one place on the dashboard that uses colour, because "sold out"
 * is genuinely urgent. Every coloured dot is followed by the word it means, so
 * the status never depends on being able to see the colour.
 */
export default function LowStockTable({ rows }: { rows: LowStockRow[] }) {
  if (rows.length === 0) {
    return <p className="py-6 text-sm text-ink-muted">Nothing running low. Everything is stocked.</p>;
  }

  return (
    <>
      {/* On a phone the table would push the status column off-screen, which is
          the one thing the owner actually needs to see. Stacked rows instead. */}
      <ul className="sm:hidden">
        {rows.map((row) => (
          <li
            key={row.variant_id}
            className="flex items-center justify-between gap-3 border-b border-line/60 py-3 last:border-0"
          >
            <div className="min-w-0">
              <p className="truncate text-sm text-ink">{row.product}</p>
              <p className="label mt-0.5">
                Size {row.size} · {number(row.units_last_30d)} sold in 30d
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="tnum text-sm text-ink">{row.inventory} left</p>
              <p className="mt-0.5">
                <StatusPill row={row} />
              </p>
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden sm:block">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="label pb-2 font-normal">Product</th>
              <th className="label pb-2 font-normal">Size</th>
              <th className="label pb-2 text-right font-normal">Left</th>
              <th className="label pb-2 text-right font-normal">Sold 30d</th>
              <th className="label pb-2 text-right font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.variant_id} className="border-b border-line/60 last:border-0">
                <td className="py-2.5 pr-3 text-ink">{row.product}</td>
                <td className="tnum py-2.5 pr-3 text-ink-muted">{row.size}</td>
                <td className="tnum py-2.5 text-right text-ink">{row.inventory}</td>
                <td className="tnum py-2.5 text-right text-ink-muted">
                  {number(row.units_last_30d)}
                </td>
                <td className="py-2.5 text-right">
                  <StatusPill row={row} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function StatusPill({ row }: { row: LowStockRow }) {
  // Sold out is obvious. Otherwise it comes down to how long the stock lasts at
  // the rate it's been selling — 3 left is fine if nobody is buying it, and 8
  // left is urgent if it shifts one a day.
  if (row.inventory === 0) {
    return <Pill colour="var(--critical)" text="Sold out" />;
  }
  if (row.days_of_stock === null) {
    return <span className="text-xs text-ink-faint">Not selling</span>;
  }

  const days = Math.round(row.days_of_stock);
  if (days <= 14) {
    return <Pill colour="var(--warning)" text={`~${days}d left`} />;
  }
  // Still worth listing, but nothing to act on today.
  return <span className="tnum text-xs text-ink-faint">~{days}d left</span>;
}

function Pill({ colour, text }: { colour: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-ink">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: colour }} aria-hidden />
      {text}
    </span>
  );
}
