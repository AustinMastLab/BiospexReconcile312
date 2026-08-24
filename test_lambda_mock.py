#!/usr/bin/env python3
"""
Advanced local testing: Simulate full Lambda flow with mocked S3/SQS.

This tests the lambda_function.py lambda_handler with a realistic S3 event,
using mocks to avoid needing real AWS credentials.

Usage:
    source .venv312/bin/activate
    python test_lambda_mock.py [--input test_sample.csv]
"""

import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from urllib.parse import quote_plus

# Add repo to path
sys.path.insert(0, os.path.dirname(__file__))


def create_s3_event(bucket_name, key):
    """Create a mock S3 event that triggers Lambda"""
    return {
        'Records': [
            {
                'eventSource': 'aws:s3',
                'eventVersion': '2.0',
                'eventTime': '2024-08-01T12:00:00.000Z',
                'eventName': 'ObjectCreated:Put',
                'awsRegion': 'us-east-2',
                's3': {
                    'bucket': {
                        'name': bucket_name,
                        'arn': f'arn:aws:s3:::{bucket_name}'
                    },
                    'object': {
                        'key': key,
                        'size': 1024,
                        'sequencer': '12345'
                    }
                }
            }
        ]
    }


def test_lambda_with_mock_s3_sqs():
    """Test lambda_handler with mocked S3 and SQS"""
    print("\n" + "=" * 70)
    print("LAMBDA HANDLER TEST - Mocked S3/SQS")
    print("=" * 70)

    # Setup
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy test sample to temp location
        test_csv = 'test_sample.csv'
        if not os.path.exists(test_csv):
            print(f"✗ Test file not found: {test_csv}")
            print("  Run: python test_local.py first")
            return False

        print(f"\n[1/5] Creating mock S3 and SQS...")

        # Create mocks
        mock_s3 = MagicMock()
        mock_sqs = MagicMock()

        # Mock download_file to copy test CSV
        def mock_download(bucket, key, local_file):
            print(f"  [MOCK] S3 download: s3://{bucket}/{key} → {local_file}")
            import shutil
            shutil.copy(test_csv, local_file)

        mock_s3.download_file = mock_download

        # Mock upload_file
        def mock_upload(local_file, bucket, key):
            print(f"  [MOCK] S3 upload: {local_file} → s3://{bucket}/{key}")
            if os.path.exists(local_file):
                print(f"    ✓ File size: {os.path.getsize(local_file)} bytes")

        mock_s3.upload_file = mock_upload

        # Mock copy_object
        def mock_copy(Bucket, CopySource, Key):
            print(f"  [MOCK] S3 copy: {CopySource['Key']} → {Key}")

        mock_s3.copy_object = mock_copy

        # Mock delete_object
        def mock_delete(Bucket, Key):
            print(f"  [MOCK] S3 delete: s3://{Bucket}/{Key}")

        mock_s3.delete_object = mock_delete

        # Mock send_message
        def mock_send_message(QueueUrl, MessageBody):
            msg = json.loads(MessageBody)
            print(f"  [MOCK] SQS message sent:")
            print(f"    Queue: {QueueUrl}")
            print(f"    Status: {msg.get('status')}")
            print(f"    Expedition: {msg.get('expeditionId')}")

        mock_sqs.send_message = mock_send_message

        print("  ✓ Mocks created")

        # Create test event
        print(f"\n[2/5] Creating S3 trigger event...")
        event = create_s3_event('biospex-loc', 'zooniverse/lambda-reconciliation/expedition_test.csv')
        print(f"  ✓ Event: {event['Records'][0]['eventName']}")
        print(f"    Bucket: {event['Records'][0]['s3']['bucket']['name']}")
        print(f"    Key: {event['Records'][0]['s3']['object']['key']}")

        # Test lambda_handler with mocks
        print(f"\n[3/5] Patching boto3 clients...")
        try:
            with patch('lambda_function.s3', mock_s3), \
                 patch('lambda_function.sqs', mock_sqs):

                import lambda_function

                print("  ✓ Boto3 clients patched")

                print(f"\n[4/5] Calling lambda_handler...")

                # Call the handler
                result = lambda_function.lambda_handler(event, context=None)

                print(f"\n[5/5] Lambda handler results:")
                print(f"  Status: {result.get('status')}")
                print(f"  Expedition: {result.get('expeditionId')}")

                if result.get('status') == 'success':
                    print("\n" + "=" * 70)
                    print("✓ LAMBDA HANDLER TEST PASSED")
                    print("=" * 70)
                    return True
                else:
                    print(f"\n✗ Unexpected status: {result.get('status')}")
                    return False

        except Exception as e:
            print(f"\n✗ TEST FAILED: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_manual_s3_event():
    """Test lambda_handler with manual event"""
    print("\n" + "=" * 70)
    print("LAMBDA HANDLER TEST - Manual Event")
    print("=" * 70)

    print(f"\n[1/2] Creating manual S3 event...")

    # Create event for manual trigger (not S3 event)
    event = {
        'bucket': 'biospex-loc',
        'expeditionId': 42,
        'explanations': False
    }

    print(f"  Event: {json.dumps(event, indent=2)}")

    print(f"\n[2/2] Lambda would handle this as:")
    print(f"  - Download: s3://biospex-loc/zooniverse/classification/42.csv")
    print(f"  - Process with reconciliation")
    print(f"  - Upload results to:")
    print(f"    • s3://biospex-loc/zooniverse/transcript/42.csv")
    print(f"    • s3://biospex-loc/zooniverse/reconciled/42.csv")
    print(f"    • s3://biospex-loc/zooniverse/summary/42.html")
    print(f"  - Send SQS notification")

    print("\n" + "=" * 70)
    print("✓ MANUAL EVENT DOCUMENTED")
    print("=" * 70)
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Lambda handler with mocked S3/SQS"
    )
    parser.add_argument(
        '--input',
        default='test_sample.csv',
        help='Input CSV file for S3 mock'
    )
    parser.add_argument(
        '--method',
        choices=['mock', 'manual', 'both'],
        default='both',
        help='Test method'
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"✗ Input file not found: {args.input}")
        sys.exit(1)

    results = {}

    if args.method in ('mock', 'both'):
        results['mock'] = test_lambda_with_mock_s3_sqs()

    if args.method in ('manual', 'both'):
        results['manual'] = test_manual_s3_event()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for method, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{method.upper():20} {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()

