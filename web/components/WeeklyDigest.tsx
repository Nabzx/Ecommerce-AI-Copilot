'use client';

import { useState } from 'react';
import { api, type Digest } from '@/lib/api';

/**
 * Last week in a few lines, plus what to do about it.
 *
 * Loaded on a button rather than with the rest of the dashboard, because it
 * asks the model to write the opening and that takes a moment. The same thing
 * goes out by email on a schedule — this is here so you can see what he'll
 * get, and read it on a day that isn't Monday.
 */
export default function WeeklyDigest() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [sent, setSent] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      setDigest(await api.digest());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function email() {
    setError(null);
    try {
      const { sent_to } = await api.sendDigest();
      setSent(sent_to);
    } catch (err) {
      // Usually "email isn't configured", which is a setup step, not a fault.
      setError((err as Error).message);
    }
  }

  if (!digest) {
    return (
      <div>
        <p className="text-sm text-ink-muted">
          A short summary of the week and what needs doing — the same one that goes out by
          email on Monday morning.
        </p>
        <button
          onClick={generate}
          disabled={busy}
          className="mt-3 rounded-full bg-accent px-4 py-1.5 text-xs font-medium text-accent-ink disabled:opacity-40"
        >
          {busy ? 'Writing…' : "Write this week's brief"}
        </button>
        {error && <p className="mt-3 text-xs text-ink-muted">{error}</p>}
      </div>
    );
  }

  return (
    <div>
      {digest.summary && (
        <p className="text-sm leading-relaxed text-ink">{digest.summary}</p>
      )}

      <pre className="thin-scroll mt-4 overflow-x-auto whitespace-pre-wrap font-sans text-xs leading-relaxed text-ink-muted">
        {digest.figures}
      </pre>

      {digest.actions.length > 0 && (
        <div className="mt-4 border-t border-line pt-3">
          <p className="label mb-2">Worth doing</p>
          <ul className="space-y-1">
            {digest.actions.map((action) => (
              <li key={action} className="flex gap-2 text-sm text-ink">
                <span className="text-ink-faint" aria-hidden>
                  ·
                </span>
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => {
            navigator.clipboard.writeText(digest.text);
            setCopied(true);
          }}
          className="text-xs text-ink-faint underline underline-offset-2 hover:text-ink"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        <button
          onClick={email}
          className="text-xs text-ink-faint underline underline-offset-2 hover:text-ink"
        >
          Email it
        </button>
        <button
          onClick={generate}
          disabled={busy}
          className="text-xs text-ink-faint underline underline-offset-2 hover:text-ink disabled:opacity-40"
        >
          {busy ? 'Writing…' : 'Rewrite'}
        </button>

        {sent && <span className="text-xs text-ink-muted">Sent to {sent}</span>}
        {error && <span className="max-w-[420px] text-xs text-ink-muted">{error}</span>}
      </div>
    </div>
  );
}
