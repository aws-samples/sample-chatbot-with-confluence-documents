#!/bin/bash

# Destroy all infrastructure
# This script destroys ALL resources including shared, ingestion, and chatbot

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🗑️  Destroying ALL Infrastructure..."

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Strong safety confirmation for full destruction
echo "⚠️  ⚠️  ⚠️  DANGER: COMPLETE INFRASTRUCTURE DESTRUCTION ⚠️  ⚠️  ⚠️"
echo ""
echo "This will destroy ALL resources including:"
echo "  • AgentCore chatbot and memory"
echo "  • Ingestion pipeline and Lambda"
echo "  • S3 bucket and all stored images"
echo "  • Secrets Manager secrets"
echo "  • SSM parameters and configuration"
echo "  • IAM roles and policies"
echo ""
echo "This action CANNOT be undone!"
echo ""

# Special confirmation for complete destruction
confirm=$(prompt_input "Type 'DESTROY' to confirm complete destruction" "" "true")
if [ "$confirm" != "DESTROY" ]; then
    echo "❌ Destruction cancelled."
    exit 1
fi

echo "🔄 Destroying all infrastructure..."
terraform destroy -auto-approve

echo "✅ All infrastructure destroyed successfully!"
echo "💡 Run './code/scripts/deploy-all.sh' to recreate the infrastructure."
