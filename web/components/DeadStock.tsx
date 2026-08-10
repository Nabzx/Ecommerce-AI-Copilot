'use client';

import { useEffect, useState } from 'react';
import { api, type DeadStock } from '@/lib/api';
import { money, number } from '@/lib/format';

/**
 * Stock that isn't moving, and the size mix that usually explains it.
 *
 * The forecast card says what to buy. This one says what to stop buying, and
 * the size table underneath is nearly always the reason — a size run ordered
 * flat when demand is a bell curve leaves the tails on the shelf.
 */
export default function DeadStockCard() {
  const [data, setData] = useState<DeadStock | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .deadstock()
      .then(setData)
      .catch(() => setError('Could not load stock levels.'));
  }, []);

  if (error) return <p className="py-6 text-sm text-ink-muted">{error}</p>;
  if (!data) return <p className="py-6 text-sm text-ink-faint">Checking what isn&apos;t moving…</p>;

  const stuck = [...data.not_selling, ...data.slow];

  if (stuck.length === 0) {
    return <p className="py-6 text-sm text-ink-muted">Nothing sitting still. Everything is turning over.</p>;
  }

  // Without cost per item the cash figures are all zero, which would read as
  // "this costs nothing to hold" rather than "we don't know".
  const value = data.have_costs ? data.stuck_at_cost : data.stuck_at_retail;
  const total = data.have_costs ? data.total_at_cost : data.total_at_retail;
  const basis = data.have_costs ? 'at cost' : 'at retail';

  return (
    <div>
      <p className="tnum text-[26px] font-semibold leading-none tracking-tight text-ink">
        {money(value)}
      </p>
      <p className="mt-2 text-xs text-ink-muted">
        {basis} in {number(data.stuck_units)} units that would take over{' '}
        {data.slow_after_days} days to clear — {Math.round((value / (total || 1)) * 100)}% of
        everything on the shelf
        {!data.have_costs && (
          <span className="text-ink-faint">
            {' '}· add cost per item in Shopify for the real figure
          </span>
        )}
      </p>

      <ul className="mt-5 space-y-2.5">
        {stuck.slice(0, 6).map((row) => (
          <li key={row.variant_id} className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">
                {row.product} <span className="text-ink-faint">· {row.size}</span>
              </p>
              <p className="label mt-0.5">
                {row.inventory} left · {row.units_sold} sold in {data.window_days}d
              </p>
            </div>
            <div className="shrink-0 text-right">
              <p className="tnum text-sm text-ink">
                {money(data.have_costs ? row.at_cost : row.at_retail)}
              </p>
              <p className="label mt-0.5">
                {row.cover_days === null ? 'no sales' : `${row.cover_days}d cover`}
              </p>
            </div>
          </li>
        ))}
      </ul>

      {data.size_mix.length > 0 && <SizeMix rows={data.size_mix} />}
    </div>
  );
}

/**
 * What sells in each size against what's stocked in each size.
 *
 * Two bars per row rather than a number, because the whole point is the gap
 * between them.
 */
function SizeMix({ rows }: { rows: DeadStock['size_mix'] }) {
  const widest = Math.max(...rows.map((r) => Math.max(r.sold_share, r.stock_share)), 1);

  return (
    <div className="mt-6 border-t border-line pt-4">
      <p className="label mb-3">Size mix — sold vs stocked</p>
      <ul className="space-y-2">
        {rows.map((row) => {
          // Stocking well above what sells is what leaves money on the shelf.
          const over = row.stock_share - row.sold_share > 4;

          return (
            <li key={row.size} className="flex items-center gap-3">
              <span className="tnum w-14 shrink-0 text-xs text-ink-muted">{row.size}</span>

              <span className="flex flex-1 flex-col gap-1">
                <Bar share={row.sold_share} widest={widest} className="bg-ink" />
                <Bar
                  share={row.stock_share}
                  widest={widest}
                  className={over ? '' : 'bg-ink-faint'}
                  style={over ? { background: 'var(--warning)' } : undefined}
                />
              </span>

              <span className="tnum w-24 shrink-0 text-right text-xs text-ink-faint">
                {row.sold_share}% / {row.stock_share}%
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-ink-faint">
        Top bar is share of sales, bottom is share of stock. Amber means more on the shelf than
        the demand for it.
      </p>
    </div>
  );
}

function Bar({
  share,
  widest,
  className = '',
  style,
}: {
  share: number;
  widest: number;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span className="block h-1 w-full overflow-hidden rounded-full bg-raised">
      <span
        className={`block h-full rounded-full ${className}`}
        style={{ width: `${(share / widest) * 100}%`, ...style }}
      />
    </span>
  );
}
