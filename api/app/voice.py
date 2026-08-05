"""
Voice questions.

The owner holds a button, asks the copilot something out loud, and the audio
comes back as text that goes through exactly the same chat path as typing
would. Nothing downstream knows the difference.

Two ways to transcribe, tried in order:

  1. faster-whisper running locally. Free, offline, and the base model is
     about 75MB, downloaded once on first use.
  2. An OpenAI-compatible /audio/transcriptions endpoint, if one is
     configured.

Neither is required for the rest of StoreSense to work — if there's no
transcriber the endpoint says so plainly instead of failing obscurely.
"""

import tempfile
from pathlib import Path

import httpx

from app.config import settings

# Loading the model takes a few seconds, so it's kept once it's built.
_model = None


class NoTranscriber(Exception):
    """Nothing available to turn audio into text."""


def local_model():
    """
    Load faster-whisper, or say why we can't.

    Imported here rather than at module scope so the whole API still starts
    when the package isn't installed — voice is optional, everything else
    shouldn't care.
    """
    global _model
    if _model is not None:
        return _model

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise NoTranscriber(
            "faster-whisper isn't installed. Run `pip install faster-whisper`, "
            "or point LLM_BASE_URL at a provider that transcribes audio."
        )

    # int8 on CPU is the combination that runs at a sensible speed on a laptop
    # without a GPU, which is what this is meant to run on.
    _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _model


async def transcribe_remote(audio: bytes, filename: str) -> str:
    """Send the audio to an OpenAI-compatible transcription endpoint."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/audio/transcriptions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            files={"file": (filename, audio)},
            data={"model": settings.whisper_remote_model},
        )

    if response.status_code >= 400:
        raise NoTranscriber(f"the transcription endpoint returned {response.status_code}")

    return response.json().get("text", "").strip()


async def transcribe(audio: bytes, filename: str = "audio.webm") -> dict:
    """Turn recorded audio into text."""
    try:
        model = local_model()
    except NoTranscriber:
        # No local model — the remote endpoint is the only hope left, and if
        # that isn't configured either its error is the one worth showing.
        text = await transcribe_remote(audio, filename)
        return {"text": text, "engine": "remote"}

    # faster-whisper reads from a path, so the upload lands in a temp file.
    suffix = Path(filename).suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as handle:
        handle.write(audio)
        handle.flush()
        segments, _info = model.transcribe(handle.name, beam_size=1)
        text = " ".join(segment.text for segment in segments).strip()

    return {"text": text, "engine": f"faster-whisper:{settings.whisper_model}"}
