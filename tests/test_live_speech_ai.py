import pytest
from app.engines.live_speech_ai import live_speech_ai


def test_speech_heuristic_hawkish():
    text = "Inflation is still too high and we are prepared for higher for longer rates."
    result = live_speech_ai.fast_heuristic_sentiment(text)
    assert result["score"] >= 40.0
    assert "HAWKISH" in result["bias"]


def test_speech_heuristic_dovish():
    text = "We are observing labor market softening and the committee is ready to ease policy with a rate cut."
    result = live_speech_ai.fast_heuristic_sentiment(text)
    assert result["score"] <= -40.0
    assert "DOVISH" in result["bias"]
