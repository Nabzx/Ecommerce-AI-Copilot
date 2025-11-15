'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

interface ChartDataPoint {
  time: string;
  price: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
}

interface PriceChartProps {
  data: ChartDataPoint[];
  isLoading?: boolean;
  isLive?: boolean;
  showBollingerBands?: boolean;
}

export default function PriceChart({ 
  data, 
  isLoading = false, 
  isLive = false,
  showBollingerBands = false 
}: PriceChartProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  if (isLoading || data.length === 0) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-8 shadow-lg">
        <div className="h-6 w-48 bg-[#1F2937] rounded mb-6 animate-pulse" />
        <div className="h-[450px] bg-[#1F2937] rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div className="relative bg-[#14161A] rounded-xl border border-[#1F2937] p-8 shadow-lg">
      {/* Live indicator */}
      <div className="absolute top-6 right-6 z-10">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#0E0F12]/80 backdrop-blur-sm border border-[#1F2937]">
          <div className={`relative w-2 h-2 rounded-full ${isLive ? 'bg-[#10B981]' : 'bg-[#6B7280]'}`}>
            {isLive && (
              <div className="absolute inset-0 rounded-full bg-[#10B981] animate-ping opacity-75" />
            )}
          </div>
          <span className="text-xs font-medium text-[#9CA3AF]">LIVE</span>
        </div>
      </div>

      <h2 className="text-2xl font-bold mb-6 text-[#F3F4F6]">Price History</h2>
      <ResponsiveContainer width="100%" height={450}>
        <AreaChart
          data={data}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="#1F2937"
            strokeOpacity={0.5}
            vertical={false}
          />
          <XAxis
            dataKey="time"
            stroke="#6B7280"
            style={{ fontSize: '11px' }}
            tick={{ fill: '#9CA3AF' }}
            axisLine={{ stroke: '#1F2937' }}
          />
          <YAxis
            stroke="#6B7280"
            style={{ fontSize: '11px' }}
            tick={{ fill: '#9CA3AF' }}
            axisLine={{ stroke: '#1F2937' }}
            domain={['dataMin - 50', 'dataMax + 50']}
            tickFormatter={(value) => `$${value.toLocaleString()}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0E0F12',
              border: '1px solid #1F2937',
              borderRadius: '8px',
              padding: '12px',
              boxShadow: '0 10px 40px rgba(0, 0, 0, 0.5)',
            }}
            labelStyle={{ color: '#F3F4F6', marginBottom: '8px', fontWeight: '600' }}
            itemStyle={{ color: '#3B82F6', fontWeight: '500' }}
            formatter={(value: number) => formatPrice(value)}
          />
          {showBollingerBands && data[0]?.bb_upper && (
            <>
              <Line
                type="monotone"
                dataKey="bb_upper"
                stroke="#F59E0B"
                strokeWidth={1}
                strokeDasharray="5 5"
                dot={false}
                name="BB Upper"
              />
              <Line
                type="monotone"
                dataKey="bb_middle"
                stroke="#9CA3AF"
                strokeWidth={1}
                strokeDasharray="3 3"
                dot={false}
                name="BB Middle"
              />
              <Line
                type="monotone"
                dataKey="bb_lower"
                stroke="#F59E0B"
                strokeWidth={1}
                strokeDasharray="5 5"
                dot={false}
                name="BB Lower"
              />
            </>
          )}
          <Area
            type="monotone"
            dataKey="price"
            stroke="#3B82F6"
            strokeWidth={2}
            fill="url(#priceGradient)"
            dot={false}
            activeDot={{ r: 5, fill: '#3B82F6', stroke: '#1E40AF', strokeWidth: 2 }}
            animationDuration={300}
            animationEasing="ease-out"
            name="Price"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
