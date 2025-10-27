#!/bin/bash

# Destroy only the chatbot module
# This script destroys just the AgentCore chatbot without touching ingestion

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🗑️  Destroying Chatbot Module..."

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Safety confirmation
echo "⚠️  This will destroy the AgentCore chatbot and all related resources."
confirm=$(prompt_yes_no "Are you sure you want to continue?" "N")
if [ "$confirm" != "yes" ]; then
    echo "❌ Destruction cancelled."
    exit 1
fi

echo "🔄 Destroying chatbot module..."
terraform destroy -target=module.chatbot -auto-approve

echo "✅ Chatbot module destroyed successfully!"
