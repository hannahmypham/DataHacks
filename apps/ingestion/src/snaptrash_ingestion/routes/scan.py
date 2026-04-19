from __future__ import annotations
import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import logging
from time import perf_counter

from snaptrash_common.schemas import ScanRow

from ..services import s3_client, grok_vision, food_analysis, plastic_analysis
from ..writers import databricks_writer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["scan"])


@router.post("")
async def create_scan(
    image: UploadFile = File(...),
    restaurant_id: str = Form(...),
    zip: str = Form(...),
    neighborhood: str = Form(""),
):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "image must be an image/* upload")

    scan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    start_total = perf_counter()

    try:
        raw = await image.read()

        # Stage 1 — upload to S3
        stage_start = perf_counter()
        s3_url = s3_client.upload_image(
            raw, restaurant_id=restaurant_id, ts=int(time.time()), content_type=image.content_type
        )
        logger.info(f"[{scan_id}] S3 upload took {perf_counter() - stage_start:.2f}s (URL: {s3_url})")

        # Stage 2 — Grok Vision (xAI)
        stage_start = perf_counter()
        vision = grok_vision.analyze_image(s3_url)
        logger.info(f"[{scan_id}] Grok Vision took {perf_counter() - stage_start:.2f}s")

        # Stage 3 — food enrichment + Stage 4 — plastic enrichment + sustainability
        stage_start = perf_counter()
        enriched_food = [food_analysis.enrich(f) for f in vision.food_items]
        enriched_plastic = [plastic_analysis.enrich(p) for p in vision.plastic_items]
        sustain_metrics = plastic_analysis.compute_sustainability_metrics(enriched_plastic)
        logger.info(f"[{scan_id}] Enrichment + sustainability metrics took {perf_counter() - stage_start:.2f}s")

        # roll up → ScanRow
        food_kg = sum(f.estimated_kg for f in enriched_food)
        compostable_kg = sum(f.estimated_kg for f in enriched_food if f.compostable and not f.contaminated)
        contaminated_kg = sum(f.estimated_kg for f in enriched_food if f.contaminated)
        dollar_wastage = sum(f.dollar_value or 0.0 for f in enriched_food)
        co2_kg = sum(f.co2_kg or 0.0 for f in enriched_food)
        plastic_count = sum(p.estimated_count for p in enriched_plastic)
        harmful_plastic_count = sum(p.estimated_count for p in enriched_plastic if getattr(p, 'harmful', False))
        pet_kg = sum(p.estimated_kg for p in enriched_plastic if getattr(p, 'polymer_type', None) == "PET")
        ps_count = sum(p.estimated_count for p in enriched_plastic if getattr(p, 'polymer_type', None) == "PS")

        row = ScanRow(
            scan_id=scan_id,
            restaurant_id=restaurant_id,
            zip=zip,
            neighborhood=neighborhood,
            timestamp=now,
            food_kg=food_kg,
            compostable_kg=compostable_kg,
            contaminated_kg=contaminated_kg,
            dollar_wastage=dollar_wastage,
            co2_kg=co2_kg,
            plastic_count=plastic_count,
            harmful_plastic_count=harmful_plastic_count,
            pet_kg=pet_kg,
            ps_count=ps_count,
            total_plastic_kg=sustain_metrics["total_plastic_kg"],
            ban_flag_count=sustain_metrics["ban_flag_count"],
            recyclable_count=sustain_metrics["recyclable_count"],
            food_items_json=json.dumps([f.model_dump() for f in enriched_food]),
            plastic_items_json=json.dumps([p.model_dump() for p in enriched_plastic]),
        )

        # Stage 5 — write to Delta
        stage_start = perf_counter()
        databricks_writer.insert_scan(row)
        logger.info(f"[{scan_id}] Databricks insert took {perf_counter() - stage_start:.2f}s")

        total_time = perf_counter() - start_total
        logger.info(f"[{scan_id}] ✅ Total scan processing: {total_time:.2f}s (SUCCESS)")

        return {
            "scan_id": scan_id,
            "s3_url": s3_url,
            "food_items": [f.model_dump() for f in enriched_food],
            "plastic_items": [p.model_dump() for p in enriched_plastic],
            "totals": row.model_dump(exclude={"food_items_json", "plastic_items_json"}),
        }

    except Exception as e:
        total_time = perf_counter() - start_total
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[{scan_id}] ❌ Scan error after {total_time:.2f}s: {error_msg}")
        logger.error(traceback.format_exc())
        raise HTTPException(500, f"Analysis failed after {total_time:.2f}s: {error_msg}")
