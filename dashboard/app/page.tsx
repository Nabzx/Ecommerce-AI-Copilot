'use client';

import { useEffect, useState, useRef } from 'react';
import MetricCard from '@/components/MetricCard';
import PriceChart from '@/components/PriceChart';
import IndicatorChart from '@/components/IndicatorChart';
import MACDChart from '@/components/MACDChart';
import ForecastCard from '@/components/ForecastCard';

interface PriceData {
  last_price: number;
  avg_price: number;
  min: number;
  max: number;
  count: number;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  volatility: number | null;
}

interface ForecastData {
  symbol: string;
  current_price: number;
  forecast_price: number;
  delta: number;
  confidence: number;
}

interface ChartDataPoint {
  time: string;
  price: number;
  bb_upper?: number;
  bb_middle?: number;
  bb_lower?: number;
}

export default function Dashboard() {
  const [priceData, setPriceData] = useState<PriceData>({
    last_price: 0,
    avg_price: 0,
    min: 0,
    max: 0,
    count: 0,
    rsi: null,
    macd: null,
    macd_signal: null,
    macd_hist: null,
    bb_upper: null,
    bb_middle: null,
    bb_lower: null,
    volatility: null,
  });
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [rsiData, setRsiData] = useState<Array<{ time: string; value: number }>>([]);
  const [macdData, setMacdData] = useState<Array<{ time: string; macd: number; signal: number; hist: number }>>([]);
  const [volatilityData, setVolatilityData] = useState<Array<{ time: string; value: number }>>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLive, setIsLive] = useState(false);
  const prevPriceRef = useRef<number>(0);

  useEffect(() => {
    let isMounted = true;
    let lastFetchTime = 0;

    const fetchPrice = async () => {
      const now = Date.now();
      if (now - lastFetchTime < 1000) {
        return;
      }
      lastFetchTime = now;

      try {
        const response = await fetch('/api/price');
        if (!response.ok) {
          throw new Error('Failed to fetch');
        }
        const data: PriceData = await response.json();

        if (!isMounted) return;

        if (data.last_price !== prevPriceRef.current && data.last_price > 0) {
          setPriceData(data);
          prevPriceRef.current = data.last_price;

          const timeStr = new Date().toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          });

          // Update price chart
          setChartData((prev) => {
            const newData = [...prev, {
              time: timeStr,
              price: data.last_price,
              bb_upper: data.bb_upper || undefined,
              bb_middle: data.bb_middle || undefined,
              bb_lower: data.bb_lower || undefined,
            }];
            return newData.slice(-100);
          });

          // Update RSI chart
          if (data.rsi !== null) {
            setRsiData((prev) => {
              const newData = [...prev, { time: timeStr, value: data.rsi! }];
              return newData.slice(-50);
            });
          }

          // Update MACD chart
          if (data.macd !== null && data.macd_signal !== null) {
            setMacdData((prev) => {
              const newData = [...prev, {
                time: timeStr,
                macd: data.macd!,
                signal: data.macd_signal!,
                hist: data.macd_hist || 0,
              }];
              return newData.slice(-50);
            });
          }

          // Update volatility chart
          if (data.volatility !== null) {
            setVolatilityData((prev) => {
              const newData = [...prev, { time: timeStr, value: data.volatility! }];
              return newData.slice(-50);
            });
          }

          setIsLive(true);
          setIsLoading(false);

          setTimeout(() => {
            if (isMounted) {
              setIsLive(false);
            }
          }, 3000);
        } else if (data.last_price > 0) {
          setPriceData(data);
          setIsLoading(false);
        }
      } catch (error) {
        console.error('Error fetching price:', error);
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    const fetchForecast = async () => {
      try {
        const response = await fetch('/api/forecast');
        if (response.ok) {
          const data: ForecastData = await response.json();
          if (isMounted && !data.error && data.confidence > 0) {
            setForecast(data);
          }
        }
      } catch (error) {
        console.error('Error fetching forecast:', error);
      }
    };

    fetchPrice();
    fetchForecast();

    const priceInterval = setInterval(fetchPrice, 1000);
    const forecastInterval = setInterval(fetchForecast, 10000); // Every 10 seconds

    return () => {
      isMounted = false;
      clearInterval(priceInterval);
      clearInterval(forecastInterval);
    };
  }, []);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  const getPriceChange = () => {
    if (chartData.length < 2) return 0;
    const current = chartData[chartData.length - 1]?.price || 0;
    const previous = chartData[chartData.length - 2]?.price || 0;
    return current - previous;
  };

  const priceChange = getPriceChange();
  const isPositive = priceChange >= 0;

  const getRSIStatus = (rsi: number | null) => {
    if (rsi === null) return { color: '#6B7280', label: 'N/A' };
    if (rsi > 70) return { color: '#EF4444', label: 'Overbought' };
    if (rsi < 30) return { color: '#10B981', label: 'Oversold' };
    return { color: '#3B82F6', label: 'Neutral' };
  };

  const rsiStatus = getRSIStatus(priceData.rsi);

  return (
    <div className="min-h-screen bg-[#0E0F12] text-[#F3F4F6]">
      <div className="container mx-auto px-6 py-10 max-w-[1920px]">
        {/* Header */}
        <header className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-4xl font-bold mb-2 text-[#F3F4F6] tracking-tight">
                TradeFlux AI
              </h1>
              <p className="text-[#9CA3AF] text-base">Real-time BTC/USD Analytics & Forecasting</p>
            </div>
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-[#14161A] border border-[#1F2937]">
              <div className={`relative w-3 h-3 rounded-full ${isLive ? 'bg-[#10B981]' : 'bg-[#6B7280]'}`}>
                {isLive && (
                  <div className="absolute inset-0 rounded-full bg-[#10B981] animate-ping opacity-75" />
                )}
              </div>
              <span className="text-sm font-medium text-[#9CA3AF]">LIVE</span>
            </div>
          </div>
        </header>

        {/* Main Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          <MetricCard
            label="Last Price"
            value={formatPrice(priceData.last_price)}
            accentColor="green"
            change={priceChange !== 0 ? { value: priceChange, isPositive } : undefined}
            isLoading={isLoading}
          />
          <MetricCard
            label="Average Price"
            value={formatPrice(priceData.avg_price)}
            accentColor="blue"
            isLoading={isLoading}
          />
          <MetricCard
            label="Minimum"
            value={formatPrice(priceData.min)}
            accentColor="red"
            isLoading={isLoading}
          />
          <MetricCard
            label="Maximum"
            value={formatPrice(priceData.max)}
            accentColor="yellow"
            isLoading={isLoading}
          />
          <MetricCard
            label="Data Points"
            value={priceData.count.toLocaleString()}
            accentColor="purple"
            isLoading={isLoading}
          />
        </div>

        {/* Indicators Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
            <div className="text-xs text-[#6B7280] mb-1">RSI (14)</div>
            <div className={`text-2xl font-bold ${rsiStatus.color}`}>
              {priceData.rsi !== null ? priceData.rsi.toFixed(2) : '--'}
            </div>
            <div className="text-xs text-[#9CA3AF] mt-1">{rsiStatus.label}</div>
          </div>
          <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
            <div className="text-xs text-[#6B7280] mb-1">MACD</div>
            <div className="text-2xl font-bold text-[#3B82F6]">
              {priceData.macd !== null ? priceData.macd.toFixed(4) : '--'}
            </div>
            <div className="text-xs text-[#9CA3AF] mt-1">
              Signal: {priceData.macd_signal !== null ? priceData.macd_signal.toFixed(4) : '--'}
            </div>
          </div>
          <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-4">
            <div className="text-xs text-[#6B7280] mb-1">Volatility</div>
            <div className="text-2xl font-bold text-[#7C3AED]">
              {priceData.volatility !== null ? priceData.volatility.toFixed(2) : '--'}
            </div>
            <div className="text-xs text-[#9CA3AF] mt-1">20-period std dev</div>
          </div>
          <ForecastCard forecast={forecast} isLoading={isLoading} />
        </div>

        {/* Main Price Chart */}
        <div className="mb-6">
          <PriceChart
            data={chartData}
            isLoading={isLoading}
            isLive={isLive}
            showBollingerBands={priceData.bb_upper !== null}
          />
        </div>

        {/* Indicator Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <IndicatorChart
            title="RSI (14)"
            data={rsiData}
            color="#3B82F6"
            isLoading={isLoading}
            height={200}
          />
          <MACDChart data={macdData} isLoading={isLoading} />
          <IndicatorChart
            title="Volatility"
            data={volatilityData}
            color="#7C3AED"
            isLoading={isLoading}
            height={200}
          />
        </div>
      </div>
    </div>
  );
}
