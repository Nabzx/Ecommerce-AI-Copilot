/**
 * Everything the dashboard knows how to ask the backend.
 *
 * One place for the base URL and one place for the types, so a change to an
 * endpoint shows up as a TypeScript error rather than a blank card.
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface Summary {
  window_days: number;
  revenue: number;
  revenue_change: number | null;
  orders: number;
  orders_change: number | null;
  aov: number;
  aov_change: number | null;
  units: number;
  units_change: number | null;
  repeat_rate: number;
}

export interface RevenuePoint {
  day: string;
  revenue: number;
}

export interface TopProduct {
  product_id: number;
  title: string;
  product_type: string;
  revenue: number;
  units: number;
}

export interface LowStockRow {
  variant_id: number;
  product_id: number;
  product: string;
  size: string;
  sku: string;
  inventory: number;
  units_last_30d: number;
  days_of_stock: number | null;
}

export interface CustomerStats {
  new_customers: number;
  active_customers: number;
  returning_customers: number;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  summary: (days: number) => get<Summary>(`/api/metrics/summary?days=${days}`),
  revenueSeries: (days: number) => get<RevenuePoint[]>(`/api/metrics/revenue-series?days=${days}`),
  topProducts: (days: number) => get<TopProduct[]>(`/api/metrics/top-products?days=${days}&limit=6`),
  lowStock: () => get<LowStockRow[]>('/api/metrics/low-stock'),
  customers: (days: number) => get<CustomerStats>(`/api/metrics/customers?days=${days}`),
};
