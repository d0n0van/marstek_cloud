#!/bin/bash
# Activation script for Marstek Cloud development environment using Conda

set -e  # Exit on error

ENV_NAME="marstek_cloud"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to find and source conda
find_and_source_conda() {
    # Common conda installation paths
    local conda_paths=(
        "$HOME/miniconda3/etc/profile.d/conda.sh"
        "$HOME/anaconda3/etc/profile.d/conda.sh"
        "$HOME/conda/etc/profile.d/conda.sh"
        "/opt/miniconda3/etc/profile.d/conda.sh"
        "/opt/anaconda3/etc/profile.d/conda.sh"
        "/usr/local/miniconda3/etc/profile.d/conda.sh"
        "/usr/local/anaconda3/etc/profile.d/conda.sh"
    )
    
    # Try to find conda.sh
    for path in "${conda_paths[@]}"; do
        if [ -f "$path" ]; then
            echo "📦 Found conda at: $path"
            source "$path"
            return 0
        fi
    done
    
    # Try using conda from PATH if it's already available
    if command -v conda &> /dev/null; then
        echo "📦 Using conda from PATH"
        return 0
    fi
    
    return 1
}

# Find and source conda
if ! find_and_source_conda; then
    echo "❌ Error: Could not find conda installation!"
    echo "Please install conda/miniconda or ensure it's in your PATH"
    exit 1
fi

# Check if environment exists
if conda env list | grep -q "^${ENV_NAME}\s"; then
    echo "✅ Found existing conda environment: $ENV_NAME"
else
    echo "🔨 Creating new conda environment: $ENV_NAME"
    conda create -n "$ENV_NAME" python=3.11 -y
fi

# Activate the environment
echo "🔄 Activating conda environment: $ENV_NAME"
conda activate "$ENV_NAME"

# Install/update requirements if needed
if [ ! -f "$SCRIPT_DIR/.env_requirements_installed" ] || \
   [ "$SCRIPT_DIR/requirements.txt" -nt "$SCRIPT_DIR/.env_requirements_installed" ] || \
   [ "$SCRIPT_DIR/requirements-dev.txt" -nt "$SCRIPT_DIR/.env_requirements_installed" ]; then
    echo "📥 Installing/updating requirements..."
    pip install --upgrade pip
    pip install -r "$SCRIPT_DIR/requirements.txt"
    pip install -r "$SCRIPT_DIR/requirements-dev.txt"
    touch "$SCRIPT_DIR/.env_requirements_installed"
    echo "✅ Requirements installed!"
fi

# Show environment info
echo ""
echo "✅ Marstek Cloud development environment activated!"
echo "🐍 Python version: $(python --version)"
echo "📍 Python path: $(which python)"
echo "🔧 Conda environment: $CONDA_DEFAULT_ENV"
echo ""
echo "📦 Core packages:"
pip list | grep -E "(aiohttp|voluptuous)" || echo "   (not installed yet)"
echo ""
echo "🛠️  Development tools:"
pip list | grep -E "(pytest|python-dotenv)" | head -3 || echo "   (not installed yet)"
echo ""
echo "🚀 Ready for development!"
echo "💡 Available commands:"
echo "   - python run_tests.py              # Run unit tests"
echo "   - python run_integration_test.py   # Run integration tests"
echo "   - pytest tests/                    # Run all tests"
echo "   - black .                          # Format code"
echo "   - flake8 .                         # Lint code"
echo "   - mypy .                           # Type checking"
echo ""
echo "💡 To deactivate: conda deactivate"
