'use client';

interface ForecastData {
  symbol: string;
  current_price: number;
  forecast_price: number;
  delta: number;
  confidence: number;
}

interface ForecastCardProps {
  forecast: ForecastData | null;
  isLoading?: boolean;
}

export default function ForecastCard({ forecast, isLoading = false }: ForecastCardProps) {
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  if (isLoading) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-6">
        <div className="h-4 w-32 bg-[#1F2937] rounded mb-4 animate-pulse" />
        <div className="h-8 w-40 bg-[#1F2937] rounded animate-pulse" />
      </div>
    );
  }

  if (!forecast || forecast.confidence === 0) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-6">
        <h3 className="text-sm font-semibold text-[#9CA3AF] mb-2">60s Forecast</h3>
        <p className="text-[#6B7280] text-sm">Forecast unavailable</p>
      </div>
    );
  }

  const isPositive = forecast.delta >= 0;
  const confidencePercent = Math.round(forecast.confidence * 100);

  return (
    <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-6">
      <h3 className="text-sm font-semibold text-[#9CA3AF] mb-4">60s Forecast</h3>
      <div className="space-y-3">
        <div>
          <div className="text-xs text-[#6B7280] mb-1">Forecast Price</div>
          <div className={`text-2xl font-bold tabular-nums ${isPositive ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>
            {formatPrice(forecast.forecast_price)}
          </div>
        </div>
        <div>
          <div className="text-xs text-[#6B7280] mb-1">Expected Change</div>
          <div className={`text-lg font-semibold ${isPositive ? 'text-[#10B981]' : 'text-[#EF4444]'}`}>
            {isPositive ? '+' : ''}{formatPrice(forecast.delta)}
          </div>
        </div>
        <div>
          <div className="text-xs text-[#6B7280] mb-1">Confidence</div>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-[#1F2937] rounded-full h-2">
              <div
                className="bg-[#3B82F6] h-2 rounded-full transition-all"
                style={{ width: `${confidencePercent}%` }}
              />
            </div>
            <span className="text-sm text-[#9CA3AF]">{confidencePercent}%</span>
          </div>
        </div>
      </div>
    </div>
  );
}

