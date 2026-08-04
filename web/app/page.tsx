'use client';

import { useCallback, useEffect, useState } from 'react';
import BestSellers from '@/components/BestSellers';
import Card from '@/components/Card';
import LowStockTable from '@/components/LowStockTable';
import MetricCard from '@/components/MetricCard';
import RevenueChart from '@/components/RevenueChart';
import ThemeToggle from '@/components/ThemeToggle';
import {
  api,
  type CustomerStats,
  type LowStockRow,
  type RevenuePoint,
  type Summary,
  type TopProduct,
} from '@/lib/api';
import { money, moneyExact, number } from '@/lib/format';

const WINDOWS = [7, 30, 90];

export default function Dashboard() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [series, setSeries] = useState<RevenuePoint[]>([]);
  const [top, setTop] = useState<TopProduct[]>([]);
  const [stock, setStock] = useState<LowStockRow[]>([]);
  const [customers, setCustomers] = useState<CustomerStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // All independent, so fetch them together rather than one after another.
      const [s, r, t, l, c] = await Promise.all([
        api.summary(days),
        api.revenueSeries(days),
        api.topProducts(days),
        api.lowStock(),
        api.customers(days),
      ]);
      setSummary(s);
      setSeries(r);
      setTop(t);
      setStock(l);
      setCustomers(c);
    } catch {
      setError('Could not reach the API. Is the backend running on port 8000?');
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1180px] px-4 pb-20 sm:px-6">
      <Header days={days} onDaysChange={setDays} />

      {error && (
        <div className="rounded-card border border-line bg-surface p-5">
          <p className="text-sm text-ink">{error}</p>
          <button
            onClick={load}
            className="mt-3 rounded-full bg-accent px-4 py-1.5 text-xs font-medium text-accent-ink"
          >
            Try again
          </button>
        </div>
      )}

      {!error && (
        <div className={loading ? 'opacity-40 transition-opacity' : 'transition-opacity'}>
          {/* headline figures */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-5">
            <MetricCard
              label="Revenue"
              value={summary ? money(summary.revenue) : '—'}
              change={summary?.revenue_change}
            />
            <MetricCard
              label="Orders"
              value={summary ? number(summary.orders) : '—'}
              change={summary?.orders_change}
            />
            <MetricCard
              label="Avg order"
              value={summary ? moneyExact(summary.aov) : '—'}
              change={summary?.aov_change}
            />
            <MetricCard
              label="Units sold"
              value={summary ? number(summary.units) : '—'}
              change={summary?.units_change}
            />
            {/* Spans the row on a phone so it doesn't sit alone in half a row. */}
            <MetricCard
              className="col-span-2 lg:col-span-1"
              label="Repeat rate"
              value={summary ? `${summary.repeat_rate}%` : '—'}
              note={
                customers
                  ? `${number(customers.returning_customers)} returning of ${number(customers.active_customers)}`
                  : undefined
              }
            />
          </div>

          {/* charts */}
          <div className="mt-3 grid gap-3 sm:mt-4 sm:gap-4 lg:grid-cols-5">
            <Card title={`Revenue · last ${days} days`} className="lg:col-span-3">
              <RevenueChart data={series} />
            </Card>
            <Card title="Best sellers" className="lg:col-span-2">
              <BestSellers data={top} />
            </Card>
          </div>

          {/* stock */}
          <div className="mt-3 sm:mt-4">
            <Card
              title="Low stock"
              action={
                <span className="text-xs text-ink-faint">
                  {stock.filter((r) => r.inventory === 0).length} sold out
                </span>
              }
            >
              <LowStockTable rows={stock} />
            </Card>
          </div>
        </div>
      )}
    </main>
  );
}

function Header({ days, onDaysChange }: { days: number; onDaysChange: (d: number) => void }) {
  return (
    <header className="sticky top-0 z-10 -mx-4 mb-4 border-b border-line bg-canvas/85 px-4 py-4 backdrop-blur sm:-mx-6 sm:mb-6 sm:px-6 sm:py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-ink">StoreSense</h1>
          <p className="label mt-0.5">noszn</p>
        </div>

        <div className="flex items-center gap-2">
          {/* Window switcher — segmented control, accent marks the active one. */}
          <div className="flex rounded-full border border-line p-0.5">
            {WINDOWS.map((w) => (
              <button
                key={w}
                onClick={() => onDaysChange(w)}
                className={`tnum rounded-full px-3 py-1 text-xs transition-colors ${
                  days === w
                    ? 'bg-accent font-medium text-accent-ink'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {w}d
              </button>
            ))}
          </div>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
