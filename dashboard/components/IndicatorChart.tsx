'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

interface IndicatorChartProps {
  title: string;
  data: Array<{ time: string; value: number }>;
  color?: string;
  isLoading?: boolean;
  height?: number;
}

export default function IndicatorChart({
  title,
  data,
  color = '#3B82F6',
  isLoading = false,
  height = 200,
}: IndicatorChartProps) {
  if (isLoading || data.length === 0) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
        <div className="h-4 w-32 bg-[#1F2937] rounded mb-4 animate-pulse" />
        <div className={`h-[${height}px] bg-[#1F2937] rounded animate-pulse`} />
      </div>
    );
  }

  return (
    <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
      <h3 className="text-sm font-semibold text-[#9CA3AF] mb-2">{title}</h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id={`gradient-${title}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1F2937" strokeOpacity={0.3} />
          <XAxis
            dataKey="time"
            stroke="#6B7280"
            style={{ fontSize: '10px' }}
            tick={{ fill: '#9CA3AF' }}
          />
          <YAxis
            stroke="#6B7280"
            style={{ fontSize: '10px' }}
            tick={{ fill: '#9CA3AF' }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0E0F12',
              border: '1px solid #1F2937',
              borderRadius: '6px',
            }}
            labelStyle={{ color: '#F3F4F6', fontSize: '11px' }}
            itemStyle={{ color, fontSize: '11px' }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#gradient-${title})`}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

