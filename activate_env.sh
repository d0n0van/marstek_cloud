#!/bin/bash
# Activation script for Marstek Cloud development environment

# Source conda
source $HOME/miniconda3/etc/profile.d/conda.sh

# Activate the marstek_cloud environment
conda activate marstek_cloud

# Show environment info
echo "✅ Marstek Cloud development environment activated!"
echo "🐍 Python version: $(python --version)"
echo "📍 Python path: $(which python)"
echo "📦 Core packages:"
pip list | grep -E "(homeassistant|aiohttp|voluptuous)"
echo "🛠️  Development tools:"
pip list | grep -E "(pytest|black|flake8|mypy|sphinx|pre-commit)" | head -5
echo ""
echo "🚀 Ready for development!"
echo "💡 Available commands:"
echo "   - pytest          # Run tests"
echo "   - black .          # Format code"
echo "   - flake8 .         # Lint code"
echo "   - mypy .           # Type checking"
echo "   - pre-commit run   # Run pre-commit hooks"
