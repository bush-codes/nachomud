#!/usr/bin/env bash
# run.sh — Launch NachoMUD (Ollama + backend + frontend)

BACKEND="${LLM_BACKEND:-ollama}"
PORT="${PORT:-4000}"

cleanup() { kill 0 2>/dev/null; exit; }
trap cleanup INT TERM

# If ollama backend, ensure ollama is serving and model is pulled
if [ "$BACKEND" = "ollama" ]; then
    MODEL="${AGENT_MODEL:-qwen2.5:7b}"
    if ! pgrep -x ollama >/dev/null; then
        echo "Starting Ollama..."
        ollama serve &
        sleep 2
    fi
    echo "Ensuring model $MODEL is available..."
    ollama pull "$MODEL"
fi

# Start FastAPI backend
echo "Starting NachoMUD server on port $PORT..."
cd web/backend
uvicorn server:app --port "$PORT" &
cd ../..

sleep 1
echo "Ready at http://localhost:$PORT"

wait
