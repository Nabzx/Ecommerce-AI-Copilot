'use client';

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RevenuePoint } from '@/lib/api';
import { money, moneyExact, shortDate } from '@/lib/format';

/**
 * Revenue per day.
 *
 * The whole chart is drawn in `currentColor`, so it inherits the text colour
 * and switches with the theme on its own — no colour values in here at all.
 * Grid and ticks are the same ink knocked back with opacity, which keeps them
 * behind the data where they belong.
 */
export default function RevenueChart({ data }: { data: RevenuePoint[] }) {
  // One tick a week is enough — a label per day would be unreadable.
  const tickGap = Math.max(1, Math.floor(data.length / 6));

  return (
    <div className="h-[260px] w-full text-ink">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid
            vertical={false}
            stroke="currentColor"
            strokeOpacity={0.1}
            strokeDasharray="0"
          />
          <XAxis
            dataKey="day"
            tickFormatter={shortDate}
            interval={tickGap - 1}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'currentColor', fillOpacity: 0.45, fontSize: 11 }}
            dy={6}
          />
          <YAxis
            tickFormatter={(v: number) => money(v)}
            tickLine={false}
            axisLine={false}
            width={64}
            tick={{ fill: 'currentColor', fillOpacity: 0.45, fontSize: 11 }}
          />
          <Tooltip
            content={<RevenueTooltip />}
            cursor={{ stroke: 'currentColor', strokeOpacity: 0.3, strokeWidth: 1 }}
          />
          <Area
            type="linear"
            dataKey="revenue"
            stroke="currentColor"
            strokeWidth={2}
            fill="currentColor"
            fillOpacity={0.07}
            // A dot per day would clutter it; they appear on hover instead.
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function RevenueTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload as RevenuePoint;

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-sm">
      <p className="label">{shortDate(point.day)}</p>
      <p className="tnum mt-1 text-sm font-semibold text-ink">{moneyExact(point.revenue)}</p>
    </div>
  );
}
