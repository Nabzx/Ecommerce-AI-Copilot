'use client';

import { useRef, useState } from 'react';
import { api } from '@/lib/api';

/**
 * Hold to record, let go to ask.
 *
 * The recording goes off to be transcribed and the text is handed back to
 * whoever owns the input — so a spoken question takes exactly the same path
 * through the app as a typed one.
 */
export default function VoiceButton({
  onTranscript,
  onError,
  disabled,
}: {
  onTranscript: (text: string) => void;
  onError: (message: string) => void;
  disabled?: boolean;
}) {
  const [recording, setRecording] = useState(false);
  const [working, setWorking] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  async function start() {
    if (disabled || working) return;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        // Release the mic straight away — a live indicator hanging around
        // after you've finished talking is unnerving.
        stream.getTracks().forEach((track) => track.stop());

        const audio = new Blob(chunksRef.current, { type: 'audio/webm' });
        if (audio.size < 1000) {
          onError('That was too short to hear.');
          return;
        }

        setWorking(true);
        try {
          const text = await api.transcribe(audio);
          if (text.trim()) onTranscript(text.trim());
          else onError("Couldn't make that out.");
        } catch (err) {
          onError((err as Error).message);
        } finally {
          setWorking(false);
        }
      };

      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      onError('No microphone access. Allow it in your browser settings.');
    }
  }

  function stop() {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  }

  return (
    <button
      type="button"
      // Pointer events rather than mouse, so it works on a phone too.
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={() => recording && stop()}
      disabled={disabled || working}
      aria-label={recording ? 'Release to send' : 'Hold to speak'}
      title="Hold to speak"
      className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-colors disabled:opacity-30 ${
        recording
          ? 'border-transparent bg-accent text-accent-ink'
          : 'border-line text-ink-muted hover:text-ink'
      }`}
    >
      {working ? <span className="label">…</span> : <MicIcon />}
    </button>
  );
}

function MicIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0M12 17v4" />
    </svg>
  );
}
