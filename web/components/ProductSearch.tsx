'use client';

import { useState } from 'react';
import { api, type ProductHit } from '@/lib/api';
import { moneyExact } from '@/lib/format';

// Queries that show it's matching on meaning rather than words — none of these
// terms appear anywhere in the catalogue.
const EXAMPLES = ['cozy autumn pieces', 'something light for summer', 'warm layer for winter'];

export default function ProductSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<ProductHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(text: string) {
    if (text.trim().length < 2) return;
    setQuery(text);
    setSearching(true);
    setError(null);
    try {
      setResults(await api.searchProducts(text));
    } catch {
      setError('Search failed. Is the backend running?');
      setResults(null);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
        className="flex items-center gap-2 rounded-full border border-line px-3 py-1.5"
      >
        <SearchIcon />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Describe what you're looking for…"
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        {searching && <span className="label">…</span>}
      </form>

      {!results && !error && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => run(example)}
              className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-muted transition-colors hover:bg-raised hover:text-ink"
            >
              {example}
            </button>
          ))}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-ink-muted">{error}</p>}

      {results && results.length === 0 && (
        <p className="mt-3 text-sm text-ink-muted">Nothing close enough to show.</p>
      )}

      {results && results.length > 0 && (
        <ul className="mt-3 space-y-2">
          {results.map((hit) => (
            <li key={hit.product_id} className="flex items-baseline gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-ink">{hit.title}</p>
                <p className="label mt-0.5">
                  {hit.sizes_in_stock.length > 0
                    ? `${hit.sizes_in_stock.join(' · ')}`
                    : 'no sizes in stock'}
                </p>
              </div>
              <span className="tnum shrink-0 text-sm text-ink-muted">
                {moneyExact(hit.price)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SearchIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      className="shrink-0 text-ink-faint"
    >
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}
