/**
 * Reading server-sent events from a fetch response.
 *
 * Both the copilot and the copy generator stream in the same shape, so the
 * frame parsing lives here once. The fiddly part is that a chunk can end
 * mid-frame — whatever comes after the last blank line is an incomplete frame
 * and has to wait for the next read.
 */

export interface SSEEvent {
  type: 'token' | 'sources' | 'error';
  text?: string;
  message?: string;
  sources?: unknown;
}

export async function readSSE(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: SSEEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split('\n\n');
    // The tail is a partial frame; keep it for the next chunk.
    buffer = frames.pop() ?? '';

    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith('data:')) continue;

      const payload = line.slice(5).trim();
      if (payload === '[DONE]') continue;

      try {
        onEvent(JSON.parse(payload) as SSEEvent);
      } catch {
        // One malformed frame shouldn't kill the rest of the stream.
      }
    }
  }
}
