#!/bin/bash

# Deploy only the chatbot module
# This script deploys just the AgentCore chatbot without touching ingestion

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🚀 Deploying Chatbot Module Only..."

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Check if terraform.tfvars exists and has required chatbot parameters
if ! validate_terraform_tfvars "true"; then
    echo "❌ terraform.tfvars not found or missing required chatbot parameters."
    echo "Creating minimal terraform.tfvars for chatbot deployment..."
    
    # Prompt for required values
    echo "Please provide the following configuration:"
    AWS_REGION=$(prompt_input "AWS Region" "${AWS_DEFAULT_REGION:-us-east-1}")
    KNOWLEDGE_BASE_TOP_N=$(prompt_input "Number of matching documents to retrieve from Knowledge Base for each chat question" "3")
    # nosemgrep: ai.generic.detect-generic-ai-anthprop
    LLM_MODEL_ID=$(prompt_input "LLM Model ID (e.g., anthropic.claude-3-7-sonnet-20250219-v1:0)" "" "true")
    
    # Create minimal terraform.tfvars
    create_minimal_terraform_tfvars "$AWS_REGION" "$KNOWLEDGE_BASE_TOP_N" "$LLM_MODEL_ID"
    
    echo "✅ Created terraform.tfvars with chatbot configuration"
fi

# Show configuration preview
show_config_preview

# Initialize and plan for chatbot module
terraform_init_and_plan -target=module.chatbot

# Apply with confirmation
echo ""
read -p "🤔 Do you want to apply these changes? (y/N): " confirm
if [[ $confirm =~ ^[Yy]$ ]]; then
    export TF_LOG=DEBUG
    echo "🔄 Applying changes to chatbot module..."
    terraform apply -target=module.chatbot -auto-approve
    
    echo "🔄 Refreshing outputs..."
    terraform apply -refresh-only -auto-approve > /dev/null 2>&1
    
    echo "✅ Chatbot deployment complete!"
else
    echo "❌ Deployment cancelled."
    exit 1
fi
