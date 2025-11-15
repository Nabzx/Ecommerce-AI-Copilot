interface MetricCardProps {
  label: string;
  value: string | number;
  accentColor?: 'blue' | 'purple' | 'green' | 'red' | 'yellow';
  change?: {
    value: number;
    isPositive: boolean;
  };
  isLoading?: boolean;
}

export default function MetricCard({
  label,
  value,
  accentColor = 'blue',
  change,
  isLoading = false,
}: MetricCardProps) {
  const colorClasses = {
    blue: {
      text: 'text-[#3B82F6]',
      hover: 'hover:border-[#3B82F6]/30',
      glow: 'hover:shadow-[#3B82F6]/10',
    },
    purple: {
      text: 'text-[#7C3AED]',
      hover: 'hover:border-[#7C3AED]/30',
      glow: 'hover:shadow-[#7C3AED]/10',
    },
    green: {
      text: 'text-[#10B981]',
      hover: 'hover:border-[#10B981]/30',
      glow: 'hover:shadow-[#10B981]/10',
    },
    red: {
      text: 'text-[#EF4444]',
      hover: 'hover:border-[#EF4444]/30',
      glow: 'hover:shadow-[#EF4444]/10',
    },
    yellow: {
      text: 'text-[#F59E0B]',
      hover: 'hover:border-[#F59E0B]/30',
      glow: 'hover:shadow-[#F59E0B]/10',
    },
  };

  const colors = colorClasses[accentColor];

  if (isLoading) {
    return (
      <div className="bg-[#14161A] rounded-xl border border-[#1F2937] p-6 shadow-lg">
        <div className="h-4 w-24 bg-[#1F2937] rounded mb-4 animate-pulse" />
        <div className="h-8 w-32 bg-[#1F2937] rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div
      className={`group bg-[#14161A] rounded-xl border border-[#1F2937] p-6 shadow-lg transition-all duration-300 hover:scale-[1.02] ${colors.hover} ${colors.glow}`}
    >
      <div className="text-[#9CA3AF] text-sm font-medium mb-2">{label}</div>
      <div className={`text-3xl font-bold tabular-nums ${colors.text}`}>
        {value}
      </div>
      {change && (
        <div
          className={`text-xs mt-2 font-medium ${
            change.isPositive ? 'text-[#10B981]' : 'text-[#EF4444]'
          }`}
        >
          {change.isPositive ? '↑' : '↓'}{' '}
          {typeof change.value === 'number'
            ? Math.abs(change.value).toLocaleString('en-US', {
                style: 'currency',
                currency: 'USD',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            : change.value}
        </div>
      )}
    </div>
  );
}

