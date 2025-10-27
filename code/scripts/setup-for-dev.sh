#!/bin/bash
set -e

# Development environment setup script
# This script sets up additional development tools including security scanning (ASH)

echo "🛠️  Setting up Development Environment"
echo "======================================"

# Get the script directory
SCRIPT_DIR="$(dirname "$0")"

# Run base setup first
echo ""
echo "📦 Running base setup..."
"$SCRIPT_DIR/setup.sh"

echo ""
echo "🔍 Setting up development tools..."

# Check for container runtime (Finch or Docker) for ASH security scanning
echo ""
echo "🐳 Checking for container runtime (required for ASH security scanning)..."
if command -v finch &> /dev/null; then
    echo "✅ Finch found: $(finch --version 2>&1 | head -n1)"
    
    # Check if Finch VM is initialized
    VM_STATUS=$(finch vm status 2>&1)
    if [[ "$VM_STATUS" == "Nonexistent" ]]; then
        echo ""
        echo "⚠️  Finch VM not initialized. Initializing now..."
        echo "   This will take a few minutes..."
        finch vm init
        echo "✅ Finch VM initialized successfully"
    else
        echo "✅ Finch VM is initialized (Status: $VM_STATUS)"
    fi
elif command -v docker &> /dev/null; then
    echo "✅ Docker found: $(docker --version)"
else
    echo "❌ ERROR: Neither Finch nor Docker found!"
    echo ""
    echo "ASH (Automated Security Helper) requires a container runtime to run security scans."
    echo "Please install one of the following:"
    echo ""
    echo "  Finch (recommended for AWS users):"
    echo "    macOS: brew install finch"
    echo "    Linux: https://github.com/runfinch/finch#installation"
    echo ""
    echo "  Docker:"
    echo "    https://docs.docker.com/get-docker/"
    echo ""
    exit 1
fi

# Navigate to code directory
cd "$SCRIPT_DIR/.."

# Activate virtual environment and install dev dependencies
echo ""
echo "📦 Installing development dependencies..."
source .venv/bin/activate
pip install -r requirements-dev.txt

echo ""
echo "✅ Development environment setup completed successfully!"
echo ""
echo "🔒 You can now run security scans with:"
echo "   ./code/scripts/scan-code.sh"
echo ""
