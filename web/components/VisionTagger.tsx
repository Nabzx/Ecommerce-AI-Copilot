'use client';

import { useRef, useState } from 'react';
import { api, type VisionTags } from '@/lib/api';

/**
 * Drop in a product photo, get Shopify-ready tags and a description back.
 *
 * The "saw" line is shown on purpose. When the tags look wrong it's the only
 * way to tell whether the model misread the photo or just mislabelled what it
 * read, and those need different fixes.
 */
export default function VisionTagger() {
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<VisionTags | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handle(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    setPreview(URL.createObjectURL(file));

    try {
      setResult(await api.tagImage(file));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handle(file);
        }}
      />

      <div className="flex items-start gap-4">
        <button
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="grid h-24 w-24 shrink-0 place-items-center overflow-hidden rounded-lg border border-dashed border-line text-ink-faint transition-colors hover:border-ink-faint hover:text-ink disabled:opacity-40"
        >
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="" className="h-full w-full object-cover" />
          ) : (
            <span className="label">Upload</span>
          )}
        </button>

        <div className="min-w-0 flex-1">
          {busy && <p className="text-sm text-ink-faint">Looking at it…</p>}

          {!busy && !result && !error && (
            <p className="text-sm text-ink-muted">
              Drop in a photo of a piece and it comes back tagged, ready to paste into
              Shopify.
            </p>
          )}

          {error && <p className="text-sm text-ink-muted">{error}</p>}

          {result && (
            <>
              <div className="flex flex-wrap gap-1.5">
                {result.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full border border-line px-2 py-0.5 text-xs text-ink"
                  >
                    {tag}
                  </span>
                ))}
                {result.product_type && (
                  <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-medium text-accent-ink">
                    {result.product_type}
                  </span>
                )}
              </div>

              {result.description && (
                <p className="mt-3 text-sm leading-relaxed text-ink">{result.description}</p>
              )}

              {result.rejected_tags.length > 0 && (
                <p className="mt-2 text-xs text-ink-faint">
                  Suggested but not in your tags: {result.rejected_tags.join(', ')}
                </p>
              )}

              {result.seen && (
                <details className="mt-3">
                  <summary className="label cursor-pointer">What it saw</summary>
                  <p className="mt-1.5 text-xs text-ink-muted">{result.seen}</p>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
