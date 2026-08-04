'use client';

import { useEffect, useState } from 'react';
import { api, type AlertRow } from '@/lib/api';

export default function AlertsPanel() {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.alerts().then(setAlerts).catch(() => undefined);
  }, []);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!draft.trim() || saving) return;

    setSaving(true);
    setError(null);
    try {
      const created = await api.createAlert(draft.trim());
      setAlerts((current) => [...current, created]);
      setDraft('');
    } catch (err) {
      // The API explains what it couldn't understand — show that, not a code.
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number) {
    setAlerts((current) => current.filter((a) => a.id !== id));
    await api.deleteAlert(id);
  }

  return (
    <div>
      <form onSubmit={add} className="flex items-center gap-2 rounded-full border border-line px-3 py-1.5">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Tell me if any product drops below 5 units…"
          className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint"
        />
        <button
          type="submit"
          disabled={!draft.trim() || saving}
          className="shrink-0 rounded-full bg-accent px-3 py-1 text-xs font-medium text-accent-ink transition-opacity disabled:opacity-30"
        >
          {saving ? 'Reading…' : 'Add'}
        </button>
      </form>

      {error && (
        <p className="mt-3 rounded-lg border border-line bg-raised px-3 py-2 text-xs text-ink-muted">
          {error}
        </p>
      )}

      {alerts.length === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">
          Write a rule in plain English and it gets checked against the store from then on.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {alerts.map((alert) => (
            <li key={alert.id} className="border-b border-line/60 pb-3 last:border-0 last:pb-0">
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{alert.phrase}</p>
                  {/* Showing how it was read is the whole trick — the owner can
                      see the model understood them before they trust it. */}
                  <p className="label mt-1">Reads as: {alert.reads_as}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Status alert={alert} />
                  <button
                    onClick={() => remove(alert.id)}
                    aria-label={`Delete alert: ${alert.phrase}`}
                    className="text-ink-faint transition-colors hover:text-ink"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>

              {alert.triggered && (
                <ul className="mt-2 space-y-0.5">
                  {alert.hits.map((hit) => (
                    <li key={hit.label} className="flex justify-between gap-3 text-xs text-ink-muted">
                      <span className="truncate">{hit.label}</span>
                      <span className="tnum shrink-0">{hit.value}</span>
                    </li>
                  ))}
                  {alert.count > alert.hits.length && (
                    <li className="text-xs text-ink-faint">
                      and {alert.count - alert.hits.length} more
                    </li>
                  )}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Status({ alert }: { alert: AlertRow }) {
  if (!alert.triggered) {
    return <span className="whitespace-nowrap text-xs text-ink-faint">Clear</span>;
  }
  return (
    <span className="flex items-center gap-1.5 whitespace-nowrap text-xs text-ink">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: 'var(--warning)' }} aria-hidden />
      {alert.count} match{alert.count === 1 ? '' : 'es'}
    </span>
  );
}
