"""Idempotent bootstrap for new AWS infrastructure: raw/analyzed S3 buckets, DynamoDB last_analyzed table.
Run with: uv run --project apps/ingestion python scripts/bootstrap_aws_infra.py
Uses credentials from .env (same as S3).
"""
from __future__ import annotations
import boto3
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
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
    print("Creating IAM role, Lambda function, and S3 event notification...")

    iam = session.client('iam')
    lambda_client = session.client('lambda')
    role_name = 'snaptrash-lambda-role'
    function_name = 'snaptrash-change-detector'
    handler_path = 'handler.lambda_handler'
    runtime = 'python3.12'

    # Create IAM role for Lambda (idempotent)
    try:
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        print(f"✅ Created IAM role {role_name}")
    except ClientError as e:
        if 'EntityAlreadyExists' in str(e):
            print(f"✅ IAM role {role_name} already exists")
        else:
            print(f"⚠️ Role error: {e}")
            return

    # Attach necessary policies (Lambda basic, S3, Rekognition, DynamoDB, Logs)
    policies = [
        'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole',
        'arn:aws:iam::aws:policy/AmazonS3FullAccess',
        'arn:aws:iam::aws:policy/AmazonRekognitionFullAccess',
        'arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess'
    ]
    for policy_arn in policies:
        try:
            iam.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
        except ClientError:
            pass  # already attached
    print("✅ Attached policies to role")

    # Build deployment package
    import tempfile
    import subprocess
    import shutil
    import zipfile
    with tempfile.TemporaryDirectory() as tmpdir:
        package_dir = f"{tmpdir}/package"
        os.makedirs(package_dir, exist_ok=True)

        # Install dependencies
        subprocess.check_call([
            'pip', 'install', '-t', package_dir, 'openai', 'pillow', 'imagehash', '--no-deps', '--no-compile'
        ])

        # Copy our code
        shutil.copytree('infrastructure/lambda-detector', package_dir, dirs_exist_ok=True)
        shutil.copytree('packages/common', f"{package_dir}/snaptrash_common", dirs_exist_ok=True)
        shutil.copytree('apps/ingestion/src/snaptrash_ingestion/services', f"{package_dir}/snaptrash_ingestion/services", dirs_exist_ok=True)
        shutil.copytree('apps/ingestion/src/snaptrash_ingestion/writers', f"{package_dir}/snaptrash_ingestion/writers", dirs_exist_ok=True)

        # Zip
        zip_path = f"{tmpdir}/lambda.zip"
        with zipfile.ZipFile(zip_path, 'w') as z:
            for root, dirs, files in os.walk(package_dir):
                for file in files:
                    z.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), package_dir))

        with open(zip_path, 'rb') as f:
            zip_content = f.read()

        print("✅ Built Lambda deployment package")

    # Get role ARN
    role = iam.get_role(RoleName=role_name)
    role_arn = role['Role']['Arn']

    # Create Lambda function (idempotent)
    try:
        lambda_client.create_function(
            FunctionName=function_name,
            Runtime=runtime,
            Role=role_arn,
            Handler=handler_path,
            Code={'ZipFile': zip_content},
            Timeout=30,
            MemorySize=512,
            Environment={
                'Variables': {
                    'XAI_API_KEY': settings.XAI_API_KEY or '',
                    'GROK_VISION_MODEL': settings.GROK_VISION_MODEL or 'grok-4.20-0309-reasoning',
                    'S3_BUCKET': settings.S3_BUCKET or 'snaptrash-bins',
                    'DATABRICKS_HOST': settings.DATABRICKS_HOST or '',
                    'DATABRICKS_TOKEN': settings.DATABRICKS_TOKEN or '',
                    'DATABRICKS_WAREHOUSE_ID': settings.DATABRICKS_WAREHOUSE_ID or '',
                    'DATABRICKS_CATALOG': settings.DATABRICKS_CATALOG or 'workspace',
                    'DATABRICKS_SCHEMA': settings.DATABRICKS_SCHEMA or 'snaptrash',
                    'ENV': 'prod',
                    'LOG_LEVEL': 'INFO',
                }
            }
        )
        print(f"✅ Created Lambda function {function_name}")
    except ClientError as e:
        if 'ResourceConflictException' in str(e):
            print(f"✅ Lambda function {function_name} already exists")
            # Update code if needed
            lambda_client.update_function_code(FunctionName=function_name, ZipFile=zip_content)
            print("✅ Updated Lambda code")
        else:
            print(f"⚠️ Lambda error: {e}")

    # Always update configuration with latest env vars (avoids reserved key errors)
    try:
        env_vars = {
            'XAI_API_KEY': settings.XAI_API_KEY or '',
            'GROK_VISION_MODEL': settings.GROK_VISION_MODEL or 'grok-4.20-0309-reasoning',
            'S3_BUCKET': settings.S3_BUCKET or 'snaptrash-bins',
            'DATABRICKS_HOST': settings.DATABRICKS_HOST or '',
            'DATABRICKS_TOKEN': settings.DATABRICKS_TOKEN or '',
            'DATABRICKS_WAREHOUSE_ID': settings.DATABRICKS_WAREHOUSE_ID or '',
            'DATABRICKS_CATALOG': settings.DATABRICKS_CATALOG or 'workspace',
            'DATABRICKS_SCHEMA': settings.DATABRICKS_SCHEMA or 'snaptrash',
            'ENV': 'prod',
            'LOG_LEVEL': 'INFO',
        }
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': env_vars}
        )
        print("✅ Updated Lambda environment variables")
    except ClientError as e:
        print(f"⚠️ Env update warning: {e}")

    # Add S3 invoke permission for the raw bucket
    try:
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId='s3-invoke',
            Action='lambda:InvokeFunction',
            Principal='s3.amazonaws.com',
            SourceArn=f'arn:aws:s3:::{ "snaptrash-raw-incoming" }'
        )
        print("✅ Added S3 invoke permission to Lambda")
    except ClientError as e:
        if 'ResourceConflictException' in str(e):
            print("✅ S3 permission already exists")
        else:
            print(f"⚠️ Permission error: {e}")

    # Add S3 event notification to raw bucket (idempotent)
    # Wait for permission propagation (common cause of validation error)
    print("Waiting 10s for IAM permission propagation...")
    time.sleep(10)
    notification = {
        'LambdaFunctionConfigurations': [{
            'LambdaFunctionArn': lambda_client.get_function(FunctionName=function_name)['Configuration']['FunctionArn'],
            'Events': ['s3:ObjectCreated:*']
        }]
    }
    try:
        s3.put_bucket_notification_configuration(
            Bucket='snaptrash-raw-incoming',
            NotificationConfiguration=notification
        )
        print("✅ Configured S3 event notification to Lambda")
    except ClientError as e:
        print(f"⚠️ Event notification error (may require manual confirmation in console): {e}")

    print("✅ Full AWS Lambda + event notification bootstrap completed")
    print("The Lambda function and event notification should now appear in the AWS Console.")
    print("Test by uploading an image to s3://snaptrash-raw-incoming/test.jpg")
    print("Check CloudWatch Logs for the Lambda and DynamoDB table `snaptrash-last-analyzed` for data.")

if __name__ == "__main__":
    main()
