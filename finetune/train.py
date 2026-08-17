"""
LoRA fine-tune of a small open model on noszn's voice.

Why LoRA rather than a full fine-tune: the base model already knows how to
write English. What it doesn't know is that this brand writes in lowercase,
stops after two lines, and never says "elevate". That's a small adjustment to
a lot of existing capability, which is exactly the case adapters are for — a
few million trainable parameters instead of half a billion, and it fits on a
laptop.

Why a 0.5B model: it trains in minutes on an M1 rather than hours, and the
thing being learned is style, not knowledge. A bigger model would write better
prose but wouldn't demonstrate anything more about the technique.

    python train.py
"""

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

HERE = Path(__file__).parent

# Ungated, small, and instruction tuned already — so it starts out able to
# follow "write a product description" and only the voice has to be taught.
BASE_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
ADAPTER_DIR = HERE / "adapters" / "noszn-voice"

MAX_LENGTH = 512


class Collator:
    """
    Pad a batch, keeping the prompt mask intact.

    The stock language-modelling collator pads input_ids and then chokes on
    labels, because masking the prompt makes labels a separate list it doesn't
    know to pad. Padding has to differ between the two anyway: input_ids get
    the pad token, labels get -100 so the padding is ignored by the loss
    rather than learned as something to predict.
    """

    def __init__(self, pad_token_id: int):
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict]) -> dict:
        longest = max(len(f["input_ids"]) for f in features)

        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in features:
            gap = longest - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [self.pad_token_id] * gap)
            batch["attention_mask"].append(f["attention_mask"] + [0] * gap)
            batch["labels"].append(f["labels"] + [-100] * gap)

        return {k: torch.tensor(v, dtype=torch.long) for k, v in batch.items()}


def device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build(tokenizer, rows: list[dict]) -> Dataset:
    """
    Tokenise, and mask the prompt out of the loss.

    Without the mask the model is also trained to predict the instruction it
    was given, which is wasted capacity — and on a dataset this small, wasted
    capacity is the difference between learning the voice and learning to
    repeat the brief back.
    """
    examples = []

    for row in rows:
        messages = row["messages"]
        prompt = tokenizer.apply_chat_template(
            messages[:-1], tokenize=False, add_generation_prompt=True
        )
        full = prompt + messages[-1]["content"] + tokenizer.eos_token

        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        full_ids = tokenizer(
            full, add_special_tokens=False, truncation=True, max_length=MAX_LENGTH
        )["input_ids"]

        labels = list(full_ids)
        for i in range(min(len(prompt_ids), len(labels))):
            labels[i] = -100  # the prompt is context, not something to predict

        examples.append(
            {"input_ids": full_ids, "attention_mask": [1] * len(full_ids), "labels": labels}
        )

    return Dataset.from_list(examples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=float, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    args = parser.parse_args()

    target = device()
    print(f"device: {target}\nbase:   {BASE_MODEL}\n")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(BASE_MODEL, dtype=torch.float32)
    model.to(target)

    # Attention and MLP projections. Adapting attention alone is the common
    # shortcut, but style lives partly in the feed-forward layers and the extra
    # parameters are cheap at this size.
    config = LoraConfig(
        r=args.rank,
        lora_alpha=args.rank * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
    )
    model = get_peft_model(model, config)
    model.print_trainable_parameters()

    train_rows = load_jsonl(HERE / "data" / "train.jsonl")
    eval_rows = load_jsonl(HERE / "data" / "eval.jsonl")
    print(f"\ntraining on {len(train_rows)} examples, holding out {len(eval_rows)}\n")

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(HERE / "runs"),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=1,
            # The batches are tiny, so accumulate to get a gradient that isn't
            # dominated by whichever single example came up.
            gradient_accumulation_steps=4,
            learning_rate=args.lr,
            # transformers 5 dropped warmup_ratio for an explicit step count.
            # 8 steps is about a tenth of this run, which is what the ratio was.
            warmup_steps=8,
            logging_steps=10,
            save_strategy="no",
            report_to=[],
            # fp16 is a CUDA thing; MPS wants float32 and is fine with it here.
            fp16=False,
        ),
        train_dataset=build(tokenizer, train_rows),
        eval_dataset=build(tokenizer, eval_rows),
        data_collator=Collator(tokenizer.pad_token_id or tokenizer.eos_token_id),
    )

    result = trainer.train()
    print(f"\nfinal training loss: {result.training_loss:.4f}")

    metrics = trainer.evaluate()
    print(f"held-out loss:       {metrics['eval_loss']:.4f}")

    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(ADAPTER_DIR)
    tokenizer.save_pretrained(ADAPTER_DIR)

    size = sum(f.stat().st_size for f in ADAPTER_DIR.rglob("*") if f.is_file())
    print(f"\nadapter saved to {ADAPTER_DIR} ({size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
