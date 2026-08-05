'use client';

import { useEffect, useState } from 'react';
import { API_BASE, api, type ProductSummary } from '@/lib/api';
import { readSSE } from '@/lib/sse';

/**
 * Writes product copy and win-back emails in noszn's voice, streamed.
 *
 * Uses the same SSE reader as the copilot, because the backend deliberately
 * streams both in the same shape.
 */
export default function CopyStudio() {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [productId, setProductId] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    api
      .products()
      .then((rows) => {
        setProducts(rows);
        if (rows.length) setProductId(rows[0].id);
      })
      .catch(() => undefined);
  }, []);

  async function generate(path: string) {
    setBusy(true);
    setError(null);
    setText('');
    setCopied(false);

    try {
      const response = await fetch(`${API_BASE}${path}`, { method: 'POST' });
      if (!response.ok || !response.body) {
        setError(`The server answered ${response.status}.`);
        return;
      }

      let received = '';
      await readSSE(response.body, (event) => {
        if (event.type === 'token') {
          received += event.text ?? '';
          setText((current) => current + (event.text ?? ''));
        } else if (event.type === 'error') {
          setError(event.message ?? 'Something went wrong.');
        }
      });

      // A stream that ends having said nothing is usually the model still
      // warming up. Better to say so than to leave an empty box.
      if (!received.trim()) {
        setError('The model returned nothing. It may still be loading — try again.');
      }
    } catch {
      setError('Lost connection to the API.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={productId ?? ''}
          onChange={(e) => setProductId(Number(e.target.value))}
          className="min-w-0 flex-1 rounded-full border border-line bg-transparent px-3 py-1.5 text-sm text-ink outline-none"
        >
          {products.map((product) => (
            <option key={product.id} value={product.id}>
              {product.title}
            </option>
          ))}
        </select>

        <button
          onClick={() => productId && generate(`/api/copy/description/${productId}`)}
          disabled={busy || !productId}
          className="shrink-0 rounded-full bg-accent px-3.5 py-1.5 text-xs font-medium text-accent-ink disabled:opacity-30"
        >
          Description
        </button>
        <button
          onClick={() => generate('/api/copy/winback')}
          disabled={busy}
          className="shrink-0 rounded-full border border-line px-3.5 py-1.5 text-xs text-ink-muted transition-colors hover:text-ink disabled:opacity-30"
        >
          Win-back email
        </button>
      </div>

      {(text || busy || error) && (
        <div className="mt-4 rounded-lg border border-line bg-raised p-4">
          {busy && !text && <p className="text-sm text-ink-faint">Writing…</p>}
          {text && (
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
              {text}
              {busy && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-ink align-middle" />}
            </p>
          )}
          {error && <p className="text-xs text-ink-muted">{error}</p>}

          {text && !busy && (
            <button
              onClick={() => {
                navigator.clipboard.writeText(text);
                setCopied(true);
              }}
              className="mt-3 text-xs text-ink-faint underline underline-offset-2 hover:text-ink"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
