'use client';

import { useEffect, useState } from 'react';
import { api, type ForecastAccuracy, type Stockout } from '@/lib/api';

/**
 * Which sizes run out next.
 *
 * The accuracy line underneath is loaded separately because working it out
 * refits the model four times and takes about half a minute — and it's worth
 * showing. A forecast with no error bar next to it is just a number with
 * confidence it hasn't earned.
 */
export default function StockoutForecast({ rows }: { rows: Stockout[] | null }) {
  const [accuracy, setAccuracy] = useState<ForecastAccuracy | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    let live = true;
    setChecking(true);
    api
      .forecastAccuracy()
      .then((result) => live && setAccuracy(result))
      .catch(() => undefined)
      .finally(() => live && setChecking(false));
    return () => {
      live = false;
    };
  }, []);

  // null means the forecast hasn't come back yet. Saying "nothing is running
  // out" while still loading would be stating something false, and it's the
  // one claim on this card the owner might act on.
  if (rows === null) {
    return <p className="py-6 text-sm text-ink-faint">Working out what runs out next…</p>;
  }

  if (rows.length === 0) {
    return <p className="py-6 text-sm text-ink-muted">Nothing forecast to run out soon.</p>;
  }

  return (
    <>
      <ul className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.variant_id} className="flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">
                {row.product} <span className="text-ink-faint">· {row.size}</span>
              </p>
              <p className="label mt-0.5">
                {row.inventory} left · {row.daily_rate}/day
              </p>
            </div>
            <DaysLeft days={row.days_to_stockout} />
          </li>
        ))}
      </ul>

      <p className="mt-4 border-t border-line pt-3 text-xs text-ink-faint">
        {checking && 'Checking the forecast against a moving average…'}
        {accuracy && (
          <>
            Over {accuracy.folds} holdout windows this was{' '}
            <span className="tnum text-ink-muted">{accuracy.error_pct}%</span> off on total units,
            against <span className="tnum text-ink-muted">{accuracy.naive_error_pct}%</span> for a
            28-day average.
          </>
        )}
      </p>
    </>
  );
}

function DaysLeft({ days }: { days: number | null }) {
  if (days === null) {
    return <span className="shrink-0 text-xs text-ink-faint">&gt; 90d</span>;
  }

  // Under a week is the only case worth colouring. The word is always there.
  const urgent = days <= 7;
  return (
    <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs text-ink">
      {urgent && (
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--warning)' }} aria-hidden />
      )}
      <span className="tnum">{days}d left</span>
    </span>
  );
}
