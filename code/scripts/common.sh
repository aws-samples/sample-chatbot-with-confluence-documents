#!/bin/bash
# Shared utility functions for deployment scripts

# Function to activate virtual environment
activate_venv() {
    # Get the actual directory where common.sh is located
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "$(dirname "${BASH_SOURCE[0]}")")"
    
    # If script_dir is relative, make it absolute
    if [[ "$script_dir" != /* ]]; then
        script_dir="$(pwd)/$script_dir"
    fi
    
    local code_dir="$(dirname "$script_dir")"
    local venv_path="$code_dir/.venv"
    
    # Handle case where script is run from different directories
    if [ ! -d "$venv_path" ]; then
        # Try alternative path resolution
        local current_dir="$(pwd)"
        if [[ "$current_dir" == *"/tutorial-chatbot" ]]; then
            venv_path="$current_dir/code/.venv"
        elif [[ "$current_dir" == *"/code" ]]; then
            venv_path="$current_dir/.venv"
        fi
    fi
    
    if [ -d "$venv_path" ]; then
        echo "🐍 Activating virtual environment..."
        source "$venv_path/bin/activate"
    else
        echo "❌ Virtual environment not found at $venv_path"
        echo "Please run './scripts/setup.sh' first to create the virtual environment."
        exit 1
    fi
}

# Function to detect Python command
detect_python() {
    if command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
        echo "python"
    else
        echo "❌ Python 3.6+ is required but not found"
        exit 1
    fi
}

# Function to prompt for input with validation
prompt_input() {
    local prompt="$1"
    local default="$2"
    local required="${3:-false}"
    local value
    
    while true; do
        if [ -n "$default" ]; then
            read -p "$prompt [$default]: " value
            value="${value:-$default}"
        else
            read -p "$prompt: " value
        fi
        
        # Check if value is required and empty
        if [ "$required" = "true" ] && [ -z "$value" ]; then
            echo "This field is required. Please enter a value."
            continue
        fi
        
        echo "$value"
        break
    done
}

# Function to prompt for yes/no
prompt_yes_no() {
    local prompt="$1"
    local default="$2"
    local value
    
    while true; do
        if [ -n "$default" ]; then
            read -p "$prompt [y/N]: " value
            value="${value:-$default}"
        else
            read -p "$prompt [y/n]: " value
        fi
        
        case "$value" in
            [Yy]|[Yy][Ee][Ss]) echo "yes"; break ;;
            [Nn]|[Nn][Oo]) echo "no"; break ;;
            *) echo "Please answer yes or no." ;;
        esac
    done
}

# Function to check AWS CLI configuration
check_aws_cli() {
    if ! aws sts get-caller-identity > /dev/null 2>&1; then
        echo "❌ AWS CLI not configured. Please run 'aws configure' first."
        exit 1
    fi
}

# Function to collect Confluence spaces
collect_confluence_spaces() {
    local spaces_json="[]"
    local add_spaces
    
    echo "" >&2
    echo "📋 Confluence Spaces" >&2
    echo "===================" >&2
    
    add_spaces=$(prompt_yes_no "Add Confluence spaces to sync?" "y")
    
    if [ "$add_spaces" = "yes" ]; then
        local spaces_array=()
        while true; do
            local space_key
            space_key=$(prompt_input "Enter Confluence space key (or press Enter to finish)")
            if [ -z "$space_key" ]; then
                break
            fi
            spaces_array+=("$space_key")
        done
        
        if [ ${#spaces_array[@]} -gt 0 ]; then
            # Use jq to properly construct JSON array with escaped strings
            spaces_json=$(printf '%s\n' "${spaces_array[@]}" | jq -R -s -c 'split("\n")[:-1]')
        fi
    fi
    
    # Only output the JSON to stdout
    printf '%s' "$spaces_json"
}

# Function to create terraform.tfvars with all parameters
create_full_terraform_tfvars() {
    local confluence_base_url="$1"
    local confluence_email="$2"
    local knowledge_base_id="$3"
    local data_source_id="$4"
    local aws_region="$5"
    local knowledge_base_top_n="$6"
    local llm_model_id="$7"
    local spaces_json="$8"
    
    # Transform spaces JSON to the required format
    local transformed_spaces
    if [ "$spaces_json" = "[]" ] || [ -z "$spaces_json" ]; then
        transformed_spaces="[]"
    else
        transformed_spaces=$(echo "$spaces_json" | jq -c '[.[] | {"key": .}]')
    fi
    
    cat > ./terraform.tfvars <<EOF
confluence_base_url = "$confluence_base_url"
confluence_email = "$confluence_email"
knowledge_base_id = "$knowledge_base_id"
data_source_id = "$data_source_id"
aws_region = "$aws_region"
knowledge_base_top_n = $knowledge_base_top_n
llm_model_id = "$llm_model_id"
confluence_spaces = $transformed_spaces
EOF
}

# Function to create minimal terraform.tfvars for chatbot-only deployment
create_minimal_terraform_tfvars() {
    local aws_region="$1"
    local knowledge_base_top_n="$2"
    local llm_model_id="$3"
    
    cat > ./terraform.tfvars <<EOF
# Minimal configuration for chatbot deployment
project_name = "confluence-bedrock"
environment = "dev"
aws_region = "$aws_region"
knowledge_base_top_n = $knowledge_base_top_n
llm_model_id = "$llm_model_id"
EOF
}

# Function to run terraform init and plan
terraform_init_and_plan() {
    local target_modules="$@"
    
    echo "🔧 Initializing Terraform..."
    terraform init
    
    echo "📦 Planning deployment..."
    if [ -n "$target_modules" ]; then
        terraform plan $target_modules
    else
        terraform plan
    fi
}

# Function to apply terraform with confirmation
terraform_apply_with_confirmation() {
    local target_modules="$1"
    local auto_approve="${2:-false}"
    
    if [ "$auto_approve" != "true" ]; then
        echo ""
        local confirm
        confirm=$(prompt_yes_no "Apply the Terraform plan?" "y")
        if [ "$confirm" != "yes" ]; then
            echo "❌ Deployment cancelled."
            exit 1
        fi
    fi
    
    export TF_LOG=DEBUG
    if [ -n "$target_modules" ]; then
        terraform apply "$target_modules" -auto-approve
    else
        terraform apply -auto-approve
    fi
}

# Function to validate required terraform.tfvars parameters
validate_terraform_tfvars() {
    local required_for_chatbot="$1"
    
    if [ ! -f "terraform.tfvars" ]; then
        return 1
    fi
    
    # Check for chatbot-specific required parameters
    if [ "$required_for_chatbot" = "true" ]; then
        if ! grep -q "knowledge_base_top_n" terraform.tfvars || ! grep -q "llm_model_id" terraform.tfvars; then
            return 1
        fi
    fi
    
    return 0
}

# Function to show configuration preview
show_config_preview() {
    echo ""
    echo "📋 Configuration Preview"
    echo "======================="
    if [ -f "./terraform.tfvars" ]; then
        cat ./terraform.tfvars
    else
        echo "❌ terraform.tfvars file not found"
    fi
    echo ""
}

# Function to prompt for secure input (like API tokens)
prompt_secure_input() {
    local prompt="$1"
    local show_input="${2:-false}"
    local value
    
    if [ "$show_input" = "true" ]; then
        # For tokens where user wants to see input for verification
        read -p "$prompt: " value
    else
        # For truly sensitive input (hidden)
        read -s -p "$prompt: " value
        echo ""  # Add newline after hidden input
    fi
    
    echo "$value"
}

# Function to find and change to code directory (for scripts that might be run from different locations)
find_and_change_to_code_directory() {
    local current_dir="$(pwd)"
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Try different possible locations for the code directory
    local possible_dirs=(
        "$script_dir/.."           # scripts/../ (normal case)
        "$current_dir"             # current directory
        "$current_dir/code"        # current/code/
        "$(dirname "$script_dir")" # parent of scripts directory
    )
    
    for dir in "${possible_dirs[@]}"; do
        if [ -f "$dir/main.tf" ] && [ -f "$dir/variables.tf" ]; then
            cd "$dir"
            return 0
        fi
    done
    
    echo "❌ Could not find code directory with Terraform files (main.tf, variables.tf)"
    echo "Please run this script from the project root or code directory."
    exit 1
}
