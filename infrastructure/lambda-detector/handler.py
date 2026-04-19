"""AWS Lambda handler for S3 change detection using Rekognition.
Triggered by PUT to snaptrash-raw-incoming bucket.
Compares new image to last analyzed reference in DynamoDB.
If different, copies to analyzed bucket and triggers full Grok analysis.
"""
from __future__ import annotations
import json
import boto3
from urllib.parse import unquote_plus
from datetime import datetime, timezone
from decimal import Decimal

from snaptrash_common.env import settings
# Import existing services (package must be included in Lambda deployment package/layer)
from snaptrash_ingestion.services.grok_vision import analyze_image
from snaptrash_ingestion.services.s3_client import get_object_bytes, copy_object
from snaptrash_ingestion.writers.databricks_writer import insert_scan
from snaptrash_common.schemas import GrokVisionResult, ScanRow

s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('snaptrash-last-analyzed')


def lambda_handler(event, context):
    """Main Lambda entrypoint for S3 event."""
    print("Received S3 event:", json.dumps(event))

    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        restaurant_id = key.split('/')[0] if '/' in key else 'unknown'

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
            return {'status': 'deduplicated', 'similarity': similarity}

        # Different - move to analyzed and run full pipeline
        analyzed_key = f"analyzed/{key}"
        analyzed_url = copy_object(key, analyzed_key, source_bucket=bucket)
        print(f"Copied to analyzed bucket as {analyzed_key}. Running full analysis.")

        # Run existing Grok pipeline (reuse the service)
        s3_url = analyzed_url
        vision_result = analyze_image(s3_url)

        # Build minimal ScanRow (extend with restaurant_id from event)
        row = ScanRow(
            scan_id=f"lambda-{datetime.now(timezone.utc).isoformat()}",
            restaurant_id=restaurant_id,
            zip="92101",  # placeholder; extract from event/metadata in production
            neighborhood="Downtown",
            timestamp=datetime.now(timezone.utc),
            food_kg=0.0,  # populated by enrichment in full flow
            compostable_kg=0.0,
            contaminated_kg=0.0,
            dollar_wastage=0.0,
            co2_kg=0.0,
            plastic_count=0,
            harmful_plastic_count=0,
            pet_kg=0.0,
            ps_count=0,
            food_items_json=json.dumps([item.model_dump() for item in vision_result.food_items]),
            plastic_items_json=json.dumps([item.model_dump() for item in vision_result.plastic_items]),
        )
        insert_scan(row)

        update_last_analyzed(restaurant_id, analyzed_key, new_labels, vision_result, similarity)

        print(f"✅ Full analysis completed for {restaurant_id}, similarity: {similarity}")
        return {'status': 'analyzed', 'similarity': similarity, 'scan_id': row.scan_id}

    return {'status': 'no_records'}


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
