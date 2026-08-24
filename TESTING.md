# Local Testing Guide for BiospexReconcile

This guide shows how to test the Lambda function locally without AWS credentials.

## Setup

### 1. Activate your Python 3.12 environment

```bash
source .venv312/bin/activate
```

### 2. Verify dependencies are installed

```bash
pip install -r requirements.txt
```

## Quick Test

Run the complete reconciliation test:

```bash
python test_local.py
```

This will:
1. Load `test_sample.csv` (sample data with 4 classifications)
2. Run the full reconciliation pipeline
3. Generate reconciled CSV and explanations
4. Display the results
5. Save output files to a temporary directory

### Sample Output

```
✓ Loaded 4 classifications
✓ Reconciled 2 subjects

Reconciled data:
                  Name subject_external_id subject_filename
subject_id                                                 
123           John Doe                 123       image1.jpg
124         Jane Smith                 124       image2.jpg
```

## Test Options

### Test only the reconciliation logic (no Lambda wrapper)

```bash
python test_local.py --method direct
```

### Test with mock S3 event (shows Lambda flow)

```bash
python test_local.py --method lambda
```

### Use a custom input file

```bash
python test_local.py --input my_data.csv
```

## Testing with Your Own Data

### 1. Prepare a Zooniverse CSV

The input must be a Zooniverse classification export CSV with these columns:
- `user_name`: Username of the classifier
- `classification_id`: Unique ID for each classification
- `subject_ids`: Semi-colon separated subject IDs (e.g., "123;")
- `workflow_id`: Workflow ID
- `workflow_name`: Workflow name
- `subject_data`: JSON object with subject metadata
- `metadata`: JSON object with started/finished times
- `annotations`: JSON array of annotation objects

### 2. Run the test

```bash
python test_local.py --input your_data.csv
```

### 3. Check the output

Results are saved to a temporary directory shown at the top of the test output:

```
Output directory: /tmp/reconcile_test_abc123def/
  ✓ /tmp/reconcile_test_abc123def/test-reconciled.csv
  ✓ /tmp/reconcile_test_abc123def/test-transcript.csv (if applicable)
```

## Simulating the Full Lambda Flow

### 1. Create a test event JSON

```json
{
  "Records": [
    {
      "eventSource": "aws:s3",
      "s3": {
        "bucket": {
          "name": "biospex-loc",
          "arn": "arn:aws:s3:::biospex-loc"
        },
        "object": {
          "key": "zooniverse/lambda-reconciliation/expedition_123.csv",
          "size": 1024
        }
      },
      "awsRegion": "us-east-2"
    }
  ]
}
```

### 2. Test the Lambda handler (requires mock S3/SQS)

For full Lambda testing with boto3, you would need:
- Mock S3 bucket access
- Mock SQS queue access
- Test data uploaded to S3

This is more complex but the `test_local.py` script covers 95% of what the Lambda does—the reconciliation logic itself.

## Understanding the Test Output

### Reconciliation Results

```
Reconciled data:
                  Name subject_external_id subject_filename
subject_id                                                 
123           John Doe                 123       image1.jpg
124         Jane Smith                 124       image2.jpg
```

This shows:
- `subject_id`: The Zooniverse subject ID
- `Name`: The reconciled transcription
- Other columns: Extracted subject metadata

### Explanations

```
Explanations:
                                             Name
subject_id                                       
123         Exact unanimous match, 2 of 2 records
124         Exact unanimous match, 2 of 2 records
```

This shows how the reconciliation decided on each value:
- "Exact unanimous match" = all classifiers entered the same value
- "Exact match" = majority of classifiers entered the same value
- "Normalized match" = same after removing punctuation/spaces
- "Partial ratio match" = fuzzy match found similar values
- "No match" = could not reconcile the value

## Testing Specific Reconciliation Types

The test CSV is configured to test text reconciliation. To test other types:

### 1. Modify `test_sample.csv`

Edit the annotations to include different task types:

```json
// Select (dropdown/choice)
{"task": "select", "select_label": "Species", "value": "Cat", "label": "Cat"}

// Multiple select (checkboxes)
{"task": "drawing", "value": ["feature1", "feature2"]}

// Box drawing
{"task": "drawing", "tool_label": "Box", "x": 10, "y": 20, "width": 100, "height": 150}

// Point drawing
{"task": "drawing", "tool_label": "Point", "x": 50, "y": 75}
```

### 2. Run the test again

```bash
python test_local.py
```

The reconciler will automatically detect the task type and apply the appropriate reconciliation logic.

## Troubleshooting

### Import Errors

```
ModuleNotFoundError: No module named 'pandas'
```

Make sure the venv is activated:
```bash
source .venv312/bin/activate
```

And dependencies are installed:
```bash
pip install -r requirements.txt
```

### JSON Parse Errors

If you get `json.decoder.JSONDecodeError`, your CSV has improperly formatted JSON. Check that:
- All JSON strings are properly quoted
- All quotes within JSON are escaped (`\"`)
- The CSV uses Python's csv.DictWriter for proper escaping

### Subject Not Found

If reconciliation produces no subjects, check:
- The `subject_ids` column has values (e.g., "123;")
- The `workflow_id` matches between all rows
- The `subject_data` JSON is valid

## Performance Testing

For larger datasets, test with your actual expedition data:

```bash
# Export from Zooniverse, save as classifications.csv
python test_local.py --input classifications.csv
```

The test will show:
- Number of classifications loaded
- Number of subjects reconciled
- Processing time
- Any errors or issues

## Next Steps

Once local testing works:

1. **Commit your test files** (optional):
   ```bash
   git add test_local.py test_sample.csv
   git commit -m "Add local testing utilities"
   ```

2. **Update Lambda function runtime** in AWS Console to Python 3.12

3. **Deploy using `deploy.sh`**:
   ```bash
   ./deploy.sh
   ```

4. **Test with real S3 trigger** by uploading a file to `zooniverse/lambda-reconciliation/` in your S3 bucket

## Questions?

- Check `README.md` for project overview
- See `AGENTS.md` for architecture details
- Review `lambda_function.py` for the actual Lambda handler code
