#!/bin/bash

# Destroy only the ingestion module
# This script destroys just the ingestion pipeline without touching chatbot

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🗑️  Destroying Ingestion Module..."

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Safety confirmation
echo "⚠️  This will destroy the ingestion pipeline and all related resources."
confirm=$(prompt_yes_no "Are you sure you want to continue?" "N")
if [ "$confirm" != "yes" ]; then
    echo "❌ Destruction cancelled."
    exit 1
fi

echo "🔄 Destroying ingestion module..."
terraform destroy -target=module.ingestion -auto-approve

echo "✅ Ingestion module destroyed successfully!"
