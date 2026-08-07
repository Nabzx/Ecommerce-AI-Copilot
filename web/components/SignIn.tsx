'use client';

import { useState } from 'react';
import { login } from '@/lib/auth';

/**
 * One password for the shop.
 *
 * Deliberately plain — this is a door, not a product surface, and the less it
 * has on it the faster it gets out of the way.
 */
export default function SignIn({ onSignedIn }: { onSignedIn: () => void }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!password || busy) return;

    setBusy(true);
    setError(null);
    try {
      await login(password);
      onSignedIn();
    } catch (err) {
      setError((err as Error).message);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-[320px]">
        <h1 className="text-lg font-semibold tracking-tight text-ink">StoreSense</h1>
        <p className="label mt-0.5">noszn</p>

        <form onSubmit={submit} className="mt-8">
          <label htmlFor="password" className="label">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoFocus
            autoComplete="current-password"
            className="mt-2 w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none"
          />

          <button
            type="submit"
            disabled={!password || busy}
            className="mt-3 w-full rounded-full bg-accent py-2 text-xs font-medium text-accent-ink transition-opacity disabled:opacity-30"
          >
            {busy ? 'Checking…' : 'Sign in'}
          </button>

          {error && <p className="mt-3 text-xs text-ink-muted">{error}</p>}
        </form>
      </div>
    </main>
  );
}
