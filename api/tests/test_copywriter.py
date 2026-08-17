"""
Tests for the copy generator's model routing.

The fine-tuned adapter is off by default and easy to forget about, so these
check the two things that would break quietly: that the flag actually sends the
copy somewhere else, and that when it does, the adapter gets the short brief it
was trained on rather than the long one written for a general model.

No model runs here — routing is a settings question, not a generation one.
"""

import pytest

from app import copywriter
from app.config import settings
from app.llm import llm


@pytest.fixture(autouse=True)
def clear_writer_cache():
    """writer() is cached, so each test has to start from a clean one."""
    copywriter.writer.cache_clear()
    yield
    copywriter.writer.cache_clear()


def test_copy_uses_the_main_model_by_default(monkeypatch):
    monkeypatch.setattr(settings, "copy_llm_base_url", "")

    assert copywriter.using_tuned() is False
    # The shared client itself, not a copy of it — otherwise the usage
    # accounting wired up at startup wouldn't apply.
    assert copywriter.writer() is llm


def test_the_flag_points_copy_at_the_adapter(monkeypatch):
    monkeypatch.setattr(settings, "copy_llm_base_url", "http://localhost:8100/v1")
    monkeypatch.setattr(settings, "copy_llm_model", "noszn-voice")

    writer = copywriter.writer()

    assert copywriter.using_tuned() is True
    assert writer is not llm
    assert writer.base_url == "http://localhost:8100/v1"
    assert writer.model == "noszn-voice"


def test_the_adapters_tokens_still_get_counted(monkeypatch):
    """
    The separate client has to report usage the same way the shared one does,
    or the tuned model's spend silently vanishes from the cost breakdown.
    """
    monkeypatch.setattr(settings, "copy_llm_base_url", "http://localhost:8100/v1")
    monkeypatch.setattr(llm, "on_usage", lambda **kw: None)

    assert copywriter.writer().on_usage is llm.on_usage


def test_the_adapter_gets_the_brief_it_was_trained_on(monkeypatch):
    """
    Sending the adapter the long TONE spec is what produced copy with a stray
    Arabic word in it — it had never seen a prompt that shape. The short brief
    is the one in finetune/data/train.jsonl.
    """
    monkeypatch.setattr(settings, "copy_llm_base_url", "http://localhost:8100/v1")

    assert "Never use marketing language" in copywriter.TUNED_TONE
    # The long brief's giveaways: a banned-word list and a bulleted voice spec.
    assert "game-changer" not in copywriter.TUNED_TONE
    assert len(copywriter.TUNED_TONE) < len(copywriter.TONE)
