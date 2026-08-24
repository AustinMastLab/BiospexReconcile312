# BiospexReconcile

## Purpose
Reconciles Zooniverse classification data into a single consensus record for each subject. It uses a custom reconciliation engine written in Python to process complex transcriptions.

## Workflow
1. **Trigger**: 
   - **S3 Event**: Automatically triggered when a new classification CSV is uploaded to `zooniverse/lambda-reconciliation/` (overnight jobs).
   - **Manual/SQS**: Triggered via SQS or direct invocation from the Laravel app for immediate processing.
2. **Download**: Pulls the source classification CSV from S3.
3. **Reconciliation**: Executes the reconciliation logic (in `lib/reconciler.py`):
   - Supports `nfn` (Notes from Nature) format.
   - Groups classifications by `subject_id`.
   - Generates consensus based on fuzzy matching and weight thresholds.
4. **Result Generation**: Produces several output files:
   - `reconciled/`: The final consensus CSV.
   - `transcript/`: A cleaned version of the raw transcriptions.
   - `summary/`: An HTML summary report of the reconciliation process.
   - `explained/`: (Optional) Detailed explanation of how each consensus was reached.
5. **Upload**: Saves the results back to the corresponding S3 prefixes.
6. **Callback**: Sends a status update to the Laravel app via a dedicated SQS queue (mapped by environment/bucket).

## Inputs/Outputs
- **Inputs**:
  - `bucket`: S3 bucket name.
  - `expeditionId`: The ID of the expedition being processed.
  - `explanations`: (Boolean) Whether to generate detailed explanations.
- **Outputs**:
  - S3: Files uploaded to `zooniverse/reconciled/`, `zooniverse/transcript/`, and `zooniverse/summary/`.
  - SQS: Status notification sent to the environment-specific reconciliation update queue.

## Configuration (Environment Variables)
- `EXPLAINED_PREFIX`: S3 prefix for detailed explanation files (Default: `zooniverse/explained/`).
- `INPUT_PREFIX`: S3 prefix where raw classification files are located (Default: `zooniverse/classification/`).
- `RECONCILED_PREFIX`: S3 prefix for final reconciled consensus CSVs (Default: `zooniverse/reconciled/`).
- `SUMMARY_PREFIX`: S3 prefix for HTML summary reports (Default: `zooniverse/summary/`).
- `TRANSCRIPT_PREFIX`: S3 prefix for cleaned transcription files (Default: `zooniverse/transcript/`).

## Related Components
- **Laravel Command**: `App\Console\Commands\SqsListenerReconcileUpdate` (Listens for `success` status).
- **Laravel Job**: `App\Jobs\LabelReconciliationJob` (Processes reconciliation results in the Laravel app).

## Deployment
Use the `deploy.sh` script for interactive deployment to AWS (Region: `us-east-2`). This function requires a Python 3.12 runtime.

### Python Version Support
- **Python 3.12**: Use `requirements.txt`
