#!/bin/bash
set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🔧 Setting up Terraform Python Environment"
echo "========================================="

# Detect Python command
PYTHON_CMD=$(detect_python)
echo "✅ Using Python command: $PYTHON_CMD"

# Check if Terraform is installed
if ! command -v terraform &> /dev/null; then
    echo "📦 Installing Terraform..."
    
    # Detect OS and install Terraform
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew tap hashicorp/tap
            brew install hashicorp/tap/terraform
        else
            echo "❌ Homebrew not found. Please install Terraform manually from https://terraform.io/downloads"
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
        echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
        sudo apt update && sudo apt install terraform
    else
        echo "❌ Unsupported OS. Please install Terraform manually from https://terraform.io/downloads"
        exit 1
    fi
else
    echo "✅ Terraform already installed"
fi

echo "✅ Terraform version: $(terraform --version | head -n1)"

# Navigate to code directory
cd "$(dirname "$0")/.."

# Create virtual environment
echo ""
echo "🐍 Creating Python virtual environment..."
"$PYTHON_CMD" -m venv .venv

# Activate virtual environment and install dependencies
echo "📦 Installing Python dependencies..."
source .venv/bin/activate
"$PYTHON_CMD" -m pip install --upgrade pip
"$PYTHON_CMD" -m pip install -r requirements.txt

echo ""
echo "✅ Setup completed successfully!"
echo ""
