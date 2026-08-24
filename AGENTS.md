# BiospexReconcile - Developer Guide

## Project Overview
BiospexReconcile is an AWS Lambda function that reconciles crowdsourced Zooniverse classifications into consensus records using a plugin-based reconciliation engine. It processes input CSVs, groups classifications by `subject_id`, applies reconciliation logic per column type, and outputs reconciled CSV, transcripts, and HTML reports to S3 with SQS status callbacks to a Laravel app.

## Architecture & Data Flow
1. Trigger: S3 events (`zooniverse/lambda-reconciliation/`) or SQS/manual invoke.
2. Download: For S3-triggered runs, process the uploaded file directly from `zooniverse/lambda-reconciliation/<expedition>.csv`; for manual/SQS/direct invoke, fetch `zooniverse/classification/<expedition>.csv`.
3. Read: Parse via format plugins (`lib/formats/nfn.py` for Notes from Nature).
4. Reconcile: Group by `subject_id`, apply column-type reconcilers (`lib/column_types/*.py`).
5. Output: Generate reconciled CSV, transcript CSV, and HTML summary report.
6. Upload: Save to S3 prefixes; send status via SQS queue (mapped by bucket prefix).

## Plugin System
- Format plugins live in `lib/formats/*.py` and expose `read(args) -> (DataFrame, column_types_dict)`.
- Column-type reconcilers live in `lib/column_types/*.py` and expose `reconcile(group, args=None) -> (reason, value)`.
- Plugins are dynamically loaded via `lib/util.py:get_plugins(subdir)`; new modules are auto-discovered if placed in the right folder.
- Existing reconciler types: `same`, `text`, `box`, `mean`, `mmr`, `select`.

## Key Files & Project Conventions
- `lambda_function.py`: Lambda handler, `Args` options, orchestration, S3/SQS interactions.
- `lib/reconciler.py`: Main grouping/aggregation loop (`build`) that routes each column to a reconciler plugin.
- `lib/reconciled.py`: Final output shaping used by `lambda_function.py`.
- `lib/merged.py`: Contains `merged_output(...)` helper but is not part of the current Lambda/test execution path.
- `lib/summary.py` + `lib/summary/template.html`: HTML report generation via Jinja2.
- S3 prefixes are fixed constants in `lambda_function.py`: `INPUT_PREFIX`, `RECONCILED_PREFIX`, `TRANSCRIPT_PREFIX`, `SUMMARY_PREFIX`, `EXPLAINED_PREFIX`.
- `QUEUE_MAPPING` in `lambda_function.py` maps bucket prefixes to SQS callback queue URLs.

## Critical Workflows
- Deploy Lambda package with `./deploy.sh` (stages files into `.build_lambda`, installs dependencies into the build root, zips to `reconcile_lambda.zip`, then performs interactive upload/version/alias steps in `us-east-2`).
- `deploy.sh` requires Python 3.12 and uses `requirements.txt`.
- Local validation entry points: `python test_local.py` (core pipeline/direct flow) and `python test_lambda_mock.py` (mocked S3/SQS `lambda_handler` flow).
- Typical local debug path: mirror the `Args` setup from `test_local.py` and run the same plugin/reconciler pipeline used in `lambda_function.py`.

## Integration Notes
- Fuzzy text reconciliation is in `lib/column_types/text.py` (threshold driven by `fuzzy_ratio_threshold`, default 90).
- SQS status callbacks include `expeditionId`, `function` (`BiospexLabelReconciliation`), `status` (`success`/`failed`), `explanations`, and optional `error`.
- S3-triggered files are reconciled first, then copied from `lambda-reconciliation/` to `classification/` and deleted from the original key.
