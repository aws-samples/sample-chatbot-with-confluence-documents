#!/bin/bash
set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🔐 Confluence API Token Upload"
echo "=============================="

# Find and change to code directory
find_and_change_to_code_directory

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Get AWS region from terraform.tfvars or default
if [ -f "terraform.tfvars" ]; then
    AWS_REGION=$(grep "aws_region" terraform.tfvars | cut -d'"' -f2)
fi
AWS_REGION=${AWS_REGION:-us-west-2}

# Get Secrets Manager ARN from Terraform outputs
SM_ARN=$(terraform output -raw secrets_manager_arn 2>/dev/null)

if [ -z "$SM_ARN" ] || [ "$SM_ARN" = "None" ]; then
    echo "❌ Could not find Confluence secret ARN. Make sure Terraform is deployed and you're in the code directory."
    exit 1
fi

echo "📋 Secret ARN: $SM_ARN"
echo ""

# Prompt for API token
echo "Please enter your Confluence API token:"
echo "(You can create one at: https://id.atlassian.com/manage-profile/security/api-tokens)"
echo ""
echo "⚠️  Note: Your input will be visible on screen for verification"

API_TOKEN=$(prompt_secure_input "Confluence API Token" "true")

if [ -z "$API_TOKEN" ]; then
    echo "❌ API token cannot be empty."
    exit 1
fi

# Update secret
echo "🔧 Uploading token to AWS Secrets Manager..."

SECRET_VALUE=$(cat <<EOF
{
    "token": "$API_TOKEN"
}
EOF
)

if aws secretsmanager update-secret \
    --secret-id "$SM_ARN" \
    --secret-string "$SECRET_VALUE" \
    --region "$AWS_REGION" \
    > /dev/null 2>&1; then
    echo "✅ Confluence API token uploaded successfully!"
else
    echo "❌ Failed to upload token. Trying with detailed error output:"
    aws secretsmanager update-secret \
        --secret-id "$SM_ARN" \
        --secret-string "$SECRET_VALUE" \
        --region "$AWS_REGION"
    exit 1
fi

echo ""
echo "The token is now securely stored in AWS Secrets Manager."
echo "You can now run the ingestion pipeline."
