"""
Turn the noszn voice examples into something a model can train on.

The dataset is hand written rather than generated, and that's deliberate. A
templated dataset teaches the model to fill slots — it would learn "400gsm
{fabric}, {cut} through the body" and produce that shape forever. Voice comes
from variety, so the examples vary in structure on purpose and several
products appear twice written from different angles.

It's synthetic in the sense that noszn didn't write it: it's written to the
brand's tone spec, which is the same spec the base model gets in its prompt.
That matters for the comparison being fair — both models are aiming at the
same target, one has just seen examples of it.

    python build_dataset.py
"""

import json
import random
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "data" / "noszn_voice.jsonl"

# The same brief the base model gets at inference, so tuned and untuned are
# asked for the same thing and only the training differs.
SYSTEM = (
    "You write for noszn, a small clothing brand. Lowercase, short lines, plain "
    "words. Say what the thing is and what it is made of, then stop. Never use "
    "marketing language."
)

# Held out for the evaluation. Small, because the dataset is small — but fixed
# by seed so the split is the same every run and the numbers are comparable.
EVAL_FRACTION = 0.2
SEED = 42


def instruction_for(row: dict) -> str:
    """What the model is asked, in the same words at train and eval time."""
    kind = row["kind"]

    if kind == "description":
        return (
            f"Write the product description for {row['product']}.\n"
            f"Facts: {row['facts']}"
        )
    if kind == "subject":
        return f"Write an email subject line. Context: {row['context']}"
    if kind == "restock":
        return f"Write a short restock note. Context: {row['context']}"
    if kind == "winback":
        return f"Write a short win-back email. Context: {row['context']}"
    if kind == "care":
        return f"Write care instructions. Context: {row['context']}"
    if kind == "sizing":
        return f"Answer this sizing question. Context: {row['context']}"

    raise ValueError(f"unknown kind: {kind}")


def load() -> list[dict]:
    rows = [json.loads(line) for line in SOURCE.read_text().splitlines() if line.strip()]
    return [
        {
            "kind": row["kind"],
            "instruction": instruction_for(row),
            "output": row["output"],
        }
        for row in rows
    ]


def split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Stratified by kind, so the eval set isn't accidentally all subject lines.

    With 51 examples an unstratified split can easily hand every one of the
    four win-back examples to training and leave the eval set unable to say
    anything about them.
    """
    by_kind: dict[str, list[dict]] = {}
    for row in rows:
        by_kind.setdefault(row["kind"], []).append(row)

    rng = random.Random(SEED)
    train: list[dict] = []
    evaluation: list[dict] = []

    for kind, group in sorted(by_kind.items()):
        shuffled = group[:]
        rng.shuffle(shuffled)
        held = max(1, round(len(shuffled) * EVAL_FRACTION))
        evaluation += shuffled[:held]
        train += shuffled[held:]

    rng.shuffle(train)
    return train, evaluation


def write(rows: list[dict], path: Path) -> None:
    with path.open("w") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    {
                        "kind": row["kind"],
                        "messages": [
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": row["instruction"]},
                            {"role": "assistant", "content": row["output"]},
                        ],
                    }
                )
                + "\n"
            )


if __name__ == "__main__":
    rows = load()
    train, evaluation = split(rows)

    write(train, HERE / "data" / "train.jsonl")
    write(evaluation, HERE / "data" / "eval.jsonl")

    print(f"{len(rows)} examples -> {len(train)} train / {len(evaluation)} eval")
    for name, group in (("train", train), ("eval", evaluation)):
        counts: dict[str, int] = {}
        for row in group:
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
        print(f"  {name:6} {counts}")
