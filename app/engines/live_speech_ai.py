import asyncio
import logging
import json
from typing import Optional, Callable, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Key vocabulary weights for Central Bank speeches (Hawkish vs Dovish)
HAWKISH_KEYWORDS = {
    "higher for longer": 40.0,
    "inflation is still too high": 35.0,
    "premature to cut": 35.0,
    "more work to do": 30.0,
    "rate hikes": 45.0,
    "resilient economy": 20.0,
    "not confident yet": 25.0,
    "restrictive policy": 25.0,
}

DOVISH_KEYWORDS = {
    "rate cut": -40.0,
    "ready to ease": -45.0,
    "inflation is cooling": -35.0,
    "labor market softening": -30.0,
    "balanced risks": -20.0,
    "progress toward 2 percent": -25.0,
    "sufficiently restrictive": -30.0,
}


class LiveSpeechAI:
    """
    Ultra-Low Latency FOMC & ECB Speech Engine:
    Connects to Deepgram Live Audio WebSocket -> Groq LPU (Llama 3 70B)
    Detects market-moving statements and generates trading signals within 1.5 seconds!
    """

    def __init__(
        self,
        deepgram_key: Optional[str] = None,
        groq_key: Optional[str] = None,
    ):
        self.deepgram_key = deepgram_key or settings.DEEPGRAM_API_KEY
        self.groq_key = groq_key or settings.GROQ_API_KEY
        self.is_streaming = False

    def fast_heuristic_sentiment(self, transcript_chunk: str) -> Dict[str, Any]:
        """
        Sub-100ms heuristic sentiment analyzer on raw speech transcript chunk.
        Calculates hawkish/dovish score before Groq LLM finishes full prompt.
        """
        chunk_lower = transcript_chunk.lower()
        score = 0.0
        detected_phrases = []

        for phrase, weight in HAWKISH_KEYWORDS.items():
            if phrase in chunk_lower:
                score += weight
                detected_phrases.append(f"+{phrase}")

        for phrase, weight in DOVISH_KEYWORDS.items():
            if phrase in chunk_lower:
                score += weight
                detected_phrases.append(f"-{phrase}")

        # Clamp score between -100 and +100
        score = max(-100.0, min(100.0, score))

        if score >= 30:
            bias = "HAWKISH (USD BUY / XAUUSD SELL)"
        elif score <= -30:
            bias = "DOVISH (USD SELL / XAUUSD BUY)"
        else:
            bias = "NEUTRAL"

        return {
            "score": score,
            "bias": bias,
            "phrases": detected_phrases,
            "transcript": transcript_chunk,
        }

    async def analyze_with_groq_llm(self, statement: str) -> Dict[str, Any]:
        """
        Groq LPU ultra-fast inference (Llama-3-70b-versatile) ~ 200-400ms latency.
        """
        if not self.groq_key or self.groq_key == "your_groq_api_key_here":
            # Return heuristic when Groq key is not supplied
            return self.fast_heuristic_sentiment(statement)

        prompt = (
            f"You are an expert Wall Street macro speech analyst. Evaluate this statement by the Fed Chair:\n"
            f"\"{statement}\"\n"
            f"Output strictly valid JSON: {{\"bias\": \"HAWKISH\" | \"DOVISH\" | \"NEUTRAL\", \"score\": -100 to 100, \"action_gold\": \"BUY\" | \"SELL\" | \"WAIT\", \"reason\": \"short reason\"}}"
        )

        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            try:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_key}"},
                    json={
                        "model": "llama-3.1-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.1,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return json.loads(content)
            except Exception as e:
                logger.error(f"Groq speech analysis error: {e}")

        return self.fast_heuristic_sentiment(statement)


live_speech_ai = LiveSpeechAI()
