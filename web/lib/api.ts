/**
 * Everything the dashboard knows how to ask the backend.
 *
 * One place for the base URL and one place for the types, so a change to an
 * endpoint shows up as a TypeScript error rather than a blank card.
 */

import { authHeaders, clearToken } from '@/lib/auth';

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

export interface Stockout {
  variant_id: number;
  product_id: number;
  product: string;
  size: string;
  sku: string;
  inventory: number;
  daily_rate: number;
  days_to_stockout: number | null;
  stockout_on: string | null;
}

export interface ForecastAccuracy {
  folds: number;
  test_days: number;
  units_actually_sold: number;
  error_pct: number;
  model_only_error_pct: number;
  naive_error_pct: number;
  beats_baseline: boolean;
}

export interface ProductHit {
  product_id: number;
  title: string;
  product_type: string;
  price: number;
  tags: string[];
  sizes_in_stock: string[];
  units_in_stock: number;
  score: number;
}

export interface AlertHit {
  label: string;
  value: number;
}

export interface AlertRow {
  id: number;
  phrase: string;
  reads_as: string;
  triggered: boolean;
  count: number;
  hits: AlertHit[];
}

export interface ReviewInsights {
  analysed: number;
  total: number;
  counts: { positive?: number; neutral?: number; negative?: number };
  positive_themes: { theme: string; count: number }[];
  negative_themes: { theme: string; count: number }[];
  examples: { body: string; theme: string; rating: number; product: string }[];
}

export interface VisionTags {
  tags: string[];
  product_type: string;
  colour: string;
  description: string;
  seen: string;
  rejected_tags: string[];
}

export interface Digest {
  store: string;
  generated_at: string;
  summary: string;
  figures: string;
  actions: string[];
  sold_out: number;
  text: string;
}

export interface DataSource {
  source: string;
  is_demo: boolean;
  store_domain?: string;
  synced_at: string | null;
  products?: number;
  orders?: number;
  customers?: number;
  note?: string;
}

export interface Health {
  status: string;
  store: string;
  auth_required: boolean;
  model_available: boolean;
  model: string;
  shopify_configured: boolean;
  data: DataSource;
}

export interface ProductSummary {
  id: number;
  title: string;
  product_type: string;
  price: number;
  in_stock: number;
}

/**
 * A 401 means the token expired or was never there. Clearing it is what makes
 * the page fall back to the login screen on the next render, rather than
 * showing a dashboard full of failed requests.
 */
function handleUnauthorised() {
  clearToken();
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('storesense-signed-out'));
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: 'no-store',
    headers: authHeaders(),
  });
  if (response.status === 401) {
    handleUnauthorised();
    throw new Error('Signed out.');
  }
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

/** Reads the message the API sent rather than showing a bare status code. */
async function detail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === 'string' ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export const api = {
  summary: (days: number) => get<Summary>(`/api/metrics/summary?days=${days}`),
  revenueSeries: (days: number) => get<RevenuePoint[]>(`/api/metrics/revenue-series?days=${days}`),
  topProducts: (days: number) => get<TopProduct[]>(`/api/metrics/top-products?days=${days}&limit=6`),
  lowStock: () => get<LowStockRow[]>('/api/metrics/low-stock'),
  customers: (days: number) => get<CustomerStats>(`/api/metrics/customers?days=${days}`),

  stockouts: (limit = 8) => get<Stockout[]>(`/api/forecast/stockouts?limit=${limit}`),
  forecastAccuracy: () => get<ForecastAccuracy>('/api/forecast/accuracy'),

  searchProducts: (q: string) =>
    get<ProductHit[]>(`/api/search/products?q=${encodeURIComponent(q)}&limit=5`),

  alerts: () => get<AlertRow[]>('/api/alerts'),

  async createAlert(phrase: string): Promise<AlertRow> {
    const response = await fetch(`${API_BASE}/api/alerts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ phrase }),
    });
    if (!response.ok) {
      throw new Error(await detail(response, `The server answered ${response.status}.`));
    }
    return response.json();
  },

  async deleteAlert(id: number): Promise<void> {
    await fetch(`${API_BASE}/api/alerts/${id}`, { method: 'DELETE', headers: authHeaders() });
  },

  products: () => get<ProductSummary[]>('/api/products'),

  digest: () => get<Digest>('/api/digest'),

  async sendDigest(): Promise<{ sent_to: string }> {
    const response = await fetch(`${API_BASE}/api/digest/send`, {
      method: 'POST',
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(await detail(response, `Could not send it (${response.status}).`));
    }
    return response.json();
  },

  /**
   * Replaces everything, demo data included. Rebuilds the search index too,
   * so it can take a little while on a real shop.
   */
  async shopifySync(): Promise<{ orders: number; note: string }> {
    const response = await fetch(`${API_BASE}/api/shopify/sync`, {
      method: 'POST',
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(await detail(response, `The sync failed (${response.status}).`));
    }
    return response.json();
  },
  reviewInsights: () => get<ReviewInsights>('/api/reviews/insights'),

  async analyseReviews(): Promise<ReviewInsights> {
    const response = await fetch(`${API_BASE}/api/reviews/analyse?limit=500`, {
      method: 'POST',
      headers: authHeaders(),
    });
    if (!response.ok) {
      throw new Error(await detail(response, `The server answered ${response.status}.`));
    }
    return response.json();
  },

  async tagImage(file: File): Promise<VisionTags> {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_BASE}/api/vision/tag`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
    if (!response.ok) {
      throw new Error(await detail(response, `The server answered ${response.status}.`));
    }
    return response.json();
  },

  async transcribe(audio: Blob): Promise<string> {
    const form = new FormData();
    form.append('file', audio, 'question.webm');
    const response = await fetch(`${API_BASE}/api/voice/transcribe`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    });
    if (!response.ok) {
      throw new Error(await detail(response, `The server answered ${response.status}.`));
    }
    return (await response.json()).text as string;
  },
};
