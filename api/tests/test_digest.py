"""
Tests for the weekly digest.

None of these need a model. The summary sentence is written by one, but the
figures and the actions are not, and those are the part that would quietly go
out wrong to someone's inbox every Monday.
"""

import pytest

from app import digest
from app.config import settings

FACTS = {
    "week": {
        "revenue": 6120.0,
        "revenue_change": -60.4,
        "orders": 60,
        "aov": 102.0,
        "units": 97,
    },
    "month": {"repeat_rate": 32.5},
    "top": [{"title": "Cargo Pant — Black", "revenue": 1425.0}],
    "running_out": [
        {"product": "Washed Tee — Charcoal", "size": "M", "inventory": 3, "days_to_stockout": 2},
        {"product": "Boxy Tee — White", "size": "S", "inventory": 4, "days_to_stockout": 5},
    ],
    "sold_out": [{"product": "Boxy Tee — Black", "size": "M"}],
    "alerts": [{"phrase": "tell me if anything drops below 5", "count": 4}],
    "top_complaint": {"theme": "sizing", "count": 7},
}


def test_the_figures_read_as_sentences_not_a_table():
    block = digest.figures_block(FACTS)

    assert "£6,120" in block
    assert "-60.4% on the week before" in block
    assert "AOV £102.00" in block
    assert "Cargo Pant — Black" in block


def test_a_missing_comparison_says_so_rather_than_showing_nothing():
    facts = {**FACTS, "week": {**FACTS["week"], "revenue_change": None}}
    assert "no comparison" in digest.figures_block(facts)


def test_sold_out_and_running_out_are_separate_lines():
    """They need different responses — one is lost sales, one is a warning."""
    block = digest.figures_block(FACTS)

    assert "sold out: Boxy Tee — Black M" in block
    assert "running out: Washed Tee — Charcoal M (2d)" in block


def test_reviews_are_left_out_when_there_are_none():
    """A synced Shopify store has no reviews, so the line shouldn't appear."""
    block = digest.figures_block({**FACTS, "top_complaint": None})
    assert "complaint" not in block


def test_the_text_holds_together_without_a_summary():
    """The model is best effort — no sentence shouldn't mean a broken email."""
    text = digest.as_text(
        {
            "store": "noszn",
            "summary": "",
            "figures": digest.figures_block(FACTS),
            "actions": ["Reorder Washed Tee — Charcoal M"],
        }
    )

    assert text.startswith("noszn — last 7 days")
    assert "£6,120" in text
    assert "worth doing:" in text
    assert "- Reorder Washed Tee — Charcoal M" in text
    # No stray blank section where the summary would have been.
    assert "\n\n\n" not in text


def test_the_summary_goes_above_the_figures_when_there_is_one():
    text = digest.as_text(
        {
            "store": "noszn",
            "summary": "quiet week, and the tees need reordering.",
            "figures": "revenue £1",
            "actions": [],
        }
    )
    assert text.index("quiet week") < text.index("revenue £1")


def test_no_actions_means_no_empty_heading():
    text = digest.as_text(
        {"store": "noszn", "summary": "all fine.", "figures": "revenue £1", "actions": []}
    )
    assert "worth doing" not in text


def test_sending_without_smtp_configured_explains_what_to_set(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    monkeypatch.setattr(settings, "digest_to", "")

    with pytest.raises(ValueError, match="SMTP_HOST"):
        digest.send_email({"store": "noszn", "summary": "", "figures": "", "actions": []})
