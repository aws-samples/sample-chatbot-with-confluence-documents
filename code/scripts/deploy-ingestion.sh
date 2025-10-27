#!/bin/bash

# Deploy only the ingestion module
# This script deploys just the Confluence ingestion Lambda without touching chatbot

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🚀 Deploying Ingestion Module Only..."

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Check if terraform.tfvars exists
if [ ! -f "terraform.tfvars" ]; then
    echo "❌ terraform.tfvars not found. Creating it now..."
    
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
    LLM_MODEL_ID=$(prompt_input "LLM Model ID (e.g., anthropic.claude-3-7-sonnet-20250219-v1:0)" "anthropic.claude-3-7-sonnet-20250219-v1:0")

    # Collect Confluence spaces
    SPACES_JSON=$(collect_confluence_spaces)

    # Create terraform.tfvars file
    create_full_terraform_tfvars "$CONFLUENCE_BASE_URL" "$CONFLUENCE_EMAIL" "$KNOWLEDGE_BASE_ID" "$DATA_SOURCE_ID" "$AWS_REGION" "$KNOWLEDGE_BASE_TOP_N" "$LLM_MODEL_ID" "$SPACES_JSON"

    # Show configuration preview
    show_config_preview

    CONFIRM=$(prompt_yes_no "Continue with this configuration?" "y")
    if [ "$CONFIRM" != "yes" ]; then
        echo "❌ Deployment cancelled."
        exit 1
    fi
fi

# Initialize and plan for ingestion modules
terraform_init_and_plan -target=module.shared -target=module.ingestion

# Apply with confirmation
echo ""
read -p "🤔 Do you want to apply these changes? (y/N): " confirm
if [[ $confirm =~ ^[Yy]$ ]]; then
    echo "🔄 Applying changes to ingestion module..."
    terraform apply -target=module.shared -target=module.ingestion -auto-approve
    
    echo "🔄 Refreshing outputs..."
    terraform apply -refresh-only -auto-approve > /dev/null 2>&1
    
    echo "✅ Ingestion deployment complete!"
else
    echo "❌ Deployment cancelled."
    exit 1
fi
