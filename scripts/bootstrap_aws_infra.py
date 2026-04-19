"""Idempotent bootstrap for new AWS infrastructure: raw/analyzed S3 buckets, DynamoDB last_analyzed table.
Run with: uv run --project apps/ingestion python scripts/bootstrap_aws_infra.py
Uses credentials from .env (same as S3).
"""
from __future__ import annotations
import boto3
from botocore.exceptions import ClientError
from snaptrash_common.env import settings
from snaptrash_common import env

def main():
    print(f"target region: {settings.AWS_REGION}")
    session = boto3.Session(
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )
    s3 = session.client('s3')
    dynamodb = session.client('dynamodb')

    # Create buckets (idempotent)
    for bucket in ['snaptrash-raw-incoming', 'snaptrash-analyzed']:
        try:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
            )
            print(f"✅ Created bucket {bucket}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'BucketAlreadyExists' or e.response['Error']['Code'] == 'BucketAlreadyOwnedByYou':
                print(f"✅ Bucket {bucket} already exists")
            else:
                print(f"⚠️ Error creating {bucket}: {e}")

    # Create DynamoDB table for last analyzed reference (idempotent)
    table_name = 'snaptrash-last-analyzed'
    try:
        dynamodb.create_table(
            TableName=table_name,
            KeySchema=[{'AttributeName': 'restaurant_id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'restaurant_id', 'AttributeType': 'S'}],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        print(f"✅ Created DynamoDB table {table_name}")
        # Wait for table to be active (in production use waiter)
        print("Waiting for table to become active...")
        waiter = dynamodb.get_waiter('table_exists')
        waiter.wait(TableName=table_name)
        print(f"✅ Table {table_name} is active")
    except ClientError as e:
        if 'ResourceInUseException' in str(e):
            print(f"✅ DynamoDB table {table_name} already exists")
        else:
            print(f"⚠️ Error creating table: {e}")

    print("✅ AWS infrastructure bootstrap completed")
    print("Next: Create Lambda function and S3 event notification (manual or via SAM).")
    print("Update .env with any new bucket names if needed.")

if __name__ == "__main__":
    main()
