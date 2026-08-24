#!/bin/bash

# Biospex Individual Lambda Deployer (Reconcile Mode)

set -e

DIR_NAME=$(basename "$PWD")
FUNCTION_NAME="${FUNCTION_NAME:-BiospexReconcile312}"
REGION="us-east-2"
S3_TEMP_BUCKET="biospex-loc"
ZIP_NAME="reconcile_lambda.zip"
BUILD_DIR=".build_lambda"

echo ">>> Starting deployment for project: $DIR_NAME"
echo ">>> Target Lambda function: $FUNCTION_NAME"

# ------------------------------------------------------------------------------
# STEP 0: Build staged package with dependencies at zip root
# ------------------------------------------------------------------------------
echo "[0/4] Building Lambda package..."

# Resolve interpreter/pip pair from current environment.
if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "Error: python is not available in PATH"
  exit 1
fi

PYTHON_VERSION=$($PYTHON_BIN --version | awk '{print $2}' | cut -d. -f1,2)
echo "Detected Python version: $PYTHON_VERSION"

if [ "$PYTHON_VERSION" != "3.12" ]; then
    echo "Error: Python 3.12 is required for this project."
    exit 1
fi
REQUIREMENTS_FILE="requirements.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "Error: $REQUIREMENTS_FILE not found"
    exit 1
fi

echo "Using: $REQUIREMENTS_FILE"

rm -rf "$BUILD_DIR" "$ZIP_NAME"
mkdir -p "$BUILD_DIR"

# Copy project files except local tooling/artifacts.
rsync -a ./ "$BUILD_DIR"/ \
  --exclude '.git/' \
  --exclude '.idea/' \
  --exclude 'venv/' \
  --exclude '.venv*/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.zip' \
  --exclude 'python/' \
  --exclude "$BUILD_DIR/" \
  --exclude 'deploy.sh' \
  --exclude 'deploy_biospexreconcile.sh'

# Install deps into build root so Lambda can import directly.
"$PYTHON_BIN" -m pip install --upgrade --target "$BUILD_DIR" -r "$REQUIREMENTS_FILE" --quiet

# ------------------------------------------------------------------------------
# STEP 1: Build zip and verify critical deps
# ------------------------------------------------------------------------------
echo "[1/4] Creating $ZIP_NAME..."
(
  cd "$BUILD_DIR"
  zip -r "../$ZIP_NAME" . -x "*/__pycache__/*" "*.pyc" >/dev/null
)

echo "Successfully created $ZIP_NAME"

if unzip -l "$ZIP_NAME" | grep -q "pandas/"; then
  echo "Verified: pandas is in the deployment package"
else
  echo "Error: pandas not found in zip. Deployment will fail."
  exit 1
fi

# ------------------------------------------------------------------------------
# STEP 2: Interactive Upload
# ------------------------------------------------------------------------------
echo ""
read -p "Step 2: Upload $ZIP_NAME to AWS? (y/n): " confirm_upload
if [[ "$confirm_upload" =~ ^[Yy]$ ]]; then
  FILESIZE=$(stat -c%s "$ZIP_NAME")
  if [ "$FILESIZE" -gt 50000000 ]; then
    echo "File size ($FILESIZE bytes) is large (>50MB). Using S3 bridge (bucket: $S3_TEMP_BUCKET)..."
    aws s3 cp "$ZIP_NAME" "s3://$S3_TEMP_BUCKET/$ZIP_NAME"
    aws lambda update-function-code --function-name "$FUNCTION_NAME" \
      --s3-bucket "$S3_TEMP_BUCKET" --s3-key "$ZIP_NAME" --region "$REGION"
    aws s3 rm "s3://$S3_TEMP_BUCKET/$ZIP_NAME"
  else
    aws lambda update-function-code --function-name "$FUNCTION_NAME" \
      --zip-file "fileb://$ZIP_NAME" --region "$REGION"
  fi
else
  echo "Upload skipped. Exiting."
  exit 0
fi

# ------------------------------------------------------------------------------
# STEP 3: Interactive Versioning
# ------------------------------------------------------------------------------
echo ""
read -p "Step 3: Create a new Lambda version? (y/n): " confirm_version
if [[ "$confirm_version" =~ ^[Yy]$ ]]; then
  read -p "Enter version description: " VERSION_DESC
  NEW_VERSION=$(aws lambda publish-version --function-name "$FUNCTION_NAME" \
    --description "$VERSION_DESC" --query 'Version' --output text --region "$REGION")
  echo "Successfully created version: $NEW_VERSION"
else
  NEW_VERSION="\$LATEST"
  echo "Versioning skipped. Using \$LATEST."
fi

# ------------------------------------------------------------------------------
# STEP 4: Interactive Aliases
# ------------------------------------------------------------------------------
echo ""
read -p "Step 4: Update aliases? (loc/dev/prod/all/n): " alias_choice
case "$alias_choice" in
  loc|dev|prod) TARGETS=("$alias_choice") ;;
  all) TARGETS=("loc" "dev" "prod") ;;
  *) echo "Alias update skipped. Done."; exit 0 ;;
esac

for ALIAS in "${TARGETS[@]}"; do
  echo "Updating alias '$ALIAS' to version $NEW_VERSION..."
  aws lambda update-alias --function-name "$FUNCTION_NAME" --name "$ALIAS" \
    --function-version "$NEW_VERSION" --region "$REGION" 2>/dev/null || \
  aws lambda create-alias --function-name "$FUNCTION_NAME" --name "$ALIAS" \
    --function-version "$NEW_VERSION" --region "$REGION"
done

echo ">>> Deployment to $FUNCTION_NAME completed successfully."