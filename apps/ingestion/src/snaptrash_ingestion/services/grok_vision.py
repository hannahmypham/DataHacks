from __future__ import annotations
import json
import re
from openai import OpenAI
from snaptrash_common import settings
from snaptrash_common.schemas import GrokVisionResult

_client: OpenAI | None = None

PROMPT = """You are an expert waste auditor for restaurants. Analyze this photo of a commercial waste bin.

Return ONLY valid JSON matching this schema, no explanation:

{
  "food_items": [{
    "type": "string",                    // e.g. "leafy greens", "cooked rice", "raw chicken", "bread", "fruit", "vegetables", "dairy", "fish"
    "decay_stage": 0,                    // 0=fresh, 1=wilting, 2=old, 3=spoiling, 4=spoiled, 5=rotten/moldy
    "color_description": "string",       // e.g. "brown mush", "vibrant green", "greyish"
    "mold_visible": false,
    "estimated_kg": 0.0,                 // best visual estimate, be realistic for a bin
    "contaminated": false,               // plastic, glass, or other non-organics mixed in
    "compostable": true
  }],
  "plastic_items": [{
    "type": "string",                    // e.g. "foam container", "plastic bottle", "cling film", "styrofoam cup", "black tray"
    "resin_code": null,                  // 1-7 if visible on packaging, otherwise null
    "color": "string",
    "is_black_plastic": false,
    "estimated_count": 1
  }],
  "organics_percent": 65,                // 0-100, visual estimate of food/organic content
  "plastic_percent": 35,                 // 0-100, visual estimate of plastic/packaging content
  "fill_level_percent": 70,              // 0-100, how full the bin appears
  "contamination_severity": "medium",    // "low", "medium", or "high"
  "problematic_packaging": ["foam container"]  // list of items that are likely problematic (PS foam, black plastic, etc.)
}

Focus especially on:
- Distinguishing food/organics from plastic/packaging contamination
- Detecting black plastic, styrofoam, and film which are hard to recycle
- Noticing if food looks spoiled or has visible mold
- Realistic weight estimates for a restaurant waste bin (not tiny portions)
"""


def client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.XAI_API_KEY:
            raise RuntimeError("XAI_API_KEY missing in .env")
        _client = OpenAI(api_key=settings.XAI_API_KEY, base_url="https://api.x.ai/v1")
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


def analyze_image(image_url: str) -> GrokVisionResult:
    """Analyze waste bin image using Grok (xAI) Vision model.

    Returns structured waste intelligence including food/plastic breakdown,
    contamination signals, fill level, and problematic packaging detection.
    """
    try:
        resp = client().chat.completions.create(
            model=settings.GROK_VISION_MODEL,
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
        return GrokVisionResult(**data)

    except Exception as e:
        print(f"❌ Grok Vision error: {type(e).__name__}: {e}")
        # Return minimal valid response as fallback
        return GrokVisionResult(
            food_items=[],
            plastic_items=[],
            organics_percent=50,
            plastic_percent=50,
            fill_level_percent=60,
            contamination_severity="medium",
            problematic_packaging=[]
        )
