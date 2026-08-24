#!/usr/bin/env python3
import json
import boto3
import os
import traceback
from urllib.parse import unquote_plus

# Boto3 clients
s3 = boto3.client('s3')
sqs = boto3.client('sqs')

# Import your existing lib modules
import lib.util as util
import lib.reconciler as reconciler
import lib.reconciled as reconciled_df
import lib.summary as summary

# Fixed prefixes
INPUT_PREFIX      = 'zooniverse/classification/'
RECONCILED_PREFIX = 'zooniverse/reconciled/'
TRANSCRIPT_PREFIX = 'zooniverse/transcript/'
SUMMARY_PREFIX    = 'zooniverse/summary/'
EXPLAINED_PREFIX  = 'zooniverse/explained/'
LAMBDA_INPUT_DIR  = 'zooniverse/lambda-reconciliation/'

# Map bucket → updates queue URL
QUEUE_MAPPING = {
    'biospex-loc': 'https://sqs.us-east-2.amazonaws.com/147899039648/loc-reconcile-update',
    'biospex-dev': 'https://sqs.us-east-2.amazonaws.com/147899039648/dev-reconcile-update',
    'biospex-app': 'https://sqs.us-east-2.amazonaws.com/147899039648/prod-reconcile-update',
}

def get_updates_queue_url(bucket: str) -> str:
    for prefix, url in QUEUE_MAPPING.items():
        if bucket.startswith(prefix):
            return url
    raise ValueError(f"Unknown bucket: {bucket}")

def send_status(queue_url: str, expedition_id: str, status: str, explanations: bool, error: str = None):
    message_body = {
        "expeditionId": expedition_id,
        "function": "BiospexLabelReconciliation",
        "status": status,
        "explanations": explanations
    }
    if error:
        message_body["error"] = error

    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))
    print(f"Sent {status} → {queue_url}")

def lambda_handler(event, context):
    try:
        bucket = None
        expedition_id = None
        explanations = False
        source = None
        original_key = None

        # CASE 1: S3 Event Trigger (overnight download)
        if 'Records' in event and event['Records'][0].get('eventSource') == 'aws:s3':
            s3_event = event['Records'][0]['s3']
            bucket = s3_event['bucket']['name']
            key = unquote_plus(s3_event['object']['key'])
            original_key = key

            if not key.startswith(LAMBDA_INPUT_DIR):
                print(f"Ignoring non-reconciliation file: {key}")
                return {"status": "ignored"}

            filename = os.path.basename(key)
            if not filename.endswith('.csv'):
                print(f"Ignoring non-CSV: {key}")
                return {"status": "ignored"}

            expedition_id = filename.replace('.csv', '')
            explanations = False
            source = 's3'
            input_key = key  # Use the file directly from lamda-reconciliation

        # CASE 2: Manual / Web Trigger (SQS, direct invoke, etc.)
        else:
            if 'Records' in event and 'body' in event['Records'][0]:
                body = json.loads(event['Records'][0]['body'])
            else:
                body = event

            bucket = body['bucket']
            expedition_id = str(body['expeditionId'])
            explanations = body.get('explanations', False)
            source = 'manual'
            input_key = f"{INPUT_PREFIX}{expedition_id}.csv"

        # Resolve updates queue
        updates_queue_url = get_updates_queue_url(bucket)

        print(f"Starting reconciliation for expedition {expedition_id} "
              f"(explanations={explanations}, source={source}) in bucket {bucket}")

        local_input = f"/tmp/{expedition_id}.csv"
        local_base = f"/tmp/{expedition_id}"

        # Download source file
        print(f"Downloading s3://{bucket}/{input_key} → {local_input}")
        s3.download_file(bucket, input_key, local_input)

        # Define output paths
        upload_targets = {}
        if explanations:
            local_reconciled = f"{local_base}-explained.csv"
            upload_targets[local_reconciled] = f"{EXPLAINED_PREFIX}{expedition_id}.csv"
        else:
            local_unreconciled = f"{local_base}-transcript.csv"
            local_reconciled   = f"{local_base}-reconciled.csv"
            local_summary      = f"{local_base}-summary.html"

            upload_targets[local_unreconciled] = f"{TRANSCRIPT_PREFIX}{expedition_id}.csv"
            upload_targets[local_reconciled]   = f"{RECONCILED_PREFIX}{expedition_id}.csv"
            upload_targets[local_summary]      = f"{SUMMARY_PREFIX}{expedition_id}.html"

        # Fake Args object
        class Args:
            def __init__(self):
                self.input_file = local_input
                self.format = 'nfn'
                self.explanations = explanations
                self.transcribers = False
                self.workflow_id = None
                self.title = f"Expedition {expedition_id}"
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

                if explanations:
                    self.reconciled = local_reconciled
                    self.unreconciled = None
                    self.summary = None
                else:
                    self.unreconciled = local_unreconciled
                    self.reconciled = local_reconciled
                    self.summary = local_summary

        args = Args()

        # === Reconciliation logic ===
        formats = util.get_plugins('formats')
        unreconciled_df, inferred_column_types = formats[args.format].read(args)

        if unreconciled_df.empty:
            raise ValueError("No classifications found")

        column_types_dict = get_column_types(args, inferred_column_types)
        validate_columns(args, column_types_dict, unreconciled_df)

        if args.unreconciled:
            unreconciled_df.to_csv(args.unreconciled, index=False)

        reconciled, explanations_df = reconciler.build(args, unreconciled_df, column_types_dict)

        if args.reconciled:
            reconciled = reconciled_df.reconciled_output(
                args, unreconciled_df, reconciled, explanations_df, column_types_dict)

        if args.summary:
            summary.report(args, unreconciled_df, reconciled, explanations_df, column_types_dict)

        # Upload results
        for local_path, s3_key in upload_targets.items():
            if os.path.exists(local_path):
                print(f"Uploading {local_path} → s3://{bucket}/{s3_key}")
                s3.upload_file(local_path, bucket, s3_key)

        # Only move file if triggered by S3 (overnight job)
        if source == 's3' and original_key:
            dest_key = f"{INPUT_PREFIX}{expedition_id}.csv"
            print(f"Moving s3://{bucket}/{original_key} → s3://{bucket}/{dest_key}")
            s3.copy_object(Bucket=bucket, CopySource={'Bucket': bucket, 'Key': original_key}, Key=dest_key)
            s3.delete_object(Bucket=bucket, Key=original_key)
            print("File moved to classification/ and deleted from lamda-reconciliation/")

        # Success
        send_status(updates_queue_url, expedition_id, "success", explanations)
        print("Reconciliation completed successfully")
        return {"status": "success", "expeditionId": expedition_id}

    except Exception as e:
        error_trace = traceback.format_exc()
        print("FATAL ERROR:", error_trace)

        try:
            exp_id = expedition_id if 'expedition_id' in locals() else "unknown"
            queue = updates_queue_url if 'updates_queue_url' in locals() else ""
            expl = explanations if 'explanations' in locals() else False
            if queue:
                send_status(queue, exp_id, "failed", expl, str(e))
        except:
            pass
        raise

# Helper functions (unchanged)
def get_column_types(args, column_types):
    last = util.last_column_type(column_types)
    if args.column_types:
        for arg in args.column_types:
            for option in arg.split(','):
                if not option.strip(): continue
                name, col_type = [x.strip() for x in option.split(':', 1)]
                order = column_types[name]['order'] if name in column_types else last + util.COLUMN_ADD
                last = order
                column_types[name] = {'type': col_type, 'order': order, 'name': name}
    return column_types

def validate_columns(args, column_types, unreconciled):
    plugins = util.get_plugins('column_types')
    plugin_types = list(plugins.keys())
    error = False
    for column, ct in column_types.items():
        if column not in unreconciled.columns:
            error = True
            print(f'ERROR: Missing column "{column}"')
        if ct['type'] not in plugin_types:
            error = True
            print(f'ERROR: Invalid column type "{ct["type"]}"')
    for col in [args.group_by, args.key_column]:
        if col not in unreconciled.columns:
            error = True
            print(f'ERROR: Required column missing: "{col}"')
    if error:
        print("Valid column types:", plugin_types)
        print("Columns in file:", list(unreconciled.columns))
        raise ValueError("Column validation failed")