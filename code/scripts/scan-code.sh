#!/bin/bash

# Run ASH (Automated Security Helper) security scan on Terraform and Python code
# This script uses ASH v3 in local mode to scan for security issues

set -e

# Source shared utility functions
source "$(dirname "$0")/common.sh"

echo "🔒 Running ASH Security Scan"
echo "============================="

# Activate virtual environment
activate_venv

# Change to the code directory
cd "$(dirname "$0")/.."

# Create output directory if it doesn't exist
OUTPUT_DIR="$(pwd)/../dev/tmp"
mkdir -p "$OUTPUT_DIR"

# Container mode detection (COMMENTED OUT - using local mode instead)
# # Detect container runtime (prioritize Finch over Docker)
# CONTAINER_RUNTIME=""
# if command -v finch &> /dev/null; then
#     # Check if Finch VM is initialized
#     VM_STATUS=$(finch vm status 2>&1)
#     if [[ "$VM_STATUS" == "Nonexistent" ]]; then
#         echo "❌ ERROR: Finch is installed but VM is not initialized!"
#         echo ""
#         echo "Please run the development setup script to initialize Finch:"
#         echo "   ./code/scripts/setup-for-dev.sh"
#         echo ""
#         echo "Or manually initialize Finch VM:"
#         echo "   finch vm init"
#         echo ""
#         exit 1
#     fi
#     CONTAINER_RUNTIME="finch"
#     echo "✅ Using Finch as container runtime"
# elif command -v docker &> /dev/null; then
#     CONTAINER_RUNTIME="docker"
#     echo "✅ Using Docker as container runtime"
# else
#     echo "❌ ERROR: Neither Finch nor Docker found!"
#     echo "Please install Finch or Docker to run security scans."
#     exit 1
# fi
#
# # Set container runtime environment variable for ASH
# export CONTAINER_RUNTIME="$CONTAINER_RUNTIME"

# Run ASH scan in local mode
echo ""
echo "🔍 Scanning code directory for security issues..."
echo "   Source: $(pwd)"
echo "   Output: $OUTPUT_DIR/.ash/"
echo "   Mode: local (no container)"
echo "   Config: .ash.yml (excludes .venv/)"
echo ""

# Run ASH in local mode (uses .ash.yml config for exclusions)
ash --mode local --source-dir "$(pwd)" --output-dir "$OUTPUT_DIR/.ash"
ASH_EXIT_CODE=$?

if [ $ASH_EXIT_CODE -eq 0 ]; then
    echo ""
    echo "✅ ASH scan completed successfully"
else
    echo ""
    echo "⚠️  ASH scan completed with findings (exit code: $ASH_EXIT_CODE)"
fi

echo ""
echo "📊 Scan Results:"
echo "   ASH log:     $OUTPUT_DIR/.ash/ash.log"
echo "   Reports dir: $OUTPUT_DIR/.ash/ash_output/reports/"
echo ""
echo "💡 To view detailed findings:"
echo "   cat $OUTPUT_DIR/.ash/ash.log"
if [ -f "$OUTPUT_DIR/.ash/ash_output/reports/ash.html" ]; then
    echo "   open $OUTPUT_DIR/.ash/ash_output/reports/ash.html"
fi
echo ""

# Always exit 0 (non-blocking)
exit 0
