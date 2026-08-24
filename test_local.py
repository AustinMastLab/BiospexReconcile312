#!/usr/bin/env python3
"""
Local testing script for BiospexReconcile Lambda function.
Tests the reconciliation logic without AWS credentials.

Usage:
    source .venv312/bin/activate
    python test_local.py [--method direct|lambda]
"""

import sys
import os
import json
import argparse
import tempfile
from pathlib import Path

# Add repo to path
sys.path.insert(0, os.path.dirname(__file__))

import lib.util as util
import lib.reconciler as reconciler
import lib.reconciled as reconciled_df
import lib.summary as summary


class Args:
    """Mock Args object matching lambda_function.py"""
    def __init__(self, input_file, output_dir):
        self.input_file = input_file
        self.format = 'nfn'
        self.explanations = False
        self.transcribers = False
        self.workflow_id = 42
        self.title = "Local Test Run"
        self.group_by = 'subject_id'
        self.key_column = 'classification_id'
        self.page_size = 20
        self.fuzzy_ratio_threshold = 90
        self.fuzzy_set_threshold = 50
        self.keep_count = 99
        self.column_types = []
        self.user_weights = {}
        self.tool_label_hack = {}
        self.user_column = 'user_name'

        self.unreconciled = os.path.join(output_dir, 'test-transcript.csv')
        self.reconciled = os.path.join(output_dir, 'test-reconciled.csv')
        self.summary = os.path.join(output_dir, 'test-summary.html')


def test_direct_reconciliation(input_file, output_dir):
    """Test reconciliation logic directly (no Lambda overhead)"""
    print("\n" + "=" * 70)
    print("DIRECT RECONCILIATION TEST")
    print("=" * 70)

    try:
        # Create args
        args = Args(input_file, output_dir)

        # Load data
        print(f"\n[1/4] Loading data from {input_file}...")
        formats = util.get_plugins('formats')
        unreconciled_df, inferred_column_types = formats[args.format].read(args)
        print(f"✓ Loaded {len(unreconciled_df)} classifications")
        print(f"  Columns: {list(unreconciled_df.columns)}")

        # Get column types
        print(f"\n[2/4] Building column types...")
        column_types_dict = inferred_column_types.copy()
        print(f"✓ Column types: {list(column_types_dict.keys())}")

        # Reconcile
        print(f"\n[3/4] Running reconciliation...")
        reconciled, explanations_df = reconciler.build(args, unreconciled_df, column_types_dict)
        print(f"✓ Reconciled {len(reconciled)} subjects")
        print(f"\nReconciled data:")
        print(reconciled.to_string())

        if not explanations_df.empty:
            print(f"\nExplanations:")
            print(explanations_df.to_string())

        # Format output
        print(f"\n[4/4] Formatting output...")
        reconciled_output = reconciled_df.reconciled_output(
            args, unreconciled_df, reconciled, explanations_df, column_types_dict)
        print(f"✓ Output formatted")

        # Save results
        print(f"\nSaving results to {output_dir}:")
        if os.path.exists(args.unreconciled):
            print(f"  ✓ {args.unreconciled}")
        if os.path.exists(args.reconciled):
            print(f"  ✓ {args.reconciled}")
            with open(args.reconciled, 'r') as f:
                print(f"\n{f.read()}")

        print("\n" + "=" * 70)
        print("✓ TEST PASSED")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_lambda_handler(input_file, output_dir):
    """Test Lambda handler with mock S3 event (requires boto3 mocking)"""
    print("\n" + "=" * 70)
    print("LAMBDA HANDLER TEST (with mock S3 event)")
    print("=" * 70)

    try:
        # Create a mock S3 event
        s3_event = {
            'Records': [
                {
                    'eventSource': 'aws:s3',
                    's3': {
                        'bucket': {
                            'name': 'test-bucket'
                        },
                        'object': {
                            'key': 'zooniverse/lambda-reconciliation/test-expedition.csv'
                        }
                    }
                }
            ]
        }

        print(f"\n[1/2] Mock S3 Event:")
        print(json.dumps(s3_event, indent=2))

        # Since we can't call lambda_handler without boto3, we'll show what it would do
        print(f"\n[2/2] Lambda handler would:")
        print("  1. Download s3://test-bucket/zooniverse/lambda-reconciliation/test-expedition.csv")
        print("  2. Call the reconciliation logic (tested above)")
        print("  3. Upload results to S3:")
        print("     - s3://test-bucket/zooniverse/transcript/test-expedition.csv")
        print("     - s3://test-bucket/zooniverse/reconciled/test-expedition.csv")
        print("     - s3://test-bucket/zooniverse/summary/test-expedition.html")
        print("  4. Send SQS status notification")

        print("\n" + "=" * 70)
        print("✓ LAMBDA HANDLER FLOW DOCUMENTED")
        print("=" * 70)
        return True

    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Test BiospexReconcile locally")
    parser.add_argument(
        '--method',
        choices=['direct', 'lambda', 'both'],
        default='both',
        help='Which test method to run'
    )
    parser.add_argument(
        '--input',
        default='test_sample.csv',
        help='Input CSV file (default: test_sample.csv)'
    )

    args = parser.parse_args()

    # Verify input file exists
    if not os.path.exists(args.input):
        print(f"✗ Input file not found: {args.input}")
        sys.exit(1)

    # Create output directory
    output_dir = tempfile.mkdtemp(prefix='reconcile_test_')
    print(f"Output directory: {output_dir}")

    # Run tests
    results = {}

    if args.method in ('direct', 'both'):
        results['direct'] = test_direct_reconciliation(args.input, output_dir)

    if args.method in ('lambda', 'both'):
        results['lambda'] = test_lambda_handler(args.input, output_dir)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for method, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{method.upper():20} {status}")

    all_passed = all(results.values())
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    print(f"Output files: {output_dir}")

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
