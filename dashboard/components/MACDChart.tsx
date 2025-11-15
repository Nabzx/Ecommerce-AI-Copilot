'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

interface MACDChartProps {
  data: Array<{ time: string; macd: number; signal: number; hist: number }>;
  isLoading?: boolean;
}

export default function MACDChart({ data, isLoading = false }: MACDChartProps) {
  if (isLoading || data.length === 0) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
        <div className="h-4 w-32 bg-[#1F2937] rounded mb-4 animate-pulse" />
        <div className="h-[200px] bg-[#1F2937] rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
      <h3 className="text-sm font-semibold text-[#9CA3AF] mb-2">MACD</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data}>
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
          <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="2 2" />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0E0F12',
              border: '1px solid #1F2937',
              borderRadius: '6px',
            }}
            labelStyle={{ color: '#F3F4F6', fontSize: '11px' }}
          />
          <Line
            type="monotone"
            dataKey="macd"
            stroke="#3B82F6"
            strokeWidth={1.5}
            dot={false}
            name="MACD"
          />
          <Line
            type="monotone"
            dataKey="signal"
            stroke="#7C3AED"
            strokeWidth={1.5}
            dot={false}
            name="Signal"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

