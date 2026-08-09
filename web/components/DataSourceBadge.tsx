'use client';

import { useState } from 'react';
import { api, type Health } from '@/lib/api';

/**
 * Says whether you're looking at demo data or the real shop.
 *
 * This is the first question anyone asks when they open it, and without an
 * answer on screen a convincing demo is indistinguishable from live numbers.
 */
export default function DataSourceBadge({
  health,
  onSynced,
}: {
  health: Health;
  onSynced: () => void;
}) {
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const data = health.data;
  const isDemo = data.is_demo;

  async function sync() {
    setSyncing(true);
    setError(null);
    try {
      await api.shopifySync();
      onSynced();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <span
        className="flex items-center gap-1.5 whitespace-nowrap text-xs"
        title={data.note || undefined}
      >
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: isDemo ? 'var(--ink-faint)' : 'var(--accent)' }}
          aria-hidden
        />
        <span className={isDemo ? 'text-ink-faint' : 'text-ink'}>
          {isDemo ? 'Demo data' : data.store_domain || 'Live data'}
        </span>
        {!isDemo && data.synced_at && (
          <span className="text-ink-faint">· {timeAgo(data.synced_at)}</span>
        )}
      </span>

      {/* Only offered once there are credentials to use. */}
      {health.shopify_configured && (
        <button
          onClick={sync}
          disabled={syncing}
          title={isDemo ? 'Replace the demo data with your real store' : 'Pull the latest'}
          className="rounded-full border border-line px-2.5 py-1 text-xs text-ink-muted transition-colors hover:text-ink disabled:opacity-40"
        >
          {syncing ? 'Syncing…' : isDemo ? 'Connect store' : 'Sync'}
        </button>
      )}

      {error && <span className="max-w-[220px] truncate text-xs text-ink-faint">{error}</span>}

      {/* Worth surfacing: without cost per item every margin reads as 100%. */}
      {!isDemo && data.note && (
        <span className="hidden max-w-[260px] truncate text-xs text-ink-faint lg:inline">
          {data.note}
        </span>
      )}
    </div>
  );
}

function timeAgo(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  if (seconds < 90) return 'just now';
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}
