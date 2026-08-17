"""
Did the fine-tune actually help?

Generates the held-out prompts twice — once from the base model, once with the
adapter loaded — and scores both the same way. Same prompts, same decoding
settings, same brief; the only difference is the adapter.

Four measures, chosen because they're objective. "Does it sound like the
brand" is a judgement call, so instead:

  banned words   the tone spec names words the brand never uses. Counting them
                 is a direct measure of voice, not a proxy for it.
  lowercase      noszn writes lowercase. A capital letter starting a line is
                 unambiguous and easy to count.
  length         the brief asks for two or three short lines. Overshooting is
                 the most common failure of a base model given a style prompt.
  stray script   added after the fact. Copy generated through the served
                 adapter came back with an Arabic word dropped into an English
                 sentence, so it's measured rather than left as an anecdote.
                 A 0.5B model tuned on 40 examples loses some of its grip on
                 staying in one language.

Base and tuned are compared greedily, so the difference between them is the
adapter and not the sampling. But greedy is not what ships — the copy endpoint
runs at temperature 0.4 — and the stray-script fault does not appear at all
under greedy decoding. So there's a third column: the tuned model sampled at
the temperature the app actually uses. Reporting only the greedy numbers would
have been a clean sheet for a fault I had already seen with my own eyes.

Similarity to the reference copy is reported too, but last and with a caveat —
on eleven examples it's noisy, and a model can score well on it by copying
sentence structure while still sounding wrong.

    python evaluate.py
"""

import json
import re
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from train import ADAPTER_DIR, BASE_MODEL, device, load_jsonl

HERE = Path(__file__).parent

# Straight from app/copywriter.py — the same list the base model is told to
# avoid in its prompt, so this measures whether it obeyed.
BANNED = [
    "elevate", "effortless", "essential", "curated", "timeless", "staple",
    "must-have", "iconic", "unlock", "luxurious", "premium", "game-changer",
    "wardrobe staple", "level up", "elevated",
]

MAX_NEW_TOKENS = 120

# What app/copywriter.py sets. The eval is only worth anything if at least one
# column matches what actually runs in the product.
SHIPPED_TEMPERATURE = 0.4
SEED = 42

# Anything outside Latin-1 that isn't punctuation the brief actually uses.
# The copy is English, so a Cyrillic, Arabic or CJK character is always a fault.
STRAY_SCRIPT = re.compile(r"[^\x00-\xFF\u2018\u2019\u201c\u201d\u2013\u2014\u2026]")


def generate(
    model, tokenizer, messages: list[dict], target: str, temperature: float = 0.0
) -> str:
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(target)

    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            # Greedy by default, so a base-vs-tuned difference is the adapter
            # and not luck. Passed a temperature, it samples the way the app
            # does instead.
            do_sample=temperature > 0,
            temperature=temperature or None,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )

    generated = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def score(text: str) -> dict:
    """The objective measures, for one generation."""
    lowered = text.lower()
    banned_hits = sum(1 for word in BANNED if word in lowered)

    # Lines that begin with a capital. Sizes like "M" and proper nouns are
    # allowed, so only a capital followed by lowercase counts as a sentence
    # start — "M and L are back" shouldn't be marked wrong.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    capitalised = sum(1 for line in lines if re.match(r"^[A-Z][a-z]", line))

    return {
        "banned": banned_hits,
        "capitalised_lines": capitalised,
        "stray_script": len(STRAY_SCRIPT.findall(text)),
        "lines": len(lines),
        "words": len(text.split()),
    }


def summarise(name: str, results: list[dict]) -> dict:
    n = len(results) or 1
    return {
        "model": name,
        "banned_per_generation": round(sum(r["banned"] for r in results) / n, 2),
        "generations_with_banned": sum(1 for r in results if r["banned"] > 0),
        "capitalised_lines": sum(r["capitalised_lines"] for r in results),
        "generations_with_stray_script": sum(1 for r in results if r["stray_script"] > 0),
        "avg_words": round(sum(r["words"] for r in results) / n, 1),
        "generations": n,
    }


def main() -> None:
    target = device()
    rows = load_jsonl(HERE / "data" / "eval.jsonl")
    print(f"device: {target}\nheld-out examples: {len(rows)}\n")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    outputs: dict[str, list[str]] = {}

    for name in ("base", "tuned"):
        model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.float32)
        if name == "tuned":
            model = PeftModel.from_pretrained(model, ADAPTER_DIR)
        model.to(target).eval()

        print(f"generating with {name}…")
        outputs[name] = [
            generate(model, tokenizer, row["messages"][:-1], target) for row in rows
        ]

        # Same adapter, sampled at the temperature app/copywriter.py runs at.
        # Seeded so the number is reproducible run to run.
        if name == "tuned":
            print(f"generating with {name} at temperature {SHIPPED_TEMPERATURE}…")
            torch.manual_seed(SEED)
            outputs["tuned_sampled"] = [
                generate(
                    model, tokenizer, row["messages"][:-1], target,
                    temperature=SHIPPED_TEMPERATURE,
                )
                for row in rows
            ]

        del model

    # --- the table ---
    print()
    header = f"{'':24} {'base':>10} {'tuned':>10} {'tuned @0.4':>12}"
    print(header)
    print("-" * len(header))

    base = summarise("base", [score(t) for t in outputs["base"]])
    tuned = summarise("tuned", [score(t) for t in outputs["tuned"]])
    sampled = summarise("tuned_sampled", [score(t) for t in outputs["tuned_sampled"]])

    for label, key in [
        ("banned words / gen", "banned_per_generation"),
        ("gens with any banned", "generations_with_banned"),
        ("capitalised lines", "capitalised_lines"),
        ("gens w/ stray script", "generations_with_stray_script"),
        ("avg words", "avg_words"),
    ]:
        print(f"{label:24} {base[key]:>10} {tuned[key]:>10} {sampled[key]:>12}")

    # --- a couple of examples, because the numbers aren't the whole story ---
    print("\n" + "=" * 70)
    for i in range(min(2, len(rows))):
        print(f"\nPROMPT: {rows[i]['messages'][1]['content'][:90]}")
        print(f"\n  WANTED: {rows[i]['messages'][2]['content'][:160]}")
        print(f"\n  BASE:   {outputs['base'][i][:160]}")
        print(f"\n  TUNED:  {outputs['tuned'][i][:160]}")
        print("-" * 70)

    (HERE / "eval_results.json").write_text(
        json.dumps(
            {
                "base": base,
                "tuned": tuned,
                "tuned_sampled": sampled,
                "samples": [
                    {
                        "prompt": r["messages"][1]["content"],
                        "reference": r["messages"][2]["content"],
                        "base": b,
                        "tuned": t,
                    }
                    for r, b, t in zip(rows, outputs["base"], outputs["tuned"])
                ],
            },
            indent=2,
        )
    )
    print("\nwritten to eval_results.json")


if __name__ == "__main__":
    main()
