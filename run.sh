#!/usr/bin/env bash
# run.sh — Launch NachoMUD (Ollama + backend + xterm terminal at /).
#
# Player mode: backend serves the xterm.js client at /, /ws is the game
# WebSocket, /health is a liveness probe. No more separate frontend dev
# server — the terminal is a single static page.

set -e

PORT="${PORT:-4000}"
SMART="${LLM_SMART_MODEL:-llama3.1:8b-instruct-q4_K_M}"
FAST="${LLM_FAST_MODEL:-llama3.2:3b}"

cleanup() { kill 0 2>/dev/null; exit; }
trap cleanup INT TERM

# Ensure Ollama is running and the two models are pulled.
if ! pgrep -x ollama >/dev/null; then
    echo "Starting Ollama..."
    ollama serve >/tmp/nachomud-ollama.log 2>&1 &
    sleep 2
fi

for m in "$SMART" "$FAST"; do
    echo "Ensuring model $m is available..."
    ollama pull "$m"
done

# Start the FastAPI backend (serves the terminal at /, WebSocket at /ws)
echo "Starting NachoMUD server on port $PORT..."
PYTHONPATH="$(pwd):$PYTHONPATH" uvicorn nachomud.server:app \
    --host 0.0.0.0 --port "$PORT" --reload &

sleep 1
echo "Ready at http://localhost:$PORT"
echo "Press Ctrl-C to stop."

# Best-effort browser open (Linux/Mac/WSL)
( command -v xdg-open >/dev/null && xdg-open "http://localhost:$PORT" ) || \
( command -v open     >/dev/null && open     "http://localhost:$PORT" ) || \
true

wait
