#!/bin/bash
set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🚀 Confluence-Bedrock Terraform Deployment"
echo "=========================================="

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Detect Python command
PYTHON_CMD=$(detect_python)

# Collect configuration parameters
echo ""
echo "📋 Configuration Setup"
echo "====================="

CONFLUENCE_BASE_URL=$(prompt_input "Confluence base URL (e.g., https://company.atlassian.net)" "" "true")
CONFLUENCE_EMAIL=$(prompt_input "Confluence email address" "" "true")

echo ""
echo "📋 AWS Configuration"
echo "==================="

KNOWLEDGE_BASE_ID=$(prompt_input "Bedrock Knowledge Base ID" "" "true")
DATA_SOURCE_ID=$(prompt_input "Bedrock Knowledge Base Data Source ID" "" "true")
AWS_REGION=$(prompt_input "AWS Region" "${AWS_DEFAULT_REGION:-us-east-1}")
KNOWLEDGE_BASE_TOP_N=$(prompt_input "Number of matching documents to retrieve from Knowledge Base for each chat question" "3")
# nosemgrep: ai.generic.detect-generic-ai-anthprop
LLM_MODEL_ID=$(prompt_input "LLM Model ID (e.g., anthropic.claude-3-7-sonnet-20250219-v1:0 or us.anthropic.claude-3-7-sonnet-20250219-v1:0)" "" "true")

# Collect Confluence spaces
SPACES_JSON=$(collect_confluence_spaces)

# Create terraform.tfvars file
create_full_terraform_tfvars "$CONFLUENCE_BASE_URL" "$CONFLUENCE_EMAIL" "$KNOWLEDGE_BASE_ID" "$DATA_SOURCE_ID" "$AWS_REGION" "$KNOWLEDGE_BASE_TOP_N" "$LLM_MODEL_ID" "$SPACES_JSON"

# Show configuration preview
show_config_preview

# Confirm deployment
CONFIRM=$(prompt_yes_no "Deploy with this configuration?" "y")
if [ "$CONFIRM" != "yes" ]; then
    echo "❌ Deployment cancelled."
    exit 1
fi

# Deploy with Terraform
echo ""
echo "🚀 Deploying Terraform infrastructure..."

# Initialize and plan
terraform_init_and_plan

# Apply with confirmation
terraform_apply_with_confirmation "" "true"

echo "✅ Deployment completed successfully!"
echo ""
echo "Next steps:"
echo "1. Run './code/scripts/upload-token.sh' to configure Confluence API token"
echo "2. Run './code/scripts/toggle-pipeline.sh enable' to start automatic ingestion"
echo "3. Test the chatbot API using the function URL from the deployment output"
