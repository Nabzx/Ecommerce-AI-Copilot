'use client';

import { useCallback, useRef, useState } from 'react';
import { API_BASE } from '@/lib/api';

export interface Source {
  n: number;
  title: string;
  source: string;
  score: number;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  error?: string;
}

/**
 * Talks to the streaming chat endpoint.
 *
 * fetch is used rather than EventSource because the question has to go up as a
 * POST body, and EventSource can only do GET. That means parsing the SSE
 * frames by hand, which is the loop below.
 */
export function useCopilot() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  /** Replace the assistant message currently being written. */
  const updateLast = useCallback((patch: (m: Message) => Message) => {
    setMessages((current) => {
      const next = [...current];
      next[next.length - 1] = patch(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = useCallback(
    async (question: string) => {
      if (!question.trim() || isStreaming) return;

      // What the backend needs to follow a "what about last month?".
      const history = messages.map((m) => ({ role: m.role, content: m.content }));

      setMessages((current) => [
        ...current,
        { role: 'user', content: question },
        { role: 'assistant', content: '' },
      ]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: question, history }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          const detail =
            response.status === 429
              ? 'Slow down a moment — too many questions at once.'
              : `The server answered ${response.status}.`;
          updateLast((m) => ({ ...m, error: detail }));
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Frames are separated by a blank line. Anything after the last one
          // is a partial frame, so it stays in the buffer for the next read.
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';

          for (const frame of frames) {
            const line = frame.trim();
            if (!line.startsWith('data:')) continue;

            const payload = line.slice(5).trim();
            if (payload === '[DONE]') continue;

            try {
              const event = JSON.parse(payload);
              if (event.type === 'token') {
                updateLast((m) => ({ ...m, content: m.content + event.text }));
              } else if (event.type === 'sources') {
                updateLast((m) => ({ ...m, sources: event.sources }));
              } else if (event.type === 'error') {
                updateLast((m) => ({ ...m, error: event.message }));
              }
            } catch {
              // A malformed frame shouldn't kill the rest of the answer.
            }
          }
        }
      } catch (err) {
        // An abort is the user pressing stop, not a failure.
        if ((err as Error).name !== 'AbortError') {
          updateLast((m) => ({
            ...m,
            error: 'Lost connection to the API. Is the backend running?',
          }));
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [messages, isStreaming, updateLast],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const reset = useCallback(() => setMessages([]), []);

  return { messages, isStreaming, send, stop, reset };
}
