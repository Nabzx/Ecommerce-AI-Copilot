'use client';

import { Bar, BarChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { TopProduct } from '@/lib/api';
import { money, moneyExact, number } from '@/lib/format';

/**
 * Best sellers by revenue.
 *
 * Every bar is the same ink — the length already encodes the ranking, so
 * shading them differently would be saying the same thing twice. Values sit
 * directly on the bars, which means the chart needs no x-axis at all.
 */
export default function BestSellers({ data }: { data: TopProduct[] }) {
  return (
    <div className="w-full text-ink" style={{ height: Math.max(200, data.length * 44) }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 60, bottom: 4, left: 0 }}
          barCategoryGap="30%"
        >
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="title"
            tickLine={false}
            axisLine={false}
            width={128}
            tick={<ProductTick />}
          />
          <Tooltip
            content={<BestSellerTooltip />}
            cursor={{ fill: 'currentColor', fillOpacity: 0.05 }}
          />
          <Bar
            dataKey="revenue"
            fill="currentColor"
            // Rounded only on the data end; the baseline end stays square.
            radius={[0, 4, 4, 0]}
            barSize={14}
            // No draw-in animation — it replays every time the date window
            // changes, which gets distracting fast on a dashboard.
            isAnimationActive={false}
          >
            <LabelList
              dataKey="revenue"
              position="right"
              offset={8}
              formatter={(value: number) => money(value)}
              fill="currentColor"
              fontSize={11}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Product titles are "Core Hoodie — Black", which wraps badly if you let the
 * chart do it. Splitting the colourway onto its own quieter line reads better
 * and keeps every label to two tidy lines.
 */
function ProductTick({ x, y, payload }: any) {
  const [name, colourway] = String(payload.value).split('—').map((part) => part.trim());

  return (
    <g transform={`translate(${x},${y})`}>
      <text textAnchor="end" fontSize={11} fill="currentColor" fillOpacity={0.85} dy={colourway ? -1 : 4}>
        {name}
      </text>
      {colourway && (
        <text textAnchor="end" fontSize={10} fill="currentColor" fillOpacity={0.45} dy={12}>
          {colourway}
        </text>
      )}
    </g>
  );
}

function BestSellerTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload as TopProduct;

  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-sm">
      <p className="text-sm font-medium text-ink">{row.title}</p>
      <p className="tnum mt-1 text-xs text-ink-muted">
        {moneyExact(row.revenue)} · {number(row.units)} units
      </p>
    </div>
  );
}
