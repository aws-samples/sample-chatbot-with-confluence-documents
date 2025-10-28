#!/bin/bash
set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🔧 Confluence Parameters Reconfiguration"
echo "This script will reconfigure Confluence parameters in the SSM parameter store."
echo "Press Enter to keep current values."
echo

# Activate virtual environment
activate_venv

# Check AWS CLI configuration
check_aws_cli

# Change to the code directory
cd "$(dirname "$0")/.."

# Detect Python command
PYTHON_CMD=$(detect_python)

# Get AWS region from Terraform outputs
AWS_REGION=$(terraform output -raw aws_region 2>/dev/null || echo "us-west-2")
SSM_PARAMETER=$(terraform output -raw ssm_parameter_name 2>/dev/null || echo "/confluence-bedrock/dev/config")
KMS_KEY_ID=$(terraform output -raw kms_ssm_key_id 2>/dev/null)

if [[ -z "$KMS_KEY_ID" ]]; then
    echo "❌ Error: Could not retrieve KMS key ID from Terraform outputs"
    exit 1
fi

echo "Using AWS region: ${AWS_REGION}"
echo "Using SSM parameter: ${SSM_PARAMETER}"
echo "Using KMS key: ${KMS_KEY_ID}"
echo

# Get current configuration
echo "Getting current configuration..."
CURRENT_CONFIG=$(aws ssm get-parameter --name "$SSM_PARAMETER" --region "$AWS_REGION" --with-decryption --query 'Parameter.Value' --output text)

# Extract current values
CURRENT_CONFLUENCE_BASE_URL=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('confluence_base_url', ''))")
CURRENT_CONFLUENCE_EMAIL=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('confluence_email', ''))")
CURRENT_KNOWLEDGE_BASE_ID=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('knowledge_base_id', ''))")
CURRENT_DATA_SOURCE_ID=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('data_source_id', ''))")
CURRENT_KNOWLEDGE_BASE_TOP_N=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('knowledge_base_top_n', '3'))")
CURRENT_LLM_MODEL_ID=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('llm_model_id', ''))")
CURRENT_AWS_REGION=$("$PYTHON_CMD" -c "import json; print(json.loads('$CURRENT_CONFIG').get('aws_region', 'us-west-2'))")
CURRENT_SPACES_JSON=$("$PYTHON_CMD" -c "import json; print(json.dumps(json.loads('$CURRENT_CONFIG').get('confluence_spaces', [])))")

echo "Current configuration:"
echo "  Confluence Base URL: $CURRENT_CONFLUENCE_BASE_URL"
echo "  Confluence Email: $CURRENT_CONFLUENCE_EMAIL"
echo "  Knowledge Base ID: $CURRENT_KNOWLEDGE_BASE_ID"
echo "  Data Source ID: $CURRENT_DATA_SOURCE_ID"
echo "  Knowledge Base Top N: $CURRENT_KNOWLEDGE_BASE_TOP_N"
echo "  LLM Model ID: $CURRENT_LLM_MODEL_ID"
echo "  AWS Region: $CURRENT_AWS_REGION"
echo "  Confluence Spaces: $CURRENT_SPACES_JSON"
echo

# Prompt for configuration values
echo "📋 Configuration Setup (press Enter to keep current value)"
echo "=========================================================="
echo

CONFLUENCE_BASE_URL=$(prompt_input "Confluence Base URL" "$CURRENT_CONFLUENCE_BASE_URL")
CONFLUENCE_EMAIL=$(prompt_input "Confluence Email" "$CURRENT_CONFLUENCE_EMAIL")
KNOWLEDGE_BASE_ID=$(prompt_input "Knowledge Base ID" "$CURRENT_KNOWLEDGE_BASE_ID")
DATA_SOURCE_ID=$(prompt_input "Data Source ID" "$CURRENT_DATA_SOURCE_ID")
AWS_REGION=$(prompt_input "AWS Region" "$CURRENT_AWS_REGION")
KNOWLEDGE_BASE_TOP_N=$(prompt_input "Number of matching documents to retrieve from Knowledge Base" "$CURRENT_KNOWLEDGE_BASE_TOP_N")
LLM_MODEL_ID=$(prompt_input "LLM Model ID (e.g., us.anthropic.claude-sonnet-4-5-20250929-v1:0)" "$CURRENT_LLM_MODEL_ID")

echo
echo "📋 Confluence Spaces"
echo "==================="

RECONFIGURE_SPACES=$(prompt_yes_no "Reconfigure Confluence spaces? (press N to keep current spaces)" "n")

if [ "$RECONFIGURE_SPACES" = "yes" ]; then
    SPACES_JSON="[]"
    while true; do
        echo
        SPACE_KEY=$(prompt_input "Enter Confluence Space Key (or press Enter to finish)")
        if [ -z "$SPACE_KEY" ]; then
            break
        fi
        
        SPACE_NAME=$(prompt_input "Enter Space Name (optional)")
        
        # Add space to JSON array
        if [ -z "$SPACE_NAME" ]; then
            SPACE_ENTRY="{\"key\": \"$SPACE_KEY\"}"
        else
            SPACE_ENTRY="{\"key\": \"$SPACE_KEY\", \"name\": \"$SPACE_NAME\"}"
        fi
        
        SPACES_JSON=$("$PYTHON_CMD" -c "
import json
spaces = json.loads('$SPACES_JSON')
new_space = json.loads('$SPACE_ENTRY')
spaces.append(new_space)
print(json.dumps(spaces))
")
        
        echo "✅ Added space: $SPACE_KEY"
    done
    
    if [ "$SPACES_JSON" = "[]" ]; then
        echo "❌ No spaces configured. Keeping current spaces."
        SPACES_JSON="$CURRENT_SPACES_JSON"
    fi
else
    echo "Keeping current spaces."
    SPACES_JSON="$CURRENT_SPACES_JSON"
fi

echo
echo "Configured spaces:"
echo "$SPACES_JSON" | "$PYTHON_CMD" -m json.tool

# Build new configuration
NEW_CONFIG=$("$PYTHON_CMD" -c "
import json
config = json.loads('$CURRENT_CONFIG')
config['confluence_base_url'] = '$CONFLUENCE_BASE_URL'
config['confluence_email'] = '$CONFLUENCE_EMAIL'
config['knowledge_base_id'] = '$KNOWLEDGE_BASE_ID'
config['data_source_id'] = '$DATA_SOURCE_ID'
config['aws_region'] = '$AWS_REGION'
config['knowledge_base_top_n'] = int('$KNOWLEDGE_BASE_TOP_N')
config['llm_model_id'] = '$LLM_MODEL_ID'
config['confluence_spaces'] = json.loads('$SPACES_JSON')
print(json.dumps(config))
")

echo
echo "📋 New Configuration Preview"
echo "==========================="
echo "$NEW_CONFIG" | "$PYTHON_CMD" -m json.tool

echo
CONFIRM=$(prompt_yes_no "Update SSM parameter with this configuration?" "y")
if [ "$CONFIRM" != "yes" ]; then
    echo "Configuration not updated."
    exit 0
fi

# Update SSM parameter
echo "Updating SSM parameter..."
aws ssm put-parameter \
    --name "$SSM_PARAMETER" \
    --value "$NEW_CONFIG" \
    --type "SecureString" \
    --key-id "$KMS_KEY_ID" \
    --overwrite \
    --region "$AWS_REGION"

echo "✅ Configuration updated successfully!"
echo
echo "📋 Next steps:"
echo "1. Upload your Confluence API token: ./code/scripts/upload-token.sh"
echo "2. Enable the ingestion pipeline: /code/scripts/toggle-pipeline.sh enable"
echo "3. Test the ingestion: aws lambda invoke --function-name \$(terraform output -raw ingestion_lambda_function_name) --region $AWS_REGION --payload '{}' /tmp/test.json && cat /tmp/test.json"
