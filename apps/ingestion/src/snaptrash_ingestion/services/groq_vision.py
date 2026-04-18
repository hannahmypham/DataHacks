from __future__ import annotations
import json
import re
from groq import Groq
from snaptrash_common import settings
from snaptrash_common.schemas import GroqVisionResult

_client: Groq | None = None

PROMPT = """Analyze this restaurant waste bin image. Return ONLY valid JSON, no prose:
{
  "food_items": [{
    "type": "string",
    "decay_stage": 0,
    "color_description": "string",
    "mold_visible": false,
    "estimated_kg": 0.0,
    "contaminated": false,
    "compostable": true
  }],
  "plastic_items": [{
    "type": "string",
    "resin_code": null,
    "color": "string",
    "is_black_plastic": false,
    "estimated_count": 1
  }]
}
decay_stage: 0=fresh ... 5=spoiled. resin_code: 1-7 if visible else null.
"""


def client() -> Groq:
    global _client
    if _client is None:
        if not settings.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY missing in .env")
        _client = Groq(api_key=settings.GROQ_API_KEY)
    return _client


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def analyze_image(image_url: str) -> GroqVisionResult:
    resp = client().chat.completions.create(
        model=settings.GROQ_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        temperature=0.1,
        max_tokens=2000,
    )
    raw = resp.choices[0].message.content or "{}"
    data = _extract_json(raw)
    return GroqVisionResult(**data)
