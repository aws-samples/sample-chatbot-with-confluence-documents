#!/bin/bash

# Run Streamlit chatbot UI using project's shared venv
# This script activates the existing venv and runs the Streamlit app

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🤖 Starting Tutorial Chatbot UI"
echo "==============================="

# Activate virtual environment
activate_venv

# Change to the code directory
cd "$(dirname "$0")/.."

# Check and set up AGENTCORE_SSM_PARAMETER_ARN environment variable
if [ -z "$AGENTCORE_SSM_PARAMETER_ARN" ]; then
    echo "🔧 Setting up AgentCore SSM Parameter configuration..."
    
    # Try to get SSM parameter ARN from terraform output
    if [ -f "terraform.tfstate" ] && command -v terraform >/dev/null 2>&1; then
        echo "📋 Getting SSM parameter ARN from Terraform output..."
        SSM_ARN=$(terraform output -raw ssm_parameter_arn 2>/dev/null || echo "")
        
        if [ -n "$SSM_ARN" ]; then
            echo "✅ Found SSM parameter ARN from Terraform: $SSM_ARN"
            use_terraform_arn=$(prompt_yes_no "Use this as default?" "Y")
            if [ "$use_terraform_arn" != "yes" ]; then
                SSM_ARN=""
            fi
        fi
    fi
    
    # If no terraform output or user declined, prompt for manual input
    if [ -z "$SSM_ARN" ]; then
        echo "📝 Please enter the SSM parameter ARN for AgentCore configuration:"
        echo "   Format: arn:aws:ssm:REGION:ACCOUNT:parameter/confluence-bedrock/ENVIRONMENT/config"
        echo "   Example: arn:aws:ssm:us-west-2:123456789012:parameter/confluence-bedrock/dev/config"
        SSM_ARN=$(prompt_input "SSM Parameter ARN" "" "true")
    fi
    
    # Export the environment variable
    export AGENTCORE_SSM_PARAMETER_ARN="$SSM_ARN"
    echo "✅ Set AGENTCORE_SSM_PARAMETER_ARN=$AGENTCORE_SSM_PARAMETER_ARN"
else
    echo "✅ Using existing AGENTCORE_SSM_PARAMETER_ARN=$AGENTCORE_SSM_PARAMETER_ARN"
fi

# Check if AgentCore is deployed (fallback check)
echo "📡 Checking AgentCore deployment..."
if [ ! -f "services/chatbot/.bedrock_agentcore.yaml" ]; then
    echo "⚠️  AgentCore YAML config not found. UI will use SSM parameter configuration."
    echo "   If you see configuration errors, ensure AgentCore is deployed: ./scripts/deploy-chatbot.sh"
fi

# Change to UI directory
cd "ui"

# Run Streamlit app
echo "🚀 Starting Streamlit UI at http://localhost:8501"
echo "   Press Ctrl+C to stop"
echo ""

streamlit run app.py --server.port 8501 --server.address localhost
