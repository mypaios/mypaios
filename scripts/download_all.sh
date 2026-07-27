#!/bin/bash
# Scripts to download all recommended models in the background

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "=== Local AI OS Model Download Script ==="
echo "Starting downloads at $(date)"

# 1. Download Kokoro Voice Model
echo "--- 1. Downloading Kokoro TTS voice model ---"
./venv/bin/python3 scripts/download_kokoro.py

# 2. Pull Qwen 2.5 Coder 32B
echo "--- 2. Pulling qwen2.5-coder:32b ---"
ollama pull qwen2.5-coder:32b

# 3. Pull DeepSeek R1 70B
echo "--- 3. Pulling deepseek-r1:70b ---"
ollama pull deepseek-r1:70b

# 4. Pull Llama 3.3 70B
echo "--- 4. Pulling llama3.3:70b ---"
ollama pull llama3.3:70b

echo "=== All model downloads complete! ==="
