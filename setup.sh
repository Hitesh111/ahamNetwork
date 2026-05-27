#!/usr/bin/env bash
set -euo pipefail

echo "=== Gossip Engine Setup ==="

# 1. Check Python
PYTHON="python3"
if ! command -v $PYTHON &>/dev/null; then
    echo "ERROR: python3 not found"
    exit 1
fi
echo "Python: $($PYTHON --version)"

# 2. Install Python dependencies
echo ""
echo "--- Installing dependencies ---"
$PYTHON -m pip install httpx pyyaml --quiet 2>&1 | tail -1

# 3. Check / setup Ollama
echo ""
echo "--- Checking Ollama ---"
if command -v ollama &>/dev/null; then
    echo "Ollama found: $(ollama --version 2>/dev/null || echo 'installed')"
    if curl -sf http://localhost:11434/api/tags &>/dev/null; then
        echo "Ollama server: running"
    else
        echo "Ollama server: NOT running (start with: ollama serve)"
    fi
else
    echo "Ollama not found."
    echo "  Install: curl -fsSL https://ollama.com/install.sh | sh"
    echo "  Or use:  brew install ollama"
fi

# 4. Pull recommended model
echo ""
echo "--- Recommended model ---"
RECOMMENDED="deepseek-coder:1.3b"
if command -v ollama &>/dev/null && curl -sf http://localhost:11434/api/tags &>/dev/null; then
    echo "Pulling $RECOMMENDED..."
    ollama pull "$RECOMMENDED" 2>&1
else
    echo "Skipping pull (Ollama not available)."
    echo "  When ready, run: ollama pull $RECOMMENDED"
fi

# 5. Verify gossip_engine imports
echo ""
echo "--- Verifying imports ---"
$PYTHON -c "from gossip_engine.main import main; print('OK: gossip_engine imports resolve')"

echo ""
echo "=== Setup complete ==="
echo "Run: ./run.sh domains/fizzbuzz.py"
