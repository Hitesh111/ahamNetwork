#!/usr/bin/env bash
set -eo pipefail

usage() {
    echo "Usage: $0 <domain.py> [options]"
    echo ""
    echo "Options:"
    echo "  --rounds N       Number of evolutionary rounds"
    echo "  --provider NAME  LLM provider: local|openai|gemini|deepseek|grok"
    echo "  --model NAME     LLM model name"
    echo "  --no-llm         Force AST-only mutations"
    echo "  --parallel       Run agents in parallel"
    echo "  --seed N         Random seed"
    echo ""
    echo "Environment:"
    echo "  GOSSIP_LLM_PROVIDER    Default LLM provider"
    echo "  GOSSIP_LOCAL_MODEL     Ollama model name"
    echo "  GOSSIP_LOCAL_BASE_URL  Ollama URL"
    echo "  GOSSIP_OPENAI_KEY      OpenAI API key"
    echo "  GOSSIP_GEMINI_KEY      Google Gemini API key"
}

DOMAIN=""
ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)          usage; exit 0 ;;
        --no-llm)           unset GOSSIP_LLM_PROVIDER; export GOSSIP_LLM_PROVIDER="" ;;
        --rounds)           shift; ARGS+=(--rounds "$1") ;;
        --provider)         shift; export GOSSIP_LLM_PROVIDER="$1" ;;
        --model)            shift; export GOSSIP_LOCAL_MODEL="$1" ;;
        --parallel)         ARGS+=(--parallel) ;;
        --seed)             shift; ARGS+=(--seed "$1") ;;
        -*)                 ARGS+=("$1") ;;
        *)                  DOMAIN="$1" ;;
    esac
    shift
done

if [[ -z "$DOMAIN" ]]; then
    echo "ERROR: No domain file specified." >&2
    usage
    exit 1
fi

if [[ ! -f "$DOMAIN" ]]; then
    echo "ERROR: Domain file not found: $DOMAIN" >&2
    exit 1
fi

echo "=== Gossip Engine ==="
echo "Domain:   $DOMAIN"
echo "Provider: ${GOSSIP_LLM_PROVIDER:-none (AST mutations only)}"
echo ""

exec python3 -m gossip_engine.main --domain "$DOMAIN" "${ARGS[@]}"
