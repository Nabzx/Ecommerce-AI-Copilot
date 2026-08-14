'use client';

import { useEffect, useState } from 'react';
import { api, type Usage } from '@/lib/api';
import { number } from '@/lib/format';

/**
 * What the AI features cost to run.
 *
 * Broken down by feature rather than shown as one total, because "the copilot
 * is most of it" is the only version of this number you can act on — it tells
 * you where a cheaper model or a cache would actually pay.
 */
export default function UsageCard() {
  const [data, setData] = useState<Usage | null>(null);

  useEffect(() => {
    api.usage().then(setData).catch(() => undefined);
  }, []);

  if (!data) return <p className="py-6 text-sm text-ink-faint">Loading usage…</p>;

  if (data.calls === 0) {
    return (
      <p className="py-6 text-sm text-ink-muted">
        No model calls yet. Ask the copilot something and it&apos;ll show up here.
      </p>
    );
  }

  const widest = Math.max(...data.by_endpoint.map((row) => row.tokens), 1);
  const free = data.cost_gbp === 0;

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <span className="tnum text-[26px] font-semibold leading-none tracking-tight text-ink">
          {free ? '£0.00' : `£${data.cost_gbp.toFixed(4)}`}
        </span>
        <span className="tnum text-sm text-ink-muted">
          {number(data.tokens)} tokens · {number(data.calls)} calls
        </span>
      </div>

      <p className="mt-2 text-xs text-ink-faint">
        {free
          ? 'Running on a local model, so the tokens are real and the bill is zero.'
          : `over the last ${data.window_days} days`}
        {data.unpriced_calls > 0 && (
          <> · {data.unpriced_calls} calls on a model with no price listed</>
        )}
      </p>

      <ul className="mt-5 space-y-2">
        {data.by_endpoint.map((row) => (
          <li key={row.endpoint} className="flex items-center gap-3">
            <span className="w-36 shrink-0 truncate text-sm text-ink">{row.endpoint}</span>
            <span className="h-1 flex-1 overflow-hidden rounded-full bg-raised">
              <span
                className="block h-full rounded-full bg-ink"
                style={{ width: `${(row.tokens / widest) * 100}%` }}
              />
            </span>
            <span className="tnum w-20 shrink-0 text-right text-xs text-ink-muted">
              {number(row.tokens)}
            </span>
          </li>
        ))}
      </ul>

      {data.models.length > 0 && (
        <p className="mt-4 border-t border-line pt-3 text-xs text-ink-faint">
          {data.models.map((m) => `${m.model} (${m.calls})`).join(' · ')}
        </p>
      )}
    </div>
  );
}
