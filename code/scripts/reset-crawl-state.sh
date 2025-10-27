#!/bin/bash

# Reset crawl state script for Confluence to Bedrock Knowledge Base Integration
# This script resets the SSM parameter that tracks crawl state, forcing a full re-crawl

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🔄 Confluence to Bedrock - Reset Crawl State"
echo "============================================="

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Check if Terraform is initialized
if [[ ! -d ".terraform" ]]; then
    echo "❌ Error: Terraform not initialized. Run ./scripts/deploy-all.sh first"
    exit 1
fi

# Get Terraform outputs
echo "📋 Getting deployment information..."

TERRAFORM_OUTPUT=$(terraform output -json 2>/dev/null)
if [[ $? -ne 0 ]]; then
    echo "❌ Error: Failed to get Terraform outputs. Make sure the infrastructure is deployed."
    exit 1
fi

PYTHON_CMD=$(detect_python)
AWS_REGION=$(echo "$TERRAFORM_OUTPUT" | "$PYTHON_CMD" -c "import sys, json; data=json.load(sys.stdin); print(data['aws_region']['value'])")
SSM_PARAMETER=$(echo "$TERRAFORM_OUTPUT" | "$PYTHON_CMD" -c "import sys, json; data=json.load(sys.stdin); print(data['ssm_parameter_name']['value'])")
KMS_KEY_ID=$(echo "$TERRAFORM_OUTPUT" | "$PYTHON_CMD" -c "import sys, json; data=json.load(sys.stdin); print(data['kms_ssm_key_id']['value'])")

if [[ -z "$AWS_REGION" || -z "$SSM_PARAMETER" || -z "$KMS_KEY_ID" ]]; then
    echo "❌ Error: Could not retrieve AWS region, SSM parameter name, or KMS key ID from Terraform outputs"
    exit 1
fi

CRAWL_STATE_PARAMETER="${SSM_PARAMETER}-crawl-state"

echo "📍 AWS Region: $AWS_REGION"
echo "📝 Crawl State Parameter: $CRAWL_STATE_PARAMETER"
echo ""

# Confirmation prompt
echo "⚠️  WARNING: This will reset all crawl state tracking!"
echo "   This means the next ingestion will process ALL pages in ALL spaces,"
echo "   not just the ones that have changed since the last crawl."
echo ""

confirm=$(prompt_yes_no "Are you sure you want to continue?" "N")
if [ "$confirm" != "yes" ]; then
    echo "❌ Operation cancelled"
    exit 0
fi

# Reset the SSM parameter
echo "🔄 Resetting crawl state..."

aws ssm put-parameter \
    --region "$AWS_REGION" \
    --name "$CRAWL_STATE_PARAMETER" \
    --value "{}" \
    --type "SecureString" \
    --key-id "$KMS_KEY_ID" \
    --overwrite

if [[ $? -eq 0 ]]; then
    echo "✅ Crawl state has been reset successfully!"
    echo ""
    echo "📋 Next steps:"
    echo "   • The next ingestion run will process all pages in all configured spaces"
    echo "   • You can trigger ingestion manually or wait for the scheduled run"
    echo "   • Use './scripts/toggle-pipeline.sh status' to check the pipeline status"
else
    echo "❌ Failed to reset crawl state"
    exit 1
fi
