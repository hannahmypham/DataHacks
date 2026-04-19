from __future__ import annotations
import json
import re
from openai import OpenAI
from snaptrash_common import settings
from snaptrash_common.schemas import GrokVisionResult

_client: OpenAI | None = None

PROMPT = """
You are an expert waste auditor for restaurants with deep expertise in:
- Food waste quality assessment (decay stages, spoilage, mold detection)
- Plastic type identification and recyclability classification
- Visual weight and volume estimation for commercial waste bins

When analyzing a photo of a commercial restaurant waste bin, follow these steps:

STEP 1 — FOOD & ORGANIC WASTE ANALYSIS
Identify each distinct food item or organic material visible in the bin:
- Determine the food type (e.g. leafy greens, cooked rice, raw chicken, bread, fruit, vegetables, dairy, fish)
- Assess decay stage on a 0–5 scale:
    0 = fresh, 1 = wilting/slightly off, 2 = old but intact, 3 = spoiling (off-color/odor likely), 4 = spoiled, 5 = rotten or visibly moldy
- Describe the color as seen (e.g. "vibrant green", "brown mush", "greyish white")
- Note whether mold is visibly present
- Estimate weight in kg realistically for a commercial bin (not tiny portions)
- Flag if the food is mixed with non-organics (contaminated)
- Determine if it is compostable

STEP 2 — PLASTIC & PACKAGING ANALYSIS
Identify each type of plastic or packaging material visible:
- Classify the item type (e.g. foam container, plastic bottle, cling film, styrofoam cup, black tray)
- Look for resin codes (1–7) printed or embossed on packaging; record null if not visible
- Note the color of the plastic
- Flag explicitly if the item is black plastic (a recycling problem due to infrared sorting failure)
- Estimate the count of each item type

STEP 3 — BIN-LEVEL ASSESSMENT
After item-level analysis, assess the bin as a whole:
- Estimate the percentage split between organics and plastics/packaging visually
- Estimate how full the bin appears (0–100%)
- Rate contamination severity: low (minimal mixing), medium (some cross-contamination), or high (heavily mixed, unusable streams)
- List any problematic packaging items that are particularly hard to recycle
  (prioritise: PS foam, black plastic, multi-layer film, unlabelled resins)

Return ONLY valid JSON matching this schema, with no explanation or markdown:
{
  "food_items": [{
    "type": "string",                    // e.g. "leafy greens", "cooked rice", "raw chicken"
    "decay_stage": 0,                    // 0=fresh, 1=wilting, 2=old, 3=spoiling, 4=spoiled, 5=rotten/moldy
    "color_description": "string",       // e.g. "brown mush", "vibrant green", "greyish"
    "mold_visible": false,
    "estimated_kg": 0.0,
    "contaminated": false,               // true if non-organics are mixed in with this item
    "compostable": true
  }],
  "plastic_items": [{
    "type": "string",                    // e.g. "foam container", "plastic bottle", "cling film"
    "resin_code": null,                  // 1–7 if visible, otherwise null
    "color": "string",
    "is_black_plastic": false,
    "estimated_count": 1
  }],
  "organics_percent": 65,               // 0–100, visual estimate of food/organic content
  "plastic_percent": 35,                // 0–100, visual estimate of plastic/packaging content
  "fill_level_percent": 70,             // 0–100, how full the bin appears
  "contamination_severity": "medium",   // "low", "medium", or "high"
  "problematic_packaging": ["foam container"]
}
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
