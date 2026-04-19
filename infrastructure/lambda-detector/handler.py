"""AWS Lambda handler for S3 change detection using Rekognition.
Triggered by PUT to snaptrash-raw-incoming bucket.
Compares new image to last analyzed reference in DynamoDB.
If different, copies to analyzed bucket and triggers full Grok analysis.
"""
from __future__ import annotations
import json
import boto3
import urllib.request
from urllib.parse import unquote_plus, unquote
from datetime import datetime, timezone
from decimal import Decimal

from snaptrash_common.env import settings
# Import existing services (package must be included in Lambda deployment package/layer)
from snaptrash_ingestion.services.grok_vision import analyze_image
from snaptrash_ingestion.services.s3_client import get_object_bytes, copy_object
from snaptrash_ingestion.services import food_analysis, plastic_analysis
from snaptrash_ingestion.writers.databricks_writer import insert_scan
from snaptrash_common.schemas import GrokVisionResult, ScanRow
import uuid

s3 = boto3.client('s3')


def _trigger_aggregation() -> None:
    """
    Fire-and-forget: submit 02_aggregations notebook to Databricks after scan write.
    Does NOT wait for result — Lambda returns immediately.
    Errors are logged but never raised (scan already saved; insights will catch up).
    """
    try:
        host  = settings.DATABRICKS_HOST.rstrip("/")
        token = settings.DATABRICKS_TOKEN
        user  = settings.DATABRICKS_USER
        nb_path = f"/Users/{user}/snaptrash/02_aggregations"
        body = json.dumps({
            "run_name": "snaptrash-agg-scan-trigger",
            "tasks": [{
                "task_key": "02_aggregations",
                "notebook_task": {"notebook_path": nb_path, "source": "WORKSPACE"},
            }],
        }).encode()
        req = urllib.request.Request(
            f"{host}/api/2.2/jobs/runs/submit",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            print(f"  Aggregation triggered: run_id={resp.get('run_id')}")
    except Exception as e:
        print(f"  Warning: could not trigger aggregation ({e}) — insights will update on next schedule")
rekognition = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('snaptrash-last-analyzed')


def lambda_handler(event, context):
    """Main Lambda entrypoint for S3 event."""
    print("Received S3 event:", json.dumps(event))

    results = []
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])

        # Key format: {restaurant_id}/{zip}/{neighborhood_urlencoded}/{ts}.ext
        # Falls back gracefully for old-format keys: {restaurant_id}/{ts}.ext
        parts = key.split('/')
        restaurant_id = parts[0] if len(parts) >= 1 else 'unknown'
        zip_code = parts[1] if len(parts) >= 4 else '00000'
        neighborhood = unquote(parts[2]) if len(parts) >= 4 else 'unknown'

        # Get image bytes using shared helper
        image_bytes = get_object_bytes(key, bucket=bucket)

        # Get or create last analyzed reference
        last = get_last_analyzed(restaurant_id)

        # Use Rekognition to get labels for comparison
        new_labels = get_rekognition_labels(image_bytes)
        similarity = calculate_similarity(new_labels, last.get('last_labels', {}) if last else {})

        if similarity > 0.85 and last:  # Tune threshold based on testing
            print(f"Image similar to last analyzed for {restaurant_id} (score: {similarity}). Deleting.")
            s3.delete_object(Bucket=bucket, Key=key)
            update_last_analyzed(restaurant_id, key, new_labels, None, similarity)
            results.append({'status': 'deduplicated', 'similarity': similarity})
            continue

        # Different - copy to snaptrash-bins (NEVER write back to source bucket
        # snaptrash-raw-incoming, which is the Lambda trigger — doing so causes recursion).
        analyzed_key = f"analyzed/{key}"
        ANALYZED_BUCKET = "snaptrash-bins"
        copy_object(key, analyzed_key, source_bucket=bucket, dest_bucket=ANALYZED_BUCKET)
        print(f"Copied to {ANALYZED_BUCKET} as {analyzed_key}. Running full analysis.")

        # Presign URL so Grok can fetch from private bucket (must use ANALYZED_BUCKET)
        s3_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": ANALYZED_BUCKET, "Key": analyzed_key},
            ExpiresIn=3600,
        )
        vision_result = analyze_image(s3_url)

        # Stage 3+4 — full enrichment + sustainability metrics (matches /scan route)
        enriched_food = [food_analysis.enrich(f) for f in vision_result.food_items]
        enriched_plastic = [plastic_analysis.enrich(p) for p in vision_result.plastic_items]
        sustain_metrics = plastic_analysis.compute_sustainability_metrics(enriched_plastic)

        # Roll up metrics (exact match to scan.py)
        food_kg = sum(f.estimated_kg for f in enriched_food)
        compostable_kg = sum(f.estimated_kg for f in enriched_food if f.compostable and not f.contaminated)
        contaminated_kg = sum(f.estimated_kg for f in enriched_food if f.contaminated)
        dollar_wastage = sum(f.dollar_value or 0.0 for f in enriched_food)
        co2_kg = sum(f.co2_kg or 0.0 for f in enriched_food)
        plastic_count = sum(p.estimated_count for p in enriched_plastic)
        harmful_plastic_count = sum(p.estimated_count for p in enriched_plastic if getattr(p, 'harmful', False))
        pet_kg = sum(p.estimated_kg for p in enriched_plastic if getattr(p, 'polymer_type', None) == "PET")
        ps_count = sum(p.estimated_count for p in enriched_plastic if getattr(p, 'polymer_type', None) == "PS")

        scan_id = str(uuid.uuid4())
        row = ScanRow(
            scan_id=scan_id,
            restaurant_id=restaurant_id,
            zip=zip_code,
            neighborhood=neighborhood,
            timestamp=datetime.now(timezone.utc),
            food_kg=food_kg,
            compostable_kg=compostable_kg,
            contaminated_kg=contaminated_kg,
            dollar_wastage=dollar_wastage,
            co2_kg=co2_kg,
            plastic_count=plastic_count,
            harmful_plastic_count=harmful_plastic_count,
            pet_kg=pet_kg,
            ps_count=ps_count,
            total_plastic_kg=sustain_metrics.get("total_plastic_kg", 0.0),
            ban_flag_count=sustain_metrics.get("ban_flag_count", 0),
            recyclable_count=sustain_metrics.get("recyclable_count", 0),
            food_items_json=json.dumps([f.model_dump() for f in enriched_food]),
            plastic_items_json=json.dumps([p.model_dump() for p in enriched_plastic]),
        )
        insert_scan(row)
        _trigger_aggregation()  # fire-and-forget: 02_aggregations runs async

        update_last_analyzed(restaurant_id, analyzed_key, new_labels, vision_result, similarity)
        print(f"✅ Full analysis completed for {restaurant_id}, similarity: {similarity}")
        results.append({'status': 'analyzed', 'similarity': similarity, 'scan_id': row.scan_id})

    return results if results else {'status': 'no_records'}


def get_last_analyzed(restaurant_id: str) -> dict:
    """Retrieve last analyzed reference from DynamoDB."""
    response = table.get_item(Key={'restaurant_id': restaurant_id})
    return response.get('Item', {})


def update_last_analyzed(restaurant_id: str, s3_key: str, labels: dict, analysis: GrokVisionResult | None, similarity: float):
    """Update DynamoDB with new reference."""
    item = {
        'restaurant_id': restaurant_id,
        'last_s3_key': s3_key,
        'last_labels': labels,
        'last_similarity': Decimal(str(similarity)),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    if analysis:
        item['last_analysis'] = analysis.model_dump()
    table.put_item(Item=item)


def get_rekognition_labels(image_bytes: bytes) -> dict:
    """Get labels and confidence from Rekognition."""
    response = rekognition.detect_labels(
        Image={'Bytes': image_bytes},
        MaxLabels=20,
        MinConfidence=60
    )
    return {label['Name']: label['Confidence'] for label in response['Labels']}


def calculate_similarity(new_labels: dict, last_labels: dict) -> float:
    """Simple label overlap score (can be improved with vector similarity)."""
    if not last_labels:
        return 0.0
    common = len(set(new_labels.keys()) & set(last_labels.keys()))
    total = len(set(new_labels.keys()) | set(last_labels.keys()))
    return common / total if total > 0 else 0.0


if __name__ == "__main__":
    # For local testing with SAM or pytest
    test_event = {
        "Records": [{
            "s3": {
                "bucket": {"name": "snaptrash-raw-incoming"},
                "object": {"key": "rest_001/1745 000000.jpg"}
            }
        }]
    }
    print(lambda_handler(test_event, None))
