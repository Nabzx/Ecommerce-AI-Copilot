'use client';

import { useEffect, useState } from 'react';
import { api, type ReviewInsights } from '@/lib/api';

/**
 * What customers keep saying.
 *
 * The split matters less than the themes. "21% negative" isn't something the
 * owner can do anything with; "most of the complaints are about sizing" is a
 * size chart problem with an obvious fix.
 */
export default function SentimentCard() {
  const [data, setData] = useState<ReviewInsights | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.reviewInsights().then(setData).catch(() => undefined);
  }, []);

  async function analyse() {
    setRunning(true);
    setError(null);
    try {
      setData(await api.analyseReviews());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRunning(false);
    }
  }

  if (!data) {
    return <p className="py-6 text-sm text-ink-faint">Loading reviews…</p>;
  }

  const unanalysed = data.total - data.analysed;

  // No reviews at all, which is what a freshly synced real store looks like:
  // Shopify has no reviews API, they live in a separate app. Better to say so
  // than to show an empty card that reads as broken.
  if (data.total === 0) {
    return (
      <p className="py-6 text-sm text-ink-muted">
        No reviews loaded. Shopify doesn&apos;t provide them through its API — they live in
        whatever review app the shop uses, so they need importing separately.
      </p>
    );
  }

  if (data.analysed === 0) {
    return (
      <div>
        <p className="text-sm text-ink-muted">
          {data.total} reviews, none classified yet.
        </p>
        <button
          onClick={analyse}
          disabled={running}
          className="mt-3 rounded-full bg-accent px-4 py-1.5 text-xs font-medium text-accent-ink disabled:opacity-40"
        >
          {running ? 'Reading them…' : 'Analyse reviews'}
        </button>
        {error && <p className="mt-3 text-xs text-ink-muted">{error}</p>}
      </div>
    );
  }

  const total = data.analysed || 1;
  const positive = data.counts.positive ?? 0;
  const negative = data.counts.negative ?? 0;
  const neutral = data.counts.neutral ?? 0;

  return (
    <div>
      {/* One bar, three segments, with a 2px gap so they read as separate. */}
      <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-full">
        <span style={{ width: `${(positive / total) * 100}%`, background: 'var(--ink)' }} />
        <span style={{ width: `${(neutral / total) * 100}%`, background: 'var(--ink-faint)' }} />
        <span style={{ width: `${(negative / total) * 100}%`, background: 'var(--warning)' }} />
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        <span className="tnum">{positive}</span> positive ·{' '}
        <span className="tnum">{neutral}</span> neutral ·{' '}
        <span className="tnum">{negative}</span> negative
      </p>

      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <ThemeList title="Complaints about" themes={data.negative_themes} />
        <ThemeList title="Praised for" themes={data.positive_themes} />
      </div>

      {data.examples.length > 0 && (
        <div className="mt-5 border-t border-line pt-3">
          <p className="label mb-2">In their words</p>
          <ul className="space-y-1.5">
            {data.examples.map((example, i) => (
              <li key={i} className="text-xs text-ink-muted">
                “{example.body}”{' '}
                <span className="text-ink-faint">— {example.product}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {unanalysed > 0 && (
        <button
          onClick={analyse}
          disabled={running}
          className="mt-4 text-xs text-ink-faint underline underline-offset-2 hover:text-ink disabled:opacity-40"
        >
          {running ? 'Reading them…' : `Classify the remaining ${unanalysed}`}
        </button>
      )}
      {error && <p className="mt-3 text-xs text-ink-muted">{error}</p>}
    </div>
  );
}

function ThemeList({
  title,
  themes,
}: {
  title: string;
  themes: { theme: string; count: number }[];
}) {
  if (themes.length === 0) return null;
  const top = themes[0].count || 1;

  return (
    <div>
      <p className="label mb-2">{title}</p>
      <ul className="space-y-1.5">
        {themes.map((row) => (
          <li key={row.theme} className="flex items-center gap-2">
            <span className="flex-1 truncate text-sm text-ink">{row.theme}</span>
            {/* A bar rather than a number alone — the ratio is the point. */}
            <span className="h-1 w-16 overflow-hidden rounded-full bg-raised">
              <span
                className="block h-full rounded-full bg-ink"
                style={{ width: `${(row.count / top) * 100}%` }}
              />
            </span>
            <span className="tnum w-5 text-right text-xs text-ink-muted">{row.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
