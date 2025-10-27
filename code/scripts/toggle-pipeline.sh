#!/bin/bash
set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

ACTION="$1"

if [ -z "$ACTION" ]; then
    echo "Usage: $0 [enable|disable|status]"
    echo ""
    echo "Commands:"
    echo "  enable  - Enable automatic ingestion (every minute)"
    echo "  disable - Disable automatic ingestion"
    echo "  status  - Show current pipeline status"
    exit 1
fi

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Get AWS region from Terraform configuration
cd "$(dirname "$0")/.."
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "${AWS_DEFAULT_REGION:-us-east-1}")

# Get EventBridge rule name from Terraform outputs
RULE_NAME=$(terraform output -raw eventbridge_rule_name 2>/dev/null)

if [ $? -ne 0 ] || [ -z "$RULE_NAME" ]; then
    echo "❌ Could not get EventBridge rule name from Terraform outputs."
    echo "Make sure you're in the correct directory and Terraform has been applied."
    exit 1
fi

case "$ACTION" in
    "enable")
        echo "🚀 Enabling automatic ingestion pipeline..."
        aws events enable-rule --name "$RULE_NAME" --region "$AWS_REGION"
        echo "✅ Pipeline enabled! Ingestion will run every minute."
        echo "📋 Rule: $RULE_NAME"
        ;;
    
    "disable")
        echo "⏸️  Disabling automatic ingestion pipeline..."
        aws events disable-rule --name "$RULE_NAME" --region "$AWS_REGION"
        echo "✅ Pipeline disabled."
        echo "📋 Rule: $RULE_NAME"
        ;;
    
    "status")
        echo "📊 Pipeline Status"
        echo "=================="
        
        RULE_INFO=$(aws events describe-rule --name "$RULE_NAME" --region "$AWS_REGION")
        STATE=$(echo "$RULE_INFO" | jq -r '.State')
        SCHEDULE=$(echo "$RULE_INFO" | jq -r '.ScheduleExpression')
        
        echo "📋 Rule: $RULE_NAME"
        echo "📋 Status: $STATE"
        echo "📋 Schedule: $SCHEDULE"
        
        if [ "$STATE" = "ENABLED" ]; then
            echo "✅ Pipeline is currently ACTIVE"
        else
            echo "⏸️  Pipeline is currently DISABLED"
        fi
        ;;
    
    *)
        echo "❌ Invalid action: $ACTION"
        echo "Valid actions: enable, disable, status"
        exit 1
        ;;
esac
