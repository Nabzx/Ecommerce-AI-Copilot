'use client';

import { useEffect, useRef, useState } from 'react';
import VoiceButton from '@/components/VoiceButton';
import { useCopilot, type Message, type Source } from '@/lib/useCopilot';

// The four things the owner actually asks, so an empty panel isn't a blank box.
const SUGGESTIONS = [
  'How did we do this week?',
  'What do I need to reorder?',
  "What's our returns policy?",
  'Does the Boxy Tee run small?',
];

/**
 * The conversation is owned by the page, not by this component, because the
 * panel is rendered twice — once in the side rail and once in the phone
 * sheet. Sharing the state means asking a question on a phone and then
 * widening the window doesn't lose the answer.
 */
export default function CopilotPanel({
  copilot,
  onClose,
}: {
  copilot: ReturnType<typeof useCopilot>;
  onClose?: () => void;
}) {
  const { messages, isStreaming, send, stop, reset } = copilot;
  const [draft, setDraft] = useState('');
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Follow the answer as it's written.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  function submit(text: string) {
    send(text);
    setDraft('');
  }

  return (
    <div className="flex h-full flex-col rounded-card border border-line bg-surface">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
          <h2 className="label">Copilot</h2>
        </div>
        <div className="flex items-center gap-3">
          {messages.length > 0 && (
            <button
              onClick={reset}
              className="text-xs text-ink-faint transition-colors hover:text-ink"
            >
              Clear
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              aria-label="Close copilot"
              className="text-ink-faint transition-colors hover:text-ink"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </header>

      <div ref={scrollRef} className="thin-scroll flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <EmptyState onPick={submit} />
        ) : (
          messages.map((message, i) => (
            <MessageBubble
              key={i}
              message={message}
              // Only the last one can still be mid-flight.
              isPending={isStreaming && i === messages.length - 1}
            />
          ))
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
        className="border-t border-line p-3"
      >
        {voiceError && <p className="mb-2 text-xs text-ink-muted">{voiceError}</p>}
        <div className="flex items-end gap-2">
          {/* A spoken question goes straight in as if it had been typed. */}
          <VoiceButton
            disabled={isStreaming}
            onTranscript={(text) => {
              setVoiceError(null);
              submit(text);
            }}
            onError={setVoiceError}
          />
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends, shift+enter makes a new line.
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit(draft);
              }
            }}
            rows={1}
            placeholder="Ask about the shop…"
            className="max-h-28 flex-1 resize-none bg-transparent py-2 text-sm text-ink outline-none placeholder:text-ink-faint"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={stop}
              className="shrink-0 rounded-full border border-line px-3 py-1.5 text-xs text-ink-muted transition-colors hover:text-ink"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!draft.trim()}
              className="shrink-0 rounded-full bg-accent px-3.5 py-1.5 text-xs font-medium text-accent-ink transition-opacity disabled:opacity-30"
            >
              Ask
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div>
      <p className="text-sm text-ink-muted">
        Ask about the store. Answers about policy or products cite where they came from.
      </p>
      <div className="mt-4 space-y-1.5">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            onClick={() => onPick(suggestion)}
            className="block w-full rounded-lg border border-line px-3 py-2 text-left text-xs text-ink-muted transition-colors hover:bg-raised hover:text-ink"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message, isPending }: { message: Message; isPending: boolean }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-raised px-3 py-2 text-sm text-ink">
          {message.content}
        </p>
      </div>
    );
  }

  // Nothing has arrived yet — show that something is happening.
  const waiting = isPending && !message.content && !message.error;

  return (
    <div className="space-y-2">
      {waiting ? (
        <TypingDots />
      ) : (
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">
          {message.content}
          {isPending && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-ink align-middle" />}
        </p>
      )}

      {!isPending && <Citations sources={message.sources} content={message.content} />}

      {message.error && (
        <p className="rounded-lg border border-line bg-raised px-3 py-2 text-xs text-ink-muted">
          {message.error}
        </p>
      )}
    </div>
  );
}

/**
 * Only the sources the answer actually pointed at.
 *
 * Four documents get retrieved for every question but a short answer usually
 * leans on one. Listing all four made the [1] in the text look decorative —
 * showing just the cited ones is what makes the marker mean something.
 */
function Citations({ sources, content }: { sources?: Source[]; content: string }) {
  if (!sources?.length || !content) return null;

  const cited = new Set(Array.from(content.matchAll(/\[(\d+)\]/g), (m) => Number(m[1])));
  const used = sources.filter((source) => cited.has(source.n));

  // Nothing was cited — the answer came from the figures, not the documents.
  if (used.length === 0) return null;

  return (
    <div className="border-t border-line pt-2">
      <p className="label mb-1.5">Sources</p>
      <ul className="space-y-1">
        {used.map((source) => (
          <li key={source.n} className="flex gap-1.5 text-xs text-ink-faint">
            <span className="tnum shrink-0 text-ink-muted">[{source.n}]</span>
            {/* Merged sections make long titles — the first part is the useful bit. */}
            <span className="truncate" title={source.title}>
              {source.title}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="flex gap-1" aria-label="Thinking">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}
