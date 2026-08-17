"""
Serve the adapter behind an OpenAI-compatible endpoint.

The point of the gateway being provider-agnostic is that this needs no change
anywhere else. Start this, point LLM_BASE_URL at it, and the copy generator
uses the fine-tuned model with the same code path it uses for OpenAI or
Ollama — same streaming, same retries, same token accounting.

    python serve.py            # then LLM_BASE_URL=http://localhost:8100/v1

Deliberately minimal: one model, loaded once, no batching, no queue. It exists
to prove the adapter drops into the existing architecture, not to be a serving
layer anyone would run at scale.
"""

import time
from pathlib import Path

import torch
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from peft import PeftModel
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from train import ADAPTER_DIR, BASE_MODEL, device

app = FastAPI(title="noszn voice adapter")

MODEL_NAME = "noszn-voice"
state: dict = {}


@app.on_event("startup")
def load() -> None:
    target = device()
    print(f"loading {BASE_MODEL} + adapter on {target}…")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.float32)
    if Path(ADAPTER_DIR).exists():
        model = PeftModel.from_pretrained(model, ADAPTER_DIR)
        print(f"adapter loaded from {ADAPTER_DIR}")
    else:
        print("no adapter found — serving the base model. run train.py first.")

    state["model"] = model.to(target).eval()
    state["tokenizer"] = tokenizer
    state["device"] = target
    print("ready")


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict]
    temperature: float = 0.4
    max_tokens: int | None = 160
    stream: bool = False
    # Accepted and ignored — the gateway sends it, and rejecting an unknown
    # field would make this look broken rather than simple.
    stream_options: dict | None = None


def run(body: ChatRequest) -> tuple[str, int, int]:
    tokenizer, model = state["tokenizer"], state["model"]

    prompt = tokenizer.apply_chat_template(
        body.messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(state["device"])
    prompt_tokens = inputs["input_ids"].shape[1]

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=body.max_tokens or 160,
            do_sample=body.temperature > 0,
            temperature=max(body.temperature, 0.01),
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )

    generated = output[0][prompt_tokens:]
    text = tokenizer.decode(generated, skip_special_tokens=True).strip()
    return text, prompt_tokens, len(generated)


@app.get("/v1/models")
def models() -> dict:
    """The gateway pings this to decide whether anything is listening."""
    return {"data": [{"id": MODEL_NAME, "object": "model"}]}


@app.post("/v1/chat/completions")
def completions(body: ChatRequest):
    text, prompt_tokens, completion_tokens = run(body)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }

    if not body.stream:
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "model": MODEL_NAME,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text}}],
            "usage": usage,
        }

    def frames():
        # Generated in one go and then chunked. Real token-by-token streaming
        # would need a threaded streamer; the gateway can't tell the difference
        # and this keeps the file readable.
        import json

        for word in text.split(" "):
            chunk = {
                "choices": [{"index": 0, "delta": {"content": word + " "}}],
                "model": MODEL_NAME,
            }
            yield f"data: {json.dumps(chunk)}\n\n"

        # The usage frame the gateway looks for: empty choices, usage attached.
        yield f"data: {json.dumps({'choices': [], 'usage': usage, 'model': MODEL_NAME})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
